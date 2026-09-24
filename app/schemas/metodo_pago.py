from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class MetodoPagoPrestamistaBase(BaseModel):
    banco: str  # Nequi, Daviplata, Bancolombia, Transfiya, etc.
    tipo_cuenta: Optional[str] = "Ahorros"  # Ahorros, Corriente, Llave
    numero_cuenta: str  # Número de cuenta, teléfono o llave
    titular: str
    documento_titular: Optional[str] = None


class MetodoPagoPrestamistaCreate(MetodoPagoPrestamistaBase):
    pass


class MetodoPagoPrestamistaUpdate(BaseModel):
    banco: Optional[str] = None
    tipo_cuenta: Optional[str] = None
    numero_cuenta: Optional[str] = None
    titular: Optional[str] = None
    documento_titular: Optional[str] = None
    activo: Optional[bool] = None


class MetodoPagoPrestamistaOut(MetodoPagoPrestamistaBase):
    id: int
    usuario_id: int 
    qr_code_url: Optional[str] = None
    activo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  