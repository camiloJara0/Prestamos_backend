"""Dashboard global e infraestructura del Backoffice.

Todas las métricas provienen de fuentes reales: conteos sobre tablas,
agregados de `metricas_api`, sistema de archivos de los respaldos y
pings de servicios. No se devuelven valores simulados.
"""

import os
import shutil
import time
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.observabilidad import INICIO_PROCESO, _version_app
from app.models.models import (
    Auditoria,
    Cliente,
    EjecucionProceso,
    ErroresApp,
    MetricaApi,
    Token,
    Usuario,
)


def _cuenta(db: Session, modelo, *filtros) -> int:
    q = db.query(func.count(modelo.id))
    if filtros:
        q = q.filter(*filtros)
    return int(q.scalar() or 0)


def resumen_dashboard(db: Session) -> dict:
    ahora = datetime.utcnow()
    hoy00 = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    hace_7d = ahora - timedelta(days=7)

    total = _cuenta(db, Usuario)
    activos = _cuenta(db, Usuario, Usuario.estado == "activo")
    inactivos = _cuenta(db, Usuario, Usuario.estado == "inactivo")
    empresas = _cuenta(
        db, Usuario, Usuario.rol == "prestamista", Usuario.estado == "activo"
    )
    clientes = _cuenta(db, Cliente)
    errores_abiertos = _cuenta(db, ErroresApp, ErroresApp.estado == "abierto")
    errores_7d = int(
        db.query(func.coalesce(func.sum(ErroresApp.ocurrencias), 0))
        .filter(ErroresApp.ultima_ocurrencia >= hace_7d)
        .scalar()
        or 0
    )

    procesos_filas = (
        db.query(EjecucionProceso.estado, func.count(EjecucionProceso.id))
        .group_by(EjecucionProceso.estado)
        .all()
    )
    procesos = {e: 0 for e in ("pendiente", "en_ejecucion", "completado", "fallido", "cancelado")}
    for estado, conteo in procesos_filas:
        procesos[estado] = conteo

    # Último respaldo real: archivo más reciente del directorio.
    from app.services.backup import DIRECTORIO_RESPALDOS

    ultimo_respaldo = None
    if DIRECTORIO_RESPALDOS.exists():
        archivos = sorted(
            (p for p in DIRECTORIO_RESPALDOS.glob("loan_soft_*") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if archivos:
            ultimo_respaldo = datetime.fromtimestamp(archivos[0].stat().st_mtime).isoformat(
                sep=" ", timespec="seconds"
            )

    ultima_actividad = [
        {
            "id": a.id,
            "usuario_id": a.usuario_id,
            "tipo_operacion": a.tipo_operacion,
            "tabla_afectada": a.tabla_afectada,
            "descripcion": a.descripcion,
            "resultado": a.resultado,
            "fecha": a.fecha.isoformat(sep=" ", timespec="seconds") if a.fecha else None,
        }
        for a in db.query(Auditoria).order_by(Auditoria.fecha.desc()).limit(10).all()
    ]

    latencia = (
        db.query(
            func.coalesce(func.sum(MetricaApi.latencia_ms_suma), 0.0),
            func.coalesce(func.sum(MetricaApi.conteo), 0),
        )
        .filter(MetricaApi.fecha_hora >= hoy00)
        .one()
    )
    latencia_promedio = (
        Decimal(str(latencia[0])) / Decimal(str(latencia[1])) 
        if latencia[1] 
        else None
    )
    peticiones_hoy = int(latencia[1] or 0)

    return {
        "usuarios_total": total,
        "usuarios_activos": activos,
        "usuarios_inactivos": inactivos,
        "empresas": empresas,
        "clientes": clientes,
        "errores_abiertos": errores_abiertos,
        "errores_7d": errores_7d,
        "procesos": procesos,
        "ultimo_respaldo": ultimo_respaldo,
        "ultima_actividad": ultima_actividad,
        "uptime_segundos": round(time.time() - INICIO_PROCESO, 1),
        "latencia_promedio_ms": round(latencia_promedio, 2) if latencia_promedio else None,
        "peticiones_hoy": peticiones_hoy,
        "version": _version_app(),
    }


def serie_metricas(
    db: Session,
    metrica: str,
    desde: datetime,
    hasta: datetime,
    granularidad: str = "dia",
) -> dict:
    """Serie histórica desde `metricas_api` (agregados horarios reales)."""
    filtros = [MetricaApi.fecha_hora >= desde, MetricaApi.fecha_hora <= hasta]
    es_errores = metrica in ("errores", "errores_5xx")
    if es_errores:
        filtros.append(MetricaApi.status_code >= 500)

    columna_valor = func.sum(MetricaApi.conteo)
    if granularidad == "hora":
        grupo = MetricaApi.fecha_hora
    else:
        grupo = func.date(MetricaApi.fecha_hora)
        granularidad = "dia"

    filas = (
        db.query(grupo, columna_valor)
        .filter(*filtros)
        .group_by(grupo)
        .order_by(grupo)
        .all()
    )
    puntos = [
        {"fecha": str(fecha), "valor": float(valor or 0)} for fecha, valor in filas
    ]
    return {"metrica": metrica, "granularidad": granularidad, "puntos": puntos}


def infraestructura(db: Session) -> dict:
    from app.services.backup import DIRECTORIO_RESPALDOS, RETENCION_RESPALDOS
    from app.services.scheduler import scheduler

    intento = None
    try:
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        intento = "ok"
    except Exception:  # noqa: BLE001
        intento = "degradado"

    try:
        disco = shutil.disk_usage(str(DIRECTORIO_RESPALDOS))
        disco_total, disco_libre = disco.total, disco.free
    except OSError:
        disco_total, disco_libre = 0, 0

    db_bytes = None
    try:
        from app.db.database import DATABASE_URL

        if DATABASE_URL.startswith("sqlite"):
            ruta = DATABASE_URL.split("///", 1)[-1]
            if os.path.exists(ruta):
                db_bytes = os.path.getsize(ruta)
    except Exception:  # noqa: BLE001
        db_bytes = None

    respaldos = 0
    if DIRECTORIO_RESPALDOS.exists():
        respaldos = sum(
            1 for p in DIRECTORIO_RESPALDOS.glob("loan_soft_*") if p.is_file()
        )

    servicios = [
        {
            "nombre": "base_datos",
            "estado": intento,
            "detalle": "SELECT 1 OK" if intento == "ok" else "sin respuesta",
        },
        {
            "nombre": "scheduler",
            "estado": "ok" if scheduler.running else "degradado",
            "detalle": "APScheduler activo" if scheduler.running else "detenido",
        },
        {
            "nombre": "smtp",
            "estado": "ok" if os.getenv("SMTP_HOST") else "desconocido",
            "detalle": "configurado" if os.getenv("SMTP_HOST") else "SMTP no configurado",
        },
        {
            "nombre": "push",
            "estado": "ok" if os.getenv("VAPID_PUBLIC_KEY") else "desconocido",
            "detalle": "VAPID configurado" if os.getenv("VAPID_PUBLIC_KEY") else "sin claves VAPID",
        },
        {
            "nombre": "mensajeria",
            "estado": "ok",
            "detalle": (
                f"SMS={os.getenv('SMS_PROVIDER', 'sin definir')} "
                f"WHATSAPP={os.getenv('WHATSAPP_PROVIDER', 'sin definir')}"
            ),
        },
    ]

    return {
        "version": _version_app(),
        "uptime_segundos": round(time.time() - INICIO_PROCESO, 1),
        "disco_total_bytes": disco_total,
        "disco_libre_bytes": disco_libre,
        "base_datos_bytes": db_bytes,
        "respaldos_directorio": str(DIRECTORIO_RESPALDOS),
        "respaldos_cantidad": respaldos,
        "servicios": servicios,
        "retencion": RETENCION_RESPALDOS,
    }
