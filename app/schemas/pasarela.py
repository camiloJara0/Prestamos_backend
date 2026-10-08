from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class IntencionPagoCreate(BaseModel):
    cuota_id: int


class ConfirmacionCreate(BaseModel):
    exito: bool = True
    referencia_externa: Optional[str] = None


class TransaccionOut(BaseModel):
    id: int
    cuota_id: int
    monto: float
    pasarela: str
    estado: str
    referencia_externa: Optional[str] = None
    url_pago: Optional[str] = None
    motivo_falla: Optional[str] = None
    pago_id: Optional[int] = None
    fecha_creacion: Optional[datetime] = None
    fecha_confirmacion: Optional[datetime] = None

    class Config:
        from_attributes = True
