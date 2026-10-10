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
)
from sqlalchemy.orm import configure_mappers, relationship

from app.models.base import Base


def generar_referencia():
    """Genera una referencia única de 6 caracteres. Ejemplo: REF-8A2F9X"""
    return f"REF-{uuid.uuid4().hex[:6].upper()}"


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    cedula = Column(String(20), unique=True, nullable=False)
    telefono = Column(String(20))
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
    estado = Column(Enum("activo", "inactivo", name="estado_tipo_prestamo"), default="activo")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamos = relationship("Prestamo", back_populates="tipo_prestamo")


class Prestamo(Base):
    __tablename__ = "prestamos"

    id = Column(Integer, primary_key=True, index=True)
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
    prestamo_anterior_id = Column(Integer, ForeignKey("prestamos.id"))
    prestamo_nuevo_id = Column(Integer, ForeignKey("prestamos.id"))
    fecha = Column(Date)
    observaciones = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PrestamoReestructuracion(Base):
    """Plan de reestructuración de un préstamo en mora (RF-035)."""
    __tablename__ = "prestamos_reestructuraciones"

    id = Column(Integer, primary_key=True, index=True)
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
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    cuota_id = Column(Integer, ForeignKey("prestamo_cuotas.id"))
    fecha = Column(Date)
    valor = Column(Float)
    estado = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)


class PrestamoPerdido(Base):
    __tablename__ = "prestamos_perdidos"

    id = Column(Integer, primary_key=True, index=True)
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
    rol = Column(Enum("admin", "usuario", name="rol_usuario"), default="usuario")
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
    access_token = Column(String(500), nullable=False)
    refresh_token = Column(String(500), nullable=False)
    activo = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    usuario = relationship("Usuario", back_populates="tokens")


class Capital(Base):
    __tablename__ = "capital"

    id = Column(Integer, primary_key=True, index=True)
    monto_total = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConfiguracionSistema(Base):
    __tablename__ = "configuracion_sistema"

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(100), unique=True, nullable=False)
    valor = Column(String(255), nullable=False)
    descripcion = Column(Text)
    tipo_valor = Column(String(50), default="float")
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ConfiguracionSistema(clave={self.clave}, valor={self.valor})>"


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

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String(80), unique=True, nullable=False)
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
    """Registro de envíos y omisiones por canal (RF-061, RF-062)."""
    __tablename__ = "envios_mensaje"

    id = Column(Integer, primary_key=True, index=True)
    canal = Column(Enum("email", "sms", "whatsapp", name="canal_envio"), nullable=False)
    destinatario = Column(String(120), nullable=False)
    asunto = Column(String(200), nullable=True)
    cuerpo = Column(Text, nullable=True)
    plantilla_id = Column(Integer, ForeignKey("plantillas_mensaje.id"), nullable=True)
    estado = Column(
        Enum("enviado", "omitido", "fallido", name="estado_envio"),
        default="enviado",
        nullable=False,
    )
    motivo = Column(String(255), nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)

    plantilla = relationship("PlantillaMensaje")


# Validar relaciones de SQLAlchemy
configure_mappers()