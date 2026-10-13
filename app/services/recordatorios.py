"""Recordatorios masivos manuales de cuotas próximas a vencer y vencidas.

Reutiliza la consulta y el formato de la ruta /notificacion/proximos-vencimientos
para no duplicar lógica, y envía los mensajes a través de las plantillas
existentes (RF-063) y los canales de mensajería (RF-061/RF-062).

Tipos de destinatario:
  - proximos:  cuotas 'pendiente' que vencen entre hoy y hoy + dias
  - vencidos:  cuotas 'vencido' o 'parcial' con fecha anterior a hoy (mora)
"""

from datetime import date, timedelta
from urllib.parse import quote_plus

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import Cliente, Prestamo, PrestamoCuota
from app.schemas.notificacion import RecordatorioCuotaResponse
from app.services import plantillas as plantillas_service

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

TIPOS_VALIDOS = ("proximos", "vencidos")


def _consulta(db: Session, tipo: str, dias: int):
    """Devuelve (hoy, filas) con las cuotas que cumplen el criterio indicado."""
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail="Tipo de recordatorio inválido; use 'proximos' o 'vencidos'",
        )

    hoy = date.today()
    query = (
        db.query(PrestamoCuota, Prestamo, Cliente)
        .join(Prestamo, PrestamoCuota.prestamo_id == Prestamo.id)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
    )

    if tipo == "proximos":
        fecha_limite = hoy + timedelta(days=dias)
        query = query.filter(
            PrestamoCuota.estado == "pendiente",
            PrestamoCuota.fecha_vencimiento >= hoy,
            PrestamoCuota.fecha_vencimiento <= fecha_limite,
        )
    else:
        query = query.filter(
            PrestamoCuota.estado.in_(("vencido", "parcial")),
            PrestamoCuota.fecha_vencimiento < hoy,
        )

    filas = query.order_by(PrestamoCuota.fecha_vencimiento.asc()).all()
    return hoy, filas


def _referencia(cuota: PrestamoCuota, prestamo: Prestamo) -> str:
    return cuota.referencia_pago or f"REF-P{prestamo.id}C{cuota.numero_cuota}"


def _contexto(cuota: PrestamoCuota, prestamo: Prestamo, cliente: Cliente, hoy: date) -> dict:
    """Variables disponibles para las plantillas de recordatorio."""
    dias_para_vencer = (cuota.fecha_vencimiento - hoy).days
    dias_atraso = (hoy - cuota.fecha_vencimiento).days
    monto_fmt = f"{int(cuota.valor_cuota):,}".replace(",", ".")
    mora_fmt = f"{int(cuota.mora or 0):,}".replace(",", ".")
    fecha_str = f"{cuota.fecha_vencimiento.day} {MESES[cuota.fecha_vencimiento.month - 1]}"
    primer_nombre = cliente.nombre.split()[0].capitalize() if cliente.nombre else "Cliente"

    return {
        "nombre": primer_nombre,
        "cliente_nombre": cliente.nombre or "",
        "prestamo_id": prestamo.id,
        "cuota_id": cuota.id,
        "numero_cuota": cuota.numero_cuota,
        "monto": monto_fmt,
        "monto_valor": cuota.valor_cuota,
        "monto_mora": mora_fmt,
        "fecha": fecha_str,
        "fecha_vencimiento": cuota.fecha_vencimiento.isoformat(),
        "referencia": _referencia(cuota, prestamo),
        "dias_para_vencer": dias_para_vencer,
        "dias_atraso": dias_atraso,
        "telefono": cliente.telefono or "",
        "email": cliente.email or "",
    }


def proximos_vencimientos(db: Session, dias_anticipacion: int) -> list[RecordatorioCuotaResponse]:
    """Cuotas próximas a vencer con mensaje y enlace de WhatsApp (ruta compartida)."""
    hoy, filas = _consulta(db, "proximos", dias_anticipacion)
    resultado = []

    for cuota, prestamo, cliente in filas:
        contexto = _contexto(cuota, prestamo, cliente, hoy)
        mensaje = (
            f"Hola {contexto['nombre']}\n"
            f"Recuerda que se acerca la fecha de pago de tu cuota con Credifast 💸\n"
            f"👉Cuota {contexto['monto']}\n"
            f"📆 Fecha límite : {contexto['fecha']}\n\n"
            f"Puedes hacer el pago por transferencia o programar recogida"
        )

        telefono_limpio = "".join(filter(str.isdigit, cliente.telefono or ""))
        if len(telefono_limpio) == 10:
            telefono_limpio = f"57{telefono_limpio}"
        url_wa = (
            f"https://api.whatsapp.com/send?phone={telefono_limpio}&text={quote_plus(mensaje)}"
            if telefono_limpio else ""
        )

        resultado.append(
            RecordatorioCuotaResponse(
                cuota_id=cuota.id,
                prestamo_id=prestamo.id,
                cliente_nombre=cliente.nombre,
                cliente_telefono=cliente.telefono or "",
                numero_cuota=cuota.numero_cuota,
                monto=cuota.valor_cuota,
                fecha_vencimiento=cuota.fecha_vencimiento,
                dias_para_vencer=contexto["dias_para_vencer"],
                referencia_pago=contexto["referencia"],
                mensaje_whatsapp=mensaje,
                whatsapp_url=url_wa,
            )
        )

    return resultado


def destinatarios(db: Session, tipo: str, dias: int) -> list[dict]:
    """Lista de destinatarios del recordatorio antes de enviar (total y detalle)."""
    hoy, filas = _consulta(db, tipo, dias)
    salida = []

    for cuota, prestamo, cliente in filas:
        contexto = _contexto(cuota, prestamo, cliente, hoy)
        salida.append({
            "cuota_id": cuota.id,
            "prestamo_id": prestamo.id,
            "cliente_id": cliente.id,
            "cliente_nombre": cliente.nombre,
            "telefono": contexto["telefono"],
            "email": contexto["email"],
            "numero_cuota": cuota.numero_cuota,
            "monto": cuota.valor_cuota,
            "fecha_vencimiento": cuota.fecha_vencimiento,
            "dias": contexto["dias_para_vencer"] if tipo == "proximos" else contexto["dias_atraso"],
            "referencia": contexto["referencia"],
        })

    return salida


def _plantilla(db: Session, plantilla_id: int):
    plantilla = plantillas_service.get_plantilla(db, plantilla_id)
    if not plantilla.activa:
        raise HTTPException(status_code=400, detail="La plantilla está inactiva")
    return plantilla


def previsualizar(db: Session, plantilla_id: int, tipo: str, dias: int) -> dict:
    """Mensaje compuesto con el contexto del primer destinatario, sin enviar."""
    plantilla = _plantilla(db, plantilla_id)
    hoy, filas = _consulta(db, tipo, dias)
    contexto = _contexto(*filas[0], hoy) if filas else {}

    vista = plantillas_service.previsualizar(
        plantilla.clave, plantilla.canal, plantilla.cuerpo, plantilla.asunto, contexto
    )
    return {
        "plantilla": plantilla.nombre,
        "canal": plantilla.canal,
        "asunto": vista["asunto"],
        "cuerpo": vista["cuerpo"],
        "variables": vista["variables"],
        "destinatarios_total": len(filas),
    }


def enviar(db: Session, plantilla_id: int, tipo: str, dias: int) -> dict:
    """Envía el recordatorio a todos los destinatarios por el canal de la plantilla.

    Usa eventos_mensajeria.disparar para deduplicar por día y registrar cada
    resultado en envios_mensaje sin lanzar excepciones.
    """
    from app.services.eventos_mensajeria import disparar

    plantilla = _plantilla(db, plantilla_id)
    hoy, filas = _consulta(db, tipo, dias)
    conteo = {"destinatarios": len(filas), "enviados": 0, "omitidos": 0, "fallidos": 0}
    hoy_iso = date.today().isoformat()
    mapa_estado = {"enviado": "enviados", "omitido": "omitidos", "fallido": "fallidos"}

    for cuota, prestamo, cliente in filas:
        contexto = _contexto(cuota, prestamo, cliente, hoy)
        destino = contexto["email"] if plantilla.canal == "email" else contexto["telefono"]
        resultado = disparar(
            db,
            clave=plantilla.clave,
            canal=plantilla.canal,
            destinatario=destino,
            contexto=contexto,
            dedupe_clave=f"recordatorio:{tipo}:{cuota.id}:{hoy_iso}",
        )
        estado = resultado.get("estado", "fallido")
        conteo[mapa_estado.get(estado, "fallidos")] += 1

    return conteo
