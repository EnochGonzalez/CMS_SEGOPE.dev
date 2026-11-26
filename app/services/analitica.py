"""Monitoreo de visitas: cómo se registra una visita y cómo se calculan las estadísticas.

Privacidad: no se guardan IP ni cookies. De cada visita queda un hash (`visitor`) calculado con la IP, el navegador, el
sitio y el DÍA; como el día entra en el cálculo, el mismo visitante tiene un hash distinto cada día y no se le puede
seguir de un día a otro. Por eso «visitantes» significa «visitantes distintos por día, sumados».
"""
import hashlib
import re
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import config
from app.errors import ApiError
from app.models import PageView, Site

REFERENCIA_INTERNA = "(interno)"        # la visita viene de otra página del mismo sitio: no cuenta como fuente de tráfico

# Días que abarca cada periodo (las mismas claves que el panel de referencia del profesor).
DIAS_POR_PERIODO = {"1d": 1, "1w": 7, "2w": 14, "1m": 30, "3m": 90, "1y": 365}

_ROBOTS = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|preview|uptime|curl|wget|python-requests|httpx", re.I)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


# ------------------------------------------------------------------ tiempo local
def ahora_local(ahora_utc: datetime | None = None) -> datetime:
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    return ahora_utc + timedelta(hours=config.ANALITICA_UTC_OFFSET_HORAS)


def hoy_local() -> date:
    return ahora_local().date()


# ------------------------------------------------------------------ normalización de lo que llega del navegador
def normalizar_ruta(ruta: str) -> str:
    """'/HTML/proyecto/index.html?x=1#a' -> '/HTML/proyecto'; '/index.html' -> '/'. Sin consulta, sin ancla, sin barra final."""
    ruta = _CONTROL.sub("", ruta).split("#", 1)[0].split("?", 1)[0].strip()
    if not ruta.startswith("/"):
        ruta = "/" + ruta
    ruta = re.sub(r"/{2,}", "/", ruta)
    if ruta.endswith("/index.html"):
        ruta = ruta[: -len("index.html")]
    if len(ruta) > 1:
        ruta = ruta.rstrip("/") or "/"
    return ruta[:200]


def host_de_referencia(referrer: str | None, dominio_propio: str) -> str | None:
    """Solo se guarda el dominio de donde viene la visita (no la dirección completa). None = directo / sin referencia."""
    if not referrer:
        return None
    try:
        host = urlparse(referrer).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    if host == dominio_propio or host == "www." + dominio_propio:
        return REFERENCIA_INTERNA
    return host[:120]


def es_robot(user_agent: str | None) -> bool:
    return not user_agent or _ROBOTS.search(user_agent) is not None


def huella_visitante(ip: str, user_agent: str, site_id: str, dia: date) -> str:
    """Hash corto y anónimo. La sal sale del secreto del servidor, así que no se puede reconstruir desde fuera."""
    sal = config.JWT_SECRET or "sin-sal"
    crudo = f"{sal}|{dia.isoformat()}|{site_id}|{ip}|{user_agent}".encode("utf-8")
    return hashlib.sha256(crudo).hexdigest()[:16]


# ------------------------------------------------------------------ límite de visitas por visitante
class LimitadorDeVistas:
    """Máximo de visitas por visitante en una ventana de tiempo (en memoria). Frena a quien intente inflar los números."""

    def __init__(self):
        self._visitas: dict[str, deque] = {}
        self._cerrojo = threading.Lock()

    def permitir(self, visitante: str) -> bool:
        ahora = time.monotonic()
        limite = ahora - config.ANALITICA_VENTANA_SEGUNDOS
        with self._cerrojo:
            fila = self._visitas.setdefault(visitante, deque())
            while fila and fila[0] < limite:
                fila.popleft()
            if len(fila) >= config.ANALITICA_MAX_VISTAS:
                return False
            fila.append(ahora)
            if len(self._visitas) > 5000:                       # limpieza: no dejar crecer la memoria sin fin
                for clave in [k for k, f in self._visitas.items() if not f or f[-1] < limite]:
                    del self._visitas[clave]
            return True

    def reiniciar(self) -> None:
        with self._cerrojo:
            self._visitas.clear()


limitador_vistas = LimitadorDeVistas()


# ------------------------------------------------------------------ sitios
def buscar_sitio(db: Session, site_id: str) -> Site:
    sitio = db.get(Site, site_id)
    if sitio is None:
        raise ApiError(404, "SITE_NOT_FOUND", f"No existe un sitio con el site_id '{site_id}'")
    return sitio


def exigir_dominio_libre(db: Session, dominio: str, excepto_id: str | None = None) -> None:
    consulta = select(Site.site_id).where(Site.domain == dominio)
    if excepto_id:
        consulta = consulta.where(Site.site_id != excepto_id)
    if db.scalar(consulta) is not None:
        raise ApiError(409, "SITE_DOMAIN_ALREADY_EXISTS", f"Ya existe un sitio con el dominio '{dominio}'",
                       [{"field": "domain", "issue": "Ya existe un sitio con ese dominio"}])


# ------------------------------------------------------------------ registrar una visita
def registrar_vista(db: Session, sitio: Site, ruta: str, referrer: str | None, ip: str, user_agent: str,
                    ahora_utc: datetime | None = None) -> PageView:
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    local = ahora_local(ahora_utc)
    vista = PageView(
        site_id=sitio.site_id,
        path=normalizar_ruta(ruta),
        visitor=huella_visitante(ip, user_agent, sitio.site_id, local.date()),
        referrer_host=host_de_referencia(referrer, sitio.domain),
        occurred_at=ahora_utc, day=local.date(), hour=local.hour,
    )
    db.add(vista)
    db.commit()
    return vista


def purgar_antiguas(db: Session, hoy: date | None = None) -> int:
    """Borra las visitas con más de ANALITICA_DIAS_RETENCION días (así la base gratuita no se llena)."""
    limite = (hoy or hoy_local()) - timedelta(days=config.ANALITICA_DIAS_RETENCION)
    resultado = db.execute(delete(PageView).where(PageView.day < limite))
    db.commit()
    return resultado.rowcount or 0


# ------------------------------------------------------------------ estadísticas
def _delta(actual: int, anterior: int) -> float | None:
    return None if anterior == 0 else round((actual - anterior) / anterior * 100, 1)


def _porcentaje(parte: int, total: int) -> float:
    return 0.0 if total == 0 else round(parte / total * 100, 1)


def calcular(db: Session, periodo: str, site_id: str | None = None, hoy: date | None = None) -> dict:
    dias = DIAS_POR_PERIODO[periodo]
    fin = hoy or hoy_local()
    inicio = fin - timedelta(days=dias - 1)
    fin_prev = inicio - timedelta(days=1)
    inicio_prev = fin_prev - timedelta(days=dias - 1)

    def en(desde: date, hasta: date):
        condiciones = [PageView.day >= desde, PageView.day <= hasta]
        if site_id:
            condiciones.append(PageView.site_id == site_id)
        return condiciones

    # ---- totales y comparación con el periodo anterior
    visitas, visitantes, paginas = db.execute(
        select(func.count(), func.count(PageView.visitor.distinct()), func.count(PageView.path.distinct())).where(*en(inicio, fin))
    ).one()
    visitas_ant, visitantes_ant = db.execute(
        select(func.count(), func.count(PageView.visitor.distinct())).where(*en(inicio_prev, fin_prev))
    ).one()

    # ---- por sitio (aparecen todos, incluso con cero visitas)
    ahora = {s: (v, u) for s, v, u in db.execute(
        select(PageView.site_id, func.count(), func.count(PageView.visitor.distinct())).where(*en(inicio, fin)).group_by(PageView.site_id))}
    antes = {s: v for s, v in db.execute(
        select(PageView.site_id, func.count()).where(*en(inicio_prev, fin_prev)).group_by(PageView.site_id))}
    consulta_sitios = select(Site).order_by(Site.created_at, Site.site_id)
    if site_id:
        consulta_sitios = consulta_sitios.where(Site.site_id == site_id)
    sitios = db.scalars(consulta_sitios).all()
    por_sitio = []
    for s in sitios:
        v, u = ahora.get(s.site_id, (0, 0))
        por_sitio.append({"site_id": s.site_id, "name": s.name, "domain": s.domain, "color": s.color, "is_active": s.is_active,
                          "views": v, "visitors": u, "share_pct": _porcentaje(v, visitas), "delta_pct": _delta(v, antes.get(s.site_id, 0))})
    por_sitio.sort(key=lambda fila: (-fila["views"], fila["name"].lower()))
    info_sitio = {s.site_id: s for s in sitios}

    # ---- serie: por hora si el periodo es «hoy», por día en los demás
    if periodo == "1d":
        granularidad = "hour"
        filas = {h: (v, u) for h, v, u in db.execute(
            select(PageView.hour, func.count(), func.count(PageView.visitor.distinct())).where(*en(fin, fin)).group_by(PageView.hour))}
        serie = [{"label": f"{h:02d}:00", "views": filas.get(h, (0, 0))[0], "visitors": filas.get(h, (0, 0))[1]} for h in range(24)]
    else:
        granularidad = "day"
        filas = {d: (v, u) for d, v, u in db.execute(
            select(PageView.day, func.count(), func.count(PageView.visitor.distinct())).where(*en(inicio, fin)).group_by(PageView.day))}
        serie = []
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            v, u = filas.get(dia, (0, 0))
            serie.append({"label": dia.isoformat(), "views": v, "visitors": u})

    # ---- páginas más vistas y fuentes de tráfico
    paginas_top = []
    for s_id, ruta, v, u in db.execute(
            select(PageView.site_id, PageView.path, func.count().label("n"), func.count(PageView.visitor.distinct()))
            .where(*en(inicio, fin)).group_by(PageView.site_id, PageView.path)
            .order_by(func.count().desc(), PageView.path).limit(10)):
        sitio = info_sitio.get(s_id) or db.get(Site, s_id)
        paginas_top.append({"site_id": s_id, "site_name": sitio.name if sitio else "—", "color": sitio.color if sitio else "#888888",
                            "path": ruta, "views": v, "visitors": u})
    fuentes = [{"source": origen, "views": v} for origen, v in db.execute(
        select(PageView.referrer_host, func.count().label("n"))
        .where(*en(inicio, fin), (PageView.referrer_host.is_(None)) | (PageView.referrer_host != REFERENCIA_INTERNA))
        .group_by(PageView.referrer_host).order_by(func.count().desc(), PageView.referrer_host).limit(8))]

    return {
        "period": periodo, "granularity": granularidad, "from_date": inicio, "to_date": fin,
        "utc_offset_hours": config.ANALITICA_UTC_OFFSET_HORAS,
        "totals": {"views": visitas, "visitors": visitantes, "pages": paginas, "views_prev": visitas_ant, "visitors_prev": visitantes_ant,
                   "views_delta_pct": _delta(visitas, visitas_ant), "visitors_delta_pct": _delta(visitantes, visitantes_ant)},
        "sites": por_sitio, "series": serie, "top_pages": paginas_top, "referrers": fuentes,
    }
