from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.models._init_ import Base

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