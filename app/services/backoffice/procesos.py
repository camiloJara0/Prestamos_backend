"""Monitoreo y administración de procesos (sobre APScheduler nativo).

No se duplica una cola: los trabajos SON los jobs de APScheduler y
`ejecuciones_proceso` guarda el historial. Reintentos y ejecuciones son
idempotentes mediante transiciones de estado condicionales.
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import EjecucionProceso
from app.utils.pagination import paginate


def _scheduler():
    from app.services.scheduler import scheduler

    return scheduler


def _tareas_administrables() -> dict:
    from app.services.scheduler import TAREAS_ADMINISTRABLES

    return TAREAS_ADMINISTRABLES


def listar_procesos(db: Session) -> list[dict]:
    """Jobs reales del scheduler + resumen de ejecuciones recientes."""
    scheduler = _scheduler()
    administrables = _tareas_administrables()

    # Último estado por tarea (portable: sin DISTINCT ON).
    ultimo_estado: dict = {}
    ultimas = (
        db.query(EjecucionProceso)
        .order_by(EjecucionProceso.fecha_solicitud.desc())
        .limit(100)
        .all()
    )
    for fila in ultimas:
        if fila.tarea not in ultimo_estado:
            ultimo_estado[fila.tarea] = fila.estado
    en_ejecucion = {
        tarea
        for (tarea,) in db.query(EjecucionProceso.tarea).filter(
            EjecucionProceso.estado.in_(("pendiente", "en_ejecucion"))
        )
    }

    try:
        jobs = scheduler.get_jobs()
    except Exception:  # noqa: BLE001 - scheduler sin iniciar
        jobs = []

    procesos = []
    for job in jobs:
        procesos.append(
            {
                "id": job.id,
                "descripcion": getattr(job, "name", None) or str(job.func),
                "trigger": str(job.trigger),
                "proxima_ejecucion": job.next_run_time,
                "estado": "activo" if job.next_run_time is not None else "pausado",
                "administrable": job.id in administrables,
                "en_ejecucion": job.id in en_ejecucion,
                "ultima_ejecucion": ultimo_estado.get(job.id),
            }
        )
    return procesos


def listar_ejecuciones(
    db: Session,
    page: int = 1,
    limit: int = 10,
    tarea: Optional[str] = None,
    estado: Optional[str] = None,
) -> dict:
    query = db.query(EjecucionProceso)
    if tarea:
        query = query.filter(EjecucionProceso.tarea == tarea)
    if estado:
        query = query.filter(EjecucionProceso.estado == estado)
    query = query.order_by(EjecucionProceso.fecha_solicitud.desc())
    return paginate(query, page=page, limit=limit)


def obtener_ejecucion(db: Session, ejecucion_id: int) -> EjecucionProceso:
    fila = (
        db.query(EjecucionProceso)
        .filter(EjecucionProceso.id == ejecucion_id)
        .first()
    )
    if not fila:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")
    return fila


def _registrar_auditoria(db: Session, admin_id, ip_address, user_agent, request_id, **kwargs):
    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        usuario_id=admin_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        resultado="ok",
        **kwargs,
    )


def ejecutar_tarea(
    db: Session,
    job_id: str,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Dispara una tarea administrable ahora (idempotente: 409 si ya corre)."""
    administrables = _tareas_administrables()
    if job_id not in administrables:
        raise HTTPException(
            status_code=400,
            detail="Proceso no administrable desde el Backoffice.",
        )

    ocupada = (
        db.query(EjecucionProceso)
        .filter(
            EjecucionProceso.tarea == job_id,
            EjecucionProceso.estado.in_(("pendiente", "en_ejecucion")),
        )
        .first()
    )
    if ocupada:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una ejecución pendiente o en curso de este proceso.",
        )

    fila = EjecucionProceso(
        tarea=job_id,
        origen="manual",
        estado="pendiente",
        solicitado_por=admin_id,
        intentos=1,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)

    from app.services.scheduler import _ejecutar_fila_manual

    try:
        _scheduler().add_job(
            _ejecutar_fila_manual,
            trigger="date",
            run_date=datetime.now(),
            args=[fila.id, job_id],
            id=f"manual:{fila.id}",
            replace_existing=False,
            misfire_grace_time=60,
        )
    except Exception as exc:  # noqa: BLE001 - reversión si no se pudo agendar
        fila.estado = "fallido"
        fila.error_mensaje = str(exc)[:2000]
        db.commit()
        raise HTTPException(
            status_code=500,
            detail="No se pudo agendar la ejecución del proceso.",
        )

    _registrar_auditoria(
        db,
        admin_id,
        ip_address,
        user_agent,
        request_id,
        tabla_afectada="ejecuciones_proceso",
        tipo_operacion="ejecucion_proceso",
        registro_id=fila.id,
        descripcion=f"Ejecución manual solicitada: {job_id}",
    )
    return {"ejecucion_id": fila.id, "estado": fila.estado}


def reintentar_ejecucion(
    db: Session,
    ejecucion_id: int,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Reintenta una ejecución fallida (transición condicional = idempotente)."""
    fila = obtener_ejecucion(db, ejecucion_id)
    if fila.estado != "fallido":
        raise HTTPException(
            status_code=409,
            detail="Solo se pueden reintentar ejecuciones fallidas.",
        )
    if fila.tarea not in _tareas_administrables():
        raise HTTPException(status_code=400, detail="Proceso no administrable.")

    # Actualización condicional: si otra petición ya lo reintentó, rowcount=0.
    actualizados = (
        db.query(EjecucionProceso)
        .filter(
            EjecucionProceso.id == ejecucion_id,
            EjecucionProceso.estado == "fallido",
        )
        .update(
            {
                "estado": "pendiente",
                "intentos": EjecucionProceso.intentos + 1,
                "error_mensaje": None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not actualizados:
        raise HTTPException(
            status_code=409,
            detail="La ejecución ya fue reintentada por otra operación.",
        )

    from app.services.scheduler import _ejecutar_fila_manual

    try:
        _scheduler().add_job(
            _ejecutar_fila_manual,
            trigger="date",
            run_date=datetime.now(),
            args=[fila.id, fila.tarea],
            id=f"reintento:{fila.id}:{datetime.now().timestamp()}",
            replace_existing=False,
            misfire_grace_time=60,
        )
    except Exception as exc:  # noqa: BLE001
        db.query(EjecucionProceso).filter(
            EjecucionProceso.id == ejecucion_id,
            EjecucionProceso.estado == "pendiente",
        ).update({"estado": "fallido", "error_mensaje": str(exc)[:2000]})
        db.commit()
        raise HTTPException(
            status_code=500,
            detail="No se pudo agendar el reintento.",
        )

    _registrar_auditoria(
        db,
        admin_id,
        ip_address,
        user_agent,
        request_id,
        tabla_afectada="ejecuciones_proceso",
        tipo_operacion="reintento_proceso",
        registro_id=fila.id,
        descripcion=f"Reintento solicitado: {fila.tarea} (intento #{fila.intentos + 1})",
    )
    return {"ejecucion_id": fila.id, "estado": "pendiente", "intentos": fila.intentos + 1}


def cancelar_tarea(
    db: Session,
    job_id: str,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Pausa la programación de un job (cancela futuras ejecuciones).

    Límite técnico: una ejecución ya en curso no se detiene de forma
    segura; solo se cancelan las pendientes de ejecutarse.
    """
    if job_id not in _tareas_administrables():
        raise HTTPException(status_code=400, detail="Proceso no administrable.")

    scheduler = _scheduler()
    try:
        scheduler.pause_job(job_id)
    except Exception:  # noqa: BLE001 - JobLookupError y similares
        raise HTTPException(status_code=404, detail="Proceso no encontrado en el scheduler.")

    _registrar_auditoria(
        db,
        admin_id,
        ip_address,
        user_agent,
        request_id,
        tabla_afectada="ejecuciones_proceso",
        tipo_operacion="cancelacion_proceso",
        descripcion=f"Programación pausada: {job_id}",
    )
    return {"id": job_id, "estado": "pausado"}


def conteos_ejecuciones(db: Session) -> dict:
    filas = (
        db.query(EjecucionProceso.estado, func.count(EjecucionProceso.id))
        .group_by(EjecucionProceso.estado)
        .all()
    )
    base = {
        "pendiente": 0,
        "en_ejecucion": 0,
        "completado": 0,
        "fallido": 0,
        "cancelado": 0,
    }
    for estado, conteo in filas:
        base[estado] = conteo
    return base
