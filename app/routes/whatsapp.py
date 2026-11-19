"""Mensajería WhatsApp: credenciales del prestamista, prueba de conexión,
envío individual/masivo e historial con trazabilidad."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.context import usuario_actual_id
from app.db.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.models.models import CredencialesWhatsApp
from app.services import whatsapp as service
from app.services.rate_limit import verificar_rate_limit

from datetime import datetime
from typing import Optional


router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CredencialesIn(BaseModel):
    proveedor: str = "meta_cloud"
    access_token: str = Field(min_length=5, max_length=1000)
    phone_number_id: str = Field(min_length=3, max_length=50)
    business_account_id: Optional[str] = Field(default=None, max_length=50)
    api_key: Optional[str] = Field(default=None, max_length=1000)


class CredencialesOut(BaseModel):
    proveedor: str
    phone_number_id: str
    business_account_id: Optional[str] = None
    # El access_token NUNCA se devuelve completo (solo máscara).
    access_token_mascara: str
    api_key_definida: bool
    estado_conexion: str
    ultima_validacion: Optional[datetime] = None
    detalle_validacion: Optional[str] = None

    class Config:
        from_attributes = True


class ProbarConexionIn(BaseModel):
    access_token: Optional[str] = Field(default=None, max_length=1000)
    phone_number_id: Optional[str] = Field(default=None, max_length=50)


class EnvioIndividualIn(BaseModel):
    cliente_id: int
    cuerpo: str = Field(min_length=1, max_length=4000)
    plantilla_id: Optional[int] = None


class EnvioMasivoIn(BaseModel):
    plantilla_id: int
    tipo: str = Query("proximos", pattern="^(proximos|vencidos)$")
    dias: int = Query(3, ge=0, le=90)


def _mascarar(valor: str) -> str:
    if not valor:
        return ""
    return f"••••{valor[-4:]}"


def _credenciales_out(fila: CredencialesWhatsApp) -> dict:
    return {
        "proveedor": fila.proveedor,
        "phone_number_id": fila.phone_number_id,
        "business_account_id": fila.business_account_id,
        "access_token_mascara": _mascarar(fila.access_token),
        "api_key_definida": bool(fila.api_key),
        "estado_conexion": fila.estado_conexion,
        "ultima_validacion": fila.ultima_validacion,
        "detalle_validacion": fila.detalle_validacion,
    }


# ---------------------------------------------------------------------------
# Credenciales (Modo 2: WhatsApp Business propio)
# ---------------------------------------------------------------------------
@router.get("/credenciales")
def ver_credenciales(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    fila = service.obtener_credenciales(db)
    if not fila:
        return {
            "configurado": False,
            "modo": "corporativo",
            "credenciales": None,
        }
    return {"configurado": True, "modo": "propio", "credenciales": _credenciales_out(fila)}


@router.put("/credenciales")
def guardar_credenciales(
    datos: CredencialesIn,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    fila = service.guardar_credenciales(db, datos)
    return {"configurado": True, "modo": "propio", "credenciales": _credenciales_out(fila)}


@router.delete("/credenciales")
def eliminar_credenciales(
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    ok = service.eliminar_credenciales(db)
    return {"message": "Credenciales eliminadas." if ok else "No había credenciales guardadas."}


@router.post("/probar-conexion")
def probar_conexion(
    datos: ProbarConexionIn = None,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    """Verificación en tiempo real de credenciales contra Meta (detalle de errores)."""
    return service.probar_conexion(db, datos)


# ---------------------------------------------------------------------------
# Envío individual (ficha del cliente / ficha del préstamo)
# ---------------------------------------------------------------------------
@router.post("/enviar")
def enviar_individual(
    datos: EnvioIndividualIn,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    uid = usuario_actual_id.get()
    verificar_rate_limit(f"wa_individual:{uid}", maximo=30, ventana_segundos=60)
    return service.enviar_individual(
        db, cliente_id=datos.cliente_id, cuerpo=datos.cuerpo,
        plantilla_id=datos.plantilla_id,
    )


# ---------------------------------------------------------------------------
# Envío masivo (recordatorios por segmento)
# ---------------------------------------------------------------------------
@router.post("/enviar-masivo")
def enviar_masivo(
    datos: EnvioMasivoIn,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    uid = usuario_actual_id.get()
    verificar_rate_limit(f"wa_masivo:{uid}", maximo=5, ventana_segundos=60)
    return service.enviar_masivo(
        db, plantilla_id=datos.plantilla_id, tipo=datos.tipo, dias=datos.dias
    )


# ---------------------------------------------------------------------------
# Historial con trazabilidad
# ---------------------------------------------------------------------------
@router.get("/envios")
def historial_envios(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    canal: Optional[str] = Query(None, pattern="^(email|sms|whatsapp)$"),
    estado: Optional[str] = Query(None, max_length=30),
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(get_current_user),
):
    return service.historial_envios(
        db, page=page, limit=limit, canal=canal, estado=estado, cliente_id=cliente_id
    )


@router.get("/variables")
def variables_disponibles(
    _usuario: dict = Depends(get_current_user),
):
    """Catálogo de variables dinámicas agrupadas por categoría (editor)."""
    from app.services.plantillas import catalogo_variables

    return catalogo_variables()
