"""Schemas Pydantic de campañas de mensajes automáticos (Fase 2)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

FrecuenciaCampana = Literal["diario", "semanal", "mensual"]
FiltroCampana = Literal["proximos", "vencidos"]
EstadoCampana = Literal["activo", "inactivo"]


class CampanaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    plantilla_id: int
    hora_ejecucion: str = Field(pattern=r"^\d{2}:\d{2}$", examples=["08:00"])
    frecuencia: FrecuenciaCampana = "diario"
    dia_semana: Optional[int] = Field(default=None, ge=0, le=6)
    dia_mes: Optional[int] = Field(default=None, ge=1, le=28)
    filtro_tipo: FiltroCampana = "proximos"
    filtro_dias: int = Field(default=3, ge=1, le=30)


class CampanaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=120)
    plantilla_id: Optional[int] = None
    hora_ejecucion: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    frecuencia: Optional[FrecuenciaCampana] = None
    dia_semana: Optional[int] = Field(default=None, ge=0, le=6)
    dia_mes: Optional[int] = Field(default=None, ge=1, le=28)
    filtro_tipo: Optional[FiltroCampana] = None
    filtro_dias: Optional[int] = Field(default=None, ge=1, le=30)
    estado: Optional[EstadoCampana] = None


class CampanaOut(BaseModel):
    id: int
    nombre: str
    plantilla_id: int
    plantilla_nombre: Optional[str] = None
    hora_ejecucion: str
    frecuencia: str
    dia_semana: Optional[int] = None
    dia_mes: Optional[int] = None
    filtro_tipo: str
    filtro_dias: int
    estado: str
    ultima_ejecucion: Optional[str] = None


class CampanaEjecucionOut(BaseModel):
    message: str
    ultima_ejecucion: Optional[str] = None
