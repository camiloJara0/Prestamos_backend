from typing import Dict, Any
from app.models.models import MetodoPagoPrestamista, PrestamoCuota


def obtener_datos_cobro_cuota(
    metodo: MetodoPagoPrestamista, 
    cuota: PrestamoCuota
) -> Dict[str, Any]:
    """
    Retorna la información clara formateada para transferencias por número,
    llave Transfiya o la app del banco.
    """
    return {
        "banco": metodo.banco,
        "tipo_cuenta": metodo.tipo_cuenta,
        "numero_cuenta": metodo.numero_cuenta,
        "titular": metodo.titular,
        "documento_titular": metodo.documento_titular,
        "monto_a_pagar": cuota.valor_cuota,
        "referencia_pago": cuota.referencia_pago,
        "instrucciones": (
            f"Realiza la transferencia a {metodo.banco} ({metodo.numero_cuenta}) "
            f"por valor de ${cuota.valor_cuota:,.0f} e incluye la referencia "
            f"{cuota.referencia_pago} en el concepto o motivo del pago."
        )
    }