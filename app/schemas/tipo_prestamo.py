from pydantic import BaseModel, model_validator
from typing import Optional

INTERVALOS_PAGO = ("mensual", "quincenal", "bimestral", "personalizado")


class TipoPrestamoBase(BaseModel):
    nombre: str
    descripcion: str
    interes_mensual: float
    max_cuotas: int
    estado: Optional[str] = "activo"
    intervalo_pago: Optional[str] = "mensual"
    intervalo_dias: Optional[int] = None

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.intervalo_pago not in INTERVALOS_PAGO:
            raise ValueError(f"intervalo_pago debe ser uno de: {', '.join(INTERVALOS_PAGO)}")
        if self.intervalo_pago == "personalizado":
            if not self.intervalo_dias or self.intervalo_dias < 1:
                raise ValueError("El intervalo personalizado requiere intervalo_dias >= 1")
        elif self.intervalo_dias is not None:
            raise ValueError("intervalo_dias solo aplica cuando intervalo_pago es 'personalizado'")
        return self


class TipoPrestamoCreate(TipoPrestamoBase):
    pass


class TipoPrestamoUpdate(TipoPrestamoBase):
    pass


class TipoPrestamoOut(TipoPrestamoBase):
    id: int

    class Config:
        from_attributes = True
