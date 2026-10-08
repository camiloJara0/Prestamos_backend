"""Pasarela de pago en línea (RF-064).

Adaptador configurable por variable de entorno:
  PASARELA_PROVIDER: 'ninguno' (default) | 'piloto' | 'externo'

Reglas del requisito:
  - Ningún pago se registra sin confirmación de la pasarela.
  - Una transacción no conciliada queda pendiente y no descuenta saldo.
"""

import logging
import os
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Capital, MovimientoCapital, Pago, PrestamoCuota, TipoPago, TransaccionPasarela
from app.schemas.pago import PagoCreate
from app.services.pago import registrar_pago
from app.utils.pagination import paginate

logger = logging.getLogger(__name__)


def _proveedor() -> str:
    return (os.getenv("PASARELA_PROVIDER") or "ninguno").lower()


def _tipo_pago_online(db: Session) -> int:
    tipo = db.query(TipoPago).filter(TipoPago.nombre == "Pago en línea").first()
    if not tipo:
        tipo = TipoPago(nombre="Pago en línea", descripcion="Pago confirmado por pasarela en línea", estado="activo")
        db.add(tipo)
        db.commit()
        db.refresh(tipo)
    return tipo.id


def _monto_pendiente_cuota(db: Session, cuota: PrestamoCuota) -> tuple[float, float, float, float]:
    """Retorna (total, capital, interes, mora) pendientes de la cuota."""
    pagos_previos = [
        p
        for p in db.query(Pago).filter(Pago.cuota_id == cuota.id, Pago.estado_pago != "devuelto").all()
    ]
    abonado = sum(p.valor_pagado for p in pagos_previos)
    capital_abonado = sum(p.capital_pagado for p in pagos_previos)
    interes_abonado = sum(p.interes_pagado for p in pagos_previos)
    mora_abonada = sum(p.mora_pagada for p in pagos_previos)

    capital = round(max(0.0, cuota.capital - capital_abonado), 2)
    interes = round(max(0.0, cuota.interes - interes_abonado), 2)
    mora = round(max(0.0, cuota.mora - mora_abonada), 2)
    total = round(max(0.0, cuota.valor_cuota + cuota.mora - abonado), 2)
    return total, capital, interes, mora


def crear_intencion_pago(db: Session, cuota_id: int, usuario_id: int | None = None) -> TransaccionPasarela:
    if _proveedor() == "ninguno":
        raise HTTPException(
            status_code=400,
            detail="Pasarela de pago no configurada. Configure PASARELA_PROVIDER para habilitar el cobro en línea.",
        )

    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    if cuota.estado == "pagado":
        raise HTTPException(status_code=400, detail="La cuota ya está pagada")

    total, _, _, _ = _monto_pendiente_cuota(db, cuota)
    if total <= 0:
        raise HTTPException(status_code=400, detail="La cuota no tiene saldo pendiente")

    proveedor = _proveedor()
    transaccion = TransaccionPasarela(
        cuota_id=cuota.id,
        monto=total,
        pasarela=proveedor,
        estado="pendiente",
        referencia_externa=f"TX-{uuid.uuid4().hex[:10].upper()}",
        creado_por=usuario_id,
    )
    if proveedor == "piloto":
        base = (os.getenv("FRONTEND_URL") or "http://localhost:3000").rstrip("/")
        transaccion.url_pago = f"{base}/pagos/en-linea?tx={transaccion.referencia_externa}"
    db.add(transaccion)
    db.commit()
    db.refresh(transaccion)
    return transaccion


def confirmar_transaccion(
    db: Session,
    transaccion_id: int,
    exito: bool = True,
    referencia_externa: str | None = None,
    usuario_id: int | None = None,
    ip_address: str | None = None,
) -> TransaccionPasarela:
    """Confirma o falla una transacción desde la pasarela (webhook o piloto).

    Solo una confirmación exitosa registra el pago y descuenta saldo.
    """
    transaccion = (
        db.query(TransaccionPasarela).filter(TransaccionPasarela.id == transaccion_id).first()
    )
    if not transaccion:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    if transaccion.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"La transacción ya está en estado '{transaccion.estado}'")

    if not exito:
        transaccion.estado = "fallida"
        transaccion.motivo_falla = "Transacción rechazada por la pasarela"
        db.commit()
        db.refresh(transaccion)
        return transaccion

    cuota = transaccion.cuota
    prestamo = cuota.prestamo
    total, capital, interes, mora = _monto_pendiente_cuota(db, cuota)

    datos_pago = PagoCreate(
        prestamo_id=prestamo.id,
        cliente_id=prestamo.cliente_id,
        cuota_id=cuota.id,
        tipo_pago_id=_tipo_pago_online(db),
        valor_pagado=total,
        capital_pagado=capital,
        interes_pagado=interes,
        mora_pagada=mora,
        observaciones=f"Pago en línea vía pasarela {transaccion.pasarela} (ref. {transaccion.referencia_externa})",
    )
    db_pago = registrar_pago(
        db,
        datos_pago,
        usuario_id if usuario_id else (transaccion.creado_por or None),
        ip_address=ip_address,
    )

    transaccion.estado = "confirmada"
    transaccion.pago_id = db_pago.id
    transaccion.fecha_confirmacion = datetime.utcnow()
    if referencia_externa:
        transaccion.referencia_externa = referencia_externa
    db.commit()
    db.refresh(transaccion)
    return transaccion


def get_transaccion(db: Session, transaccion_id: int) -> TransaccionPasarela:
    transaccion = (
        db.query(TransaccionPasarela).filter(TransaccionPasarela.id == transaccion_id).first()
    )
    if not transaccion:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return transaccion


def get_transaccion_por_referencia(db: Session, referencia: str) -> TransaccionPasarela | None:
    return (
        db.query(TransaccionPasarela)
        .filter(TransaccionPasarela.referencia_externa == referencia)
        .first()
    )


def get_transacciones(db: Session, page: int = 1, limit: int = 10, estado: str | None = None):
    query = db.query(TransaccionPasarela).order_by(TransaccionPasarela.id.desc())
    if estado:
        query = query.filter(TransaccionPasarela.estado == estado)
    return paginate(query, page=page, limit=limit)
