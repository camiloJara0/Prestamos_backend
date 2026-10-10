# Servicio de prestamos : maneja la logica de creacion de prestamos
# calcula interes, monto total, genera cuotas y registra movimiento de capital
# usa transacciones para garantizar consistencia en la DB

import secrets
import string

from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import or_, func

from app.models.models import Prestamo, PrestamoCuota, MovimientoCapital, Capital, Cliente, TipoPrestamo, PrestamoRenovacion, PrestamoPerdido, PrestamoReestructuracion, Mora, Pago
from app.schemas.prestamo import PrestamoCreate
from app.services.capital import get_or_create_capital
from app.utils.pagination import paginate


def generar_referencia_unica_cuota(prestamo_id: int, numero_cuota: int) -> str:
    """
    Genera un código de referencia de pago único e impredecible para cada cuota.
    Ejemplo de salida: REF-P12C1-9F2B
    """
    caracteres = string.ascii_uppercase + string.digits
    hash_aleatorio = ''.join(secrets.choice(caracteres) for _ in range(4))
    return f"REF-P{prestamo_id}C{numero_cuota}-{hash_aleatorio}"


def fecha_vencimiento_cuota(
    fecha_base: date,
    numero_cuota: int,
    intervalo_pago: str | None = "mensual",
    intervalo_dias: int | None = None,
) -> date:
    """RF-076: fecha de vencimiento de la cuota según el intervalo de cobro del tipo de préstamo."""
    intervalo = intervalo_pago or "mensual"
    if intervalo == "quincenal":
        return fecha_base + timedelta(days=15 * numero_cuota)
    if intervalo == "bimestral":
        return fecha_base + relativedelta(months=2 * numero_cuota)
    if intervalo == "personalizado":
        return fecha_base + timedelta(days=(intervalo_dias or 30) * numero_cuota)
    return fecha_base + relativedelta(months=numero_cuota)


def crear_prestamo(db: Session, prestamo: PrestamoCreate, usuario_id: int, ip_address: str | None = None):
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
        fecha_vencimiento = fecha_vencimiento_cuota(
            date.today(), i, tipo_prestamo.intervalo_pago, tipo_prestamo.intervalo_dias
        )
        
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
            referencia_pago=generar_referencia_unica_cuota(db_prestamo.id, i),  # <-- REFERENCIA AUTO-GENERADA
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
        descripcion=f"Préstamo creado para cliente {cliente.nombre}",
        ip_address=ip_address,
    )

    _correo_prestamo_creado(db, db_prestamo, cliente, usuario_id)

    return db_prestamo


def _correo_prestamo_creado(db: Session, prestamo, cliente, usuario_id: int) -> None:
    """RF-061: aviso por correo de la creación del préstamo; un fallo no revierte la operación."""
    try:
        from app.models.models import Usuario
        from app.services.canales import enviar_por_canal

        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            return
        enviar_por_canal(
            db,
            canal="email",
            destinatario=usuario.email,
            clave="prestamo_creado",
            contexto={
                "nombre": cliente.nombre.split()[0] if cliente.nombre else "cliente",
                "prestamo_id": prestamo.id,
                "monto": f"{prestamo.capital_prestado:,.0f}",
                "numero_cuotas": prestamo.numero_cuotas,
            },
        )
    except Exception:  # noqa: BLE001 - el fallo de correo no revierte la creación
        pass


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
    return (
        db.query(Prestamo)
        .options(
            selectinload(Prestamo.cliente),
            selectinload(Prestamo.tipo_prestamo),
            selectinload(Prestamo.cuotas),
            selectinload(Prestamo.pagos),
        )
        .filter(Prestamo.id == prestamo_id)
        .first()
    )


def renovar_prestamo(db: Session, prestamo_id: int, renovacion, usuario_id=None, ip_address: str | None = None):
    prestamo_original = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not prestamo_original:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    if prestamo_original.estado in ["pagado", "perdido", "renovado"]:
        raise HTTPException(status_code=400, detail=f"No se puede renovar un prestamo en estado {prestamo_original.estado}")

    tipo_renovacion = db.query(TipoPrestamo).filter(TipoPrestamo.id == prestamo_original.tipo_prestamo_id).first()

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
            fecha_vencimiento = fecha_vencimiento_cuota(
                renovacion.fecha_renovacion, i,
                tipo_renovacion.intervalo_pago if tipo_renovacion else None,
                tipo_renovacion.intervalo_dias if tipo_renovacion else None,
            )
            
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
                referencia_pago=generar_referencia_unica_cuota(nuevo_prestamo.id, i),  # <-- REFERENCIA AUTO-GENERADA EN RENOVACIÓN
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

        from app.services.auditoria import registrar_auditoria
        registrar_auditoria(
            db,
            usuario_id=usuario_id,
            tabla_afectada="prestamos_renovaciones",
            tipo_operacion="CREATE",
            registro_id=renovacion_registro.id,
            valores_nuevos={
                "prestamo_anterior_id": prestamo_original.id,
                "prestamo_nuevo_id": nuevo_prestamo.id,
                "capital_nuevo": capital_nuevo,
                "abono": abono,
            },
            descripcion=f"Renovación del préstamo #{prestamo_original.id} → nuevo préstamo #{nuevo_prestamo.id}",
            ip_address=ip_address,
        )
        return nuevo_prestamo

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al renovar el prestamo: {str(e)}")


def marcar_prestamo_perdido(db: Session, prestamo_id: int, datos, usuario_id=None, ip_address: str | None = None):
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

        from app.services.auditoria import registrar_auditoria
        registrar_auditoria(
            db,
            usuario_id=usuario_id,
            tabla_afectada="prestamos_perdidos",
            tipo_operacion="CREATE",
            registro_id=perdido.id,
            valores_nuevos={
                "prestamo_id": prestamo.id,
                "valor_perdido": valor_perdido,
                "motivo": datos.motivo,
            },
            descripcion=f"Préstamo #{prestamo.id} declarado perdido",
            ip_address=ip_address,
        )
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


def ajustar_capital_prestamo(db: Session, prestamo_id: int, nuevo_capital: float, usuario_id: int, ip_address: str | None = None):
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

    # El saldo pendiente descuenta lo ya efectivamente pagado (RF-034)
    pagado_no_devuelto = (
        db.query(func.coalesce(func.sum(Pago.capital_pagado + Pago.interes_pagado), 0.0))
        .filter(Pago.prestamo_id == prestamo_id, Pago.estado_pago != "devuelto")
        .scalar()
    )
    db_prestamo.saldo_pendiente = max(0.0, round(db_prestamo.monto_total - pagado_no_devuelto, 2))
    
    cuotas = db.query(PrestamoCuota).filter(
        PrestamoCuota.prestamo_id == prestamo_id,
        PrestamoCuota.estado.in_(["pendiente", "vencido"])
    ).all()
    
    for cuota in cuotas:
        cuota.valor_cuota = db_prestamo.valor_cuota
        cuota.monto_interes = round(db_prestamo.interes_total / db_prestamo.numero_cuotas, 2)
        cuota.capital = round(nuevo_capital / db_prestamo.numero_cuotas, 2)
        cuota.interes = round(db_prestamo.interes_total / db_prestamo.numero_cuotas, 2)
    
    capital = db.query(Capital).first()
    if capital is not None and diferencia != 0:
        capital.monto_total = round(capital.monto_total - diferencia, 2)
    
    if diferencia != 0:
        movimiento = MovimientoCapital(
            tipo_movimiento="ajuste_prestamo",
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
        descripcion=f"Capital ajustado: ${capital_anterior:,.2f} → ${nuevo_capital:,.2f}",
        ip_address=ip_address,
    )
    
    return db_prestamo


def reestructurar_prestamo(db: Session, prestamo_id: int, datos, usuario_id: int, ip_address: str | None = None):
    """
    Renegocia plazo e interés de un préstamo en mora generando un plan de cuotas
    nuevo vinculado al préstamo original, sin cancelar el histórico (RF-035).
    """
    prestamo = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
    if not prestamo:
        raise HTTPException(status_code=404, detail="Préstamo no encontrado")
    if prestamo.estado != "activo":
        raise HTTPException(status_code=400, detail=f"No se puede reestructurar un préstamo en estado {prestamo.estado}")

    tipo_reestructuracion = db.query(TipoPrestamo).filter(TipoPrestamo.id == prestamo.tipo_prestamo_id).first()

    hoy = date.today()

    cuotas_vencidas = db.query(PrestamoCuota).filter(
        PrestamoCuota.prestamo_id == prestamo_id,
        PrestamoCuota.estado.in_(["vencido", "parcial"]),
        PrestamoCuota.fecha_vencimiento < hoy,
    ).count()
    moras_generadas = db.query(Mora).filter(
        Mora.prestamo_id == prestamo_id, Mora.estado == "generada"
    ).count()
    if cuotas_vencidas == 0 and moras_generadas == 0:
        raise HTTPException(
            status_code=400,
            detail="El préstamo no tiene cuotas vencidas; la reestructuración aplica solo a préstamos en mora",
        )

    # Una reestructuración múltiple exige cerrar la anterior (RF-035)
    activa = (
        db.query(PrestamoReestructuracion)
        .filter(
            PrestamoReestructuracion.prestamo_id == prestamo_id,
            PrestamoReestructuracion.estado == "activa",
        )
        .first()
    )
    if activa:
        activa.estado = "cerrada"

    # Absorber del plan a generar todas las cuotas sin pagos (se reemplazan)
    cuotas_previas = (
        db.query(PrestamoCuota)
        .filter(
            PrestamoCuota.prestamo_id == prestamo_id,
            PrestamoCuota.estado.in_(["pendiente", "vencido"]),
        )
        .all()
    )
    ids_con_pago = {
        fila[0]
        for fila in db.query(Pago.cuota_id)
        .filter(Pago.cuota_id.in_([c.id for c in cuotas_previas]))
        .distinct()
        .all()
    } if cuotas_previas else set()
    ids_eliminar = [c.id for c in cuotas_previas if c.id not in ids_con_pago]

    if ids_eliminar:
        db.query(Mora).filter(Mora.cuota_id.in_(ids_eliminar)).update(
            {"estado": "cancelada"}, synchronize_session=False
        )
        db.query(PrestamoCuota).filter(PrestamoCuota.id.in_(ids_eliminar)).delete(
            synchronize_session=False
        )

    # Cuotas parciales conservadas: su residual sigue exigible y no se refinancia
    parciales = (
        db.query(PrestamoCuota)
        .filter(PrestamoCuota.prestamo_id == prestamo_id, PrestamoCuota.estado == "parcial")
        .all()
    )
    pagado_por_cuota = dict(
        db.query(Pago.cuota_id, func.coalesce(func.sum(Pago.valor_pagado), 0.0))
        .filter(
            Pago.cuota_id.in_([c.id for c in parciales]),
            Pago.estado_pago != "devuelto",
        )
        .group_by(Pago.cuota_id)
        .all()
    ) if parciales else {}
    residuales = round(
        sum(max(c.valor_cuota - pagado_por_cuota.get(c.id, 0.0), 0.0) for c in parciales), 2
    )

    saldo_anterior = round(prestamo.saldo_pendiente, 2)
    base = round(max(saldo_anterior - residuales, 0.0), 2)
    if base <= 0:
        raise HTTPException(status_code=400, detail="No hay saldo pendiente para reestructurar")

    interes_nuevo = round(base * (datos.porcentaje_interes / 100) * datos.numero_cuotas, 2)
    plan_total = round(base + interes_nuevo, 2)

    pagado_total = round(prestamo.monto_total - saldo_anterior, 2)
    prestamo.interes_total = round(prestamo.interes_total + interes_nuevo, 2)
    prestamo.saldo_pendiente = round(residuales + plan_total, 2)
    prestamo.monto_total = round(pagado_total + prestamo.saldo_pendiente, 2)
    prestamo.porcentaje_interes = datos.porcentaje_interes
    prestamo.valor_cuota = round(plan_total / datos.numero_cuotas, 2)

    reestructuracion = PrestamoReestructuracion(
        prestamo_id=prestamo_id,
        fecha=hoy,
        motivo=datos.motivo,
        saldo_anterior=saldo_anterior,
        numero_cuotas=datos.numero_cuotas,
        porcentaje_interes=datos.porcentaje_interes,
        valor_cuota=prestamo.valor_cuota,
        monto_plan=plan_total,
        estado="activa",
    )
    db.add(reestructuracion)
    db.flush()

    max_numero = (
        db.query(func.max(PrestamoCuota.numero_cuota))
        .filter(PrestamoCuota.prestamo_id == prestamo_id)
        .scalar()
        or 0
    )

    capital_regular = round(base / datos.numero_cuotas, 2)
    interes_regular = round(interes_nuevo / datos.numero_cuotas, 2)
    for i in range(datos.numero_cuotas):
        if i == datos.numero_cuotas - 1:
            val_capital = round(base - capital_regular * (i), 2)
            val_interes = round(interes_nuevo - interes_regular * (i), 2)
        else:
            val_capital = capital_regular
            val_interes = interes_regular
        numero = max_numero + i + 1
        db.add(PrestamoCuota(
            prestamo_id=prestamo_id,
            numero_cuota=numero,
            fecha_vencimiento=fecha_vencimiento_cuota(
                datos.fecha_inicio, i,
                tipo_reestructuracion.intervalo_pago if tipo_reestructuracion else None,
                tipo_reestructuracion.intervalo_dias if tipo_reestructuracion else None,
            ),
            valor_cuota=round(val_capital + val_interes, 2),
            monto_interes=val_interes,
            capital=val_capital,
            interes=val_interes,
            mora=0.0,
            estado="pendiente",
            referencia_pago=generar_referencia_unica_cuota(prestamo_id, numero),
            reestructuracion_id=reestructuracion.id,
        ))

    db.commit()
    db.refresh(reestructuracion)

    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="prestamos_reestructuraciones",
        tipo_operacion="CREATE",
        registro_id=reestructuracion.id,
        valores_nuevos={
            "prestamo_id": prestamo_id,
            "saldo_anterior": saldo_anterior,
            "numero_cuotas": datos.numero_cuotas,
            "porcentaje_interes": datos.porcentaje_interes,
            "monto_plan": plan_total,
        },
        descripcion=(
            f"Reestructuración del préstamo #{prestamo_id}: {datos.numero_cuotas} cuotas al "
            f"{datos.porcentaje_interes}% — motivo: {datos.motivo}"
        ),
        ip_address=ip_address,
    )

    return reestructuracion