import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import configure_mappers, relationship

from app.models.base import Base


def generar_referencia():
    """Genera una referencia única de 6 caracteres. Ejemplo: REF-8A2F9X"""
    return f"REF-{uuid.uuid4().hex[:6].upper()}"


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    nombre = Column(String(100), nullable=False)
    # La cédula ya NO es única global: dos prestamistas pueden tener clientes
    # con la misma cédula sin verse entre sí (el servicio valida unicidad
    # dentro del portafolio del usuario).
    cedula = Column(String(20), nullable=False, index=True)
    telefono = Column(String(20))
    email = Column(String(120), nullable=True)  # RF-081: contacto del formulario público
    direccion = Column(String(200))
    persona_referencia = Column(String(100))
    telefono_referencia = Column(String(20))
    observaciones = Column(Text)
    estado = Column(Enum("activo", "inactivo", name="estado_cliente"), default="activo")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamos = relationship("Prestamo", back_populates="cliente")
    pagos = relationship("Pago", back_populates="cliente")


class TipoPrestamo(Base):
    __tablename__ = "tipos_prestamo"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text)
    interes_mensual = Column(Float)
    max_cuotas = Column(Integer)
    # RF-076: periodicidad de cobro de las cuotas del préstamo
    intervalo_pago = Column(
        Enum("mensual", "quincenal", "bimestral", "personalizado", name="intervalo_pago"),
        default="mensual",
        nullable=False,
    )
    intervalo_dias = Column(Integer, nullable=True)  # solo si intervalo_pago = "personalizado"
    # Cómo se aplica el interés de este tipo: "mensual" cobra el % por cada mes
    # calendario; "por_pago" cobra el % por cada cuota/pago (ej. quincenal = 2%
    # por quincena). Ver services/prestamo.calcular_interes_total.
    aplicacion_interes = Column(
        Enum("mensual", "por_pago", name="aplicacion_interes"),
        default="por_pago",
        nullable=False,
    )
    estado = Column(Enum("activo", "inactivo", name="estado_tipo_prestamo"), default="activo")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamos = relationship("Prestamo", back_populates="tipo_prestamo")


class Prestamo(Base):
    __tablename__ = "prestamos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    tipo_prestamo_id = Column(Integer, ForeignKey("tipos_prestamo.id"))

    fecha_prestamo = Column(Date)
    capital_prestado = Column(Float)
    porcentaje_interes = Column(Float)
    interes_total = Column(Float)
    monto_total = Column(Float)

    numero_cuotas = Column(Integer)
    valor_cuota = Column(Float)
    saldo_pendiente = Column(Float)

    estado = Column(Enum("activo", "pagado", "perdido", "renovado", name="estado_prestamo"), default="activo")
    observaciones = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="prestamos")
    tipo_prestamo = relationship("TipoPrestamo", back_populates="prestamos")
    cuotas = relationship("PrestamoCuota", back_populates="prestamo")
    pagos = relationship("Pago", back_populates="pagos" if False else "prestamo")
    reestructuraciones = relationship("PrestamoReestructuracion", back_populates="prestamo")


class PrestamoCuota(Base):
    __tablename__ = "prestamo_cuotas"

    id = Column(Integer, primary_key=True, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    numero_cuota = Column(Integer)
    fecha_vencimiento = Column(Date)
    valor_cuota = Column(Float)
    monto_interes = Column(Float, default=0.0)
    capital = Column(Float)
    interes = Column(Float)
    mora = Column(Float)
    estado = Column(Enum("pendiente", "pagado", "vencido", "parcial", name="estado_cuota"), default="pendiente")
    reestructuracion_id = Column(Integer, ForeignKey("prestamos_reestructuraciones.id"), nullable=True)

    referencia_pago = Column(
        String(50), 
        unique=True, 
        index=True, 
        default=generar_referencia, 
        nullable=True
    )
    fecha_pago = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamo = relationship("Prestamo", back_populates="cuotas")
    pagos = relationship("Pago", back_populates="cuota")


class TipoPago(Base):
    __tablename__ = "tipos_pago"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)
    estado = Column(Enum("activo", "inactivo", name="estado_tipo_pago"), default="activo")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    pagos = relationship("Pago", back_populates="tipo_pago")


class MetodoPagoPrestamista(Base):
    """Tabla para registrar las cuentas de Nequi, Daviplata, Bancolombia y QR del prestamista."""
    __tablename__ = "metodos_pago_prestamista"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    banco = Column(String(50), nullable=False)        # Ej: Nequi, Daviplata, Bancolombia
    tipo_cuenta = Column(String(50), default="Ahorros") # Ej: Ahorros, Corriente, Llave
    numero_cuenta = Column(String(50), nullable=False)  # Número de cuenta o teléfono
    titular = Column(String(100), nullable=False)       # Nombre del titular
    documento_titular = Column(String(20), nullable=True) # Cédula/NIT para soporte tributario
    qr_code_url = Column(String(255), nullable=True)   # Ruta/URL de la imagen del QR
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="metodos_pago")


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    cuota_id = Column(Integer, ForeignKey("prestamo_cuotas.id"), nullable=True)
    tipo_pago_id = Column(Integer, ForeignKey("tipos_pago.id"))

    fecha_pago = Column(Date)
    valor_pagado = Column(Float)
    capital_pagado = Column(Float)
    interes_pagado = Column(Float)
    mora_pagada = Column(Float)
    observaciones = Column(Text)

    # NUEVOS CAMPOS: Referencia de recibo y lógica de devolución
    referencia_recibo = Column(
        String(50),
        unique=True,
        index=True,
        default=generar_referencia,
        nullable=False,
    )
    estado_pago = Column(
        Enum("confirmado", "devuelto", name="estado_pago"),
        default="confirmado",
        nullable=False,
    )
    fecha_devolucion = Column(DateTime, nullable=True)
    motivo_devolucion = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamo = relationship("Prestamo", back_populates="pagos")
    cliente = relationship("Cliente", back_populates="pagos")
    cuota = relationship("PrestamoCuota", back_populates="pagos")
    tipo_pago = relationship("TipoPago", back_populates="pagos")

    @property
    def referencia_pago(self) -> Optional[str]:
        """Obtiene la referencia única del pago/recibo."""
        return self.referencia_recibo or (self.cuota.referencia_pago if self.cuota else None)


class MovimientoCapital(Base):
    __tablename__ = "movimientos_capital"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    tipo_movimiento = Column(Enum(
        "inversion",
        "retiro",
        "prestamo_otorgado",
        "pago_recibido",
        "ajuste_prestamo",
        "devolucion_pago",
        "perdida",
        name="tipo_movimiento"
    ))
    descripcion = Column(Text)
    valor = Column(Float)
    fecha = Column(Date)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PrestamoRenovacion(Base):
    __tablename__ = "prestamos_renovaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    prestamo_anterior_id = Column(Integer, ForeignKey("prestamos.id"))
    prestamo_nuevo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(Date)
    observaciones = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PrestamoReestructuracion(Base):
    """Plan de reestructuración de un préstamo en mora (RF-035)."""
    __tablename__ = "prestamos_reestructuraciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(Date)
    motivo = Column(Text)
    saldo_anterior = Column(Float)
    numero_cuotas = Column(Integer)
    porcentaje_interes = Column(Float)
    valor_cuota = Column(Float)
    monto_plan = Column(Float)
    estado = Column(String(20), default="activa")  # activa | cerrada
    created_at = Column(DateTime, default=datetime.utcnow)

    prestamo = relationship("Prestamo", back_populates="reestructuraciones")


class Mora(Base):
    __tablename__ = "moras"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    cuota_id = Column(Integer, ForeignKey("prestamo_cuotas.id"))
    fecha = Column(Date)
    valor = Column(Float)
    estado = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)


class PrestamoPerdido(Base):
    __tablename__ = "prestamos_perdidos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(Date)
    valor_perdido = Column(Float)
    motivo = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    rol = Column(Enum("admin", "prestamista", "usuario", name="rol_usuario"), default="usuario")
    estado = Column(Enum("activo", "inactivo", name="estado_usuario"), default="activo")

    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    tokens = relationship("Token", back_populates="usuario", cascade="all, delete-orphan")
    auditorias = relationship("Auditoria", back_populates="usuario")
    push_subscriptions = relationship(
        "PushSubscription",
        back_populates="usuario",
        cascade="all, delete-orphan",
    )
    metodos_pago = relationship(
        "MetodoPagoPrestamista",
        back_populates="usuario",
        cascade="all, delete-orphan",
    )


class Token(Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    activo = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    # Backoffice: contexto de la sesión (nunca se almacenan secretos aquí,
    # solo metadatos para el historial de accesos).
    ultimo_uso_at = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)

    usuario = relationship("Usuario", back_populates="tokens")


class Capital(Base):
    __tablename__ = "capital"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    monto_total = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConfiguracionSistema(Base):
    __tablename__ = "configuracion_sistema"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    clave = Column(String(100), unique=True, nullable=False)
    valor = Column(String(255), nullable=False)
    descripcion = Column(Text)
    tipo_valor = Column(String(50), default="float")
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ConfiguracionSistema(clave={self.clave}, valor={self.valor})>"


class ConfiguracionUsuario(Base):
    """Override de parámetro (ej. mora) propio de un usuario.

    La lectura siempre es en cascada: si el usuario autenticado tiene esta
    clave, se usa su valor; si no, se usa la fila global de
    `configuracion_sistema`. Esto permite la configuración personalizada
    por usuario (RF de mora configurable) sin tocar el esquema global.
    """

    __tablename__ = "configuracion_usuario"
    __table_args__ = (
        UniqueConstraint("usuario_id", "clave", name="uq_config_usuario_usuario_clave"),
    )

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=False)
    clave = Column(String(100), nullable=False, index=True)
    valor = Column(String(255), nullable=False)
    descripcion = Column(Text)
    tipo_valor = Column(String(50), default="string")
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ConfiguracionUsuario(clave={self.clave}, usuario_id={self.usuario_id})>"


class Auditoria(Base):
    __tablename__ = "auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    tabla_afectada = Column(String(100), nullable=False)
    tipo_operacion = Column(String(50), nullable=False)
    registro_id = Column(Integer)
    valores_anteriores = Column(Text)
    valores_nuevos = Column(Text)
    descripcion = Column(Text)
    ip_address = Column(String(50))
    fecha = Column(DateTime, default=datetime.utcnow)
    # Backoffice: trazabilidad de eventos de seguridad.
    user_agent = Column(String(255), nullable=True)
    request_id = Column(String(36), nullable=True)
    resultado = Column(
        Enum("ok", "fallido", name="resultado_auditoria"),
        nullable=True,
    )

    usuario = relationship("Usuario", back_populates="auditorias")

    def __repr__(self):
        return f"<Auditoria(tabla={self.tabla_afectada}, operacion={self.tipo_operacion}, fecha={self.fecha})>"


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String(255), primary_key=True, index=True)
    response = Column(Text, nullable=False)
    status_code = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    usuario = relationship("Usuario", back_populates="push_subscriptions")


class SolicitudPrestamo(Base):
    """Solicitud de préstamo (RF-020 a RF-022, RF-065)."""
    __tablename__ = "solicitudes_prestamo"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    tipo_prestamo_id = Column(Integer, ForeignKey("tipos_prestamo.id"), nullable=False)

    monto_solicitado = Column(Float, nullable=False)
    plazo_cuotas = Column(Integer, nullable=False)
    porcentaje_interes = Column(Float, nullable=False)
    motivo = Column(Text, nullable=False)

    estado = Column(
        Enum(
            "pendiente",
            "aprobada",
            "rechazada",
            "convertida",
            "expirada",
            name="estado_solicitud",
        ),
        default="pendiente",
        nullable=False,
    )

    usuario_creador_id = Column(Integer, ForeignKey("usuarios.id"))
    evaluador_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_decision = Column(DateTime, nullable=True)
    motivo_decision = Column(Text, nullable=True)
    fecha_expiracion = Column(Date, nullable=True)

    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=True)

    puntaje_scoring = Column(Float, nullable=True)
    scoring_detalle = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente = relationship("Cliente")
    tipo_prestamo = relationship("TipoPrestamo")
    prestamo = relationship("Prestamo")
    creador = relationship("Usuario", foreign_keys=[usuario_creador_id])
    evaluador = relationship("Usuario", foreign_keys=[evaluador_id])


class Notificacion(Base):
    """Registro interno de notificaciones (RF-023)."""
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    titulo = Column(String(150), nullable=False)
    mensaje = Column(Text, nullable=False)
    url = Column(String(255), nullable=True)
    tipo = Column(String(50), default="solicitud")
    leida = Column(Boolean, default=False)
    push_enviado = Column(Boolean, default=False)
    fecha = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario")


class PlantillaMensaje(Base):
    """Plantillas de mensajes por canal (RF-063)."""
    __tablename__ = "plantillas_mensaje"
    # La clave es única POR USUARIO: dos prestamistas pueden tener plantillas
    # con la misma clave sin afectarse entre sí (aislamiento multiusuario).
    __table_args__ = (
        UniqueConstraint("usuario_id", "clave", "canal", name="uq_plantillas_usuario_clave"),
    )

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    clave = Column(String(80), nullable=False)
    canal = Column(
        Enum("email", "sms", "whatsapp", name="canal_plantilla"),
        nullable=False,
    )
    nombre = Column(String(120), nullable=False)
    asunto = Column(String(200), nullable=True)
    cuerpo = Column(Text, nullable=False)
    activa = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Contrato(Base):
    """Contrato electrónico generado y firmado (RF-066)."""
    __tablename__ = "contratos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    solicitud_id = Column(Integer, ForeignKey("solicitudes_prestamo.id"), nullable=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=True)
    estado = Column(
        Enum("emitido", "en_firma", "firmado", "rechazado", name="estado_contrato"),
        default="emitido",
        nullable=False,
    )
    ruta_archivo = Column(String(255), nullable=False)
    hash_documento = Column(String(64), nullable=False)
    firmante_nombre = Column(String(120), nullable=True)
    firmante_documento = Column(String(30), nullable=True)
    fecha_emision = Column(DateTime, default=datetime.utcnow)
    fecha_firma = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    solicitud = relationship("SolicitudPrestamo")
    prestamo = relationship("Prestamo")


class TransaccionPasarela(Base):
    """Transacción de pago en línea vía pasarela (RF-064)."""
    __tablename__ = "transacciones_pasarela"

    id = Column(Integer, primary_key=True, index=True)
    cuota_id = Column(Integer, ForeignKey("prestamo_cuotas.id"), nullable=False)
    monto = Column(Float, nullable=False)
    pasarela = Column(String(50), default="piloto")
    estado = Column(
        Enum("pendiente", "confirmada", "fallida", "expirada", name="estado_pasarela"),
        default="pendiente",
        nullable=False,
    )
    referencia_externa = Column(String(100), nullable=True)
    url_pago = Column(String(255), nullable=True)
    motivo_falla = Column(String(255), nullable=True)
    pago_id = Column(Integer, ForeignKey("pagos.id"), nullable=True)
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_confirmacion = Column(DateTime, nullable=True)

    cuota = relationship("PrestamoCuota")
    pago = relationship("Pago")


class EnvioMensaje(Base):
    """Registro de envíos y omisiones por canal (RF-061, RF-062).

    Trazabilidad completa: usuario dueño, cliente destinatario, plantilla,
    canal, estado (pendiente/enviado/entregado/leído/omitido/fallido),
    respuesta del proveedor y error detallado.
    """
    __tablename__ = "envios_mensaje"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), index=True, nullable=True)
    canal = Column(Enum("email", "sms", "whatsapp", name="canal_envio"), nullable=False)
    destinatario = Column(String(120), nullable=False)
    asunto = Column(String(200), nullable=True)
    cuerpo = Column(Text, nullable=True)
    plantilla_id = Column(Integer, ForeignKey("plantillas_mensaje.id"), nullable=True)
    # Sin CHECK para permitir los estados de entrega de WhatsApp
    # (pendiente/enviado/entregado/leído) además de omitido/fallido.
    estado = Column(String(30), default="enviado", nullable=False, index=True)
    motivo = Column(String(255), nullable=True)
    dedupe_clave = Column(String(120), nullable=True)  # RF-079: evita duplicados por evento/día
    fecha = Column(DateTime, default=datetime.utcnow)
    # Trazabilidad WhatsApp
    whatsapp_message_id = Column(String(120), nullable=True)
    respuesta_proveedor = Column(Text, nullable=True)
    error_detalle = Column(Text, nullable=True)

    plantilla = relationship("PlantillaMensaje")


class CredencialesWhatsApp(Base):
    """Credenciales propias de WhatsApp Business por prestamista (Modo 2).

    La empresa administra el modo corporativo (variables de entorno); este
    registro permite que cada usuario use su propia cuenta Business con
    validación de conexión y trazabilidad de la última comprobación.
    """
    __tablename__ = "credenciales_whatsapp"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    proveedor = Column(String(40), default="meta_cloud", nullable=False)
    access_token = Column(Text, nullable=False)
    phone_number_id = Column(String(50), nullable=False)
    business_account_id = Column(String(50), nullable=True)
    api_key = Column(Text, nullable=True)
    estado_conexion = Column(String(20), default="sin_probar", nullable=False)
    ultima_validacion = Column(DateTime, nullable=True)
    detalle_validacion = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("usuario_id", name="uq_credenciales_whatsapp_usuario"),
    )


class TipoCita(Base):
    """Tipos de cita personalizados de la agenda (RF-080 / HU-5.3)."""

    __tablename__ = "tipos_cita"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    color = Column(String(20), default="#7c3aed", nullable=False)
    duracion_minutos = Column(Integer, default=30, nullable=False)
    estado = Column(
        Enum("activo", "inactivo", name="estado_tipo_cita"),
        default="activo",
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EventoAgenda(Base):
    """Eventos del calendario operativo (RF-080): cuotas, recogidas, citas y seguimientos."""

    __tablename__ = "eventos_agenda"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), index=True, nullable=True)
    tipo = Column(
        Enum("cuota_vence", "recogida", "cita", "seguimiento", "otro", name="tipo_evento_agenda"),
        nullable=False,
    )
    titulo = Column(String(200), nullable=False)
    descripcion = Column(String(500), nullable=True)
    fecha = Column(Date, nullable=False, index=True)
    hora_inicio = Column(String(5), nullable=True)  # HH:MM
    hora_fin = Column(String(5), nullable=True)  # HH:MM
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    tipo_cita_id = Column(Integer, ForeignKey("tipos_cita.id"), nullable=True)
    estado = Column(
        Enum("pendiente", "completado", "cancelado", "vencido", name="estado_evento_agenda"),
        default="pendiente",
        nullable=False,
    )
    observaciones = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente")
    prestamo = relationship("Prestamo")
    tipo_cita = relationship("TipoCita")


class ErroresApp(Base):
    """Incidentes de error agrupados por fingerprint (Backoffice)."""

    __tablename__ = "errores_app"

    id = Column(Integer, primary_key=True, index=True)
    origen = Column(
        Enum("backend", "frontend", name="origen_error"),
        nullable=False,
    )
    nivel = Column(
        Enum("error", "critico", name="nivel_error"),
        default="error",
        nullable=False,
    )
    tipo_exception = Column(String(150), nullable=False)
    mensaje = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    endpoint = Column(String(200), nullable=True)
    componente = Column(String(200), nullable=True)
    metodo_http = Column(String(10), nullable=True)
    status_code = Column(Integer, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    request_id = Column(String(36), nullable=True, index=True)
    version = Column(String(20), nullable=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    ocurrencias = Column(Integer, default=1, nullable=False)
    primera_ocurrencia = Column(DateTime, default=datetime.utcnow, nullable=False)
    ultima_ocurrencia = Column(DateTime, default=datetime.utcnow, nullable=False)
    estado = Column(
        Enum("abierto", "en_seguimiento", "resuelto", "ignorado", name="estado_error"),
        default="abierto",
        nullable=False,
        index=True,
    )
    responsable_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    resolucion = Column(Text, nullable=True)
    fecha_resolucion = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    usuario = relationship("Usuario", foreign_keys=[usuario_id])
    responsable = relationship("Usuario", foreign_keys=[responsable_id])


class MetricaApi(Base):
    """Agregado horario de peticiones API (fuente de series del dashboard)."""

    __tablename__ = "metricas_api"
    __table_args__ = (
        UniqueConstraint(
            "fecha_hora",
            "endpoint",
            "metodo",
            "status_code",
            name="uq_metricas_api_clave",
        ),
    )

    fecha_hora = Column(DateTime, primary_key=True)
    endpoint = Column(String(200), primary_key=True)
    metodo = Column(String(10), primary_key=True)
    status_code = Column(Integer, primary_key=True)
    conteo = Column(Integer, default=0, nullable=False)
    latencia_ms_suma = Column(Float, default=0.0, nullable=False)
    latencia_ms_max = Column(Float, default=0.0, nullable=False)


class EjecucionProceso(Base):
    """Historial de ejecuciones de procesos programados y manuales."""

    __tablename__ = "ejecuciones_proceso"

    id = Column(Integer, primary_key=True, index=True)
    tarea = Column(String(80), nullable=False, index=True)
    origen = Column(
        Enum("programada", "manual", name="origen_ejecucion"),
        default="programada",
        nullable=False,
    )
    estado = Column(
        Enum(
            "pendiente",
            "en_ejecucion",
            "completado",
            "fallido",
            "cancelado",
            name="estado_ejecucion",
        ),
        default="pendiente",
        nullable=False,
        index=True,
    )
    solicitado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_solicitud = Column(DateTime, default=datetime.utcnow, nullable=False)
    inicio = Column(DateTime, nullable=True)
    fin = Column(DateTime, nullable=True)
    duracion_ms = Column(Integer, nullable=True)
    intentos = Column(Integer, default=1, nullable=False)
    resultado = Column(Text, nullable=True)
    error_mensaje = Column(Text, nullable=True)

    solicitante = relationship("Usuario", foreign_keys=[solicitado_por])


# Validar relaciones de SQLAlchemy
configure_mappers()