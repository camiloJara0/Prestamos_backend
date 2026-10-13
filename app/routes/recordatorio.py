from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.dependencies.auth import get_db, require_rol
from app.schemas.recordatorio import (
    DestinatariosOut,
    RecordatorioEnvioIn,
    RecordatorioEnvioOut,
    RecordatorioPreviewOut,
)
from app.services import recordatorios as recordatorio_service

router = APIRouter(prefix="/recordatorios", tags=["Recordatorios"])


@router.get("/destinatarios", response_model=DestinatariosOut)
def listar_destinatarios(
    tipo: str = Query(default="proximos"),
    dias: int = Query(default=3, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    """Total y detalle de destinatarios antes de enviar el recordatorio."""
    filas = recordatorio_service.destinatarios(db, tipo, dias)
    return DestinatariosOut(tipo=tipo, dias=dias, total=len(filas), destinatarios=filas)


@router.get("/preview", response_model=RecordatorioPreviewOut)
def previsualizar(
    plantilla_id: int,
    tipo: str = Query(default="proximos"),
    dias: int = Query(default=3, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    """Mensaje compuesto con la plantilla seleccionada, sin enviar."""
    return recordatorio_service.previsualizar(db, plantilla_id, tipo, dias)


@router.post("/enviar", response_model=RecordatorioEnvioOut)
def enviar(
    body: RecordatorioEnvioIn,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    """Envío masivo del recordatorio a todos los destinatarios del criterio."""
    return recordatorio_service.enviar(db, body.plantilla_id, body.tipo, body.dias)
