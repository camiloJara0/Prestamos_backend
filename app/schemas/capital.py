from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class MovimientoCapitalCreate(BaseModel):
    tipo_movimiento: str  # "inversion" o "retiro"
    descripcion: str = Field(min_length=5)  # concepto obligatorio (RF-051)
    valor: float
    fecha: date

class MovimientoCapitalOut(BaseModel):
    id: int
    tipo_movimiento: str
    descripcion: Optional[str] = None
    valor: float
    fecha: date
    prestamo_id: Optional[int] = None

    class Config:
        from_attributes = True

class CapitalOut(BaseModel):
    id: int
    monto_total: float

    class Config:
        from_attributes = True

class ResumenCajaOut(BaseModel):
    periodo: str
    ingresos: float
    egresos: float
    cantidad_ingresos: int
    cantidad_egresos: int
    saldo_capital: float
