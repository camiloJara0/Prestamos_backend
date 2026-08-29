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

class CuotaCobranzaOut(BaseModel):
    cuota_id: int
    prestamo_id: int
    cliente_nombre: str
    numero_cuota: int
    fecha_vencimiento: date
    valor_cuota: float
    estado: str
    dias_atraso: int

class ReporteCobranzaOut(BaseModel):
    total_cuotas_por_vencer: int
    monto_por_vencer: float
    total_cuotas_vencidas: int
    monto_vencido: float
    total_cuotas_pagadas: int
    monto_pagado: float
    cuotas_por_vencer: list[CuotaCobranzaOut]
    cuotas_vencidas: list[CuotaCobranzaOut]
    cuotas_pagadas: list[CuotaCobranzaOut]

class PrestamosCarteraOut(BaseModel):
    total_activos: int
    monto_activos: float
    total_renovados: int
    monto_renovados: float
    total_perdidos: int
    monto_perdidos: float
    distribucion_por_tipo: dict