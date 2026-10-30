from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.models import Mora, PrestamoCuota, Pago, ConfiguracionSistema
from app.schemas.mora import MoraCreate, MoraUpdate, MoraOut
from app.core.context import aplicar_filtro_usuario
from datetime import date, timedelta


def obtener_parametro_config(db: Session, clave: str, default_value: str = "0.0") -> float:
    """Obtiene un parámetro de configuración del sistema, retorna float"""
    config = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == clave,
        ConfiguracionSistema.activo == True
    ).first()
    
    if config:
        try:
            return float(config.valor)
        except ValueError:
            return float(default_value)
    return float(default_value)


def obtener_parametro_texto(db: Session, clave: str, default_value: str = "") -> str:
    """Obtiene un parámetro de configuración del sistema como texto."""
    config = db.query(ConfiguracionSistema).filter(
        ConfiguracionSistema.clave == clave,
        ConfiguracionSistema.activo == True
    ).first()
    if config and config.valor is not None:
        return str(config.valor).strip()
    return default_value


def valor_mora_diaria(db: Session, cuota: PrestamoCuota, tasa_forzada: float | None = None) -> float:
    """Mora diaria según el modo configurado (RF: porcentaje o valor fijo).

    - mora_tipo = "porcentaje" (default): cuota.valor_cuota * (tasa_mora_diaria / 100)
    - mora_tipo = "fijo": mora_valor_fijo por día de atraso (ej. 3000)
    """
    if tasa_forzada is not None:
        return cuota.valor_cuota * (tasa_forzada / 100)

    modo = obtener_parametro_texto(db, "mora_tipo", "porcentaje").lower()
    if modo == "fijo":
        return obtener_parametro_config(db, "mora_valor_fijo", "0.0")
    tasa_diaria = obtener_parametro_config(db, "tasa_mora_diaria", "0.5") / 100
    return cuota.valor_cuota * tasa_diaria


def get_moras(db: Session, page: int = 1, limit: int = 10):
    """Obtiene las moras en estado generada con paginación B11."""
    query = aplicar_filtro_usuario(db.query(Mora), Mora).filter(Mora.estado == "generada")
    total = query.count()
    offset = (page - 1) * limit
    items = query.order_by(Mora.fecha.desc()).offset(offset).limit(limit).all()
    pages = (total + limit - 1) // limit if total > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit
    }

def get_moras_prestamo(db: Session, prestamo_id: int):
    """Moras en estado generada de un préstamo, más recientes primero (RF-045)."""
    return (
        db.query(Mora)
        .filter(Mora.prestamo_id == prestamo_id, Mora.estado == "generada")
        .order_by(Mora.fecha.desc())
        .all()
    )

def get_mora(db: Session, mora_id: int):
    return aplicar_filtro_usuario(db.query(Mora), Mora).filter(Mora.id == mora_id).first()

def update_mora(db: Session, mora_id: int, mora: MoraUpdate, usuario_id=None, ip_address: str | None = None):
    db_mora = get_mora(db, mora_id)
    if not db_mora:
        return None
    anteriores = {"valor": db_mora.valor, "estado": db_mora.estado, "fecha": str(db_mora.fecha)}
    for key, value in mora.dict(exclude_unset=True).items():
        setattr(db_mora, key, value)
    db.commit()
    db.refresh(db_mora)

    from app.services.auditoria import registrar_auditoria
    registrar_auditoria(
        db,
        usuario_id=usuario_id,
        tabla_afectada="moras",
        tipo_operacion="UPDATE",
        registro_id=db_mora.id,
        valores_anteriores=anteriores,
        valores_nuevos={"valor": db_mora.valor, "estado": db_mora.estado, "fecha": str(db_mora.fecha)},
        descripcion=f"Mora #{db_mora.id} editada manualmente",
        ip_address=ip_address,
    )
    return db_mora

def delete_mora(db: Session, mora_id: int, usuario_id=None, ip_address: str | None = None):
    db_mora = get_mora(db, mora_id)
    if db_mora:
        anteriores = {
            "prestamo_id": db_mora.prestamo_id,
            "cuota_id": db_mora.cuota_id,
            "valor": db_mora.valor,
            "estado": db_mora.estado,
        }
        registro_id = db_mora.id
        db.delete(db_mora)
        db.commit()

        from app.services.auditoria import registrar_auditoria
        registrar_auditoria(
            db,
            usuario_id=usuario_id,
            tabla_afectada="moras",
            tipo_operacion="DELETE",
            registro_id=registro_id,
            valores_anteriores=anteriores,
            descripcion=f"Mora #{registro_id} eliminada manualmente",
            ip_address=ip_address,
        )
    return db_mora

def calcular_mora(db: Session, cuota: PrestamoCuota, pago: Pago = None, tasa_forzada: float | None = None) -> Mora | None:
    """
    Calcula mora para una cuota usando parámetros de ConfiguracionSistema.
    - tasa_mora_diaria: porcentaje diario de mora
    - dias_gracia_mora: días de gracia antes de aplicar mora
    """
    
    # Obtener parámetros del sistema
    dias_gracia = int(obtener_parametro_config(db, "dias_gracia_mora", "3"))
    
    # Si cuota está pagada, no hay mora
    if cuota.estado == "pagado":
        return None
    
    # Si la fecha de vencimiento aún no llegó, no hay mora
    if cuota.fecha_vencimiento >= date.today():
        return None
    
    # Calcular días de atraso considerando días de gracia
    fecha_inicio_mora = cuota.fecha_vencimiento + timedelta(days=dias_gracia)
    if date.today() <= fecha_inicio_mora:
        return None  # Aún estamos dentro del período de gracia
    
    dias_atraso = (date.today() - fecha_inicio_mora).days
    
    # Caso especial: cuota parcial pero intereses ya cubiertos
    if cuota.estado == "parcial" and pago and pago.interes_pagado == cuota.interes:
        return None
    
    # Calcular valor de mora (modo porcentaje o valor fijo)
    valor_mora = valor_mora_diaria(db, cuota, tasa_forzada=tasa_forzada) * dias_atraso
    
    # Buscar si ya existe una mora registrada para esta cuota
    mora_existente = (
        db.query(Mora)
        .filter(Mora.cuota_id == cuota.id, Mora.estado == "generada")
        .first()
    )
    
    if mora_existente:
        # Actualizar valor y fecha
        mora_existente.valor = valor_mora
        mora_existente.fecha = date.today()
        db.add(mora_existente)
        db.commit()
        return mora_existente
    else:
        # Crear nueva mora
        mora = Mora(
            prestamo_id=cuota.prestamo_id,
            cuota_id=cuota.id,
            fecha=date.today(),
            valor=valor_mora,
            estado="generada"
        )
        # Cambiar estado de cuota a vencido
        cuota.estado = "vencido"
        db.add(mora)
        db.commit()
        
        # Registrar en auditoria
        from app.services.auditoria import registrar_auditoria
        registrar_auditoria(
            db,
            usuario_id=1,  # Sistema
            tabla_afectada="moras",
            tipo_operacion="CREATE",
            registro_id=mora.id,
            valores_nuevos={
                "cuota_id": mora.cuota_id,
                "prestamo_id": mora.prestamo_id,
                "valor": mora.valor,
                "estado": mora.estado
            },
            descripcion=f"Mora generada automáticamente para cuota #{mora.cuota_id}"
        )

        try:
            from app.services.eventos_mensajeria import notificar_mora_aviso
            notificar_mora_aviso(db, cuota, valor_mora, dias_atraso)
        except Exception:  # noqa: BLE001 - la mensajería no revierte la mora
            pass

        return mora

def procesar_moras(db: Session, tasa_diaria: float = None):
    """
    Procesa moras para todas las cuotas vencidas.
    Si se proporciona tasa_diaria explícitamente se usa como porcentaje;
    si no, cada cuota lee su modo de mora (porcentaje o fijo) de configuración.
    """
    cuotas = db.query(PrestamoCuota).filter(PrestamoCuota.estado != "pagado").all()
    moras_generadas = []

    for cuota in cuotas:
        pago = db.query(Pago).filter(Pago.cuota_id == cuota.id).first()
        # modo fijo no se ve afectado por la tasa explícita (es un valor por día)
        modo = obtener_parametro_texto(db, "mora_tipo", "porcentaje").lower()
        if tasa_diaria is not None and modo != "fijo":
            cuota_valor_forzado = tasa_diaria
        else:
            cuota_valor_forzado = None
        mora = calcular_mora(db, cuota, pago, tasa_forzada=cuota_valor_forzado)
        if mora:
            moras_generadas.append(mora)
    
    return moras_generadas