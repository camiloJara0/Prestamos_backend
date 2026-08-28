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
from datetime import date
from dateutil.relativedelta import relativedelta


def crear_prestamo(db: Session, prestamo: PrestamoCreate, usuario_id: int):
    """
    Crea un nuevo préstamo con validación de cuotas vencidas.
    Valida que el cliente no tenga cuotas vencidas sin pagar.
    """
    
    # Validar que el cliente exista
    cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id, Cliente.estado == "activo").first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado o inactivo")
    
    # VALIDACIÓN: Verificar que el cliente no tenga cuotas vencidas sin pagar
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
    
    # Validar que el tipo de préstamo exista
    tipo_prestamo = db.query(TipoPrestamo).filter(
        TipoPrestamo.id == prestamo.tipo_prestamo_id,
        TipoPrestamo.estado == "activo"
    ).first()
    if not tipo_prestamo:
        raise HTTPException(status_code=404, detail="Tipo de préstamo no encontrado o inactivo")
    
    # Obtener capital disponible
    capital = db.query(Capital).first()
    if not capital or capital.monto_total < prestamo.capital_prestado:
        raise HTTPException(status_code=400, detail="Capital insuficiente para otorgar el préstamo")
    
    # Crear el préstamo
    db_prestamo = Prestamo(
        cliente_id=prestamo.cliente_id,
        tipo_prestamo_id=prestamo.tipo_prestamo_id,
        fecha_prestamo=date.today(),
        capital_prestado=prestamo.capital_prestado,
        porcentaje_interes=prestamo.porcentaje_interes,
        numero_cuotas=prestamo.numero_cuotas,
        estado="activo"
    )
    
    # Cálculos financieros
    db_prestamo.interes_total = round(
        prestamo.capital_prestado * (prestamo.porcentaje_interes / 100) * prestamo.numero_cuotas, 2
    )
    db_prestamo.monto_total = round(prestamo.capital_prestado + db_prestamo.interes_total, 2)
    db_prestamo.valor_cuota = round(db_prestamo.monto_total / prestamo.numero_cuotas, 2)
    db_prestamo.saldo_pendiente = db_prestamo.monto_total
    
    db.add(db_prestamo)
    db.flush()
    
    # Generar cuotas
    for i in range(1, prestamo.numero_cuotas + 1):
        fecha_vencimiento = date.today() + relativedelta(months=i)
        cuota = PrestamoCuota(
            prestamo_id=db_prestamo.id,
            numero_cuota=i,
            fecha_vencimiento=fecha_vencimiento,
            valor_cuota=db_prestamo.valor_cuota,
            monto_interes=round(db_prestamo.interes_total / prestamo.numero_cuotas, 2),
            capital=round(prestamo.capital_prestado / prestamo.numero_cuotas, 2),
            interes=round(db_prestamo.interes_total / prestamo.numero_cuotas, 2),
            mora=0.0,
            estado="pendiente"
        )
        db.add(cuota)
    
    # Actualizar capital
    capital.monto_total -= prestamo.capital_prestado
    movimiento = MovimientoCapital(
        tipo_movimiento="prestamo_otorgado",
        descripcion=f"Préstamo #{db_prestamo.id} al cliente {cliente.nombre}",
        valor=prestamo.capital_prestado,
        fecha=date.today()
    )
    db.add(movimiento)
    
    db.commit()
    db.refresh(db_prestamo)
    return db_prestamo

def get_prestamos(db: Session, skip: int = 0, limit: int = 10, estado: str = "activo",
                  cliente_id: int = None, fecha_desde: date = None, fecha_hasta: date = None,
                  busqueda: str = None):
    """Lista préstamos con filtros.

    - estado: "activo" (default) o cualquier estado ("pagado", "perdido", "renovado"). Usar "todos" para todos.
    - cliente_id: filtra por cliente.
    - fecha_desde / fecha_hasta: rango de fechas de otorgamiento.
    - busqueda: busca por nombre o cédula del cliente.
    """
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
    return query.order_by(Prestamo.id.desc()).offset(skip).limit(limit).all()


def obtener_prestamo(db: Session, prestamo_id: int):
    """Devuelve un préstamo con sus relaciones cargadas (cliente, tipo, cuotas y pagos)."""
    return db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()

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
    
def marcar_prestamo_perdido(db: Session, prestamo_id: int, datos):
    # Busca el prestamo y valida que exista y este activo
    prestamo = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if prestamo.estado in ["pagado", "perdido", "renovado"]:
        raise HTTPException(status_code=400, detail=f"No se puede marcar como perdido un prestamo en estado {prestamo.estado}")

    valor_perdido = prestamo.saldo_pendiente

    try:
        # Registra en prestamos_perdidos
        from app.models.models import PrestamoPerdido
        perdido = PrestamoPerdido(
            prestamo_id=prestamo.id,
            fecha=datos.fecha,
            valor_perdido=valor_perdido,
            motivo=datos.motivo
        )
        db.add(perdido)

        # Actualiza estado del prestamo
        prestamo.estado = "perdido"

        # Registra impacto en movimientos de capital
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
        return  {
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

def ajustar_capital_prestamo(db: Session, prestamo_id: int, nuevo_capital: float):
    """
    Ajusta el capital de un préstamo y recalcula todas las cuotas.
    Solo puede ser usado por administradores para correcciones.
    """
    
    # Obtener el préstamo
    db_prestamo = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not db_prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    
    if db_prestamo.estado != "activo":
        raise HTTPException(status_code=400, detail="Solo se pueden ajustar préstamos activos")
    
    # Diferencia entre nuevo y viejo capital
    diferencia = nuevo_capital - db_prestamo.capital_prestado
    
    # Validar que haya capital disponible si aumenta
    if diferencia > 0:
        capital = db.query(Capital).first()
        if not capital or capital.monto_total < diferencia:
            raise HTTPException(status_code=400, detail="Capital insuficiente para el ajuste")
    
    # Actualizar capital del préstamo
    capital_anterior = db_prestamo.capital_prestado
    db_prestamo.capital_prestado = nuevo_capital
    
    # Recalcular valores
    db_prestamo.interes_total = round(
        nuevo_capital * (db_prestamo.porcentaje_interes / 100) * db_prestamo.numero_cuotas, 2
    )
    db_prestamo.monto_total = round(nuevo_capital + db_prestamo.interes_total, 2)
    db_prestamo.valor_cuota = round(db_prestamo.monto_total / db_prestamo.numero_cuotas, 2)
    db_prestamo.saldo_pendiente = db_prestamo.monto_total
    
    # Actualizar todas las cuotas
    cuotas = db.query(PrestamoCuota).filter(
        PrestamoCuota.prestamo_id == prestamo_id,
        PrestamoCuota.estado == "pendiente"
    ).all()
    
    for cuota in cuotas:
        cuota.valor_cuota = db_prestamo.valor_cuota
        cuota.monto_interes = round(db_prestamo.interes_total / db_prestamo.numero_cuotas, 2)
        cuota.capital = round(nuevo_capital / db_prestamo.numero_cuotas, 2)
        cuota.interes = round(db_prestamo.interes_total / db_prestamo.numero_cuotas, 2)
    
    # Actualizar capital disponible
    capital = db.query(Capital).first()
    capital.monto_total -= diferencia
    
    # Registrar movimiento
    if diferencia != 0:
        movimiento = MovimientoCapital(
            tipo_movimiento="ajuste_prestamo",
            descripcion=f"Ajuste de capital en préstamo #{prestamo_id}: ${capital_anterior:,.2f} → ${nuevo_capital:,.2f}",
            valor=abs(diferencia),
            fecha=date.today()
        )
        db.add(movimiento)
    
    db.commit()
    db.refresh(db_prestamo)
    return db_prestamo