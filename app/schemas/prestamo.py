from pydantic import BaseModel
from typing import Optional
from datetime import date

class PrestamoCreate(BaseModel):
    cliente_id: int
    tipo_prestamo_id: int
    fecha_prestamo: date
    capital_prestado: float
    porcentaje_interes: float
    numero_cuotas: int
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