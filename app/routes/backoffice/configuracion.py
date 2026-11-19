"""Parámetros de configuración (Backoffice)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.backoffice import ConfigActualizarRequest, ConfigItemOut
from app.services.backoffice import configuracion as service

from ._comun import admin_id, contexto_request

router = APIRouter(
    prefix="/backoffice/configuracion", tags=["Backoffice · Configuración"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=list[ConfigItemOut])
def listar(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.config.ver")),
):
    return service.listar_configuraciones(db)


@router.put("/{clave}", response_model=ConfigItemOut)
def actualizar(
    clave: str,
    body: ConfigActualizarRequest,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.config.editar")),
):
    ctx = contexto_request(request)
    return service.actualizar_configuracion_global(
        db,
        clave=clave,
        valor=body.valor,
        admin_id=admin_id(usuario),
        **ctx,
    )
