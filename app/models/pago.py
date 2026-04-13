from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.models._init_ import Base

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