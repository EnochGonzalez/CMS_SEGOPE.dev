"""Registro público de visitas y el script que lo envía.

  POST /api/v1/track    Lo llama el script del blog en cada visita (sin token)
  GET  /t.js            El script de seguimiento: una línea en el HTML del blog lo carga

El script envía la visita con `navigator.sendBeacon` y cuerpo de texto (text/plain). Es una petición «simple» del
navegador: no necesita permiso CORS ni petición previa, y funciona aunque el visitante cierre la pestaña enseguida.
Como cualquiera puede llamar a una URL pública, se exige que el sitio esté registrado y activo y que el encabezado
Origin (que el navegador pone solo y un script de página no puede cambiar) sea el dominio de ese sitio.
"""
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import config
from app.database import get_db
from app.errors import ApiError
from app.models import Site
from app.routers.comunes import ERROR_404, ERROR_422
from app.schemas import ErrorEnvelope
from app.services import analitica

router = APIRouter(tags=["Monitoreo (público)"])
MAX_CUERPO = 4096
ARCHIVO_SCRIPT = config.RAIZ / "app" / "rastreador.js"


class VistaIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    site: str = Field(min_length=3, max_length=120, description="Dominio del sitio, como está registrado en el CMS")
    path: str = Field(min_length=1, max_length=300, description="Ruta de la página (location.pathname)")
    referrer: str | None = Field(None, max_length=500)


def _ip(request: Request) -> str:
    adelante = request.headers.get("x-forwarded-for", "").split(",")[0].strip()      # detrás del proxy de Render
    return adelante or (request.client.host if request.client else "")


def _anotar(db: Session, datos: VistaIn, origen: str | None, ip: str, user_agent: str) -> int:
    sitio = db.scalar(select(Site).where(Site.domain == datos.site.strip().lower()))
    if sitio is None or not sitio.is_active:
        raise ApiError(404, "SITE_NOT_FOUND", "Ese sitio no está registrado o está en pausa")
    host_origen = (urlparse(origen).hostname or "").lower() if origen else ""
    if host_origen != sitio.domain:
        raise ApiError(403, "ORIGIN_NOT_ALLOWED", "La visita no viene del dominio del sitio")
    if analitica.es_robot(user_agent):
        return 204                                                   # los robots se ignoran sin hacer ruido
    visitante = analitica.huella_visitante(ip, user_agent, sitio.site_id, analitica.hoy_local())
    if not analitica.limitador_vistas.permitir(visitante):
        raise ApiError(429, "TOO_MANY_VIEWS", "Demasiadas visitas seguidas desde el mismo visitante")
    analitica.registrar_vista(db, sitio, datos.path, datos.referrer, ip, user_agent)
    return 204


@router.post("/api/v1/track", status_code=204, summary="Registrar una visita (lo llama el script del blog)",
             responses={403: {"model": ErrorEnvelope, "description": "El Origin no es el dominio del sitio"},
                        429: {"model": ErrorEnvelope, "description": "Demasiadas visitas seguidas del mismo visitante"},
                        **ERROR_404, **ERROR_422})
async def registrar_visita(request: Request, db: Session = Depends(get_db)):
    """Cuerpo JSON `{"site": "segope.vercel.app", "path": "/index.html", "referrer": "https://..."}` (puede ir como text/plain)."""
    cuerpo = await request.body()
    if len(cuerpo) > MAX_CUERPO:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "El cuerpo es demasiado grande")
    try:
        datos = VistaIn.model_validate_json(cuerpo)
    except ValidationError as error:
        detalles = [{"field": ".".join(str(p) for p in e["loc"]) or "(cuerpo)", "issue": e["msg"]} for e in error.errors()]
        raise ApiError(422, "VALIDATION_ERROR", "Los datos enviados no son válidos", detalles)
    await run_in_threadpool(_anotar, db, datos, request.headers.get("origin"), _ip(request), request.headers.get("user-agent", ""))
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/t.js", include_in_schema=False)
def script_de_seguimiento():
    """El script que se pega en el blog: <script defer src="https://TU-API/t.js" data-site="tu-dominio"></script>"""
    return Response(ARCHIVO_SCRIPT.read_text(encoding="utf-8"), media_type="text/javascript",
                    headers={"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"})
