from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ContratoFirmarCreate(BaseModel):
    firmante_nombre: str = Field(min_length=3, max_length=120)
    firmante_documento: str = Field(min_length=3, max_length=30)


class ContratoOut(BaseModel):
    id: int
    solicitud_id: Optional[int] = None
    prestamo_id: Optional[int] = None
    estado: str
    hash_documento: str
    firmante_nombre: Optional[str] = None
    firmante_documento: Optional[str] = None
    fecha_emision: Optional[datetime] = None
    fecha_firma: Optional[datetime] = None

    class Config:
        from_attributes = True
