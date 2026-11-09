from pydantic import BaseModel, model_validator
from typing import Optional

INTERVALOS_PAGO = ("mensual", "quincenal", "bimestral", "personalizado")
APLICACIONES_INTERES = ("mensual", "por_pago")


class TipoPrestamoBase(BaseModel):
    nombre: str
    descripcion: str
    interes_mensual: float
    max_cuotas: int
    estado: Optional[str] = "activo"
    intervalo_pago: Optional[str] = "mensual"
    intervalo_dias: Optional[int] = None
    # Cómo se aplica el interés: "mensual" (% por mes cubierto) o
    # "por_pago" (% por cada cuota/pago).
    aplicacion_interes: Optional[str] = "por_pago"

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.intervalo_pago not in INTERVALOS_PAGO:
            raise ValueError(f"intervalo_pago debe ser uno de: {', '.join(INTERVALOS_PAGO)}")
        if self.intervalo_pago == "personalizado":
            if not self.intervalo_dias or self.intervalo_dias < 1:
                raise ValueError("El intervalo personalizado requiere intervalo_dias >= 1")
        elif self.intervalo_dias is not None:
            raise ValueError("intervalo_dias solo aplica cuando intervalo_pago es 'personalizado'")
        if (self.aplicacion_interes or "por_pago") not in APLICACIONES_INTERES:
            raise ValueError(f"aplicacion_interes debe ser uno de: {', '.join(APLICACIONES_INTERES)}")
        return self


class TipoPrestamoCreate(TipoPrestamoBase):
    pass


class TipoPrestamoUpdate(TipoPrestamoBase):
    pass


class TipoPrestamoOut(TipoPrestamoBase):
    id: int
    # En BD puede quedar sin descripción (columna nullable): el detalle del
    # préstamo debe poder serializarse igual.
    descripcion: Optional[str] = None

    class Config:
        from_attributes = True
