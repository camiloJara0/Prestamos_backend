from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

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
