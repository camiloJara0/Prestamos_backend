from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from app.models._init_ import Base

class TipoPago(Base):
    __tablename__ = "tipos_pago"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    descripcion = Column(Text)

    pagos = relationship("Pago", back_populates="tipo_pago")