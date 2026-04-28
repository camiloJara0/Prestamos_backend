from pydantic import BaseModel
from typing import Optional
from datetime import date

class ReporteGananciasOut(BaseModel):
    total_invertido: float
    total_prestado: float
    total_pagos_recibidos: float
    total_intereses: float
    ganancia_neta: float

class ReportePérdidasOut(BaseModel):
    total_perdidas: float
    cantidad_prestamos_perdidos: float
    detalle: list