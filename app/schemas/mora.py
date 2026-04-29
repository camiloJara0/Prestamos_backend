from pydantic import BaseModel
from typing import Optional

class MoraBase(BaseModel):
    prestamo_id: int
    cuota_id: int
    fecha: str
    valor: float
    estado: str

class MoraCreate(MoraBase):
    pass

class MoraUpdate(MoraBase):
    pass

class MoraOut(MoraBase):
    id: int

    class Config:
        from_attributes = True
