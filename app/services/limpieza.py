"""Limpieza de datos residuales según la retención configurada (Backoffice).

Política (parámetros en `configuracion_sistema`, sembrados por init_db):

- tokens                : se purgan expirados siempre y los revocados con
                          `tokens_retencion_dias` (historial de accesos).
- auditoria             : `auditoria_retencion_dias = 0` → NUNCA se elimina.
- errores_app           : resueltos/ignorados con `errores_retencion_dias`.
- metricas_api          : `metricas_retencion_dias`.
- idempotency_keys      : `idempotency_retencion_horas`.
- notificaciones        : solo leídas con `notificaciones_retencion_dias` (0 = off).
- envios_mensaje        : `envios_retencion_dias`.
- usuarios.reset_token* : tokens de recuperación vencidos se anulan.

Nunca se tocan tablas del dominio financiero ni registros abiertos.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.models import (
    Auditoria,
    EjecucionProceso,
    EnvioMensaje,
    ErroresApp,
    IdempotencyKey,
    MetricaApi,
    Notificacion,
    Token,
    Usuario,
)


def _parametro(db: Session, clave: str, default: int) -> int:
    try:
        from app.services.configuracion import resolver_parametro

        valor, _ = resolver_parametro(db, clave, str(default))
        return int(valor) if valor is not None else default
    except (TypeError, ValueError):
        return default


def ejecutar_limpieza(db: Session | None = None) -> str:
    """Ejecuta la limpieza completa. Devuelve un resumen legible."""
    from app.db.database import SessionLocal

    propio = db is None
    if propio:
        db = SessionLocal()

    resumen: dict[str, int] = {}
    try:
        ahora = datetime.utcnow()

        ret_tokens = _parametro(db, "tokens_retencion_dias", 30)
        # Tokens expirados: siempre se eliminan (inutilizables).
        resumen["tokens_expirados"] = (
            db.query(Token)
            .filter(Token.expires_at < ahora)
            .delete(synchronize_session=False)
        )
        # Revocados: se conservan como historial durante la retención.
        if ret_tokens > 0:
            corte = ahora - timedelta(days=ret_tokens)
            resumen["tokens_revocados"] = (
                db.query(Token)
                .filter(Token.activo == 0, Token.created_at < corte)
                .delete(synchronize_session=False)
            )

        ret_errores = _parametro(db, "errores_retencion_dias", 180)
        if ret_errores > 0:
            corte = ahora - timedelta(days=ret_errores)
            resumen["errores"] = (
                db.query(ErroresApp)
                .filter(
                    ErroresApp.estado.in_(("resuelto", "ignorado")),
                    ErroresApp.ultima_ocurrencia < corte,
                )
                .delete(synchronize_session=False)
            )

        ret_metricas = _parametro(db, "metricas_retencion_dias", 180)
        if ret_metricas > 0:
            corte = ahora - timedelta(days=ret_metricas)
            resumen["metricas"] = (
                db.query(MetricaApi)
                .filter(MetricaApi.fecha_hora < corte)
                .delete(synchronize_session=False)
            )

        ret_idem = _parametro(db, "idempotency_retencion_horas", 48)
        if ret_idem > 0:
            corte = ahora - timedelta(hours=ret_idem)
            resumen["idempotency"] = (
                db.query(IdempotencyKey)
                .filter(IdempotencyKey.created_at < corte)
                .delete(synchronize_session=False)
            )

        ret_notif = _parametro(db, "notificaciones_retencion_dias", 90)
        if ret_notif > 0:
            corte = ahora - timedelta(days=ret_notif)
            resumen["notificaciones"] = (
                db.query(Notificacion)
                .filter(Notificacion.leida == True, Notificacion.fecha < corte)  # noqa: E712
                .delete(synchronize_session=False)
            )

        ret_envios = _parametro(db, "envios_retencion_dias", 180)
        if ret_envios > 0:
            corte = ahora - timedelta(days=ret_envios)
            resumen["envios"] = (
                db.query(EnvioMensaje)
                .filter(EnvioMensaje.fecha < corte)
                .delete(synchronize_session=False)
            )

        # Tokens de recuperación vencidos: se anulan (no se almacena valor).
        resumen["reset_tokens"] = (
            db.query(Usuario)
            .filter(
                Usuario.reset_token_expires.isnot(None),
                Usuario.reset_token_expires < ahora,
            )
            .update(
                {"reset_token": None, "reset_token_expires": None},
                synchronize_session=False,
            )
        )

        # Auditoría: solo se elimina si la retención lo permite (0 = nunca).
        ret_auditoria = _parametro(db, "auditoria_retencion_dias", 0)
        if ret_auditoria > 0:
            corte = ahora - timedelta(days=ret_auditoria)
            resumen["auditoria"] = (
                db.query(Auditoria)
                .filter(Auditoria.fecha < corte)
                .delete(synchronize_session=False)
            )

        # Excluir la propia limpieza de la política de errores/métricas.
        db.query(EjecucionProceso).filter(
            EjecucionProceso.tarea == "limpieza_periodica",
            EjecucionProceso.estado.in_(("completado", "fallido")),
            EjecucionProceso.fin < ahora - timedelta(days=30),
        ).delete(synchronize_session=False)

        db.commit()
        return ", ".join(f"{k}={v}" for k, v in resumen.items() if v) or "sin datos por limpiar"
    finally:
        if propio:
            db.close()
