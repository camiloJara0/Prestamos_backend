from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.services.mora import procesar_moras, get_moras
from app.schemas.mora import MoraOut
from app.schemas.pagination import PaginatedResponse

# Se ajusta el prefijo a /mora para coincidir con las llamadas del cliente
router = APIRouter(prefix="/mora", tags=["Moras"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=PaginatedResponse[MoraOut])
def listar_moras(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Lista todas las moras activas generadas con paginación estandarizada B11."""
    return get_moras(db, page=page, limit=limit)

@router.post("/procesar-manual", status_code=status.HTTP_200_OK)
def procesar_moras_manual(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Ejecuta manualmente el cálculo de moras. Exclusivo para administradores."""
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Requiere rol de administrador."
        )
    
    try:
        moras = procesar_moras(db)
        return {
            "mensaje": "Procesamiento de moras ejecutado correctamente.",
            "total_moras_procesadas": len(moras)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar moras: {str(e)}"
        )