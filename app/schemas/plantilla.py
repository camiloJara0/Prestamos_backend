from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class PlantillaCreate(BaseModel):
    clave: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9_]+$")
    canal: Literal["email", "sms", "whatsapp"]
    nombre: str = Field(min_length=3, max_length=120)
    asunto: Optional[str] = Field(default=None, max_length=200)
    cuerpo: str = Field(min_length=5)
    activa: bool = True


class PlantillaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=3, max_length=120)
    asunto: Optional[str] = Field(default=None, max_length=200)
    cuerpo: Optional[str] = Field(default=None, min_length=5)
    activa: Optional[bool] = None


class PlantillaOut(BaseModel):
    id: int
    clave: str
    canal: str
    nombre: str
    asunto: Optional[str] = None
    cuerpo: str
    activa: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlantillaPreview(BaseModel):
    clave: str = Field(min_length=3, max_length=80)
    canal: Literal["email", "sms", "whatsapp"]
    asunto: Optional[str] = None
    cuerpo: str = Field(min_length=1)
    contexto: dict = Field(default_factory=dict)


class PlantillaPreviewOut(BaseModel):
    asunto: str
    cuerpo: str
    variables: list[str]
