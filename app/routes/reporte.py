# Endpoints de reportes financieros
# GET /reportes/ganancias : reporte de ganancias en JSON
# GET /reportes/perdidas : reporte de perdidas en JSON
# GET /reportes/ganancias/excel : exportar ganancias en Excel
# GET /reportes/ganancias/pdf : exportar ganancias en PDF
# GET /reportes/perdidas/excel : exportar perdidas en Excel
# GET /reportes/perdidas/pdf : exportar perdidas en PDF

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.services.reporte import get_reporte_ganancias, get_reporte_perdidas, exportar_excel, exportar_pdf
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/reportes", tags=["Reportes"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/ganancias")
def reporte_ganancias(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_reporte_ganancias(db)

@router.get("/perdidas")
def reporte_perdidas(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return get_reporte_perdidas(db)

@router.get("/ganancias/excel")
def ganancias_excel(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    buffer = exportar_excel(db, "ganancias")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ganancias.xlsx"}
    )

@router.get("/ganancias/pdf")
def ganancias_pdf(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    buffer = exportar_pdf(db, "ganancias")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ganancias.pdf"}
    )

@router.get("/perdidas/excel")
def perdidas_excel(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    buffer = exportar_excel(db, "perdidas")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=perdidas.xlsx"}
    )

@router.get("/perdidas/pdf")
def perdidas_pdf(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    buffer = exportar_pdf(db, "perdidas")
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=perdidas.pdf"}
    )