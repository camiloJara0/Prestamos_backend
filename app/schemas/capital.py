from pydantic import BaseModel
from typing import Optional
from datetime import date

class MovimientoCapitalCreate(BaseModel):
    tipo_movimiento: str  # "inversion" o "retiro"
    descripcion: Optional[str] = None
    valor: float
    fecha: date

class MovimientoCapitalOut(BaseModel):
    id: int
    tipo_movimiento: str
    descripcion: Optional[str] = None
    valor: float
    fecha: date

    class Config:
        from_attributes = True

class CapitalOut(BaseModel):
    id: int
    monto_total: float

    class Config:
        from_attributes = True