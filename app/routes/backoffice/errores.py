"""Monitor de errores (Backoffice) + endpoint público de reporte."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.permisos import require_permiso
from app.db.database import SessionLocal
from app.schemas.backoffice import (
    ErrorActualizarRequest,
    ErrorCrearRequest,
    ErrorDetalleOut,
    ErrorOut,
)
from app.schemas.pagination import PaginatedResponse
from app.services.backoffice import errores as service
from app.services.rate_limit import verificar_rate_limit

from ._comun import admin_id, contexto_request

router = APIRouter(prefix="/backoffice/errores", tags=["Backoffice · Errores"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=PaginatedResponse[ErrorOut])
def listar_errores(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    estado: Optional[str] = Query(
        None, pattern="^(abierto|en_seguimiento|resuelto|ignorado)$"
    ),
    origen: Optional[str] = Query(None, pattern="^(backend|frontend)$"),
    nivel: Optional[str] = Query(None, pattern="^(error|critico)$"),
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    q: Optional[str] = Query(None, max_length=200),
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.errores.ver")),
):
    return service.listar_errores(
        db,
        page=page,
        limit=limit,
        estado=estado,
        origen=origen,
        nivel=nivel,
        desde=desde,
        hasta=hasta,
        q=q,
    )


@router.get("/{error_id}", response_model=ErrorDetalleOut)
def obtener_error(
    error_id: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("backoffice.errores.ver")),
):
    return service.obtener_error(db, error_id)


@router.patch("/{error_id}", response_model=ErrorOut)
def actualizar_error(
    error_id: int,
    body: ErrorActualizarRequest,
    request: Request,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("backoffice.errores.gestionar")),
):
    ctx = contexto_request(request)
    service._verificar_usuario(db, body.responsable_id)
    return service.actualizar_error(
        db,
        error_id,
        datos=body.model_dump(exclude_unset=True),
        admin_id=admin_id(usuario),
        **ctx,
    )


@router.post("/report", response_model=ErrorOut, status_code=201)
def reportar_error(
    body: ErrorCrearRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Reporte de errores del frontend (público y tasa-limitado).

    Cualquier cliente puede reportar un error; se limita por IP para
    evitar abuso y se registran IP/UA para trazabilidad.
    """
    ip = request.client.host if request.client else None
    verificar_rate_limit(f"error_report:{ip}", maximo=30, ventana_segundos=60)
    ctx = contexto_request(request)
    registro = service.crear_error(
        db,
        datos=body.model_dump(),
        usuario_id=body.usuario_id,
        **ctx,
    )
    return registro
