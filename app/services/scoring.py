"""Consulta de scoring crediticio (RF-065).

Adaptador configurable por variables de entorno:
  BURÓ_PROVIDER / BURO_PROVIDER: 'piloto' (default) | 'externo'

El proveedor piloto calcula un puntaje heurístico con el historial local del
sistema. Un proveedor externo real se conecta aquí cuando exista convenio.

El puntaje es informativo: no sustituye la decisión humana de evaluación.
"""

import json
import logging
import os

from sqlalchemy.orm import Session

from app.models.models import Cliente, Mora, Prestamo, PrestamoCuota

logger = logging.getLogger(__name__)


def consultar_scoring(db: Session, cliente_id: int) -> tuple[float | None, str, str | None]:
    """Retorna (puntaje, detalle, advertencia).

    Si la consulta falla o no hay proveedor útil, devuelve advertencia y la
    evaluación continúa sin puntaje.
    """
    proveedor = (os.getenv("BURO_PROVIDER") or "piloto").lower()
    if proveedor == "ninguno":
        return None, "", "Proveedor de buró no configurado: la evaluación continúa sin puntaje."

    try:
        if proveedor == "piloto":
            return _scoring_piloto(db, cliente_id)
        logger.warning("[SCORING] Proveedor desconocido '%s', se usa piloto", proveedor)
        return _scoring_piloto(db, cliente_id)
    except Exception as exc:  # noqa: BLE001 - el fallo del buró no detiene la evaluación
        logger.error("[SCORING] Error consultando scoring cliente %s: %s", cliente_id, exc)
        return None, "", "Sin respuesta del buró: la evaluación continúa con la advertencia correspondiente."


def _scoring_piloto(db: Session, cliente_id: int) -> tuple[float, str, str | None]:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise ValueError("cliente no encontrado")

    prestamos = db.query(Prestamo).filter(Prestamo.cliente_id == cliente_id).all()
    pagados = sum(1 for p in prestamos if p.estado == "pagado")
    perdidos = sum(1 for p in prestamos if p.estado == "perdido")
    activos = sum(1 for p in prestamos if p.estado == "activo")

    cuotas_vencidas = (
        db.query(PrestamoCuota)
        .join(Prestamo)
        .filter(
            Prestamo.cliente_id == cliente_id,
            PrestamoCuota.estado.in_(["vencido", "parcial"]),
        )
        .count()
    )
    moras_activas = (
        db.query(Mora)
        .join(Prestamo)
        .filter(Prestamo.cliente_id == cliente_id, Mora.estado != "pagada")
        .count()
    )

    puntaje = 600.0
    puntaje += min(pagados * 25, 100)
    puntaje -= min(perdidos * 100, 300)
    puntaje -= min(cuotas_vencidas * 40, 120)
    puntaje -= min(moras_activas * 30, 90)
    puntaje += 15 if activos and not cuotas_vencidas else 0
    puntaje = max(300.0, min(850.0, puntaje))

    detalle = json.dumps(
        {
            "proveedor": "piloto",
            "prestamos_pagados": pagados,
            "prestamos_perdidos": perdidos,
            "prestamos_activos": activos,
            "cuotas_vencidas": cuotas_vencidas,
            "moras_activas": moras_activas,
        },
        ensure_ascii=False,
    )
    advertencia = None
    if not prestamos:
        advertencia = "Cliente sin historial crediticio: puntaje base asignado."
    return puntaje, detalle, advertencia
