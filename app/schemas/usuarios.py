from pydantic import BaseModel, EmailStr
from typing import Optional, Literal

class UsuarioBase(BaseModel):
    nombre: str
    email: EmailStr
    rol: Literal["admin", "prestamista", "usuario"] = "usuario"  # admin: equipo | prestamista: cartera propia | usuario: personal

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[Literal["admin", "prestamista", "usuario"]] = None
    password: Optional[str] = None
    estado: Optional[str] = None

class UsuarioOut(UsuarioBase):
    id: int
    estado: str

    class Config:
        from_attributes = True