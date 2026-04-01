from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from models._init_ import Base

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