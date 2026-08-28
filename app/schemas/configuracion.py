from pydantic import BaseModel
from typing import Optional

class ConfiguracionBase(BaseModel):
    clave: str
    valor: str
    descripcion: Optional[str] = None
    tipo_valor: str = "string"  # float, int, string, boolean

class ConfiguracionCreate(ConfiguracionBase):
    pass

class ConfiguracionUpdate(BaseModel):
    valor: str
    descripcion: Optional[str] = None

class ConfiguracionOut(ConfiguracionBase):
    id: int
    activo: bool

    class Config:
        from_attributes = True