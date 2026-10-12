"""Agenda y calendario operativo (RF-080): eventos, tipos de cita y auto-generación."""

import logging
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.models import Cliente, EventoAgenda, Prestamo, PrestamoCuota, TipoCita
from app.schemas.agenda import (
    EventoAgendaCreate,
    EventoAgendaOut,
    EventoAgendaUpdate,
    TipoCitaCreate,
    TipoCitaUpdate,
)

logger = logging.getLogger(__name__)

ESTADOS_EVENTO = ("pendiente", "completado", "cancelado", "vencido")


def _out(evento: EventoAgenda) -> EventoAgendaOut:
    return EventoAgendaOut(
        id=evento.id,
        tipo=evento.tipo,
        titulo=evento.titulo,
        descripcion=evento.descripcion,
        fecha=evento.fecha,
        hora_inicio=evento.hora_inicio,
        hora_fin=evento.hora_fin,
        prestamo_id=evento.prestamo_id,
        cliente_id=evento.cliente_id,
        cliente_nombre=evento.cliente.nombre if evento.cliente else None,
        tipo_cita_id=evento.tipo_cita_id,
        estado=evento.estado,
        observaciones=evento.observaciones,
        created_at=evento.created_at,
    )


def _validar_vinculos(db: Session, cliente_id, prestamo_id, tipo_cita_id) -> None:
    if cliente_id and not db.query(Cliente).filter(Cliente.id == cliente_id).first():
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    if prestamo_id and not db.query(Prestamo).filter(Prestamo.id == prestamo_id).first():
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    if tipo_cita_id and not db.query(TipoCita).filter(TipoCita.id == tipo_cita_id).first():
        raise HTTPException(status_code=404, detail="Tipo de cita no encontrado")


def get_eventos(
    db: Session,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
) -> list[EventoAgendaOut]:
    """CA-R5-1: eventos filtrables por rango de fecha, tipo y estado."""
    query = db.query(EventoAgenda).options(joinedload(EventoAgenda.cliente))
    if fecha_desde:
        query = query.filter(EventoAgenda.fecha >= fecha_desde)
    if fecha_hasta:
        query = query.filter(EventoAgenda.fecha <= fecha_hasta)
    if tipo:
        query = query.filter(EventoAgenda.tipo == tipo)
    if estado:
        query = query.filter(EventoAgenda.estado == estado)
    eventos = query.order_by(EventoAgenda.fecha.asc(), EventoAgenda.hora_inicio.asc(), EventoAgenda.id.asc()).all()
    return [_out(e) for e in eventos]


def get_evento(db: Session, evento_id: int) -> EventoAgenda:
    evento = (
        db.query(EventoAgenda)
        .options(joinedload(EventoAgenda.cliente))
        .filter(EventoAgenda.id == evento_id)
        .first()
    )
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return evento


def crear_evento(db: Session, datos: EventoAgendaCreate) -> EventoAgendaOut:
    _validar_vinculos(db, datos.cliente_id, datos.prestamo_id, datos.tipo_cita_id)
    evento = EventoAgenda(**datos.model_dump())
    db.add(evento)
    db.commit()
    db.refresh(evento)
    return _out(evento)


def actualizar_evento(db: Session, evento_id: int, datos: EventoAgendaUpdate) -> EventoAgendaOut:
    evento = get_evento(db, evento_id)
    cambios = datos.model_dump(exclude_unset=True)
    nuevo_estado = cambios.get("estado")
    if nuevo_estado and nuevo_estado not in ESTADOS_EVENTO:
        raise HTTPException(status_code=400, detail="Estado de evento no válido")
    _validar_vinculos(
        db,
        cambios.get("cliente_id", evento.cliente_id),
        cambios.get("prestamo_id", evento.prestamo_id),
        cambios.get("tipo_cita_id", evento.tipo_cita_id),
    )
    for campo, valor in cambios.items():
        setattr(evento, campo, valor)
    db.commit()
    db.refresh(evento)
    return _out(evento)


def eliminar_evento(db: Session, evento_id: int) -> None:
    """Solo eventos operativos manuales; los de cuota se gestionan por estado."""
    evento = get_evento(db, evento_id)
    db.delete(evento)
    db.commit()


def cambiar_estado_evento(db: Session, evento_id: int, estado: str) -> EventoAgendaOut:
    """CA-R5-6: completar/cancelar sin eliminar el evento."""
    if estado not in ESTADOS_EVENTO:
        raise HTTPException(status_code=400, detail="Estado de evento no válido")
    evento = get_evento(db, evento_id)
    evento.estado = estado
    db.commit()
    db.refresh(evento)
    return _out(evento)


def get_tipos_cita(db: Session, estado: Optional[str] = None) -> list[TipoCita]:
    query = db.query(TipoCita)
    if estado:
        query = query.filter(TipoCita.estado == estado)
    return query.order_by(TipoCita.nombre.asc()).all()


def _get_tipo_cita(db: Session, tipo_cita_id: int) -> TipoCita:
    tipo = db.query(TipoCita).filter(TipoCita.id == tipo_cita_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de cita no encontrado")
    return tipo


def crear_tipo_cita(db: Session, datos: TipoCitaCreate) -> TipoCita:
    tipo = TipoCita(**datos.model_dump())
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    return tipo


def actualizar_tipo_cita(db: Session, tipo_cita_id: int, datos: TipoCitaUpdate) -> TipoCita:
    tipo = _get_tipo_cita(db, tipo_cita_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(tipo, campo, valor)
    db.commit()
    db.refresh(tipo)
    return tipo


def eliminar_tipo_cita(db: Session, tipo_cita_id: int) -> None:
    tipo = _get_tipo_cita(db, tipo_cita_id)
    en_uso = db.query(EventoAgenda).filter(EventoAgenda.tipo_cita_id == tipo_cita_id).count()
    if en_uso:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar: {en_uso} evento(s) usan este tipo de cita. Márcalo como inactivo.",
        )
    db.delete(tipo)
    db.commit()


def resumen_agenda(db: Session, fecha: Optional[date] = None, mes: Optional[str] = None) -> dict:
    """CA-R5-5: eventos del día y conteo total del mes."""
    fecha = fecha or date.today()
    mes = mes or fecha.strftime("%Y-%m")

    eventos_dia = (
        db.query(EventoAgenda)
        .options(joinedload(EventoAgenda.cliente))
        .filter(EventoAgenda.fecha == fecha)
        .order_by(EventoAgenda.hora_inicio.asc(), EventoAgenda.id.asc())
        .all()
    )

    anio, num_mes = (int(p) for p in mes.split("-"))
    from sqlalchemy import func as sa_func

    total_mes = (
        db.query(sa_func.count(EventoAgenda.id))
        .filter(
            sa_func.extract("year", EventoAgenda.fecha) == anio,
            sa_func.extract("month", EventoAgenda.fecha) == num_mes,
        )
        .scalar()
        or 0
    )

    return {
        "fecha": fecha,
        "mes": mes,
        "total_dia": len(eventos_dia),
        "total_mes": total_mes,
        "eventos_dia": [_out(e) for e in eventos_dia],
    }


def generar_eventos_cuota(db: Session, prestamo_id: int) -> dict:
    """CA-R5-4: crea un evento cuota_vence por cada cuota; idempotente por
    (prestamo_id, fecha, tipo) — repetir la llamada no duplica eventos."""
    prestamo = (
        db.query(Prestamo)
        .options(joinedload(Prestamo.cuotas), joinedload(Prestamo.cliente))
        .filter(Prestamo.id == prestamo_id)
        .first()
    )
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")

    cuotas: list[PrestamoCuota] = sorted(prestamo.cuotas, key=lambda c: c.numero_cuota)
    creados = 0
    for cuota in cuotas:
        if not cuota.fecha_vencimiento:
            continue
        existe = (
            db.query(EventoAgenda)
            .filter(
                EventoAgenda.prestamo_id == prestamo.id,
                EventoAgenda.tipo == "cuota_vence",
                EventoAgenda.fecha == cuota.fecha_vencimiento,
            )
            .first()
        )
        if existe:
            continue
        nombre = prestamo.cliente.nombre.split()[0] if prestamo.cliente else "cliente"
        db.add(
            EventoAgenda(
                tipo="cuota_vence",
                titulo=f"Vence cuota #{cuota.numero_cuota} - {nombre}",
                descripcion=f"Cuota #{cuota.numero_cuota} de ${cuota.valor_cuota:,.2f} del préstamo #{prestamo.id}",
                fecha=cuota.fecha_vencimiento,
                prestamo_id=prestamo.id,
                cliente_id=prestamo.cliente_id,
                estado="pendiente",
            )
        )
        creados += 1

    if creados:
        db.commit()

    return {"prestamo_id": prestamo.id, "creados": creados, "total_cuotas": len(cuotas)}
