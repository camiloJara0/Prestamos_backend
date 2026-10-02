from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.services.mora import procesar_moras, get_moras, get_moras_prestamo, get_mora, update_mora, delete_mora
from app.schemas.mora import MoraOut, MoraUpdate
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

@router.get("/prestamo/{prestamo_id}", response_model=list[MoraOut])
def listar_moras_por_prestamo(
    prestamo_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Lista las moras en estado generada de un préstamo (RF-045)."""
    return get_moras_prestamo(db, prestamo_id)

@router.get("/{mora_id}", response_model=MoraOut)
def obtener_mora(
    mora_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Consulta individual de una mora (RF-045)."""
    mora = get_mora(db, mora_id)
    if not mora:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mora no encontrada"
        )
    return mora

@router.put("/{mora_id}", response_model=MoraOut)
def editar_mora(
    mora_id: int,
    payload: MoraUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Actualiza una mora. Exclusivo para administradores."""
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Requiere rol de administrador."
        )
    mora = update_mora(db, mora_id, payload)
    if not mora:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mora no encontrada"
        )
    return mora

@router.delete("/{mora_id}")
def eliminar_mora(
    mora_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Elimina una mora. Exclusivo para administradores."""
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Requiere rol de administrador."
        )
    mora = delete_mora(db, mora_id)
    if not mora:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mora no encontrada"
        )
    return {"mensaje": "Mora eliminada"}

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