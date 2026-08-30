# Endpoints de reportes financieros
# GET /reportes/ganancias : reporte de ganancias en JSON
# GET /reportes/perdidas : reporte de perdidas en JSON
# GET /reportes/ganancias/excel : exportar ganancias en Excel
# GET /reportes/ganancias/pdf : exportar ganancias en PDF
# GET /reportes/perdidas/excel : exportar perdidas en Excel
# GET /reportes/perdidas/pdf : exportar perdidas en PDF
# GET /reportes/cobranza : reporte de cobranza en JSON (PÚBLICO)
# GET /reportes/cartera : reporte de cartera en JSON (PÚBLICO)
# Todos los endpoints aceptan filtros opcionales: desde, hasta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from app.db.database import SessionLocal
from app.services.reporte import (
    get_reporte_ganancias, get_reporte_perdidas, exportar_excel, exportar_pdf,
    get_reporte_cobranza, get_reporte_cartera
)
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/reportes", tags=["Reportes"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/ganancias")
def reporte_ganancias(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return get_reporte_ganancias(db, desde=desde, hasta=hasta)

@router.get("/perdidas")
def reporte_perdidas(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return get_reporte_perdidas(db, desde=desde, hasta=hasta)

@router.get("/ganancias/excel")
def ganancias_excel(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    buffer = exportar_excel(db, "ganancias", desde=desde, hasta=hasta)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ganancias.xlsx"}
    )

@router.get("/ganancias/pdf")
def ganancias_pdf(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    buffer = exportar_pdf(db, "ganancias", desde=desde, hasta=hasta)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ganancias.pdf"}
    )

@router.get("/perdidas/excel")
def perdidas_excel(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    buffer = exportar_excel(db, "perdidas", desde=desde, hasta=hasta)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=perdidas.xlsx"}
    )

@router.get("/perdidas/pdf")
def perdidas_pdf(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    buffer = exportar_pdf(db, "perdidas", desde=desde, hasta=hasta)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=perdidas.pdf"}
    )

@router.get("/cobranza")
def reporte_cobranza(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Reporte de cobranza: información financiera de la empresa"""
    return get_reporte_cobranza(db, desde=desde, hasta=hasta)

@router.get("/cartera")
def reporte_cartera(
    desde: Optional[date] = Query(None, description="Fecha desde (ej: 2026-08-01)"),
    hasta: Optional[date] = Query(None, description="Fecha hasta (ej: 2026-08-31)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Reporte de cartera: información financiera de la empresa"""
    return get_reporte_cartera(db, desde=desde, hasta=hasta)