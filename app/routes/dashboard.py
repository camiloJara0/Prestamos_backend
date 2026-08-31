from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user, get_db
from app.schemas.dashboard import DashboardResumenOut
from app.services.dashboard import obtener_resumen_dashboard

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/resumen", response_model=DashboardResumenOut)
def obtener_resumen(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Retorna los indicadores clave (KPIs) para la vista principal del dashboard."""
    return obtener_resumen_dashboard(db)