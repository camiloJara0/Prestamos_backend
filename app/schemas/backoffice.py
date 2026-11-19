"""Schemas Pydantic del módulo Backoffice (consola interna)."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Dashboard / infraestructura
# ---------------------------------------------------------------------------
class DashboardOut(BaseModel):
    usuarios_total: int
    usuarios_activos: int
    usuarios_inactivos: int
    empresas: int  # usuarios con rol prestamista activos
    clientes: int
    errores_abiertos: int
    errores_7d: int
    procesos: dict  # {"pendiente": n, "en_ejecucion": n, ...}
    ultimo_respaldo: Optional[str] = None
    ultima_actividad: list = []
    uptime_segundos: float
    latencia_promedio_ms: Optional[float] = None
    peticiones_hoy: int = 0
    version: str


class PuntoSerie(BaseModel):
    fecha: str
    valor: float


class SerieOut(BaseModel):
    metrica: str
    granularidad: str
    puntos: List[PuntoSerie]


class ServicioEstado(BaseModel):
    nombre: str
    estado: Literal["ok", "degradado", "desconocido"]
    detalle: Optional[str] = None


class InfraestructuraOut(BaseModel):
    version: str
    uptime_segundos: float
    disco_total_bytes: int
    disco_libre_bytes: int
    base_datos_bytes: Optional[int] = None
    respaldos_directorio: str
    respaldos_cantidad: int
    retencion: int
    servicios: List[ServicioEstado]


# ---------------------------------------------------------------------------
# Usuarios globales
# ---------------------------------------------------------------------------
class SesionOut(BaseModel):
    id: int
    activo: bool
    created_at: datetime
    expires_at: datetime
    ultimo_uso_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UsuarioGlobalOut(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    estado: str
    created_at: Optional[datetime] = None
    ultima_actividad: Optional[datetime] = None
    sesiones_activas: int = 0
    clientes: int = 0

    model_config = ConfigDict(from_attributes=True)


class UsuarioDetalleOut(UsuarioGlobalOut):
    permisos: List[str] = []
    accesos: List[SesionOut] = []
    ultimos_eventos: list = []


class SesionRevocadaOut(BaseModel):
    revocadas: int


class MotivoRequest(BaseModel):
    motivo: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------
class ErrorOut(BaseModel):
    id: int
    origen: str
    nivel: str
    tipo_exception: str
    mensaje: str
    endpoint: Optional[str] = None
    componente: Optional[str] = None
    metodo_http: Optional[str] = None
    status_code: Optional[int] = None
    usuario_id: Optional[int] = None
    request_id: Optional[str] = None
    version: Optional[str] = None
    fingerprint: str
    ocurrencias: int
    primera_ocurrencia: datetime
    ultima_ocurrencia: datetime
    estado: str
    responsable_id: Optional[int] = None
    resolucion: Optional[str] = None
    fecha_resolucion: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ErrorDetalleOut(ErrorOut):
    stack_trace: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ErrorActualizarRequest(BaseModel):
    estado: Optional[Literal["abierto", "en_seguimiento", "resuelto", "ignorado"]] = None
    responsable_id: Optional[int] = None
    resolucion: Optional[str] = Field(default=None, max_length=2000)


class ErrorCrearRequest(BaseModel):
    origen: Literal["backend", "frontend"] = "frontend"
    nivel: Literal["error", "critico"] = "error"
    tipo_exception: str = Field(min_length=1, max_length=150)
    mensaje: str = Field(min_length=1, max_length=2000)
    stack_trace: Optional[str] = Field(default=None, max_length=8000)
    endpoint: Optional[str] = Field(default=None, max_length=200)
    componente: Optional[str] = Field(default=None, max_length=200)
    metodo_http: Optional[str] = Field(default=None, max_length=10)
    status_code: Optional[int] = None
    usuario_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Procesos
# ---------------------------------------------------------------------------
class ProcesoOut(BaseModel):
    id: str
    descripcion: str
    trigger: str
    proxima_ejecucion: Optional[datetime] = None
    estado: Literal["activo", "pausado", "desconocido"]
    administrable: bool
    en_ejecucion: bool = False
    ultima_ejecucion: Optional[str] = None  # estado de la última fila


class EjecucionOut(BaseModel):
    id: int
    tarea: str
    origen: str
    estado: str
    solicitado_por: Optional[int] = None
    fecha_solicitud: datetime
    inicio: Optional[datetime] = None
    fin: Optional[datetime] = None
    duracion_ms: Optional[int] = None
    intentos: int
    resultado: Optional[str] = None
    error_mensaje: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Respaldos
# ---------------------------------------------------------------------------
class RespaldoOut(BaseModel):
    nombre: str
    tamano_bytes: int
    fecha: datetime


class RespaldosOut(BaseModel):
    items: List[RespaldoOut]
    retencion_dias: int
    directorio: str
    ultimo_estado: Optional[str] = None
    ultimo_resultado: Optional[str] = None
    ultimo_fin: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
class ConfigItemOut(BaseModel):
    id: int
    clave: str
    valor: str
    descripcion: Optional[str] = None
    tipo_valor: str
    activo: bool

    model_config = ConfigDict(from_attributes=True)


class ConfigActualizarRequest(BaseModel):
    valor: str = Field(min_length=1, max_length=255)
