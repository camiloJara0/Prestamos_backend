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

def renovar_prestamo(db: Session, prestamo_id: int, renovacion):
    # Obtiene el prestamo original y valida que exista y este activo
    prestamo_original = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not prestamo_original:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if prestamo_original.estado in ["pagado", "perdido", "renovado"]:
        raise HTTPException(status_code=400, detail=f"No se puede renovar un prestamo en estado {prestamo_original.estado}")

    # Calcula el saldo pendiente real
    saldo = prestamo_original.saldo_pendiente

    # Si hay abono lo descuenta del saldo
    abono = renovacion.abono or 0.0
    if abono > saldo:
        raise HTTPException(status_code=400, detail="El abono no puede ser mayor al saldo pendiente")
    capital_nuevo = round(saldo - abono, 2)

    # Calcula nuevos intereses y cuotas
    interes_total = round(capital_nuevo * (renovacion.porcentaje_interes / 100) * renovacion.numero_cuotas, 2)
    monto_total = round(capital_nuevo + interes_total, 2)
    valor_cuota = round(monto_total / renovacion.numero_cuotas, 2)

    try:
        # Crea el nuevo prestamo
        nuevo_prestamo = Prestamo(
            cliente_id=prestamo_original.cliente_id,
            tipo_prestamo_id=prestamo_original.tipo_prestamo_id,
            fecha_prestamo=renovacion.fecha_renovacion,
            capital_prestado=capital_nuevo,
            porcentaje_interes=renovacion.porcentaje_interes,
            interes_total=interes_total,
            monto_total=monto_total,
            numero_cuotas=renovacion.numero_cuotas,
            valor_cuota=valor_cuota,
            saldo_pendiente=monto_total,
            estado="activo",
            observaciones=renovacion.observaciones
        )
        db.add(nuevo_prestamo)
        db.flush()

        # Genera las nuevas cuotas
        for i in range(1, renovacion.numero_cuotas + 1):
            fecha_vencimiento = renovacion.fecha_renovacion + relativedelta(months=i)
            cuota = PrestamoCuota(
                prestamo_id=nuevo_prestamo.id,
                numero_cuota=i,
                fecha_vencimiento=fecha_vencimiento,
                valor_cuota=valor_cuota,
                capital=round(capital_nuevo / renovacion.numero_cuotas, 2),
                interes=round(interes_total / renovacion.numero_cuotas, 2),
                mora=0.0,
                estado="pendiente"
            )
            db.add(cuota)

        # Marca el prestamo original como renovado
        prestamo_original.estado = "renovado"

        # Registra la relacion en prestamos_renovaciones
        from app.models.models import PrestamoRenovacion
        renovacion_registro = PrestamoRenovacion(
            prestamo_anterior_id=prestamo_original.id,
            prestamo_nuevo_id=nuevo_prestamo.id,
            fecha=renovacion.fecha_renovacion,
            observaciones=renovacion.observaciones
        )
        db.add(renovacion_registro)

        db.commit()
        db.refresh(nuevo_prestamo)
        return nuevo_prestamo

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al renovar el prestamo: {str(e)}")