from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date


class PagoCreate(BaseModel):
    prestamo_id: int
    cliente_id: int
    cuota_id: int
    tipo_pago_id: int
    fecha_pago: Optional[datetime] = None
    valor_pagado: float
    capital_pagado: float
    interes_pagado: float
    mora_pagada: float = 0.0
    observaciones: Optional[str] = None


class PagoDevolucionCreate(BaseModel):
    motivo_devolucion: str = Field(
        ..., 
        min_length=5, 
        description="Justificación detallada del porqué se devuelve o anula el pago"
    )


class PagoOut(BaseModel):
    id: int
    prestamo_id: int
    cliente_id: int
    cuota_id: Optional[int] = None
    tipo_pago_id: int
    fecha_pago: datetime
    valor_pagado: float
    capital_pagado: float
    interes_pagado: float
    mora_pagada: float
    observaciones: Optional[str] = None
    
    # Nuevos campos de referencia y devolución
    referencia_recibo: str
    estado_pago: str
    fecha_devolucion: Optional[datetime] = None
    motivo_devolucion: Optional[str] = None

    class Config:
        from_attributes = True