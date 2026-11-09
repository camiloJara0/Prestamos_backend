# Endpoints de prestamos
# POST /prestamos : crea un nuevo prestamo con cuotas automaticas
# GET /prestamos : lista los prestamos con filtros y paginación
# GET /prestamos/{id} : detalle completo con cuotas, pagos y cliente

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional

from app.db.database import SessionLocal
from app.schemas.prestamo import PrestamoCreate, PrestamoOut, PrestamoDetalleOut, RenovacionCreate, MarcarPerdidoRequest, ReestructuracionCreate, ReestructuracionOut
from app.schemas.pagination import PaginatedResponse
from app.services.prestamo import crear_prestamo, get_prestamos, obtener_prestamo, renovar_prestamo, marcar_prestamo_perdido, ajustar_capital_prestamo, reestructurar_prestamo
from app.dependencies.auth import get_current_user, require_rol
from app.services import prestamo as services

router = APIRouter(prefix="/prestamos", tags=["Prestamos"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None

@router.post("/", response_model=PrestamoOut)
def crear(
    prestamo: PrestamoCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return services.crear_prestamo(db, prestamo, current_user["sub"], ip_address=_ip(request))

@router.get("/", response_model=PaginatedResponse[PrestamoOut])
def listar(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    estado: Optional[str] = "activo",
    cliente_id: Optional[int] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    busqueda: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_prestamos(
        db,
        page=page,
        limit=limit,
        estado=estado,
        cliente_id=cliente_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        busqueda=busqueda,
    )

@router.get("/{prestamo_id}", response_model=PrestamoDetalleOut)
def obtener(prestamo_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_prestamo = obtener_prestamo(db, prestamo_id)
    if not db_prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    from app.services.pago import resumen_deuda_prestamo

    db_prestamo.mora_vigente = resumen_deuda_prestamo(db, db_prestamo)
    return db_prestamo


@router.get("/{prestamo_id}/deuda", summary="Deuda vigente de un préstamo (tiempo real)")
def deuda_vigente(
    prestamo_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mora vigente, cuotas vencidas y parámetros aplicados del préstamo.

    Se recalcula en cada consulta con la configuración del usuario (para
    refresco en tiempo real del detalle y las métricas).
    """
    db_prestamo = obtener_prestamo(db, prestamo_id)
    if not db_prestamo:
        raise HTTPException(status_code=404, detail="Prestamo no encontrado")
    from app.services.pago import resumen_deuda_prestamo

    return resumen_deuda_prestamo(db, db_prestamo)

@router.post("/{prestamo_id}/renovar", response_model=PrestamoOut)
def renovar(
    prestamo_id: int,
    renovacion: RenovacionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return renovar_prestamo(db, prestamo_id, renovacion, usuario_id=current_user.get("sub"), ip_address=_ip(request))

@router.post("/{prestamo_id}/marcar_perdido")
def marcar_perdido(
    prestamo_id: int,
    datos: MarcarPerdidoRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return marcar_prestamo_perdido(db, prestamo_id, datos, usuario_id=current_user.get("sub"), ip_address=_ip(request))

@router.put("/{prestamo_id}/ajustar-capital")
def ajustar_capital(
    prestamo_id: int,
    nuevo_capital: float,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin"))
):
    prestamo = ajustar_capital_prestamo(
        db, prestamo_id, nuevo_capital,
        usuario_id=current_user["sub"], ip_address=_ip(request),
    )
    return {
        "mensaje": "Capital ajustado exitosamente",
        "prestamo_id": prestamo.id,
        "capital_nuevo": prestamo.capital_prestado,
        "monto_total": prestamo.monto_total,
        "valor_cuota": prestamo.valor_cuota
    }


@router.post("/{prestamo_id}/reestructurar", response_model=ReestructuracionOut)
def reestructurar(
    prestamo_id: int,
    datos: ReestructuracionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    """Genera un plan de cuotas nuevo para un préstamo en mora (RF-035). Solo administrador."""
    return reestructurar_prestamo(
        db, prestamo_id, datos,
        usuario_id=current_user["sub"], ip_address=_ip(request),
    )