"""Parámetros de configuración del sistema (Backoffice).

Diferencia con `app.services.configuracion`: aquí SIEMPRE se escribe la
fila global (el admin gestiona la plataforma, no su override personal),
con auditoría de valor anterior/nuevo.
"""

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.models import ConfiguracionSistema


def listar_configuraciones(db: Session) -> list[ConfiguracionSistema]:
    return (
        db.query(ConfiguracionSistema)
        .filter(ConfiguracionSistema.activo == True)  # noqa: E712
        .order_by(ConfiguracionSistema.clave.asc())
        .all()
    )


def obtener_configuracion(db: Session, clave: str) -> ConfiguracionSistema:
    fila = (
        db.query(ConfiguracionSistema)
        .filter(
            ConfiguracionSistema.clave == clave,
            ConfiguracionSistema.activo == True,  # noqa: E712
        )
        .first()
    )
    if not fila:
        raise HTTPException(status_code=404, detail="Configuración no encontrada.")
    return fila


def actualizar_configuracion_global(
    db: Session,
    clave: str,
    valor: str,
    descripcion: Optional[str] = None,
    admin_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> ConfiguracionSistema:
    fila = obtener_configuracion(db, clave)

    from app.services.configuracion import _validar_valor

    nuevo_valor = _validar_valor(fila.tipo_valor, valor)

    valores_anteriores = {"valor": fila.valor}
    fila.valor = nuevo_valor
    if descripcion:
        fila.descripcion = descripcion
    db.commit()
    db.refresh(fila)

    from app.services.auditoria import registrar_auditoria

    registrar_auditoria(
        db,
        tabla_afectada="configuracion_sistema",
        tipo_operacion="actualizacion_configuracion",
        usuario_id=admin_id,
        registro_id=fila.id,
        valores_anteriores=valores_anteriores,
        valores_nuevos={"valor": nuevo_valor},
        descripcion=f"Parámetro '{clave}' actualizado",
        resultado="ok",
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    return fila
