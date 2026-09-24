from pydantic import BaseModel
from typing import List, Optional


class ResultadoItemConciliacion(BaseModel):
    fila_o_pagina: int  # Número de fila (Excel/CSV) o página (PDF)
    referencia_encontrada: Optional[str] = None
    referencia_coincidente: Optional[str] = None
    monto_extraido: float
    monto_cuota: Optional[float] = None
    cliente_nombre: Optional[str] = None
    cuota_id: Optional[int] = None
    estado_conciliacion: str  # "MATCH_EXACTO", "MONTO_DIFERENTE", "NO_ENCONTRADO"
    mensaje: str


class ConciliacionResumenResponse(BaseModel):
    total_procesados: int
    total_conciliados: int
    total_con_diferencia: int
    total_no_encontrados: int
    detalles: List[ResultadoItemConciliacion]