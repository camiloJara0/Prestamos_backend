"""Seguridad (Backoffice): auditoría y accesos."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.auditoria import AuditoriaOut
from app.schemas.backoffice import SesionOut
from app.schemas.pagination import PaginatedResponse
from app.services.backoffice import seguridad as service

router = APIRouter(prefix="/backoffice/seguridad", tags=["Backoffice · Seguridad"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/auditoria", response_model=PaginatedResponse[AuditoriaOut])
def listar_auditoria(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    usuario_id: Optional[int] = None,
    tabla_afectada: Optional[str] = Query(None, max_length=100),
    tipo_operacion: Optional[str] = Query(None, max_length=50),
    resultado: Optional[str] = Query(None, pattern="^(ok|fallido)$"),
    evento: Optional[str] = Query(
        None, pattern="^(sesiones|usuarios|sesion_admin)$"
    ),
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    q: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.seguridad.ver")),
):
    return service.listar_auditoria(
        db,
        page=page,
        limit=limit,
        usuario_id=usuario_id,
        tabla_afectada=tabla_afectada,
        tipo_operacion=tipo_operacion,
        resultado=resultado,
        evento=evento,
        desde=desde,
        hasta=hasta,
        q=q,
    )


@router.get("/eventos")
def eventos_por_tipo(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.seguridad.ver")),
):
    return service.eventos_por_tipo(db)


@router.get("/accesos/{usuario_id}", response_model=PaginatedResponse[SesionOut])
def accesos_usuario(
    usuario_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.seguridad.ver")),
):
    return service.accesos_usuario(db, usuario_id, page=page, limit=limit)
