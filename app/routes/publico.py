"""Endpoints públicos sin autenticación (RF-081: simulador de préstamos)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.dependencies.auth import get_db
from app.models.models import TipoPrestamo
from app.schemas.solicitud import (
    PlanPublicoOut,
    SimulacionOut,
    SolicitudPublicaCreate,
    SolicitudPublicaOut,
)
from app.services import solicitudes as solicitudes_service
from app.services.prestamo import get_planes_publicos, simular_prestamo
from app.services.rate_limit import verificar_rate_limit

router_planes = APIRouter(prefix="/planes-prestamo", tags=["Publico"])
router_simulacion = APIRouter(prefix="/solicitudes", tags=["Publico"])
router_solicitud = APIRouter(prefix="/solicitud-publica", tags=["Publico"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router_planes.get("/", response_model=list[PlanPublicoOut])
def planes_prestamo(db: Session = Depends(get_db)):
    """CA-R6-2: planes activos con campos públicos seguros, sin token."""
    return get_planes_publicos(db)


@router_simulacion.get("/simular", response_model=SimulacionOut)
def simular(
    tipo_id: int = Query(..., description="Tipo de préstamo activo"),
    capital: float = Query(..., gt=0, description="Monto solicitado"),
    cuotas: int = Query(..., ge=1, le=120, description="Número de cuotas"),
    porcentaje: float | None = Query(None, ge=0, le=100),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """CA-R6-3/4: simulación server-side sin token con la lógica de crear_prestamo."""
    verificar_rate_limit(f"simular:{_ip(request) or 'desconocida'}", maximo=120, ventana_segundos=60)
    return simular_prestamo(db, tipo_id, capital, cuotas, porcentaje)


@router_solicitud.post("/", response_model=SolicitudPublicaOut, status_code=201)
def solicitud_publica(
    datos: SolicitudPublicaCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """CA-R6-5/6: formulario público con rate limiting; notifica a los administradores."""
    solicitud = solicitudes_service.crear_solicitud_publica(db, datos, ip_address=_ip(request))
    tipo = db.query(TipoPrestamo).filter(TipoPrestamo.id == solicitud.tipo_prestamo_id).first()
    return {
        "solicitud_id": solicitud.id,
        "mensaje": "¡Solicitud enviada! Revisaremos tu caso y te contactaremos pronto.",
        "resumen": {
            "tipo_nombre": tipo.nombre if tipo else "—",
            "monto_solicitado": solicitud.monto_solicitado,
            "plazo_cuotas": solicitud.plazo_cuotas,
            "porcentaje_interes": solicitud.porcentaje_interes,
        },
    }
