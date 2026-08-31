# Servicio de prestamos : maneja la logica de creacion de prestamos
# calcula interes, monto total, genera cuotas y registra movimiento de capital
# usa transacciones para garantizar consistencia en la DB

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import or_

from app.models.models import Prestamo, PrestamoCuota, MovimientoCapital, Capital, Cliente, TipoPrestamo, PrestamoRenovacion, PrestamoPerdido, Mora
from app.schemas.prestamo import PrestamoCreate
from app.services.capital import get_or_create_capital
from app.utils.pagination import paginate

def crear_prestamo(db: Session, prestamo: PrestamoCreate, usuario_id: int):
    cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id, Cliente.estado == "activo").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado o inactivo")
    
    cuotas_vencidas = db.query(PrestamoCuota).join(Prestamo).filter(
        Prestamo.cliente_id == prestamo.cliente_id,
        PrestamoCuota.estado.in_(["vencido", "parcial"]),
        PrestamoCuota.fecha_vencimiento < date.today()
    ).all()
    
    if cuotas_vencidas:
        cuotas_pendientes = len(cuotas_vencidas)
        valor_pendiente = sum(c.valor_cuota for c in cuotas_vencidas)
        raise HTTPException(
            status_code=400,
            detail=f"Cliente tiene {cuotas_pendientes} cuota(s) vencida(s) sin pagar. Monto pendiente: ${valor_pendiente:,.2f}. Debe pagar antes de solicitar nuevo préstamo."
        )
    
    tipo_prestamo = db.query(TipoPrestamo).filter(
        TipoPrestamo.id == prestamo.tipo_prestamo_id,
        TipoPrestamo.estado == "activo"
    ).first()
    if not tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de préstamo no encontrado o inactivo")
    
    capital = db.query(Capital).first()
    if not capital or capital.monto_total < prestamo.capital_prestado:
        raise HTTPException(status_code=400, detail="Capital insuficiente para otorgar el préstamo")
    
    db_prestamo = Prestamo(
        cliente_id=prestamo.cliente_id,
        tipo_prestamo_id=prestamo.tipo_prestamo_id,
        fecha_prestamo=date.today(),
        capital_prestado=prestamo.capital_prestado,
        porcentaje_interes=prestamo.porcentaje_interes,
        numero_cuotas=prestamo.numero_cuotas,
        estado="activo"
    )
    
    db_prestamo.interes_total = round(
        prestamo.capital_prestado * (prestamo.porcentaje_interes / 100) * prestamo.numero_cuotas, 2
    )
    db_prestamo.monto_total = round(prestamo.capital_prestado + db_prestamo.interes_total, 2)
    db_prestamo.valor_cuota = round(db_prestamo.monto_total / prestamo.numero_cuotas, 2)
    db_prestamo.saldo_pendiente = db_prestamo.monto_total
    
    db.add(db_prestamo)
    db.flush()
    
    cuota_regular = db_prestamo.valor_cuota
    interes_regular = round(db_prestamo.interes_total / prestamo.numero_cuotas, 2)
    capital_regular = round(prestamo.capital_prestado / prestamo.numero_cuotas, 2)

    for i in range(1, prestamo.numero_cuotas + 1):
        fecha_vencimiento = date.today() + relativedelta(months=i)
        
        if i == prestamo.numero_cuotas:
            val_cuota = round(db_prestamo.monto_total - (cuota_regular * (prestamo.numero_cuotas - 1)), 2)
            val_interes = round(db_prestamo.interes_total - (interes_regular * (prestamo.numero_cuotas - 1)), 2)
            val_capital = round(prestamo.capital_prestado - (capital_regular * (prestamo.numero_cuotas - 1)), 2)
        else:
            val_cuota = cuota_regular
            val_interes = interes_regular
            val_capital = capital_regular

        cuota = PrestamoCuota(
            prestamo_id=db_prestamo.id,
            numero_cuota=i,
            fecha_vencimiento=fecha_vencimiento,
            valor_cuota=val_cuota,
            monto_interes=val_interes,
            capital=val_capital,
            interes=val_interes,
            mora=0.0,
            estado="pendiente"
        )
        db.add(cuota)
    
    capital.monto_total -= prestamo.capital_prestado
    movimiento = MovimientoCapital(
        tipo_movimiento="prestamo_otorgado",
        descripcion=f"Préstamo #{db_prestamo.id} al cliente {cliente.nombre}",
        valor=prestamo.capital_prestado,
        fecha=date.today(),
        prestamo_id=db_prestamo.id
    )
    db.add(movimiento)
    
    db.commit()
    db.refresh(db_prestamo)
    
    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="prestamos",
        tipo_operacion="CREATE",
        registro_id=db_prestamo.id,
        valores_nuevos={
            "cliente_id": db_prestamo.cliente_id,
            "capital_prestado": db_prestamo.capital_prestado,
            "porcentaje_interes": db_prestamo.porcentaje_interes,
            "numero_cuotas": db_prestamo.numero_cuotas,
            "monto_total": db_prestamo.monto_total,
            "estado": db_prestamo.estado
        },
        descripcion=f"Préstamo creado para cliente {cliente.nombre}"
    )
    
    return db_prestamo

def get_prestamos(
    db: Session, 
    page: int = 1, 
    limit: int = 10, 
    estado: str = "activo",
    cliente_id: int = None, 
    fecha_desde: date = None, 
    fecha_hasta: date = None,
    busqueda: str = None
):
    query = db.query(Prestamo)
    if estado and estado != "todos":
        query = query.filter(Prestamo.estado == estado)
    if cliente_id:
        query = query.filter(Prestamo.cliente_id == cliente_id)
    if fecha_desde:
        query = query.filter(Prestamo.fecha_prestamo >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Prestamo.fecha_prestamo <= fecha_hasta)
    if busqueda:
        query = query.join(Cliente).filter(
            or_(Cliente.nombre.ilike(f"%{busqueda}%"), Cliente.cedula.ilike(f"%{busqueda}%"))
        )
    
    query = query.order_by(Prestamo.id.desc())
    return paginate(query, page=page, limit=limit)

def obtener_prestamo(db: Session, prestamo_id: int):
    return db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()

def renovar_prestamo(db: Session, prestamo_id: int, renovacion):
    prestamo_original = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not prestamo_original:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if prestamo_original.estado in ["pagado", "perdido", "renovado"]:
        raise HTTPException(status_code=400, detail=f"No se puede renovar un prestamo en estado {prestamo_original.estado}")

    saldo = prestamo_original.saldo_pendiente

    abono = renovacion.abono or 0.0
    if abono > saldo:
        raise HTTPException(status_code=400, detail="El abono no puede ser mayor al saldo pendiente")
    capital_nuevo = round(saldo - abono, 2)

    interes_total = round(capital_nuevo * (renovacion.porcentaje_interes / 100) * renovacion.numero_cuotas, 2)
    monto_total = round(capital_nuevo + interes_total, 2)
    valor_cuota = round(monto_total / renovacion.numero_cuotas, 2)

    try:
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

        cuota_reg = valor_cuota
        cap_reg = round(capital_nuevo / renovacion.numero_cuotas, 2)
        int_reg = round(interes_total / renovacion.numero_cuotas, 2)

        for i in range(1, renovacion.numero_cuotas + 1):
            fecha_vencimiento = renovacion.fecha_renovacion + relativedelta(months=i)
            
            if i == renovacion.numero_cuotas:
                v_cuota = round(monto_total - (cuota_reg * (renovacion.numero_cuotas - 1)), 2)
                v_cap = round(capital_nuevo - (cap_reg * (renovacion.numero_cuotas - 1)), 2)
                v_int = round(interes_total - (int_reg * (renovacion.numero_cuotas - 1)), 2)
            else:
                v_cuota = cuota_reg
                v_cap = cap_reg
                v_int = int_reg

            cuota = PrestamoCuota(
                prestamo_id=nuevo_prestamo.id,
                numero_cuota=i,
                fecha_vencimiento=fecha_vencimiento,
                valor_cuota=v_cuota,
                capital=v_cap,
                interes=v_int,
                mora=0.0,
                estado="pendiente"
            )
            db.add(cuota)

        prestamo_original.estado = "renovado"

        renovacion_registro = PrestamoRenovacion(
            prestamo_anterior_id=prestamo_original.id,
            prestamo_nuevo_id=nuevo_prestamo.id,
            fecha=renovacion.fecha_renovacion,
            observaciones=renovacion.observaciones
        )
        db.add(renovacion_registro)

        if abono > 0:
            capital_obj = db.query(Capital).first()
            if capital_obj:
                capital_obj.monto_total += abono
                mov_abono = MovimientoCapital(
                    tipo_movimiento="pago_recibido",
                    descripcion=f"Abono por renovación del préstamo #{prestamo_original.id}",
                    valor=abono,
                    fecha=renovacion.fecha_renovacion,
                    prestamo_id=nuevo_prestamo.id
                )
                db.add(mov_abono)

        db.commit()
        db.refresh(nuevo_prestamo)
        return nuevo_prestamo

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al renovar el prestamo: {str(e)}")

def marcar_prestamo_perdido(db: Session, prestamo_id: int, datos):
    prestamo = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if prestamo.estado in ["pagado", "perdido", "renovado"]:
        raise HTTPException(status_code=400, detail=f"No se puede marcar como perdido un prestamo en estado {prestamo.estado}")

    valor_perdido = prestamo.saldo_pendiente

    try:
        perdido = PrestamoPerdido(
            prestamo_id=prestamo.id,
            fecha=datos.fecha,
            valor_perdido=valor_perdido,
            motivo=datos.motivo
        )
        db.add(perdido)

        prestamo.estado = "perdido"

        capital_obj = db.query(Capital).first()
        if capital_obj:
            capital_obj.monto_total -= valor_perdido

        movimiento = MovimientoCapital(
            tipo_movimiento="perdida",
            descripcion=f"Prestamo {prestamo.id} marcado como perdido",
            valor=valor_perdido,
            fecha=datos.fecha,
            prestamo_id=prestamo.id
        )
        db.add(movimiento)

        db.commit()
        db.refresh(prestamo)
        return {
            "prestamo": prestamo,
            "valor_perdido": valor_perdido,
            "motivo": datos.motivo,
            "fecha": datos.fecha  
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al marcar prestamo como perdido: {str(e)}")

def ajustar_capital_prestamo(db: Session, prestamo_id: int, nuevo_capital: float, usuario_id: int):
    db_prestamo = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not db_prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    
    if db_prestamo.estado != "activo":
        raise HTTPException(status_code=400, detail="Solo se pueden ajustar préstamos activos")
    
    diferencia = nuevo_capital - db_prestamo.capital_prestado
    
    if diferencia > 0:
        capital = db.query(Capital).first()
        if not capital or capital.monto_total < diferencia:
            raise HTTPException(status_code=400, detail="Capital insuficiente para el ajuste")
    
    capital_anterior = db_prestamo.capital_prestado
    db_prestamo.capital_prestado = nuevo_capital
    
    db_prestamo.interes_total = round(
        nuevo_capital * (db_prestamo.porcentaje_interes / 100) * db_prestamo.numero_cuotas, 2
    )
    db_prestamo.monto_total = round(nuevo_capital + db_prestamo.interes_total, 2)
    db_prestamo.valor_cuota = round(db_prestamo.monto_total / db_prestamo.numero_cuotas, 2)
    db_prestamo.saldo_pendiente = db_prestamo.monto_total
    
    cuotas = db.query(PrestamoCuota).filter(
        PrestamoCuota.prestamo_id == prestamo_id,
        PrestamoCuota.estado == "pendiente"
    ).all()
    
    for cuota in cuotas:
        cuota.valor_cuota = db_prestamo.valor_cuota
        cuota.monto_interes = round(db_prestamo.interes_total / db_prestamo.numero_cuotas, 2)
        cuota.capital = round(nuevo_capital / db_prestamo.numero_cuotas, 2)
        cuota.interes = round(db_prestamo.interes_total / db_prestamo.numero_cuotas, 2)
    
    capital = db.query(Capital).first()
    capital.monto_total -= diferencia
    
    if diferencia != 0:
        movimiento = MovimientoCapital(
            tipo_movimiento="prestamo_otorgado" if diferencia > 0 else "retiro",
            descripcion=f"Ajuste de capital en préstamo #{prestamo_id}: ${capital_anterior:,.2f} → ${nuevo_capital:,.2f}",
            valor=abs(diferencia),
            fecha=date.today(),
            prestamo_id=prestamo_id
        )
        db.add(movimiento)
    
    db.commit()
    db.refresh(db_prestamo)
    
    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="prestamos",
        tipo_operacion="UPDATE",
        registro_id=prestamo_id,
        valores_anteriores={
            "capital_prestado": capital_anterior
        },
        valores_nuevos={
            "capital_prestado": db_prestamo.capital_prestado,
            "monto_total": db_prestamo.monto_total,
            "valor_cuota": db_prestamo.valor_cuota
        },
        descripcion=f"Capital ajustado: ${capital_anterior:,.2f} → ${nuevo_capital:,.2f}"
    )
    
    return db_prestamo