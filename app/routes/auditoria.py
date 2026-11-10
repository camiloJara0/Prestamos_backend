from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.services.auditoria import (
    get_auditorias, get_auditorias_por_usuario, 
    get_auditorias_por_tabla, get_auditorias_por_operacion
)
from app.schemas.auditoria import AuditoriaOut
from app.schemas.pagination import PaginatedResponse
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verificar_admin(current_user: dict):
    """Auditoría disponible para el equipo (admin) y los prestamistas.

    El servicio de auditoría aplica el aislamiento por usuario: el prestamista
    solo ve su propio historial; el admin ve el historial global.
    """
    if current_user.get("rol") not in ("admin", "prestamista"):
        raise HTTPException(status_code=403, detail="No tienes permiso para ver auditoria")

@router.get("/", response_model=PaginatedResponse[AuditoriaOut])
def listar_auditorias(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Lista todas las entradas de auditoría (solo admins)."""
    verificar_admin(current_user)
    return get_auditorias(db, page=page, limit=limit)

@router.get("/usuario/{usuario_id}", response_model=PaginatedResponse[AuditoriaOut])
def auditorias_usuario(
    usuario_id: int,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene auditorías de un usuario específico (solo admins)."""
    verificar_admin(current_user)
    return get_auditorias_por_usuario(db, usuario_id=usuario_id, page=page, limit=limit)

@router.get("/tabla/{tabla_afectada}", response_model=PaginatedResponse[AuditoriaOut])
def auditorias_tabla(
    tabla_afectada: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene auditorías de una tabla específica (solo admins)."""
    verificar_admin(current_user)
    return get_auditorias_por_tabla(db, tabla_afectada=tabla_afectada, page=page, limit=limit)

@router.get("/operacion/{tipo_operacion}", response_model=PaginatedResponse[AuditoriaOut])
def auditorias_operacion(
    tipo_operacion: str,
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene auditorías de un tipo de operación específico (solo admins)."""
    verificar_admin(current_user)
    return get_auditorias_por_operacion(db, tipo_operacion=tipo_operacion, page=page, limit=limit)