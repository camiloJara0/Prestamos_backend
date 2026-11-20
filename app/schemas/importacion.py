"""Schemas Pydantic de importación masiva Excel/CSV (Fase 4)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

EntidadImportacion = Literal["clientes", "prestamos", "pagos", "cuotas"]


class ColumnaDetectada(BaseModel):
    nombre: str
    valores_unicos: list[str] = []


class ColumnasOut(BaseModel):
    columnas: list[ColumnaDetectada]
    total_filas: int


class ImportacionItemVista(BaseModel):
    fila: int
    datos: dict
    valido: bool
    errores: list[str] = []
    homologaciones: dict = {}


class ImportacionErrorItem(BaseModel):
    fila: int
    campo: Optional[str] = None
    mensaje: str


class ImportacionResultado(BaseModel):
    entidad: str
    total_filas: int
    validas: int
    con_error: int
    vista_previa: list[ImportacionItemVista] = []
    errores: list[ImportacionErrorItem] = []
    bitacora_id: Optional[int] = None
    mensaje: Optional[str] = None


class ImportacionBitacoraOut(BaseModel):
    id: int
    entidad: str
    archivo_nombre: Optional[str] = None
    total_filas: int
    exitosos: int
    errores: int
    created_at: datetime

    class Config:
        from_attributes = True
