from pydantic import BaseModel
from typing import Optional

class TipoPrestamoBase(BaseModel):
    nombre: str
    descripcion: str
    interes_mensual: float
    max_cuotas: int
    estado: Optional[str] = "activo"

class TipoPrestamoCreate(TipoPrestamoBase):
    pass

class TipoPrestamoUpdate(TipoPrestamoBase):
    pass

class TipoPrestamoOut(TipoPrestamoBase):
    id: int

    class Config:
        from_attributes = True