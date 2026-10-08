from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user, get_db, get_usuario_id, require_rol
from app.models.models import Contrato
from app.schemas.pagination import PaginatedResponse
from app.schemas.solicitud import (
    ConvertirCreate,
    DecisionCreate,
    ScoringOut,
    SolicitudCreate,
    SolicitudDetalleOut,
    SolicitudOut,
)
from app.services import solicitudes as solicitudes_service
from app.services.contratos import firmar_contrato, obtener_contrato_solicitud
from app.schemas.contrato import ContratoFirmarCreate, ContratoOut

router = APIRouter(prefix="/solicitudes", tags=["Solicitudes"])
router_contratos = APIRouter(prefix="/contratos", tags=["Contratos"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _detalle(solicitud) -> SolicitudDetalleOut:
    out = SolicitudDetalleOut.model_validate(solicitud)
    out.nombre_creador = solicitud.creador.nombre if solicitud.creador else None
    out.nombre_evaluador = solicitud.evaluador.nombre if solicitud.evaluador else None
    return out


@router.get("/", response_model=PaginatedResponse[SolicitudOut])
def listar_solicitudes(
    page: int = 1,
    limit: int = 10,
    estado: str | None = None,
    cliente_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return solicitudes_service.get_solicitudes(
        db, page=page, limit=limit, estado=estado, cliente_id=cliente_id
    )


@router.post("/", response_model=SolicitudDetalleOut, status_code=201)
def registrar_solicitud(
    datos: SolicitudCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-020: captura de la solicitud por el usuario operativo."""
    solicitud = solicitudes_service.crear_solicitud(
        db, datos, get_usuario_id(current_user), ip_address=_ip(request)
    )
    return _detalle(solicitudes_service.get_solicitud(db, solicitud.id))


@router.get("/{solicitud_id}", response_model=SolicitudDetalleOut)
def obtener_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return _detalle(solicitudes_service.get_solicitud(db, solicitud_id))


@router.post("/{solicitud_id}/scoring", response_model=ScoringOut)
def evaluar_scoring(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-065: consulta el puntaje y lo adjunta a la solicitud."""
    return solicitudes_service.evaluar_scoring(db, solicitud_id)


@router.post("/{solicitud_id}/decision", response_model=SolicitudDetalleOut)
def decidir_solicitud(
    solicitud_id: int,
    datos: DecisionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    """RF-021/RF-024: solo el administrador aprueba o rechaza."""
    solicitud = solicitudes_service.decidir_solicitud(
        db, solicitud_id, datos, get_usuario_id(current_user), ip_address=_ip(request)
    )
    return _detalle(solicitud)


@router.post("/{solicitud_id}/convertir")
def convertir_solicitud(
    solicitud_id: int,
    datos: ConvertirCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-022: convierte la solicitud aprobada en préstamo."""
    solicitud, prestamo = solicitudes_service.convertir_solicitud(
        db,
        solicitud_id,
        porcentaje_interes=datos.porcentaje_interes,
        numero_cuotas=datos.numero_cuotas,
        observaciones=datos.observaciones,
        usuario_id=get_usuario_id(current_user),
        ip_address=_ip(request),
    )
    return {
        "solicitud": _detalle(solicitud),
        "prestamo_id": prestamo.id,
        "mensaje": f"Solicitud convertida en préstamo #{prestamo.id}",
    }


@router.get("/{solicitud_id}/contrato", response_model=ContratoOut)
def contrato_de_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return obtener_contrato_solicitud(db, solicitud_id)


@router_contratos.get("/{contrato_id}/documento")
def descargar_contrato(
    contrato_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    contrato = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    return FileResponse(
        contrato.ruta_archivo,
        media_type="application/pdf",
        filename=f"contrato-{contrato_id}.pdf",
    )


@router_contratos.post("/{contrato_id}/firmar", response_model=ContratoOut)
def firmar(
    contrato_id: int,
    datos: ContratoFirmarCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-066: firma electrónica del contrato."""
    return firmar_contrato(db, contrato_id, datos.firmante_nombre, datos.firmante_documento)
