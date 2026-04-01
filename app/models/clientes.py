from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from models._init_ import Base

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