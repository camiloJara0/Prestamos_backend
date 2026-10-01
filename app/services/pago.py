import uuid
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.models import Pago, PrestamoCuota, Prestamo, MovimientoCapital, TipoPago, Capital
from app.schemas.pago import PagoCreate, PagoDevolucionCreate
from app.utils.pagination import paginate


def _generar_referencia_recibo() -> str:
    fecha_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"REC-{fecha_str}-{unique_suffix}"


def _validar_pago(db: Session, pago: PagoCreate):
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago.cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    if cuota.estado == "pagado":
        raise HTTPException(status_code=400, detail="La cuota ya ha sido completamente pagada")

    prestamo = db.query(Prestamo).filter(Prestamo.id == pago.prestamo_id).first()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    if cuota.prestamo_id != prestamo.id:
        raise HTTPException(status_code=400, detail="La cuota no pertenece al préstamo indicado")

    if pago.cliente_id != prestamo.cliente_id:
        raise HTTPException(status_code=400, detail="El cliente del pago no coincide con el préstamo")

    if not db.query(TipoPago).filter(TipoPago.id == pago.tipo_pago_id).first():
        raise HTTPException(status_code=404, detail="Tipo de pago no encontrado")

    if pago.valor_pagado < 0 or pago.capital_pagado < 0 or pago.interes_pagado < 0 or pago.mora_pagada < 0:
        raise HTTPException(status_code=400, detail="Los montos del pago no pueden ser negativos")

    desglose = round(pago.capital_pagado + pago.interes_pagado + pago.mora_pagada, 2)
    if abs(desglose - round(pago.valor_pagado, 2)) > 0.01:
        raise HTTPException(
            status_code=400,
            detail="El desglose (capital + interés + mora) no coincide con el valor pagado"
        )

    return cuota, prestamo


def registrar_pago(db: Session, pago: PagoCreate, usuario_id: int):
    cuota, prestamo = _validar_pago(db, pago)

    fecha_pago_val = pago.fecha_pago or datetime.now(timezone.utc)
    referencia_recibo = _generar_referencia_recibo()

    db_pago = Pago(
        prestamo_id=pago.prestamo_id,
        cliente_id=pago.cliente_id,
        cuota_id=pago.cuota_id,
        tipo_pago_id=pago.tipo_pago_id,
        fecha_pago=fecha_pago_val,
        valor_pagado=pago.valor_pagado,
        capital_pagado=pago.capital_pagado,
        interes_pagado=pago.interes_pagado,
        mora_pagada=pago.mora_pagada,
        observaciones=pago.observaciones,
        referencia_recibo=referencia_recibo,
        estado_pago="confirmado"
    )
    db.add(db_pago)

    # Actualizar estado de cuota (considerando solo pagos no devueltos)
    pagos_anteriores = (
        db.query(Pago)
        .filter(Pago.cuota_id == cuota.id, Pago.estado_pago != "devuelto")
        .all()
    )
    total_abonado = sum(p.valor_pagado for p in pagos_anteriores) + pago.valor_pagado

    if total_abonado >= cuota.valor_cuota - 0.01:
        cuota.estado = "pagado"
    else:
        cuota.estado = "parcial"

    # Actualizar saldo del préstamo (capital + interés; protección para no bajar de 0)
    nuevo_saldo = round(prestamo.saldo_pendiente - (pago.capital_pagado + pago.interes_pagado), 2)
    prestamo.saldo_pendiente = max(0.0, nuevo_saldo)
    if prestamo.saldo_pendiente <= 0:
        prestamo.estado = "pagado"

    # Actualizar capital global
    capital_obj = db.query(Capital).first()
    if capital_obj:
        capital_obj.monto_total += pago.capital_pagado

    movimiento = MovimientoCapital(
        prestamo_id=pago.prestamo_id,
        tipo_movimiento="pago_recibido",
        descripcion=f"Pago cuota #{cuota.numero_cuota} (Recibo: {referencia_recibo}) - Préstamo #{prestamo.id}",
        valor=pago.capital_pagado,
        fecha=fecha_pago_val
    )
    db.add(movimiento)

    db.commit()
    db.refresh(db_pago)

    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="pagos",
        tipo_operacion="CREATE",
        registro_id=db_pago.id,
        valores_nuevos={
            "cuota_id": db_pago.cuota_id,
            "referencia_recibo": db_pago.referencia_recibo,
            "monto_pagado": db_pago.valor_pagado,
            "capital_pagado": db_pago.capital_pagado,
            "interes_pagado": db_pago.interes_pagado,
            "mora_pagada": db_pago.mora_pagada,
            "fecha_pago": str(db_pago.fecha_pago)
        },
        descripcion=f"Pago registrado para cuota #{cuota.numero_cuota} con Recibo: {referencia_recibo}"
    )

    return db_pago


def devolver_pago(db: Session, pago_id: int, datos_devolucion: PagoDevolucionCreate, usuario_id: int):
    db_pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not db_pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    if db_pago.estado_pago == "devuelto":
        raise HTTPException(status_code=400, detail="Este pago ya fue devuelto previamente")

    # Manejo seguro de conversión de date a datetime para evitar AttributeError con tzinfo
    fecha_pago_raw = db_pago.fecha_pago
    if isinstance(fecha_pago_raw, date) and not isinstance(fecha_pago_raw, datetime):
        fecha_pago_aware = datetime.combine(fecha_pago_raw, datetime.min.time())
    else:
        fecha_pago_aware = fecha_pago_raw

    # Asegurar timezone UTC / Aware para la comparación
    if fecha_pago_aware.tzinfo is None:
        fecha_pago_aware = fecha_pago_aware.replace(tzinfo=timezone.utc)

    # Restricción de 30 días
    ahora = datetime.now(timezone.utc)
    if (ahora - fecha_pago_aware) > timedelta(days=30):
        raise HTTPException(
            status_code=400, 
            detail="No se puede devolver un pago realizado hace más de 30 días"
        )

    # 1. Reversión en Préstamo
    prestamo = db.query(Prestamo).filter(Prestamo.id == db_pago.prestamo_id).first()
    if prestamo:
        # Control para evitar inflar el saldo más allá del monto total original
        monto_a_reversar = db_pago.capital_pagado + db_pago.interes_pagado
        nuevo_saldo = round(prestamo.saldo_pendiente + monto_a_reversar, 2)
        prestamo.saldo_pendiente = min(nuevo_saldo, round(prestamo.monto_total, 2))

        if prestamo.estado == "pagado" and prestamo.saldo_pendiente > 0:
            prestamo.estado = "activo"

    # 2. Reversión en Cuota
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == db_pago.cuota_id).first()
    if cuota:
        pagos_restantes = (
            db.query(Pago)
            .filter(
                Pago.cuota_id == cuota.id, 
                Pago.id != db_pago.id, 
                Pago.estado_pago != "devuelto"
            )
            .all()
        )
        total_abonado_restante = sum(p.valor_pagado for p in pagos_restantes)

        if total_abonado_restante <= 0:
            cuota.estado = "pendiente"
        else:
            cuota.estado = "parcial"

    # 3. Ajuste de Capital Global (misma convención que el registro: solo la porción de capital)
    capital_obj = db.query(Capital).first()
    if capital_obj:
        capital_obj.monto_total = round(capital_obj.monto_total - db_pago.capital_pagado, 2)

    movimiento = MovimientoCapital(
        prestamo_id=db_pago.prestamo_id,
        tipo_movimiento="devolucion_pago",
        descripcion=f"Devolución de pago Recibo: {db_pago.referencia_recibo} - Motivo: {datos_devolucion.motivo_devolucion}",
        valor=-db_pago.capital_pagado,
        fecha=ahora
    )
    db.add(movimiento)

    # 4. Actualizar Estado del Pago
    db_pago.estado_pago = "devuelto"
    db_pago.fecha_devolucion = ahora
    db_pago.motivo_devolucion = datos_devolucion.motivo_devolucion

    db.commit()
    db.refresh(db_pago)

    # 5. Auditoría
    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="pagos",
        tipo_operacion="UPDATE",
        registro_id=db_pago.id,
        valores_nuevos={
            "estado_pago": "devuelto",
            "fecha_devolucion": str(db_pago.fecha_devolucion),
            "motivo_devolucion": db_pago.motivo_devolucion
        },
        descripcion=f"Devolución de pago Recibo {db_pago.referencia_recibo}. Motivo: {datos_devolucion.motivo_devolucion}"
    )

    return db_pago


def get_pagos(db: Session, page: int = 1, limit: int = 10):
    query = db.query(Pago).order_by(Pago.id.desc())
    return paginate(query, page=page, limit=limit)