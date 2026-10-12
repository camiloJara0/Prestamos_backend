"""Schemas del módulo de agenda (RF-080)."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

TipoEvento = Literal["cuota_vence", "recogida", "cita", "seguimiento", "otro"]
EstadoEvento = Literal["pendiente", "completado", "cancelado", "vencido"]
EstadoTipoCita = Literal["activo", "inactivo"]


class TipoCitaCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=255)
    color: str = Field(default="#7c3aed", max_length=20)
    duracion_minutos: int = Field(default=30, ge=5, le=720)
    estado: EstadoTipoCita = "activo"


class TipoCitaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=255)
    color: Optional[str] = Field(default=None, max_length=20)
    duracion_minutos: Optional[int] = Field(default=None, ge=5, le=720)
    estado: Optional[EstadoTipoCita] = None


class TipoCitaOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    color: str
    duracion_minutos: int
    estado: EstadoTipoCita

    class Config:
        from_attributes = True


class EventoAgendaCreate(BaseModel):
    tipo: TipoEvento
    titulo: str = Field(min_length=3, max_length=200)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    fecha: date
    hora_inicio: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    hora_fin: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    prestamo_id: Optional[int] = None
    cliente_id: Optional[int] = None
    tipo_cita_id: Optional[int] = None
    observaciones: Optional[str] = Field(default=None, max_length=500)


class EventoAgendaUpdate(BaseModel):
    tipo: Optional[TipoEvento] = None
    titulo: Optional[str] = Field(default=None, min_length=3, max_length=200)
    descripcion: Optional[str] = Field(default=None, max_length=500)
    fecha: Optional[date] = None
    hora_inicio: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    hora_fin: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    prestamo_id: Optional[int] = None
    cliente_id: Optional[int] = None
    tipo_cita_id: Optional[int] = None
    observaciones: Optional[str] = Field(default=None, max_length=500)
    estado: Optional[EstadoEvento] = None


class EventoAgendaOut(BaseModel):
    id: int
    tipo: TipoEvento
    titulo: str
    descripcion: Optional[str] = None
    fecha: date
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    prestamo_id: Optional[int] = None
    cliente_id: Optional[int] = None
    cliente_nombre: Optional[str] = None
    tipo_cita_id: Optional[int] = None
    estado: EstadoEvento
    observaciones: Optional[str] = None
    created_at: Optional[datetime] = None


class ResumenAgendaOut(BaseModel):
    """CA-R5-5: eventos del día y conteo del mes."""
    fecha: date
    mes: str  # YYYY-MM
    total_dia: int
    total_mes: int
    eventos_dia: list[EventoAgendaOut]


class GeneracionEventosOut(BaseModel):
    """CA-R5-4: resultado de la generación idempotente de eventos de cuota."""
    prestamo_id: int
    creados: int
    total_cuotas: int
