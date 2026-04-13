from pydantic import BaseModel
from typing import Optional

class ClienteBase(BaseModel):
    nombre: str
    cedula: str
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    persona_referencia: Optional[str] = None
    telefono_referencia: Optional[str] = None
    observaciones: Optional[str] = None
    estado: Optional[str] = "activo"

class ClienteCreate(ClienteBase):
    pass

class ClienteUpdate(ClienteBase):
    pass

class ClienteOut(ClienteBase):
    id: int

    class Config:
        from_attributes = True
