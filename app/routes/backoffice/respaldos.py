"""Respaldos de base de datos (Backoffice)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.backoffice import RespaldosOut
from app.services.backoffice import respaldos as service
from app.services.rate_limit import verificar_rate_limit

from ._comun import admin_id, contexto_request

router = APIRouter(prefix="/backoffice/respaldos", tags=["Backoffice · Respaldos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=RespaldosOut)
def listar_respaldos(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.respaldos.ver")),
):
    return service.listar_respaldos(db)


@router.post("/")
def crear_respaldo(
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.respaldos.gestionar")),
):
    ctx = contexto_request(request)
    verificar_rate_limit(f"bo_respaldo:{admin_id(usuario)}", maximo=3, ventana_segundos=60)
    return service.crear_respaldo_manual(db, admin_id=admin_id(usuario), **ctx)
