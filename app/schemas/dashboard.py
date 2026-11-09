from typing import Optional

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

    # Indicadores de cobranza y mora (RF-058)
    monto_vencido: float = 0.0
    mora_pendiente: float = 0.0
    mora_vigente: float = 0.0  # mora acumulada al día de hoy (tiempo real)
    cuotas_con_mora: int = 0
    parametros_mora: Optional[dict] = None  # gracia/tasa/modo vigentes
    cobro_del_dia: float = 0.0

    # Indicadores de pérdidas (RF-059)
    total_perdidas: float = 0.0
    cantidad_prestamos_perdidos: int = 0