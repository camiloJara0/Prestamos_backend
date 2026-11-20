from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from app.db.database import SessionLocal
from app.models.models import Cliente, Prestamo, PrestamoCuota, Usuario
from app.services.mora import procesar_moras
from app.services.push import enviar_notificacion_push

scheduler = BackgroundScheduler()


def enviar_recordatorios_vencimiento(db):
    """
    Busca cuotas que vencen en 3 días y en 1 día, y envía notificaciones push
    a los administradores (o usuarios registrados del sistema).
    """
    hoy = date.today()
    rangos = [
        (hoy + timedelta(days=3), "en 3 días"),
        (hoy + timedelta(days=1), "mañana"),
    ]
    rangos.append((hoy, "hoy"))  # el mismo día del vencimiento

    # Obtener usuarios admins para enviarles las alertas de vencimientos
    admins = db.query(Usuario).filter(Usuario.rol == "admin", Usuario.estado == "activo").all()
    if not admins:
        return 0

    total_enviados = 0

    for fecha_target, texto_tiempo in rangos:
        cuotas = (
            db.query(PrestamoCuota)
            .filter(
                PrestamoCuota.estado == "pendiente",
                PrestamoCuota.fecha_vencimiento == fecha_target,
            )
            .all()
        )

        for cuota in cuotas:
            prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
            cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first() if prestamo else None

            nombre_cliente = cliente.nombre if cliente else "Cliente"
            mensaje = f"La cuota #{cuota.numero_cuota} de {nombre_cliente} por ${cuota.valor_cuota:,.0f} vence {texto_tiempo}."

            # Notificar a los administradores
            for admin in admins:
                res = enviar_notificacion_push(
                    db=db,
                    usuario_id=admin.id,
                    titulo="Recordatorio de Vencimiento",
                    mensaje=mensaje,
                    url=f"/prestamos/{cuota.prestamo_id}" if prestamo else "/",
                )
                total_enviados += res.get("enviados", 0)
                _correo_recordatorio(db, admin, cuota, prestamo, cliente, texto_tiempo)

            # Canal principal: aviso por WhatsApp al cliente registrado
            if cliente and cliente.telefono:
                _whatsapp_recordatorio(db, cliente, cuota, texto_tiempo,
                                       clave="recordatorio_vencimiento")

    # Cuotas vencidas DENTRO del período de gracia: aviso de pago pendiente
    gracia = _dias_gracia(db)
    if gracia > 0:
        vencidas_recientes = (
            db.query(PrestamoCuota)
            .filter(
                PrestamoCuota.estado.in_(("vencido", "parcial")),
                PrestamoCuota.fecha_vencimiento < hoy,
                PrestamoCuota.fecha_vencimiento >= hoy - timedelta(days=gracia),
            )
            .all()
        )
        for cuota in vencidas_recientes:
            prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
            cliente = (
                db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first()
                if prestamo else None
            )
            if cliente and cliente.telefono:
                _whatsapp_recordatorio(
                    db, cliente, cuota,
                    f"{(hoy - cuota.fecha_vencimiento).days} día(s) de atraso",
                    clave="recordatorio_gracia",
                )

    return total_enviados


def _correo_recordatorio(db, admin, cuota, prestamo, cliente, texto_tiempo):
    """RF-061: recordatorio de pago por correo al usuario responsable."""
    try:
        from app.services.canales import enviar_por_canal

        enviar_por_canal(
            db,
            canal="email",
            destinatario=admin.email,
            clave="recordatorio_vencimiento_email",
            contexto={
                "nombre": (cliente.nombre.split()[0] if cliente and cliente.nombre else "cliente"),
                "numero_cuota": cuota.numero_cuota,
                "monto": f"{cuota.valor_cuota:,.0f}",
                "fecha": f"{cuota.fecha_vencimiento} ({texto_tiempo})",
                "referencia": cuota.referencia_pago or f"REF-P{cuota.prestamo_id}C{cuota.numero_cuota}",
            },
        )
    except Exception as exc:  # noqa: BLE001 - el fallo de correo no revierte la tarea
        print(f"[SCHEDULER] Error en correo de recordatorio: {exc}")


def _dias_gracia(db):
    try:
        from app.services.configuracion import resolver_parametro

        valor, _ = resolver_parametro(db, "dias_gracia_mora", "3")
        return max(0, int(valor or 3))
    except (TypeError, ValueError):
        return 3


def _whatsapp_recordatorio(db, cliente, cuota, texto_tiempo, clave="recordatorio_vencimiento"):
    """Canal principal: aviso por WhatsApp al cliente; sin proveedor se omite
    y queda registrado. Flexible: cambiar `canal` reactiva el SMS."""
    try:
        from app.services.canales import enviar_por_canal
        from app.services.configuracion import (
            obtener_nombre_empresa,
            obtener_telefono_empresa,
        )

        enviar_por_canal(
            db,
            canal="whatsapp",
            destinatario=cliente.telefono,
            clave=clave,
            contexto={
                "nombre": cliente.nombre.split()[0] if cliente.nombre else "cliente",
                "cliente_nombre": cliente.nombre or "",
                "cliente_documento": cliente.cedula or "",
                "cliente_telefono": cliente.telefono or "",
                "cliente_direccion": cliente.direccion or "",
                "prestamo_id": cuota.prestamo_id,
                "cuota_numero": cuota.numero_cuota,
                "cuota_valor": f"${cuota.valor_cuota:,.0f}",
                "cuota_fecha_vencimiento": str(cuota.fecha_vencimiento),
                "monto": f"${cuota.valor_cuota:,.0f}",
                "monto_mora": f"${cuota.mora or 0:,.0f}",
                "dias_atraso": texto_tiempo if isinstance(texto_tiempo, int) else texto_tiempo,
                "fecha": f"{cuota.fecha_vencimiento} ({texto_tiempo})",
                "referencia": cuota.referencia_pago or f"REF-P{cuota.prestamo_id}C{cuota.numero_cuota}",
                "empresa_nombre": obtener_nombre_empresa(db),
                "empresa_telefono": obtener_telefono_empresa(db),
            },
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[SCHEDULER] Error en WhatsApp de recordatorio: {exc}")


def ejecutar_tareas_diarias() -> str:
    """
    Tarea programada que ejecuta el procesamiento de moras
    y el envío de recordatorios Web Push.
    """
    db = SessionLocal()
    try:
        # 1. Procesar Moras
        moras = procesar_moras(db)

        # 2. Enviar Recordatorios Web Push
        notif_enviadas = enviar_recordatorios_vencimiento(db)

        resumen = (
            f"{len(moras)} moras procesadas, "
            f"{notif_enviadas} notificaciones push enviadas."
        )
        print(f"[{datetime.now()}] Scheduler ejecutado: {resumen}")
        return resumen
    except Exception as e:
        print(f"[{datetime.now()}] Error en el scheduler de tareas diarias: {e}")
        raise
    finally:
        db.close()


def ejecutar_respaldo_diario() -> str:
    """RF-075: respaldo automático diario con retención aplicada."""
    from app.services.backup import crear_respaldo

    destino = crear_respaldo()
    resumen = f"Respaldo creado: {destino.name}"
    print(f"[{datetime.now()}] {resumen}")
    return resumen


def ejecutar_limpieza_periodica() -> str:
    """Limpieza de datos residuales según la retención configurada (Backoffice)."""
    from app.services.limpieza import ejecutar_limpieza

    resumen = ejecutar_limpieza()
    print(f"[{datetime.now()}] Limpieza periódica: {resumen}")
    return resumen


def ejecutar_flush_metricas() -> str:
    """Vuelca el buffer de métricas API a la tabla de agregados."""
    from app.core.observabilidad import volcar_metricas

    db = SessionLocal()
    try:
        claves = volcar_metricas(db)
        return f"{claves} claves volcadas"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Registro de ejecuciones en `ejecuciones_proceso` (historial del Backoffice)
# ---------------------------------------------------------------------------
TAREAS_ADMINISTRABLES: dict = {
    "tarea_diaria_sistema": ejecutar_tareas_diarias,
    "respaldo_diario_bd": ejecutar_respaldo_diario,
    "limpieza_periodica": ejecutar_limpieza_periodica,
}


def _ejecutar_y_registrar(
    tarea: str,
    origen: str,
    fn,
    solicitado_por: int | None = None,
    fila_id: int | None = None,
    intentos: int = 1,
) -> str:
    """Ejecuta `fn` dejando trazabilidad en `ejecuciones_proceso`.

    Si `fila_id` viene dado se reutiliza la fila (reintento/manual ya
    creada); si no, se crea una nueva. El estado transita a
    `en_ejecucion` y luego a `completado`/`fallido`.
    """
    from app.models.models import EjecucionProceso

    db = SessionLocal()
    try:
        if fila_id is not None:
            fila = db.query(EjecucionProceso).filter(EjecucionProceso.id == fila_id).first()
            if fila is None:
                return f"Ejecución {fila_id} no encontrada"
        else:
            fila = EjecucionProceso(
                tarea=tarea,
                origen=origen,
                estado="pendiente",
                solicitado_por=solicitado_por,
                intentos=intentos,
            )
            db.add(fila)
            db.commit()

        fila.estado = "en_ejecucion"
        fila.inicio = datetime.utcnow()
        if fila_id is None:
            fila.intentos = intentos
        db.commit()

        try:
            resultado = fn()
            fila.estado = "completado"
            fila.fin = datetime.utcnow()
            fila.duracion_ms = int((fila.fin - fila.inicio).total_seconds() * 1000)
            fila.resultado = str(resultado)[:2000] if resultado is not None else None
            fila.error_mensaje = None
        except Exception as exc:  # noqa: BLE001 - el historial registra el fallo
            fila.estado = "fallido"
            fila.fin = datetime.utcnow()
            if fila.inicio:
                fila.duracion_ms = int((fila.fin - fila.inicio).total_seconds() * 1000)
            fila.error_mensaje = str(exc)[:2000]
        db.commit()
        return fila.estado
    finally:
        db.close()


def _envolver_programada(tarea: str, fn):
    def wrapper():
        return _ejecutar_y_registrar(tarea, "programada", fn)

    return wrapper


def _ejecutar_fila_manual(fila_id: int, tarea: str):
    """Punto de entrada de ejecuciones manuales (agendadas por el Backoffice)."""
    fn = TAREAS_ADMINISTRABLES.get(tarea)
    if fn is None:
        from app.models.models import EjecucionProceso

        db = SessionLocal()
        try:
            fila = (
                db.query(EjecucionProceso)
                .filter(EjecucionProceso.id == fila_id)
                .first()
            )
            if fila:
                fila.estado = "fallido"
                fila.error_mensaje = f"Tarea '{tarea}' no disponible"
                db.commit()
        finally:
            db.close()
        return
    return _ejecutar_y_registrar(tarea, "manual", fn, fila_id=fila_id)


def programar_campana(
    campana_id: int,
    hora=None,
    frecuencia: str = "diario",
    dia_semana: int | None = None,
    dia_mes: int | None = None,
    activo: bool = True,
) -> None:
    """Registra/actualiza (o retira) el job cron de una campaña (Fase 2).

    Import perezoso de campanas para evitar importación circular.
    """
    from functools import partial

    from app.services.campanas import ejecutar_campana_job

    job_id = f"campana_{campana_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:  # noqa: BLE001 - el job aún no existía
        pass

    if not activo or hora is None:
        return

    kwargs = {}
    if frecuencia == "semanal" and dia_semana is not None:
        kwargs["day_of_week"] = dia_semana
    elif frecuencia == "mensual" and dia_mes is not None:
        kwargs["day"] = dia_mes

    scheduler.add_job(
        _envolver_programada(
            f"campana_{campana_id}",
            partial(ejecutar_campana_job, campana_id),
        ),
        trigger="cron",
        hour=hora.hour,
        minute=hora.minute,
        id=job_id,
        replace_existing=True,
        misfire_grace_time=3600,
        **kwargs,
    )


def _programar_campanas_activas() -> None:
    """Registra los jobs de todas las campañas activas al arrancar."""
    from app.models.models import CampanaMensaje

    db = SessionLocal()
    try:
        activas = (
            db.query(CampanaMensaje).filter(CampanaMensaje.estado == "activo").all()
        )
        for campana in activas:
            try:
                programar_campana(
                    campana_id=campana.id,
                    hora=campana.hora_ejecucion,
                    frecuencia=campana.frecuencia,
                    dia_semana=campana.dia_semana,
                    dia_mes=campana.dia_mes,
                    activo=True,
                )
            except Exception as exc:  # noqa: BLE001 - una campaña rota no tumba el scheduler
                print(f"[SCHEDULER] Error programando campaña {campana.id}: {exc}")
        print(f"[SCHEDULER] {len(activas)} campañas activas programadas")
    finally:
        db.close()


def iniciar_scheduler():
    scheduler.add_job(
        _envolver_programada("tarea_diaria_sistema", ejecutar_tareas_diarias),
        trigger="cron",
        hour=0,
        minute=0,
        id="tarea_diaria_sistema",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _envolver_programada("respaldo_diario_bd", ejecutar_respaldo_diario),
        trigger="cron",
        hour=0,
        minute=30,
        id="respaldo_diario_bd",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _envolver_programada("limpieza_periodica", ejecutar_limpieza_periodica),
        trigger="cron",
        hour=3,
        minute=0,
        id="limpieza_periodica",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Campañas de mensajes automáticas del usuario (Fase 2)
    _programar_campanas_activas()
    # Infraestructura: vuelco de métricas (no genera filas de historial).
    scheduler.add_job(
        ejecutar_flush_metricas,
        trigger="interval",
        seconds=60,
        id="flush_metricas",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()