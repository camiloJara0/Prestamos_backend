from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.context import aplicar_filtro_usuario
from app.models.models import (
    Capital,
    Mora,
    MovimientoCapital,
    Pago,
    Prestamo,
    PrestamoCuota,
    PrestamoPerdido,
)
from app.services.mora import mora_vigente_total, parametros_mora


def _cuotas(db: Session):
    """Cuotas visibles para el usuario actual (se ven por su préstamo)."""
    query = db.query(PrestamoCuota).join(Prestamo, PrestamoCuota.prestamo_id == Prestamo.id)
    return aplicar_filtro_usuario(query, Prestamo)


def obtener_resumen_dashboard(db: Session) -> dict:
    # 1. Capital Actual
    capital_obj = aplicar_filtro_usuario(db.query(Capital), Capital).first()
    capital_actual = capital_obj.monto_total if capital_obj else 0.0

    # 2. Conteo de préstamos agrupado por estado
    estados_query = (
        aplicar_filtro_usuario(db.query(Prestamo.estado, func.count(Prestamo.id)), Prestamo)
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
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(Prestamo.saldo_pendiente), 0.0)), Prestamo
        )
        .filter(Prestamo.estado == "activo")
        .scalar()
    )

    # 4. Total prestado
    total_prestado_periodo = (
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(Prestamo.monto_total), 0.0)), Prestamo
        ).scalar()
    )

    # 5. Ganancia neta (interés recaudado, excluyendo pagos devueltos)
    ganancia_neta = (
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(Pago.interes_pagado), 0.0)), Pago
        )
        .filter(Pago.estado_pago != "devuelto")
        .scalar()
    )

    # 6. Mora histórica registrada (registros Mora de la cartera del usuario)
    mora_acumulada = (
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(Mora.valor), 0.0)), Mora
        ).scalar()
    )

    # 7. Indicadores de cobranza y mora (RF-058) — calculados en TIEMPO REAL
    hoy = date.today()

    # Monto vencido: cuotas vencidas o parciales cuyo vencimiento ya pasó
    monto_vencido = (
        _cuotas(db)
        .filter(
            PrestamoCuota.estado.in_(["vencido", "parcial"]),
            PrestamoCuota.fecha_vencimiento < hoy,
        )
        .with_entities(func.coalesce(func.sum(PrestamoCuota.valor_cuota), 0.0))
        .scalar()
    )

    # Mora pendiente: NO depende de que el procesamiento diario haya corrido.
    # Se recalcula con la configuración vigente del usuario (gracia, porcentaje
    # o fijo, simple o compuesta) y se resta lo ya cobrado por concepto de mora.
    vigente = mora_vigente_total(db, hoy=hoy)
    mora_vigente_total_monto = float(vigente["total"])
    mora_pagada = (
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(Pago.mora_pagada), 0.0)), Pago
        )
        .filter(Pago.estado_pago != "devuelto")
        .scalar()
        or 0.0
    )
    mora_pendiente = round(max(0.0, mora_vigente_total_monto - float(mora_pagada)), 2)

    # Cobro del día: pagos registrados hoy, sin contar devoluciones
    cobro_del_dia = (
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(Pago.valor_pagado), 0.0)), Pago
        )
        .filter(
            func.date(Pago.fecha_pago) == hoy,
            Pago.estado_pago != "devuelto",
        )
        .scalar()
    )

    # 8. Pérdidas del tablero (RF-059): mismo criterio del reporte de pérdidas
    total_perdidas = (
        aplicar_filtro_usuario(
            db.query(func.coalesce(func.sum(MovimientoCapital.valor), 0.0)), MovimientoCapital
        )
        .filter(MovimientoCapital.tipo_movimiento == "perdida")
        .scalar()
    )
    cantidad_prestamos_perdidos = (
        aplicar_filtro_usuario(db.query(func.count(PrestamoPerdido.id)), PrestamoPerdido).scalar()
        or 0
    )

    return {
        "capital_actual": float(capital_actual),
        "prestamos_activos": prestamos_activos,
        "saldo_pendiente_total": float(saldo_pendiente_total),
        "ganancia_neta": float(ganancia_neta),
        "total_prestado_periodo": float(total_prestado_periodo),
        "mora_acumulada": float(mora_acumulada),
        "prestamos_por_estado": prestamos_por_estado,
        "monto_vencido": float(monto_vencido),
        "mora_pendiente": mora_pendiente,
        "mora_vigente": mora_vigente_total_monto,
        "cuotas_con_mora": int(vigente["cuotas_con_mora"]),
        "parametros_mora": parametros_mora(db),
        "cobro_del_dia": float(cobro_del_dia),
        "total_perdidas": float(total_perdidas),
        "cantidad_prestamos_perdidos": int(cantidad_prestamos_perdidos),
    }
