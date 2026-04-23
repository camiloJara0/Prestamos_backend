# Servicio de prestamos : maneja la logica de creacion de prestamos
# calcula interes, monto total, genera cuotas y registra movimiento de capital
# usa transacciones para garantizar consistencia en la DB

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date
from dateutil.relativedelta import relativedelta
from app.models.models import Prestamo, PrestamoCuota, MovimientoCapital, Capital
from app.schemas.prestamo import PrestamoCreate
from app.services.capital import get_or_create_capital

def crear_prestamo(db: Session, prestamo: PrestamoCreate):
    # Verifica capital disponible
    capital = get_or_create_capital(db)
    if prestamo.capital_prestado > capital.monto_total:
        raise HTTPException(status_code=400, detail="Capital insuficiente para otorgar el prestamo")

    # Calcula interes y monto total
    interes_total = round(prestamo.capital_prestado * (prestamo.porcentaje_interes / 100) * prestamo.numero_cuotas, 2)
    monto_total = round(prestamo.capital_prestado + interes_total, 2)
    valor_cuota = round(monto_total / prestamo.numero_cuotas, 2)

    try:
        # Crea el prestamo
        db_prestamo = Prestamo(
            cliente_id=prestamo.cliente_id,
            tipo_prestamo_id=prestamo.tipo_prestamo_id,
            fecha_prestamo=prestamo.fecha_prestamo,
            capital_prestado=prestamo.capital_prestado,
            porcentaje_interes=prestamo.porcentaje_interes,
            interes_total=interes_total,
            monto_total=monto_total,
            numero_cuotas=prestamo.numero_cuotas,
            valor_cuota=valor_cuota,
            saldo_pendiente=monto_total,
            estado="activo",
            observaciones=prestamo.observaciones
        )
        db.add(db_prestamo)
        db.flush()  # genera el id sin hacer commit aun

        # Genera las cuotas automaticamente una por mes
        for i in range(1, prestamo.numero_cuotas + 1):
            fecha_vencimiento = prestamo.fecha_prestamo + relativedelta(months=i)
            cuota = PrestamoCuota(
                prestamo_id=db_prestamo.id,
                numero_cuota=i,
                fecha_vencimiento=fecha_vencimiento,
                valor_cuota=valor_cuota,
                capital=round(prestamo.capital_prestado / prestamo.numero_cuotas, 2),
                interes=round(interes_total / prestamo.numero_cuotas, 2),
                mora=0.0,
                estado="pendiente"
            )
            db.add(cuota)

        # Descuenta el capital
        capital.monto_total -= prestamo.capital_prestado

        # Registra el movimiento de capital
        movimiento = MovimientoCapital(
            tipo_movimiento="prestamo_otorgado",
            descripcion=f"Prestamo otorgado al cliente {prestamo.cliente_id}",
            valor=prestamo.capital_prestado,
            fecha=prestamo.fecha_prestamo,
            prestamo_id=db_prestamo.id
        )
        db.add(movimiento)

        db.commit()
        db.refresh(db_prestamo)
        return db_prestamo

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el prestamo: {str(e)}")

def get_prestamos(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Prestamo).filter(Prestamo.estado == "activo").offset(skip).limit(limit).all()