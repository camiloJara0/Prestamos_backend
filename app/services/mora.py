from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.models.models import Mora, Prestamo, PrestamoCuota, Pago
from app.schemas.mora import MoraCreate, MoraUpdate, MoraOut
from app.core.context import aplicar_filtro_usuario
from datetime import date, timedelta


def obtener_parametro_config(db: Session, clave: str, default_value: str = "0.0") -> float:
    """Obtiene un parámetro de configuración (override del usuario → global), retorna float"""
    from app.services.configuracion import resolver_parametro

    valor, _origen = resolver_parametro(db, clave, default_value)
    if valor is None:
        return float(default_value)
    try:
        return float(valor)
    except ValueError:
        return float(default_value)


def obtener_parametro_texto(db: Session, clave: str, default_value: str = "") -> str:
    """Obtiene un parámetro de configuración (override del usuario → global) como texto."""
    from app.services.configuracion import resolver_parametro

    valor, _origen = resolver_parametro(db, clave, default_value)
    if valor is None:
        return default_value
    return str(valor).strip()


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


def parametros_mora(db: Session) -> dict:
    """Configuración de mora vigente del usuario (para calcular y mostrar)."""
    return {
        # 'porcentaje' (% de la cuota/día) o 'fijo' (monto por día)
        "modo": (obtener_parametro_texto(db, "mora_tipo", "porcentaje") or "porcentaje").lower(),
        # 'simple' (lineal) o 'compuesta' (interés sobre interés) — preparado
        # para futuras ampliaciones.
        "tipo": (obtener_parametro_texto(db, "mora_tipo_calculo", "simple") or "simple").lower(),
        "tasa_diaria_pct": obtener_parametro_config(db, "tasa_mora_diaria", "0.5"),
        "valor_fijo": obtener_parametro_config(db, "mora_valor_fijo", "0.0"),
        "dias_gracia": int(obtener_parametro_config(db, "dias_gracia_mora", "3")),
    }


def mora_vigente_cuota(
    db: Session,
    cuota: PrestamoCuota,
    hoy: date | None = None,
    parametros: dict | None = None,
) -> dict:
    """Mora acumulada AL DÍA DE HOY de una cuota, sin persistir nada.

    Es el cálculo en tiempo real que se muestra en el formulario de pago, el
    detalle del préstamo y las métricas. Respeta la configuración del usuario
    (días de gracia, porcentaje o valor fijo) y está preparada para mora
    simple o compuesta. No toca la base de datos.
    """
    hoy = hoy or date.today()
    p = parametros or parametros_mora(db)
    dias_gracia = p["dias_gracia"]

    dias_atraso = 0
    dias_mora = 0
    if cuota.estado != "pagado" and cuota.fecha_vencimiento and cuota.fecha_vencimiento < hoy:
        dias_atraso = (hoy - cuota.fecha_vencimiento).days
        inicio_mora = cuota.fecha_vencimiento + timedelta(days=dias_gracia)
        if hoy > inicio_mora:
            dias_mora = (hoy - inicio_mora).days

    if dias_mora <= 0:
        valor = 0.0
        valor_diario = 0.0
    elif p["modo"] == "fijo":
        valor_diario = p["valor_fijo"]
        valor = round(valor_diario * dias_mora, 2)
    else:
        base = cuota.valor_cuota or 0.0
        tasa = p["tasa_diaria_pct"] / 100
        valor_diario = round(base * tasa, 2)
        if p["tipo"] == "compuesta":
            valor = round(base * ((1 + tasa) ** dias_mora - 1), 2)
        else:
            valor = round(valor_diario * dias_mora, 2)

    return {
        "valor": valor,
        "valor_diario": valor_diario,
        "dias_atraso": dias_atraso,
        "dias_mora": dias_mora,
        "dias_gracia": dias_gracia,
        "en_gracia": dias_atraso > 0 and dias_mora == 0,
        "modo": p["modo"],
        "tipo": p["tipo"],
        "tasa_diaria_pct": p["tasa_diaria_pct"],
        "fecha_vencimiento": cuota.fecha_vencimiento,
    }


def mora_vigente_prestamo(
    db: Session,
    cuotas: list[PrestamoCuota],
    hoy: date | None = None,
) -> dict:
    """Mora vigente agregada de un conjunto de cuotas (mismo día, misma config)."""
    hoy = hoy or date.today()
    p = parametros_mora(db)
    detalle = [mora_vigente_cuota(db, c, hoy=hoy, parametros=p) for c in cuotas]
    return {
        "total": round(sum(m["valor"] for m in detalle), 2),
        "cuotas_con_mora": sum(1 for m in detalle if m["valor"] > 0),
        "parametros": p,
        "hoy": hoy.isoformat(),
    }


def mora_vigente_total(db: Session, hoy: date | None = None) -> dict:
    """Mora vigente de todas las cuotas vencidas sin pagar (dashboard/reportes).

    Se calcula en tiempo real con la configuración vigente, por lo que no
    depende de que el procesamiento diario haya corrido.
    """
    hoy = hoy or date.today()
    cuotas = (
        aplicar_filtro_usuario(
            db.query(PrestamoCuota).join(Prestamo, PrestamoCuota.prestamo_id == Prestamo.id),
            Prestamo,
        )
        .filter(
            PrestamoCuota.estado.in_(["pendiente", "vencido", "parcial"]),
            PrestamoCuota.fecha_vencimiento < hoy,
        )
        .all()
    )
    return mora_vigente_prestamo(db, cuotas, hoy=hoy)


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
    Persiste la mora de una cuota. El VALOR se obtiene con el mismo cálculo en
    vivo que muestran el formulario de pago, el detalle y las métricas
    (mora_vigente_cuota), de forma que lo registrado nunca diverge de lo
    mostrado. Respeta días de gracia, modo porcentaje/fijo y simple/compuesta.
    """
    # Si cuota está pagada, no hay mora
    if cuota.estado == "pagado":
        return None
    
    # Si la fecha de vencimiento aún no llegó, no hay mora
    if cuota.fecha_vencimiento >= date.today():
        return None
    
    # Caso especial: cuota parcial pero intereses ya cubiertos
    if cuota.estado == "parcial" and pago and pago.interes_pagado == cuota.interes:
        return None

    vigente = mora_vigente_cuota(db, cuota)
    if tasa_forzada is not None and vigente["dias_mora"] > 0:
        # Tasa alternativa forzada (procesamiento manual): sólo modo porcentaje.
        vigente["valor"] = round(cuota.valor_cuota * (tasa_forzada / 100) * vigente["dias_mora"], 2)

    # Aún en gracia o sin atraso: no se registra mora
    if vigente["dias_mora"] <= 0 or vigente["valor"] <= 0:
        return None

    valor_mora = vigente["valor"]
    dias_atraso = vigente["dias_atraso"]
    
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