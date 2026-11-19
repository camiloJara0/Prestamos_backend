"""Dashboard e infraestructura (Backoffice)."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.backoffice import DashboardOut, InfraestructuraOut, SerieOut
from app.services.backoffice import dashboard as service

router = APIRouter(prefix="/backoffice", tags=["Backoffice · Dashboard"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard", response_model=DashboardOut)
def resumen(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.dashboard.ver")),
):
    return service.resumen_dashboard(db)


@router.get("/dashboard/serie", response_model=SerieOut)
def serie(
    metrica: str = Query(
        "peticiones",
        pattern="^(peticiones|errores|errores_5xx)$",
        description="Métrica a graficar",
    ),
    granularidad: str = Query("dia", pattern="^(hora|dia)$"),
    dias: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.dashboard.ver")),
):
    hasta = datetime.utcnow()
    desde = hasta - timedelta(days=dias)
    return service.serie_metricas(
        db, metrica=metrica, desde=desde, hasta=hasta, granularidad=granularidad
    )


@router.get("/dashboard/infraestructura", response_model=InfraestructuraOut)
def infraestructura(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.dashboard.ver")),
):
    return service.infraestructura(db)
