from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.clientes import ClienteOut
from app.schemas.tipo_prestamo import TipoPrestamoOut


class SolicitudCreate(BaseModel):
    cliente_id: int
    tipo_prestamo_id: int
    monto_solicitado: float = Field(gt=0)
    plazo_cuotas: int = Field(ge=1, le=120)
    motivo: str = Field(min_length=5, max_length=500)
    porcentaje_interes: Optional[float] = Field(default=None, ge=0, le=100)


class DecisionCreate(BaseModel):
    accion: Literal["aprobar", "rechazar"]
    motivo: str = Field(min_length=5, max_length=500)


class ConvertirCreate(BaseModel):
    porcentaje_interes: Optional[float] = Field(default=None, ge=0, le=100)
    numero_cuotas: Optional[int] = Field(default=None, ge=1, le=120)
    observaciones: Optional[str] = None


class ScoringOut(BaseModel):
    solicitud_id: int
    puntaje: Optional[float] = None
    detalle: Optional[str] = None
    advertencia: Optional[str] = None


class SolicitudOut(BaseModel):
    id: int
    cliente_id: int
    tipo_prestamo_id: int
    monto_solicitado: float
    plazo_cuotas: int
    porcentaje_interes: float
    motivo: str
    estado: str
    usuario_creador_id: Optional[int] = None
    evaluador_id: Optional[int] = None
    fecha_decision: Optional[datetime] = None
    motivo_decision: Optional[str] = None
    fecha_expiracion: Optional[date] = None
    prestamo_id: Optional[int] = None
    puntaje_scoring: Optional[float] = None
    scoring_detalle: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SolicitudDetalleOut(SolicitudOut):
    cliente: Optional[ClienteOut] = None
    tipo_prestamo: Optional[TipoPrestamoOut] = None
    nombre_creador: Optional[str] = None
    nombre_evaluador: Optional[str] = None


class CalendarioItem(BaseModel):
    """RF-081: fila del calendario de pagos del simulador público."""
    numero_cuota: int
    fecha_vencimiento: date
    valor_cuota: float


class SimulacionOut(BaseModel):
    """RF-081/HU-6.2: resultado server-side del simulador (misma lógica que crear_prestamo)."""
    tipo_prestamo_id: int
    tipo_nombre: str
    capital: float
    porcentaje_interes: float
    numero_cuotas: int
    interes_total: float
    monto_total: float
    valor_cuota: float
    fecha_primera_cuota: date
    frecuencia: str
    calendario: list[CalendarioItem]


class PlanPublicoOut(BaseModel):
    """RF-081/HU-6.1: campos públicos seguros de los planes de préstamo activos."""
    id: int
    nombre: str
    descripcion: Optional[str] = None
    interes_mensual: float
    max_cuotas: int
    intervalo_pago: str = "mensual"
    intervalo_dias: Optional[int] = None
    frecuencia: str = "mensuales"


class SolicitudPublicaCreate(BaseModel):
    """RF-081/HU-6.3: formulario público sin sesión."""
    nombre: str = Field(min_length=3, max_length=100)
    cedula: str = Field(min_length=5, max_length=20)
    telefono: str = Field(min_length=7, max_length=20)
    email: Optional[EmailStr] = Field(default=None, max_length=120)
    tipo_prestamo_id: int
    monto_solicitado: float = Field(gt=0, le=100_000_000_000)
    plazo_cuotas: int = Field(ge=1, le=120)
    motivo: str = Field(min_length=5, max_length=500)


class SolicitudPublicaOut(BaseModel):
    """RF-081: confirmación al visitante; sin datos internos (CA-R6-8)."""
    solicitud_id: int
    mensaje: str
    resumen: dict
