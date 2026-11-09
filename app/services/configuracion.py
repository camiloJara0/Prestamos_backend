from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.context import usuario_actual_id, usuario_actual_rol
from app.models.models import ConfiguracionSistema, ConfiguracionUsuario
from app.schemas.configuracion import ConfiguracionCreate, ConfiguracionUpdate


def _uid_override() -> int | None:
    """Id del usuario si debe leer/escribir sus propios overrides (no admin)."""
    uid = usuario_actual_id.get()
    if uid and usuario_actual_rol.get() != "admin":
        return uid
    return None


def override_parametro(db: Session, clave: str) -> ConfiguracionUsuario | None:
    """Override propio del usuario actual para una clave, si existe."""
    uid = _uid_override()
    if not uid:
        return None
    return (
        db.query(ConfiguracionUsuario)
        .filter(
            ConfiguracionUsuario.usuario_id == uid,
            ConfiguracionUsuario.clave == clave,
            ConfiguracionUsuario.activo == True,
        )
        .first()
    )


def resolver_parametro(db: Session, clave: str, default_value: str | None = None):
    """Valor efectivo de un parámetro en cascada: override del usuario → global.

    Devuelve (valor, origen) donde origen es 'usuario', 'global' o 'default'.
    Es el punto único de lectura para todo el sistema (mora, mensajería, etc.).
    """
    propio = override_parametro(db, clave)
    if propio is not None:
        return propio.valor, "usuario"
    config = (
        db.query(ConfiguracionSistema)
        .filter(
            ConfiguracionSistema.clave == clave,
            ConfiguracionSistema.activo == True,
        )
        .first()
    )
    if config is not None:
        return config.valor, "global"
    return default_value, "default"


def get_configuracion_por_clave(db: Session, clave: str):
    """Configuración efectiva (override propio si existe, si no la global)."""
    propio = override_parametro(db, clave)
    if propio is not None:
        if not hasattr(propio, "origen"):
            propio.origen = "usuario"
        return propio
    config = (
        db.query(ConfiguracionSistema)
        .filter(
            ConfiguracionSistema.clave == clave,
            ConfiguracionSistema.activo == True,
        )
        .first()
    )
    if not config:
        raise HTTPException(status_code=404, detail=f"Configuración '{clave}' no encontrada")
    if not hasattr(config, "origen"):
        config.origen = "global"
    return config


def get_todas_configuraciones(db: Session):
    """Todas las claves activas con el valor efectivo de cada usuario."""
    globales = (
        db.query(ConfiguracionSistema)
        .filter(ConfiguracionSistema.activo == True)
        .all()
    )
    for g in globales:
        g.origen = "global"

    uid = _uid_override()
    if not uid:
        return globales

    propios = {
        o.clave: o
        for o in (
            db.query(ConfiguracionUsuario)
            .filter(
                ConfiguracionUsuario.usuario_id == uid,
                ConfiguracionUsuario.activo == True,
            )
            .all()
        )
    }
    if not propios:
        return globales

    efectivas = []
    for g in globales:
        propio = propios.get(g.clave)
        if propio is not None:
            propio.origen = "usuario"
            efectivas.append(propio)
        else:
            efectivas.append(g)
    return efectivas


def actualizar_configuracion(db: Session, clave: str, datos: ConfiguracionUpdate):
    """Actualiza un parámetro validando tipo y rango.

    - Admin: escribe la fila global (comportamiento histórico).
    - Usuario normal: escribe su propio override (upsert), de modo que la
      configuración queda personalizada por usuario sin tocar la global.
    """
    global_fila = (
        db.query(ConfiguracionSistema)
        .filter(
            ConfiguracionSistema.clave == clave,
            ConfiguracionSistema.activo == True,
        )
        .first()
    )
    if not global_fila:
        raise HTTPException(status_code=404, detail=f"Configuración '{clave}' no encontrada")

    nuevo_valor = _validar_valor(global_fila.tipo_valor, datos.valor)

    uid = _uid_override()
    if uid is None:
        global_fila.valor = nuevo_valor
        if datos.descripcion:
            global_fila.descripcion = datos.descripcion
        db.commit()
        db.refresh(global_fila)
        global_fila.origen = "global"
        return global_fila

    propio = override_parametro(db, clave)
    if propio is not None:
        propio.valor = nuevo_valor
        if datos.descripcion:
            propio.descripcion = datos.descripcion
        registro = propio
    else:
        registro = ConfiguracionUsuario(
            usuario_id=uid,
            clave=clave,
            valor=nuevo_valor,
            descripcion=datos.descripcion or global_fila.descripcion,
            tipo_valor=global_fila.tipo_valor,
            activo=True,
        )
        db.add(registro)
    db.commit()
    db.refresh(registro)
    registro.origen = "usuario"
    return registro


def _validar_valor(tipo_valor: str, valor: str) -> str:
    """RF-011: los valores numéricos deben ser no negativos."""
    if tipo_valor in ("float", "int", "number"):
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="El valor debe ser numérico.")
        if numero < 0:
            raise HTTPException(status_code=422, detail="El valor no puede ser negativo.")
        if tipo_valor == "int" and not numero.is_integer():
            raise HTTPException(status_code=422, detail="El valor debe ser un entero.")
    return valor


def crear_configuracion(db: Session, datos: ConfiguracionCreate):
    """Crea una nueva configuración"""
    config = ConfiguracionSistema(**datos.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config
