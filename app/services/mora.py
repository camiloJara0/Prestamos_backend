from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.models import Mora, PrestamoCuota, Pago, ConfiguracionSistema
from app.schemas.mora import MoraCreate, MoraUpdate, MoraOut
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


def get_moras(db: Session, skip: int = 0, limit: int = 10):
    return db.query(Mora).filter(Mora.estado == "generada").order_by(Mora.fecha.desc()).offset(skip).limit(limit).all()

def get_moras_prestamo(db: Session, prestamo_id: int):
    return db.query(Mora).filter(Mora.prestamo_id == prestamo_id).order_by(Mora.fecha.desc()).all()

def get_mora(db: Session, mora_id: int):
    return db.query(Mora).filter(Mora.id == mora_id).first()

def update_mora(db: Session, mora_id: int, mora: MoraUpdate):
    db_mora = get_mora(db, mora_id)
    if not db_mora:
        return None
    for key, value in mora.dict(exclude_unset=True).items():
        setattr(db_mora, key, value)
    db.commit()
    db.refresh(db_mora)
    return db_mora

def delete_mora(db: Session, mora_id: int):
    db_mora = get_mora(db, mora_id)
    if db_mora:
        db.delete(db_mora)
        db.commit()
    return db_mora

def calcular_mora(db: Session, cuota: PrestamoCuota, pago: Pago = None) -> Mora | None:
    """
    Calcula mora para una cuota usando parámetros de ConfiguracionSistema.
    - tasa_mora_diaria: porcentaje diario de mora
    - dias_gracia_mora: días de gracia antes de aplicar mora
    """
    
    # Obtener parámetros del sistema
    tasa_diaria = obtener_parametro_config(db, "tasa_mora_diaria", "0.5") / 100  # Convertir de porcentaje a decimal
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
    
    # Calcular valor de mora
    valor_mora = cuota.valor_cuota * tasa_diaria * dias_atraso
    
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
            valores_nuevas={
                "cuota_id": mora.cuota_id,
                "prestamo_id": mora.prestamo_id,
                "valor": mora.valor,
                "estado": mora.estado
            },
            descripcion=f"Mora generada automáticamente para cuota #{mora.cuota_id}"
        )
        
        return mora

def procesar_moras(db: Session, tasa_diaria: float = None):
    """
    Procesa moras para todas las cuotas vencidas.
    Si no se proporciona tasa_diaria, se obtiene de ConfiguracionSistema.
    """
    
    # Si se proporciona tasa_diaria explícitamente, usarla; sino, leer de configuración
    if tasa_diaria is None:
        tasa_diaria = obtener_parametro_config(db, "tasa_mora_diaria", "0.5") / 100
    else:
        tasa_diaria = tasa_diaria / 100  # Convertir de porcentaje a decimal
    
    # Obtener solo cuotas no pagadas
    cuotas = db.query(PrestamoCuota).filter(PrestamoCuota.estado != "pagado").all()
    moras_generadas = []
    
    for cuota in cuotas:
        pago = db.query(Pago).filter(Pago.cuota_id == cuota.id).first()
        mora = calcular_mora(db, cuota, pago)
        if mora:
            moras_generadas.append(mora)
    
    return moras_generadas