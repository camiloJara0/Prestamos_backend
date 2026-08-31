from pydantic import BaseModel


class PrestamosPorEstado(BaseModel):
    activo: int = 0
    pagado: int = 0
    perdido: int = 0
    renovado: int = 0


class DashboardResumenOut(BaseModel):
    capital_actual: float
    prestamos_activos: int
    saldo_pendiente_total: float
    ganancia_neta: float
    total_prestado_periodo: float
    mora_acumulada: float
    prestamos_por_estado: PrestamosPorEstado