from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import Capital, Mora, MovimientoCapital, Pago, Prestamo, PrestamoCuota, PrestamoPerdido


def obtener_resumen_dashboard(db: Session) -> dict:
    # 1. Capital Actual
    capital_obj = db.query(Capital).first()
    capital_actual = capital_obj.monto_total if capital_obj else 0.0

    # 2. Conteo de préstamos agrupado por estado
    estados_query = (
        db.query(Prestamo.estado, func.count(Prestamo.id))
        .group_by(Prestamo.estado)
        .all()
    )
    prestamos_por_estado = {
        "activo": 0,
        "pagado": 0,
        "perdido": 0,
        "renovado": 0,
    }
    for estado, conteo in estados_query:
        if estado in prestamos_por_estado:
            prestamos_por_estado[estado] = conteo

    # 3. Préstamos activos y saldo pendiente total
    prestamos_activos = prestamos_por_estado.get("activo", 0)
    saldo_pendiente_total = (
        db.query(func.coalesce(func.sum(Prestamo.saldo_pendiente), 0.0))
        .filter(Prestamo.estado == "activo")
        .scalar()
    )

    # 4. Total prestado
    total_prestado_periodo = (
        db.query(func.coalesce(func.sum(Prestamo.monto_total), 0.0)).scalar()
    )

    # 5. Ganancia neta (interés recaudado, excluyendo pagos devueltos)
    ganancia_neta = (
        db.query(func.coalesce(func.sum(Pago.interes_pagado), 0.0))
        .filter(Pago.estado_pago != "devuelto")
        .scalar()
    )

    # 6. Mora acumulada (Detecta automáticamente el atributo disponible en Mora o Cuotas)
    if hasattr(Mora, "monto"):
        columna_mora = Mora.monto
    elif hasattr(Mora, "valor"):
        columna_mora = Mora.valor
    elif hasattr(Mora, "monto_mora"):
        columna_mora = Mora.monto_mora
    else:
        columna_mora = None

    if columna_mora is not None:
        mora_acumulada = db.query(
            func.coalesce(func.sum(columna_mora), 0.0)
        ).scalar()
    else:
        # Fallback a las cuotas si el modelo Mora no define el valor
        mora_acumulada = (
            db.query(
                func.coalesce(func.sum(PrestamoCuota.mora_acumulada), 0.0)
            ).scalar()
            if hasattr(PrestamoCuota, "mora_acumulada")
            else 0.0
        )

    # 7. Indicadores de cobranza y mora (RF-058)
    hoy = date.today()

    # Monto vencido: cuotas vencidas o parciales cuyo vencimiento ya pasó
    monto_vencido = (
        db.query(func.coalesce(func.sum(PrestamoCuota.valor_cuota), 0.0))
        .filter(
            PrestamoCuota.estado.in_(["vencido", "parcial"]),
            PrestamoCuota.fecha_vencimiento < hoy,
        )
        .scalar()
    )

    # Mora pendiente: moras en estado generada aún no saldadas
    mora_pendiente = (
        db.query(func.coalesce(func.sum(Mora.valor), 0.0))
        .filter(Mora.estado == "generada")
        .scalar()
    )

    # Cobro del día: pagos registrados hoy, sin contar devoluciones
    cobro_del_dia = (
        db.query(func.coalesce(func.sum(Pago.valor_pagado), 0.0))
        .filter(
            func.date(Pago.fecha_pago) == hoy,
            Pago.estado_pago != "devuelto",
        )
        .scalar()
    )

    # 8. Pérdidas del tablero (RF-059): mismo criterio del reporte de pérdidas
    total_perdidas = (
        db.query(func.coalesce(func.sum(MovimientoCapital.valor), 0.0))
        .filter(MovimientoCapital.tipo_movimiento == "perdida")
        .scalar()
    )
    cantidad_prestamos_perdidos = db.query(func.count(PrestamoPerdido.id)).scalar() or 0

    return {
        "capital_actual": float(capital_actual),
        "prestamos_activos": prestamos_activos,
        "saldo_pendiente_total": float(saldo_pendiente_total),
        "ganancia_neta": float(ganancia_neta),
        "total_prestado_periodo": float(total_prestado_periodo),
        "mora_acumulada": float(mora_acumulada),
        "prestamos_por_estado": prestamos_por_estado,
        "monto_vencido": float(monto_vencido),
        "mora_pendiente": float(mora_pendiente),
        "cobro_del_dia": float(cobro_del_dia),
        "total_perdidas": float(total_perdidas),
        "cantidad_prestamos_perdidos": int(cantidad_prestamos_perdidos),
    }