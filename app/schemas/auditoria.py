from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AuditoriaCreate(BaseModel):
    tabla_afectada: str
    tipo_operacion: str
    registro_id: Optional[int] = None
    valores_anteriores: Optional[str] = None
    valores_nuevos: Optional[str] = None
    descripcion: Optional[str] = None
    ip_address: Optional[str] = None

class AuditoriaOut(BaseModel):
    id: int
    usuario_id: int
    tabla_afectada: str
    tipo_operacion: str
    registro_id: Optional[int]
    valores_anteriores: Optional[str]
    valores_nuevos: Optional[str]
    descripcion: Optional[str]
    ip_address: Optional[str]
    fecha: datetime

    class Config:
        from_attributes = True