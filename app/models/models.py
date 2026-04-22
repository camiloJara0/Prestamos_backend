from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.models.base import Base


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
    pagos = relationship("Pago", back_populates="prestamo")


class PrestamoCuota(Base):
    __tablename__ = "prestamo_cuotas"

    id = Column(Integer, primary_key=True, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    numero_cuota = Column(Integer)
    fecha_vencimiento = Column(Date)
    valor_cuota = Column(Float)
    capital = Column(Float)
    interes = Column(Float)
    mora = Column(Float)
    estado = Column(Enum("pendiente", "pagado", "vencido", name="estado_cuota"), default="pendiente")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamo = relationship("Prestamo", back_populates="cuotas")
    pagos = relationship("Pago", back_populates="cuota")


class TipoPago(Base):
    __tablename__ = "tipos_pago"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)

    pagos = relationship("Pago", back_populates="tipo_pago")

class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"))
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    cuota_id = Column(Integer, ForeignKey("prestamo_cuotas.id"))
    tipo_pago_id = Column(Integer, ForeignKey("tipos_pago.id"))

    fecha_pago = Column(Date)
    valor_pagado = Column(Float)
    capital_pagado = Column(Float)
    interes_pagado = Column(Float)
    mora_pagada = Column(Float)
    observaciones = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    prestamo = relationship("Prestamo", back_populates="pagos")
    cliente = relationship("Cliente", back_populates="pagos")
    cuota = relationship("PrestamoCuota", back_populates="pagos")
    tipo_pago = relationship("TipoPago", back_populates="pagos")

class MovimientoCapital(Base):
    __tablename__ = "movimientos_capital"

    id = Column(Integer, primary_key=True, index=True)
    tipo_movimiento = Column(Enum("inversion", "retiro", "prestamo_otorgado", "pago_recibido", "perdida", name="tipo_movimiento"))
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

# Modelo de Usuario : Es la tabla en la base de datos que guarda los usuarios del sistema. 
# Tiene email, contraseña (guardada como hash), rol (admin/usuario) y estado. 

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    rol = Column(Enum("admin", "usuario", name="rol_usuario"), default="usuario")
    estado = Column(Enum("activo", "inactivo", name="estado_usuario"), default="activo")
    created_at = Column(DateTime, default=datetime.utcnow)

    tokens = relationship("Token", back_populates="usuario")

# cuando el usuario haga login guardamos el token en la DB, y cuando haga logout lo marcamos como inválido. 
# Así aunque el token no haya expirado, si está en la tabla como inválido el servidor lo rechaza.

class Token (Base):
    __tablename__ = "tokens"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    access_token = Column(String(500), nullable=False)
    refresh_token = Column(String(500), nullable=False)
    activo = Column(Integer, default=1) # 1 = activo - 0 = inactivo
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    usuario = relationship("Usuario", back_populates="tokens")