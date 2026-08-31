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

    return total_enviados


def ejecutar_tareas_diarias():
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

        print(
            f"[{datetime.now()}] Scheduler ejecutado: "
            f"{len(moras)} moras procesadas, {notif_enviadas} notificaciones push enviadas."
        )
    except Exception as e:
        print(f"[{datetime.now()}] Error en el scheduler de tareas diarias: {e}")
    finally:
        db.close()


def iniciar_scheduler():
    scheduler.add_job(
        ejecutar_tareas_diarias,
        trigger="cron",
        hour=0,
        minute=0,
        id="tarea_diaria_sistema",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()