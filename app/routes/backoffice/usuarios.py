"""Gestión global de usuarios (Backoffice)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.backoffice import (
    MotivoRequest,
    SesionOut,
    SesionRevocadaOut,
    UsuarioDetalleOut,
    UsuarioGlobalOut,
)
from app.schemas.pagination import PaginatedResponse
from app.services.backoffice import usuarios as service
from app.services.rate_limit import verificar_rate_limit

from ._comun import admin_id, contexto_request

router = APIRouter(
    prefix="/backoffice/usuarios", tags=["Backoffice · Usuarios"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=PaginatedResponse[UsuarioGlobalOut])
def listar_usuarios(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=100),
    rol: Optional[str] = Query(None, pattern="^(admin|prestamista|usuario)$"),
    estado: Optional[str] = Query(None, pattern="^(activo|inactivo)$"),
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.usuarios.ver")),
):
    return service.listar_usuarios(
        db, page=page, limit=limit, q=q, rol=rol, estado=estado, desde=desde, hasta=hasta
    )


@router.get("/{usuario_id}", response_model=UsuarioDetalleOut)
def detalle_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.usuarios.ver")),
):
    return service.detalle_usuario(db, usuario_id)


@router.get("/{usuario_id}/sesiones", response_model=list[SesionOut])
def sesiones(
    usuario_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.usuarios.sesiones")),
):
    service.detalle_usuario(db, usuario_id)  # valida existencia (404)
    return service.sesiones_activas(db, usuario_id)


@router.delete("/{usuario_id}/sesiones/{token_id}", response_model=SesionRevocadaOut)
def revocar_sesion(
    usuario_id: int,
    token_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.usuarios.sesiones")),
):
    ctx = contexto_request(request)
    service.revocar_sesion(
        db, usuario_id=usuario_id, token_id=token_id, admin_id=admin_id(usuario), **ctx
    )
    return {"revocadas": 1}


@router.post("/{usuario_id}/suspender", response_model=SesionRevocadaOut)
def suspender(
    usuario_id: int,
    body: MotivoRequest,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.usuarios.gestionar")),
):
    ctx = contexto_request(request)
    verificar_rate_limit(f"bo_suspender:{admin_id(usuario)}", maximo=20, ventana_segundos=60)
    service.suspender_usuario(
        db,
        usuario_id=usuario_id,
        motivo=body.motivo,
        admin_id=admin_id(usuario),
        **ctx,
    )
    return {"revocadas": 0}


@router.post("/{usuario_id}/reactivar", response_model=SesionRevocadaOut)
def reactivar(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.usuarios.gestionar")),
):
    ctx = contexto_request(request)
    service.reactivar_usuario(
        db, usuario_id=usuario_id, admin_id=admin_id(usuario), **ctx
    )
    return {"revocadas": 0}


@router.post("/{usuario_id}/restablecer-acceso")
def restablecer_acceso(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.usuarios.gestionar")),
):
    ctx = contexto_request(request)
    verificar_rate_limit(f"bo_reset:{admin_id(usuario)}", maximo=5, ventana_segundos=60)
    mensaje = service.restablecer_acceso(
        db, usuario_id=usuario_id, admin_id=admin_id(usuario), **ctx
    )
    return {"message": mensaje}
