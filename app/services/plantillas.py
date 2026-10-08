"""Plantillas de mensajes con variables reemplazables (RF-063).

Las plantillas se almacenan en base de datos para que el administrador las
edite sin desplegar código. El motor sustituye variables {{nombre_variable}}
por los valores del contexto.
"""

import re
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import EnvioMensaje, PlantillaMensaje

_VARIABLE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

PLANTILLAS_POR_DEFECTO = [
    {
        "clave": "recordatorio_vencimiento",
        "canal": "sms",
        "nombre": "Recordatorio de vencimiento",
        "asunto": "Recordatorio de pago",
        "cuerpo": (
            "Hola {{nombre}}, te recordamos que la cuota {{numero_cuota}} de ${{monto}} "
            "vence el {{fecha}}. Referencia de pago: {{referencia}}."
        ),
    },
    {
        "clave": "recordatorio_vencimiento_email",
        "canal": "email",
        "nombre": "Recordatorio de vencimiento (correo)",
        "asunto": "Próximo vencimiento de cuota - {{nombre}}",
        "cuerpo": (
            "Hola {{nombre}},\n\nTu cuota {{numero_cuota}} por ${{monto}} vence el {{fecha}}.\n"
            "Referencia de pago: {{referencia}}.\n\nGracias por su puntualidad."
        ),
    },
    {
        "clave": "prestamo_creado",
        "canal": "email",
        "nombre": "Confirmación de préstamo creado",
        "asunto": "Préstamo #{{prestamo_id}} registrado",
        "cuerpo": (
            "Hola {{nombre}},\n\nSe registró el préstamo #{{prestamo_id}} por ${{monto}} "
            "a {{numero_cuotas}} cuotas.\n\nSaludos."
        ),
    },
    {
        "clave": "password_cambiada",
        "canal": "email",
        "nombre": "Contraseña actualizada",
        "asunto": "Tu contraseña fue actualizada",
        "cuerpo": (
            "Hola {{nombre}},\n\nTu contraseña fue actualizada correctamente el {{fecha}}.\n"
            "Si no fuiste tú, contacta al administrador."
        ),
    },
    {
        "clave": "solicitud_decidida",
        "canal": "sms",
        "nombre": "Decisión de solicitud",
        "asunto": "Solicitud de préstamo",
        "cuerpo": (
            "Hola {{nombre}}, tu solicitud de préstamo por ${{monto}} fue {{estado}}. "
            "Motivo: {{motivo}}."
        ),
    },
]


def renderizar(texto: str, contexto: dict) -> str:
    """Sustituye las variables {{variable}} del texto por el contexto dado."""
    if not texto:
        return ""

    def _reemplazar(match: re.Match) -> str:
        clave = match.group(1)
        valor = contexto.get(clave)
        return "" if valor is None else str(valor)

    return _VARIABLE.sub(_reemplazar, texto)


def obtener_plantilla(db: Session, clave: str, canal: str) -> Optional[PlantillaMensaje]:
    return (
        db.query(PlantillaMensaje)
        .filter(PlantillaMensaje.clave == clave, PlantillaMensaje.canal == canal)
        .first()
    )


def _defecto(clave: str, canal: str) -> dict:
    for plantilla in PLANTILLAS_POR_DEFECTO:
        if plantilla["clave"] == clave and plantilla["canal"] == canal:
            return plantilla
    raise HTTPException(status_code=404, detail="Plantilla no encontrada")


def componer_mensaje(
    db: Session, clave: str, canal: str, contexto: dict
) -> tuple[str, str, Optional[PlantillaMensaje]]:
    """Compone asunto y cuerpo con la plantilla almacenada (o la de defecto)."""
    plantilla = obtener_plantilla(db, clave, canal)
    if plantilla and not plantilla.activa:
        raise HTTPException(status_code=400, detail=f"La plantilla '{clave}' está inactiva")
    if plantilla:
        asunto = renderizar(plantilla.asunto or "", contexto)
        cuerpo = renderizar(plantilla.cuerpo, contexto)
        return asunto, cuerpo, plantilla

    defecto = _defecto(clave, canal)
    return renderizar(defecto["asunto"] or "", contexto), renderizar(defecto["cuerpo"], contexto), None


def get_plantillas(db: Session, canal: str | None = None) -> list[PlantillaMensaje]:
    query = db.query(PlantillaMensaje).order_by(PlantillaMensaje.canal, PlantillaMensaje.clave)
    if canal:
        query = query.filter(PlantillaMensaje.canal == canal)
    return query.all()


def get_plantilla(db: Session, plantilla_id: int) -> PlantillaMensaje:
    plantilla = db.query(PlantillaMensaje).filter(PlantillaMensaje.id == plantilla_id).first()
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return plantilla


def crear_plantilla(db: Session, datos) -> PlantillaMensaje:
    existente = db.query(PlantillaMensaje).filter(PlantillaMensaje.clave == datos.clave).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe una plantilla con esa clave")
    plantilla = PlantillaMensaje(**datos.model_dump())
    db.add(plantilla)
    db.commit()
    db.refresh(plantilla)
    return plantilla


def actualizar_plantilla(db: Session, plantilla_id: int, datos) -> PlantillaMensaje:
    plantilla = get_plantilla(db, plantilla_id)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(plantilla, campo, valor)
    db.commit()
    db.refresh(plantilla)
    return plantilla


def eliminar_plantilla(db: Session, plantilla_id: int) -> None:
    plantilla = get_plantilla(db, plantilla_id)
    envios_recientes = (
        db.query(EnvioMensaje)
        .filter(EnvioMensaje.plantilla_id == plantilla_id, EnvioMensaje.estado == "enviado")
        .count()
    )
    if envios_recientes:
        raise HTTPException(
            status_code=400,
            detail="La plantilla tiene envíos registrados y no puede eliminarse. Desactívela en su lugar.",
        )
    db.delete(plantilla)
    db.commit()


def previsualizar(clave: str, canal: str, cuerpo: str, asunto: str | None, contexto: dict) -> dict:
    """Devuelve el mensaje compuesto sin enviar (vista previa para el administrador)."""
    return {
        "asunto": renderizar(asunto or "", contexto),
        "cuerpo": renderizar(cuerpo, contexto),
        "variables": sorted(_VARIABLE.findall(cuerpo or "")),
    }


def registrar_envio(
    db: Session,
    canal: str,
    destinatario: str,
    asunto: str | None,
    cuerpo: str,
    estado: str,
    motivo: str | None = None,
    plantilla_id: int | None = None,
) -> EnvioMensaje:
    registro = EnvioMensaje(
        canal=canal,
        destinatario=destinatario,
        asunto=asunto,
        cuerpo=cuerpo,
        estado=estado,
        motivo=motivo,
        plantilla_id=plantilla_id,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro
