from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


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
    usuario_id: Optional[int] = None
    tabla_afectada: str
    tipo_operacion: str
    registro_id: Optional[int] = None
    valores_anteriores: Optional[str] = None
    valores_nuevos: Optional[str] = None
    descripcion: Optional[str] = None
    ip_address: Optional[str] = None
    fecha: datetime

    model_config = ConfigDict(from_attributes=True)