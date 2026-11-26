"""Estadísticas de visitas para el panel de la consola (requiere token Bearer).

  GET /api/v1/stats?period=1w&site_id=...    Totales, comparación con el periodo anterior, serie, páginas y fuentes
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import exigir_admin
from app.routers.comunes import ERROR_401, ERROR_404
from app.schemas import Envelope, Periodo, StatsOut
from app.services import analitica

router = APIRouter(
    prefix="/api/v1/stats",
    tags=["Estadísticas (administración)"],
    dependencies=[Depends(exigir_admin)],
    responses=ERROR_401,
)


@router.get("", response_model=Envelope[StatsOut], summary="Estadísticas de visitas", responses=ERROR_404)
def estadisticas(
    period: Periodo = Query(Periodo.SEMANA, description="1d = hoy (por hora) · 1w · 2w · 1m · 3m · 1y"),
    site_id: str | None = Query(None, description="Solo este sitio. Sin él, se suman todos."),
    db: Session = Depends(get_db),
):
    """«Visitantes» son visitantes distintos por día, sumados (no se rastrea a nadie de un día a otro).
    Los días y las horas son locales (ver ANALITICA_UTC_OFFSET_HORAS). Se compara con el mismo número de días justo antes."""
    if site_id:
        analitica.buscar_sitio(db, site_id)
    return Envelope[StatsOut](message="Estadísticas obtenidas exitosamente",
                              data=StatsOut(**analitica.calcular(db, period.value, site_id)))
