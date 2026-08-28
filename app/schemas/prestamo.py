from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

from app.schemas.clientes import ClienteOut
from app.schemas.tipo_prestamo import TipoPrestamoOut
from app.schemas.pago import PagoOut

class PrestamoCreate(BaseModel):
    cliente_id: int
    tipo_prestamo_id: int
    capital_prestado: float
    porcentaje_interes: float
    numero_cuotas: int
    fecha_prestamo: Optional[date] = None
    observaciones: Optional[str] = None

class PrestamoOut(BaseModel):
    id: int
    cliente_id: int
    tipo_prestamo_id: int
    fecha_prestamo: date
    capital_prestado: float
    porcentaje_interes: float
    interes_total: float
    monto_total: float
    numero_cuotas: int
    valor_cuota: float
    saldo_pendiente: float
    estado: str
    observaciones: Optional[str] = None

    class Config:
        from_attributes = True

class CuotaOut(BaseModel):
    id: int
    prestamo_id: int
    numero_cuota: int
    fecha_vencimiento: date
    valor_cuota: float
    capital: float
    interes: float
    mora: float
    estado: str

    class Config:
        from_attributes = True


class PrestamoDetalleOut(PrestamoOut):
    cliente: Optional[ClienteOut] = None
    tipo_prestamo: Optional[TipoPrestamoOut] = None
    cuotas: list[CuotaOut] = Field(default_factory=list)
    pagos: list[PagoOut] = Field(default_factory=list)


class RenovacionCreate(BaseModel):
    porcentaje_interes: float
    numero_cuotas: int
    abono: Optional[float] = 0.0
    fecha_renovacion: date
    observaciones: Optional[str] = None

class PrestamoPerdidoOut(BaseModel):
    id: int
    prestamo_id: int
    fecha: date
    valor_perdido: float
    motivo: Optional[str] = None

    class Config:
        from_attributes = True

class MarcarPerdidoRequest(BaseModel):
    motivo: Optional[str] = None
    fecha: date