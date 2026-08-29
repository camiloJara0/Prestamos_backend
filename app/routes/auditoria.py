from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.database import SessionLocal
from app.services.auditoria import (
    get_auditorias, get_auditorias_por_usuario, 
    get_auditorias_por_tabla, get_auditorias_por_operacion
)
from app.schemas.auditoria import AuditoriaOut
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[AuditoriaOut])
def listar_auditorias(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Lista todas las entradas de auditoria (solo admins)"""
    if current_user["rol"] != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Solo administradores pueden ver auditoria")
    return get_auditorias(db, skip=skip, limit=limit)

@router.get("/usuario/{usuario_id}", response_model=list[AuditoriaOut])
def auditorias_usuario(
    usuario_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene auditorias de un usuario específico (solo admins)"""
    if current_user["rol"] != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Solo administradores pueden ver auditoria")
    return get_auditorias_por_usuario(db, usuario_id=usuario_id, skip=skip, limit=limit)

@router.get("/tabla/{tabla_afectada}", response_model=list[AuditoriaOut])
def auditorias_tabla(
    tabla_afectada: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene auditorias de una tabla específica (solo admins)"""
    if current_user["rol"] != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Solo administradores pueden ver auditoria")
    return get_auditorias_por_tabla(db, tabla_afectada=tabla_afectada, skip=skip, limit=limit)

@router.get("/operacion/{tipo_operacion}", response_model=list[AuditoriaOut])
def auditorias_operacion(
    tipo_operacion: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Obtiene auditorias de un tipo de operación específico (solo admins)"""
    if current_user["rol"] != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Solo administradores pueden ver auditoria")
    return get_auditorias_por_operacion(db, tipo_operacion=tipo_operacion, skip=skip, limit=limit)