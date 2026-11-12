from pydantic import BaseModel


class LandingEstadisticasOut(BaseModel):
    """Contadores públicos agregados para la landing (sin datos sensibles)."""

    prestamos_gestionados: int = 0
    clientes_registrados: int = 0
    pagos_procesados: int = 0
    monto_total_prestado: float = 0.0


class PrestamistaPublicoOut(BaseModel):
    """Identidad mínima de un prestamista para enlaces personalizados."""

    id: int
    nombre: str
