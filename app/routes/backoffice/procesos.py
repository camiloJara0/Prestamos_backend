"""Procesos programados (Backoffice)."""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.backoffice import EjecucionOut, ProcesoOut
from app.schemas.pagination import PaginatedResponse
from app.services.backoffice import procesos as service
from app.services.rate_limit import verificar_rate_limit

from ._comun import admin_id, contexto_request

router = APIRouter(prefix="/backoffice/procesos", tags=["Backoffice · Procesos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=list[ProcesoOut])
def listar_procesos(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.procesos.ver")),
):
    return service.listar_procesos(db)


@router.get("/ejecuciones", response_model=PaginatedResponse[EjecucionOut])
def listar_ejecuciones(
    page: int = 1,
    limit: int = 10,
    tarea: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.procesos.ver")),
):
    return service.listar_ejecuciones(
        db, page=page, limit=limit, tarea=tarea, estado=estado
    )


@router.get("/ejecuciones/{ejecucion_id}", response_model=EjecucionOut)
def obtener_ejecucion(
    ejecucion_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.procesos.ver")),
):
    return service.obtener_ejecucion(db, ejecucion_id)


@router.post("/{job_id}/ejecutar")
def ejecutar(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.procesos.gestionar")),
):
    ctx = contexto_request(request)
    verificar_rate_limit(f"bo_ejecutar:{admin_id(usuario)}", maximo=10, ventana_segundos=60)
    return service.ejecutar_tarea(
        db, job_id=job_id, admin_id=admin_id(usuario), **ctx
    )


@router.post("/ejecuciones/{ejecucion_id}/reintentar")
def reintentar(
    ejecucion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.procesos.gestionar")),
):
    ctx = contexto_request(request)
    verificar_rate_limit(f"bo_reintentar:{admin_id(usuario)}", maximo=10, ventana_segundos=60)
    return service.reintentar_ejecucion(
        db, ejecucion_id=ejecucion_id, admin_id=admin_id(usuario), **ctx
    )


@router.post("/{job_id}/cancelar")
def cancelar(
    job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.procesos.gestionar")),
):
    ctx = contexto_request(request)
    return service.cancelar_tarea(
        db, job_id=job_id, admin_id=admin_id(usuario), **ctx
    )
