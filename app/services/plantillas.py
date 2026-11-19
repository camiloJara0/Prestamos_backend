"""Plantillas de mensajes con variables reemplazables (RF-063).

Las plantillas se almacenan en base de datos para que el administrador las
edite sin desplegar código. El motor sustituye variables {{nombre_variable}}
por los valores del contexto.
"""

import re
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.context import aplicar_filtro_usuario, usuario_actual_id
from app.models.models import EnvioMensaje, PlantillaMensaje

_VARIABLE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# ---------------------------------------------------------------------------
# Canal principal: WHATSAPP. Las plantillas base de SMS se retiran de esta
# lista (el canal SMS sigue soportado por la arquitectura: basta volver a
# añadirlas aquí, o reactivar las desactivadas por la migración, para
# rehabilitar SMS en futuras versiones sin tocar la lógica).
# ---------------------------------------------------------------------------
PLANTILLAS_POR_DEFECTO = [
    {
        "clave": "recordatorio_vencimiento",
        "canal": "whatsapp",
        "nombre": "Recordatorio de vencimiento",
        "asunto": "Recordatorio de pago",
        "cuerpo": (
            "Hola {{cliente_nombre}} 👋\n\n"
            "Te recordamos que tu cuota {{cuota_numero}} de {{empresa_nombre}} vence el "
            "{{cuota_fecha_vencimiento}}.\n\n"
            "💰 Valor: {{cuota_valor}}\n"
            "📌 Referencia: {{referencia}}\n\n"
            "Gracias por tu puntualidad."
        ),
    },
    {
        "clave": "recordatorio_gracia",
        "canal": "whatsapp",
        "nombre": "Recordatorio dentro del período de gracia",
        "asunto": "Pago pendiente",
        "cuerpo": (
            "Hola {{cliente_nombre}} 👋\n\n"
            "Tu cuota {{cuota_numero}} venció el {{cuota_fecha_vencimiento}} y aún "
            "estás dentro del período de gracia ({{dias_atraso}} día(s) de atraso).\n\n"
            "💰 Valor pendiente: {{cuota_valor}}\n"
            "📌 Referencia: {{referencia}}\n\n"
            "Escríbenos para ponerte al día y evitar cargos por mora."
        ),
    },
    {
        "clave": "prestamo_creado",
        "canal": "whatsapp",
        "nombre": "Resumen inicial del préstamo",
        "asunto": "Préstamo registrado",
        "cuerpo": (
            "Hola {{cliente_nombre}} 🎉\n\n"
            "Tu préstamo #{{prestamo_id}} con {{empresa_nombre}} quedó registrado.\n\n"
            "💵 Monto: {{prestamo_monto}}\n"
            "📅 Cuotas: {{prestamo_cuotas}}\n"
            "🗓️ Primera cuota: {{cuota_fecha_vencimiento}}\n\n"
            "Cualquier duda, responde este mensaje."
        ),
    },
    {
        "clave": "pago_confirmado",
        "canal": "whatsapp",
        "nombre": "Confirmación de pago recibido",
        "asunto": "Pago recibido",
        "cuerpo": (
            "Hola {{cliente_nombre}}, recibimos tu pago ✅\n\n"
            "💰 Valor: {{monto}}\n"
            "🧾 Cuota: {{cuota_numero}}\n"
            "📌 Recibo: {{referencia}}\n\n"
            "Gracias por tu puntualidad. — {{empresa_nombre}}"
        ),
    },
    {
        "clave": "mora_aviso",
        "canal": "whatsapp",
        "nombre": "Aviso de mora",
        "asunto": "Aviso de mora",
        "cuerpo": (
            "Hola {{cliente_nombre}}, la cuota {{cuota_numero}} acumula "
            "{{monto_mora}} de mora por {{dias_atraso}} día(s) de atraso.\n\n"
            "📌 Referencia: {{referencia}}\n"
            "Contáctanos para ponerte al día. — {{empresa_nombre}}"
        ),
    },
    {
        "clave": "cliente_bienvenida",
        "canal": "whatsapp",
        "nombre": "Bienvenida de nuevo cliente",
        "asunto": "Bienvenido",
        "cuerpo": (
            "Hola {{cliente_nombre}}, bienvenido(a) a {{empresa_nombre}} 🤝\n\n"
            "Tu registro quedó completo. Estamos listos para ayudarte con tu préstamo."
        ),
    },
    {
        "clave": "solicitud_decidida",
        "canal": "whatsapp",
        "nombre": "Decisión de solicitud",
        "asunto": "Solicitud de préstamo",
        "cuerpo": (
            "Hola {{cliente_nombre}}, tu solicitud de préstamo por {{monto}} fue "
            "{{estado}}. Motivo: {{motivo}}. — {{empresa_nombre}}"
        ),
    },
    {
        "clave": "recordatorio_vencimiento_email",
        "canal": "email",
        "nombre": "Recordatorio de vencimiento (correo)",
        "asunto": "Próximo vencimiento de cuota - {{cliente_nombre}}",
        "cuerpo": (
            "Hola {{cliente_nombre}},\n\nTu cuota {{cuota_numero}} por {{cuota_valor}} "
            "vence el {{cuota_fecha_vencimiento}}.\n"
            "Referencia de pago: {{referencia}}.\n\nGracias por su puntualidad."
        ),
    },
    {
        "clave": "password_cambiada",
        "canal": "email",
        "nombre": "Contraseña actualizada",
        "asunto": "Tu contraseña fue actualizada",
        "cuerpo": (
            "Hola {{cliente_nombre}},\n\nTu contraseña fue actualizada correctamente el {{fecha}}.\n"
            "Si no fuiste tú, contacta al administrador."
        ),
    },
]

# Claves base de SMS retiradas del conjunto predeterminado (arquitectura
# flexible: pueden volver a habilitarse restaurando estas entradas).
PLANTILLAS_SMS_RETIRADAS = ("recordatorio_vencimiento", "pago_confirmado", "mora_aviso",
                            "cliente_bienvenida", "solicitud_decidida")

# ---------------------------------------------------------------------------
# Catálogo de variables dinámicas para el editor de plantillas.
# Cada entrada: (variable, descripción, ejemplo renderizado).
# ---------------------------------------------------------------------------
CATALOGO_VARIABLES: list[dict] = [
    {
        "categoria": "Cliente",
        "variables": [
            {"variable": "cliente_nombre", "descripcion": "Nombre completo del cliente", "ejemplo": "María Gómez"},
            {"variable": "cliente_documento", "descripcion": "Cédula del cliente", "ejemplo": "1.020.334.556"},
            {"variable": "cliente_telefono", "descripcion": "Teléfono del cliente", "ejemplo": "3001234567"},
            {"variable": "cliente_direccion", "descripcion": "Dirección del cliente", "ejemplo": "Cra 45 #12-30, Medellín"},
        ],
    },
    {
        "categoria": "Préstamo",
        "variables": [
            {"variable": "prestamo_id", "descripcion": "Identificador del préstamo", "ejemplo": "12"},
            {"variable": "prestamo_monto", "descripcion": "Capital prestado", "ejemplo": "$500.000"},
            {"variable": "prestamo_saldo", "descripcion": "Saldo pendiente del préstamo", "ejemplo": "$350.000"},
            {"variable": "prestamo_fecha_inicio", "descripcion": "Fecha de inicio del préstamo", "ejemplo": "10/05/2026"},
            {"variable": "prestamo_cuotas", "descripcion": "Número total de cuotas", "ejemplo": "10"},
        ],
    },
    {
        "categoria": "Cuota",
        "variables": [
            {"variable": "cuota_numero", "descripcion": "Número de la cuota", "ejemplo": "3"},
            {"variable": "cuota_valor", "descripcion": "Valor de la cuota", "ejemplo": "$62.000"},
            {"variable": "cuota_fecha_vencimiento", "descripcion": "Fecha de vencimiento de la cuota", "ejemplo": "15/05/2026"},
            {"variable": "cuota_saldo", "descripcion": "Saldo pendiente de la cuota", "ejemplo": "$25.000"},
            {"variable": "monto_mora", "descripcion": "Mora acumulada de la cuota", "ejemplo": "$4.500"},
            {"variable": "referencia", "descripcion": "Referencia de pago de la cuota", "ejemplo": "REF-P12C3"},
        ],
    },
    {
        "categoria": "Empresa",
        "variables": [
            {"variable": "empresa_nombre", "descripcion": "Nombre de la empresa (configuración)", "ejemplo": "Presta YA"},
            {"variable": "empresa_telefono", "descripcion": "Teléfono de la empresa (configuración)", "ejemplo": "3007654321"},
        ],
    },
    {
        "categoria": "Otros",
        "variables": [
            {"variable": "nombre", "descripcion": "Primer nombre del cliente (compatibilidad)", "ejemplo": "María"},
            {"variable": "monto", "descripcion": "Monto del evento (pago o cuota)", "ejemplo": "$62.000"},
            {"variable": "fecha", "descripcion": "Fecha corta legible del vencimiento", "ejemplo": "15 mayo"},
            {"variable": "dias_para_vencer", "descripcion": "Días que faltan para el vencimiento", "ejemplo": "5"},
            {"variable": "dias_atraso", "descripcion": "Días de atraso de la cuota", "ejemplo": "2"},
            {"variable": "estado", "descripcion": "Estado de una decisión (aprobada/rechazada)", "ejemplo": "aprobada"},
            {"variable": "motivo", "descripcion": "Motivo de una decisión o evento", "ejemplo": "Ingresos verificados"},
        ],
    },
]

# Mapa plano variable → ejemplo (para validación y ejemplos de render).
VARIABLES_CONOCIDAS: dict[str, str] = {
    item["variable"]: item["ejemplo"]
    for grupo in CATALOGO_VARIABLES
    for item in grupo["variables"]
}


def catalogo_variables() -> list[dict]:
    """Catálogo agrupado por categoría para el editor de plantillas."""
    return CATALOGO_VARIABLES


def variables_desconocidas(texto: str) -> list[str]:
    """Variables usadas en el texto que NO están en el catálogo conocido."""
    return sorted(
        v for v in _VARIABLE.findall(texto or "")
        if v not in VARIABLES_CONOCIDAS
    )


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
    # Aislamiento: cada prestamista usa SUS plantillas (o la de defecto).
    return (
        aplicar_filtro_usuario(db.query(PlantillaMensaje), PlantillaMensaje)
        .filter(PlantillaMensaje.clave == clave, PlantillaMensaje.canal == canal)
        .first()
    )


def _defecto(clave: str, canal: str) -> dict:
    for plantilla in PLANTILLAS_POR_DEFECTO:
        if plantilla["clave"] == clave and plantilla["canal"] == canal:
            return plantilla
    raise HTTPException(status_code=404, detail="Plantilla no encontrada")


def _contexto_extendido(db: Session, contexto: dict) -> dict:
    """Agrega las variables de empresa al contexto de render."""
    try:
        from app.services.configuracion import (
            obtener_nombre_empresa,
            obtener_telefono_empresa,
        )

        empresa = obtener_nombre_empresa(db)
        telefono = obtener_telefono_empresa(db)
        return {
            **contexto,
            "empresa": empresa,
            "empresa_nombre": contexto.get("empresa_nombre") or empresa,
            "empresa_telefono": contexto.get("empresa_telefono") or telefono,
        }
    except Exception:  # noqa: BLE001
        return {**contexto, "empresa": "LoanSoft", "empresa_nombre": "LoanSoft"}


def componer_mensaje(
    db: Session, clave: str, canal: str, contexto: dict
) -> tuple[str, str, Optional[PlantillaMensaje]]:
    """Compone asunto y cuerpo con la plantilla almacenada (o la de defecto)."""
    contexto = _contexto_extendido(db, contexto)

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
    query = (
        aplicar_filtro_usuario(db.query(PlantillaMensaje), PlantillaMensaje)
        .order_by(PlantillaMensaje.canal, PlantillaMensaje.clave)
    )
    if canal:
        query = query.filter(PlantillaMensaje.canal == canal)
    return query.all()


def get_plantilla(db: Session, plantilla_id: int) -> PlantillaMensaje:
    # IDOR: solo plantillas propias (admin ve todas).
    plantilla = (
        aplicar_filtro_usuario(db.query(PlantillaMensaje), PlantillaMensaje)
        .filter(PlantillaMensaje.id == plantilla_id)
        .first()
    )
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return plantilla


def crear_plantilla(db: Session, datos) -> PlantillaMensaje:
    dueño = usuario_actual_id.get()
    # La clave es única POR USUARIO (dos prestamistas pueden tener la misma).
    existente = (
        aplicar_filtro_usuario(db.query(PlantillaMensaje), PlantillaMensaje)
        .filter(PlantillaMensaje.clave == datos.clave)
        .first()
    )
    if existente:
        raise HTTPException(status_code=400, detail="Ya existe una plantilla con esa clave")
    plantilla = PlantillaMensaje(**datos.model_dump(), usuario_id=dueño)
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
        aplicar_filtro_usuario(db.query(EnvioMensaje), EnvioMensaje)
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


def previsualizar(
    db: Session, clave: str, canal: str, cuerpo: str, asunto: str | None, contexto: dict
) -> dict:
    """Devuelve el mensaje compuesto sin enviar (vista previa).

    Inyecta las variables de empresa, marca las variables no reconocidas
    y devuelve ejemplos renderizados por variable (para el panel de ayuda).
    """
    contexto = _contexto_extendido(db, contexto)

    usadas = sorted(_VARIABLE.findall(cuerpo or ""))
    # Ejemplo renderizado: variables sin valor en el contexto usan el ejemplo
    # del catálogo, para que la vista previa siempre sea representativa.
    contexto_ejemplo = {**VARIABLES_CONOCIDAS, **contexto}
    return {
        "asunto": renderizar(asunto or "", contexto),
        "cuerpo": renderizar(cuerpo, contexto),
        "cuerpo_ejemplo": renderizar(cuerpo, contexto_ejemplo),
        "variables": usadas,
        "variables_no_reconocidas": variables_desconocidas(cuerpo or ""),
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
    dedupe_clave: str | None = None,
    usuario_id: int | None = None,
    cliente_id: int | None = None,
    respuesta_proveedor: str | None = None,
    error_detalle: str | None = None,
    whatsapp_message_id: str | None = None,
) -> EnvioMensaje:
    registro = EnvioMensaje(
        canal=canal,
        destinatario=destinatario,
        asunto=asunto,
        cuerpo=cuerpo,
        estado=estado,
        motivo=(motivo or "")[:255] if motivo else None,
        plantilla_id=plantilla_id,
        dedupe_clave=dedupe_clave,
        usuario_id=usuario_id if usuario_id is not None else usuario_actual_id.get(),
        cliente_id=cliente_id,
        respuesta_proveedor=respuesta_proveedor,
        error_detalle=error_detalle,
        whatsapp_message_id=whatsapp_message_id,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro


def get_metricas_envios(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None) -> dict:
    """RF-079: totales de envíos por canal, estado y plantilla en el rango
    consultado. Solo envíos del usuario (admin ve todos)."""
    from sqlalchemy import func

    def _filtro(query):
        query = aplicar_filtro_usuario(query, EnvioMensaje)
        if desde:
            query = query.filter(func.date(EnvioMensaje.fecha) >= desde)
        if hasta:
            query = query.filter(func.date(EnvioMensaje.fecha) <= hasta)
        return query

    filas_canal = _filtro(
        db.query(EnvioMensaje.canal, EnvioMensaje.estado, func.count(EnvioMensaje.id))
    ).group_by(EnvioMensaje.canal, EnvioMensaje.estado).all()

    por_canal: dict[str, dict] = {}
    resumen = {"enviado": 0, "omitido": 0, "fallido": 0}
    for canal, estado, cantidad in filas_canal:
        bloque = por_canal.setdefault(canal, {"enviado": 0, "omitido": 0, "fallido": 0, "total": 0})
        bloque[estado] = cantidad
        bloque["total"] += cantidad
        resumen[estado] += cantidad

    total_envios = sum(resumen.values())
    tasa = round(resumen["enviado"] / total_envios * 100, 1) if total_envios else 0.0

    filas_plantilla = _filtro(
        db.query(PlantillaMensaje.clave, PlantillaMensaje.nombre, EnvioMensaje.estado, func.count(EnvioMensaje.id))
        .join(PlantillaMensaje, EnvioMensaje.plantilla_id == PlantillaMensaje.id)
    ).group_by(PlantillaMensaje.clave, PlantillaMensaje.nombre, EnvioMensaje.estado).all()
    por_plantilla: dict[str, dict] = {}
    for clave, nombre, estado, cantidad in filas_plantilla:
        bloque = por_plantilla.setdefault(
            clave, {"clave": clave, "nombre": nombre, "enviado": 0, "omitido": 0, "fallido": 0, "total": 0}
        )
        bloque[estado] = cantidad
        bloque["total"] += cantidad

    return {
        "periodo": _label_periodo_metricas(desde, hasta),
        "resumen": {**resumen, "total": total_envios, "tasa_exito": tasa},
        "por_canal": por_canal,
        "por_plantilla": sorted(por_plantilla.values(), key=lambda f: f["clave"]),
    }


def _label_periodo_metricas(desde, hasta) -> str:
    if desde and hasta:
        return f"{desde} a {hasta}"
    if desde:
        return f"Desde {desde}"
    if hasta:
        return f"Hasta {hasta}"
    return "Todos los periodos"


def get_envios(
    db: Session,
    plantilla_id: int | None = None,
    canal: str | None = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    limit: int = 50,
) -> list[dict]:
    """RF-079: historial reciente de envíos para auditar la comunicación con clientes."""
    from sqlalchemy import func

    query = aplicar_filtro_usuario(db.query(EnvioMensaje, PlantillaMensaje.clave), EnvioMensaje)
    query = query.join(PlantillaMensaje, EnvioMensaje.plantilla_id == PlantillaMensaje.id, isouter=True)
    if plantilla_id:
        query = query.filter(EnvioMensaje.plantilla_id == plantilla_id)
    if canal:
        query = query.filter(EnvioMensaje.canal == canal)
    if desde:
        query = query.filter(func.date(EnvioMensaje.fecha) >= desde)
    if hasta:
        query = query.filter(func.date(EnvioMensaje.fecha) <= hasta)
    filas = query.order_by(EnvioMensaje.fecha.desc()).limit(limit).all()

    return [
        {
            "id": envio.id,
            "fecha": str(envio.fecha),
            "canal": envio.canal,
            "destinatario": envio.destinatario,
            "asunto": envio.asunto,
            "estado": envio.estado,
            "motivo": envio.motivo,
            "plantilla_id": envio.plantilla_id,
            "clave": clave,
        }
        for envio, clave in filas
    ]


def sembrar_plantillas_base(db: Session, usuario_id: int) -> int:
    """Crea el conjunto de plantillas predeterminadas para un prestamista.

    Se llama automáticamente al registrar un usuario con rol prestamista.
    Cada plantilla queda asociada EXCLUSIVAMENTE al nuevo usuario; puede
    modificarla o eliminarla sin afectar a otros. Idempotente: no duplica
    claves que ya existan para el usuario.
    """
    creadas = 0
    for defecto in PLANTILLAS_POR_DEFECTO:
        existe = (
            db.query(PlantillaMensaje)
            .filter(
                PlantillaMensaje.usuario_id == usuario_id,
                PlantillaMensaje.clave == defecto["clave"],
                PlantillaMensaje.canal == defecto["canal"],
            )
            .first()
        )
        if existe:
            continue
        db.add(
            PlantillaMensaje(
                clave=defecto["clave"],
                canal=defecto["canal"],
                nombre=defecto["nombre"],
                asunto=defecto["asunto"],
                cuerpo=defecto["cuerpo"],
                activa=True,
                usuario_id=usuario_id,
            )
        )
        creadas += 1
    if creadas:
        db.commit()
    return creadas
