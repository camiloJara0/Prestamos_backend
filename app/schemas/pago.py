from pydantic import BaseModel
from typing import Optional
from datetime import date

class PagoCreate(BaseModel):
    prestamo_id: int
    cliente_id: int
    cuota_id: int
    tipo_pago_id: int
    fecha_pago: date
    valor_pagado: float
    capital_pagado: float
    interes_pagado: float
    mora_pagada: float
    observaciones: Optional[str] = None

class PagoOut(BaseModel):
    id: int
    prestamo_id: int
    cliente_id: int
    cuota_id: int
    tipo_pago_id: int
    fecha_pago: date
    valor_pagado: float
    capital_pagado: float
    interes_pagado: float
    mora_pagada: float
    observaciones: Optional[str] = None

    class Config:
        from_attributes = True