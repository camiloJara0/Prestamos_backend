from pydantic import BaseModel
from typing import Optional

class TipoPagoBase(BaseModel):
    nombre: str
    descripcion: str

class TipoPagoCreate(TipoPagoBase):
    pass

class TipoPagoUpdate(TipoPagoBase):
    pass

class TipoPagoOut(TipoPagoBase):
    id: int

    class Config:
        from_attributes = True