"""Servicio de WhatsApp Business: credenciales por usuario (Modo 2),
modo corporativo (Modo 1, variables de entorno), prueba de conexión,
envío individual desde fichas y envío masivo por segmentos.

Arquitectura flexible: el canal WhatsApp es el predeterminado; SMS sigue
soportado por `canales.py` y puede reactivarse sin tocar esta lógica.
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.context import aplicar_filtro_usuario, usuario_actual_id
from app.models.models import CredencialesWhatsApp, Cliente, EnvioMensaje, Usuario


# ---------------------------------------------------------------------------
# Credenciales (Modo 2: WhatsApp Business propio del prestamista)
# ---------------------------------------------------------------------------
def credenciales_de_usuario(db: Session, usuario_id: int) -> Optional[dict]:
    """Credenciales propias del prestamista si existen (dict para canales)."""
    fila = (
        db.query(CredencialesWhatsApp)
        .filter(CredencialesWhatsApp.usuario_id == usuario_id)
        .first()
    )
    if not fila or fila.estado_conexion == "invalidas":
        return None
    return {
        "access_token": fila.access_token,
        "phone_number_id": fila.phone_number_id,
        "business_account_id": fila.business_account_id or "",
        "api_key": fila.api_key or "",
    }


def obtener_credenciales(db: Session) -> CredencialesWhatsApp | None:
    """Credenciales del usuario autenticado (admin ve la suya)."""
    uid = usuario_actual_id.get()
    if uid is None:
        raise HTTPException(status_code=401, detail="Sin usuario autenticado")
    return (
        db.query(CredencialesWhatsApp)
        .filter(CredencialesWhatsApp.usuario_id == uid)
        .first()
    )


def guardar_credenciales(db: Session, datos) -> CredencialesWhatsApp:
    """Crea o actualiza las credenciales del usuario autenticado."""
    uid = usuario_actual_id.get()
    if uid is None:
        raise HTTPException(status_code=401, detail="Sin usuario autenticado")

    fila = (
        db.query(CredencialesWhatsApp)
        .filter(CredencialesWhatsApp.usuario_id == uid)
        .first()
    )
    if fila is None:
        fila = CredencialesWhatsApp(usuario_id=uid)
        db.add(fila)

    fila.proveedor = datos.proveedor
    fila.access_token = datos.access_token
    fila.phone_number_id = datos.phone_number_id
    fila.business_account_id = datos.business_account_id
    fila.api_key = datos.api_key
    fila.estado_conexion = "sin_probar"
    fila.ultima_validacion = None
    fila.detalle_validacion = None
    db.commit()
    db.refresh(fila)
    return fila


def eliminar_credenciales(db: Session) -> bool:
    uid = usuario_actual_id.get()
    if uid is None:
        return False
    fila = (
        db.query(CredencialesWhatsApp)
        .filter(CredencialesWhatsApp.usuario_id == uid)
        .first()
    )
    if fila:
        db.delete(fila)
        db.commit()
        return True
    return False


def _credenciales_para_probar(db: Session, datos=None) -> dict:
    """Credenciales a validar: las del cuerpo (sin guardar) o las guardadas."""
    if datos is not None and datos.access_token and datos.phone_number_id:
        return {
            "access_token": datos.access_token,
            "phone_number_id": datos.phone_number_id,
        }
    guardadas = obtener_credenciales(db)
    if not guardadas:
        raise HTTPException(
            status_code=400,
            detail="No hay credenciales guardadas ni datos para validar.",
        )
    return {
        "access_token": guardadas.access_token,
        "phone_number_id": guardadas.phone_number_id,
    }


def probar_conexion(db: Session, datos=None) -> dict:
    """Verificación en tiempo real contra la WhatsApp Cloud API de Meta.

    Consulta el perfil del Phone Number ID con el token dado. Devuelve
    detalle de error legible cuando falla y actualiza estado_conexion.
    """
    import httpx

    creds = _credenciales_para_probar(db, datos)
    url = (
        f"https://graph.facebook.com/v21.0/{creds['phone_number_id']}"
        "?fields=id,display_phone_number,verified_name,quality_rating"
    )
    ahora = datetime.utcnow()
    try:
        with httpx.Client(timeout=20) as cliente:
            respuesta = cliente.get(
                url, headers={"Authorization": f"Bearer {creds['access_token']}"}
            )
        if respuesta.status_code == 200:
            info = respuesta.json()
            resultado = {
                "ok": True,
                "estado": "conectado",
                "detalle": (
                    f"Número {info.get('display_phone_number', '?')} "
                    f"({info.get('verified_name', 'sin nombre')})"
                ),
                "info": info,
            }
        else:
            cuerpo = respuesta.json() if respuesta.status_code != 503 else {}
            error = (cuerpo.get("error") or {})
            mensaje = error.get("message") or f"HTTP {respuesta.status_code}"
            resultado = {
                "ok": False,
                "estado": "invalidas",
                "detalle": mensaje,
            }
    except Exception as exc:  # noqa: BLE001
        resultado = {"ok": False, "estado": "invalidas", "detalle": str(exc)[:250]}

    # Si se validó con datos sin guardar no actualiza el registro.
    fila = (
        db.query(CredencialesWhatsApp)
        .filter(CredencialesWhatsApp.usuario_id == usuario_actual_id.get())
        .first()
    )
    if fila and creds.get("access_token") == fila.access_token:
        fila.estado_conexion = resultado["estado"]
        fila.ultima_validacion = ahora
        fila.detalle_validacion = resultado["detalle"][:250]
        db.commit()

    return resultado


def _telefono_limpio(telefono: str) -> str:
    digitos = "".join(c for c in (telefono or "") if c.isdigit())
    if len(digitos) == 10:
        digitos = f"57{digitos}"
    return digitos


# ---------------------------------------------------------------------------
# Envío individual (ficha del cliente / ficha del préstamo)
# ---------------------------------------------------------------------------
def enviar_individual(
    db: Session,
    cliente_id: int,
    cuerpo: str,
    plantilla_id: int | None = None,
    documento: bytes | None = None,
    nombre_archivo: str | None = None,
) -> dict:
    """Envía un mensaje manual de WhatsApp a un cliente del usuario.

    Renderiza variables {{...}} si la plantilla viene dada. Valida
    aislamiento (solo clientes propios) y teléfono registrado.
    """
    from app.services.canales import enviar_whatsapp_directo
    from app.services.plantillas import renderizar, _contexto_extendido

    cliente = (
        aplicar_filtro_usuario(db.query(Cliente), Cliente)
        .filter(Cliente.id == cliente_id)
        .first()
    )
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    telefono = _telefono_limpio(cliente.telefono or "")
    if not telefono:
        raise HTTPException(
            status_code=400,
            detail="El cliente no tiene número telefónico registrado.",
        )

    uid = usuario_actual_id.get()
    contexto = _contexto_extendido(db, {
        "cliente_nombre": cliente.nombre or "",
        "cliente_documento": cliente.cedula or "",
        "cliente_telefono": cliente.telefono or "",
        "cliente_direccion": cliente.direccion or "",
    })
    mensaje = renderizar(cuerpo or "", contexto)

    resultado = enviar_whatsapp_directo(
        db,
        destinatario=telefono,
        cuerpo=mensaje,
        documento=documento,
        nombre_archivo=nombre_archivo,
        asunto="Mensaje manual",
        plantilla_id=plantilla_id,
        usuario_id=uid,
        cliente_id=cliente.id,
    )
    return {**resultado, "destinatario": telefono}


# ---------------------------------------------------------------------------
# Envío masivo (recordatorios por segmento)
# ---------------------------------------------------------------------------
def enviar_masivo(
    db: Session,
    plantilla_id: int,
    tipo: str = "proximos",
    dias: int = 3,
) -> dict:
    """Envía el recordatorio masivo por WhatsApp a todos los destinatarios
    del segmento (solo clientes con teléfono). Usa la deduplicación diaria
    y registra cada envío con trazabilidad completa. Nunca lanza.

    Límite por minuto: el envío es secuencial; el límite práctico se controla
    con el parámetro `whatsapp_max_por_minuto` cuando se programa por lotes.
    """
    from app.services import recordatorios as recordatorios_service

    plantilla = recordatorios_service._plantilla(db, plantilla_id)
    conteo = recordatorios_service.enviar(
        db, plantilla_id, tipo, dias
    )
    return {
        "plantilla": plantilla.nombre,
        "canal": plantilla.canal,
        **conteo,
    }


def historial_envios(
    db: Session,
    page: int = 1,
    limit: int = 20,
    canal: str | None = None,
    estado: str | None = None,
    cliente_id: int | None = None,
) -> list[dict]:
    """Historial de envíos con trazabilidad (aislado por usuario)."""
    query = aplicar_filtro_usuario(db.query(EnvioMensaje), EnvioMensaje)
    if canal:
        query = query.filter(EnvioMensaje.canal == canal)
    if estado:
        query = query.filter(EnvioMensaje.estado == estado)
    if cliente_id is not None:
        query = query.filter(EnvioMensaje.cliente_id == cliente_id)
    filas = (
        query.order_by(EnvioMensaje.fecha.desc())
        .offset((max(1, page) - 1) * limit)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "fecha": str(e.fecha),
            "canal": e.canal,
            "destinatario": e.destinatario,
            "cliente_id": e.cliente_id,
            "asunto": e.asunto,
            "plantilla_id": e.plantilla_id,
            "estado": e.estado,
            "motivo": e.motivo,
            "respuesta_proveedor": (e.respuesta_proveedor or "")[:200],
            "error_detalle": (e.error_detalle or "")[:200],
            "whatsapp_message_id": e.whatsapp_message_id,
        }
        for e in filas
    ]
