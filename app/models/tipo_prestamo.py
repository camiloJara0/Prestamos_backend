from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.models._init_ import Base

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