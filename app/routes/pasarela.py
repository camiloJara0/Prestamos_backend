from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user, get_db, get_usuario_id, require_rol
from app.schemas.pagination import PaginatedResponse
from app.schemas.pasarela import ConfirmacionCreate, IntencionPagoCreate, TransaccionOut
from app.services import pasarela as pasarela_service
from app.services.auditoria import registrar_auditoria

router = APIRouter(prefix="/pagos-online", tags=["Pasarela de pago"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/", response_model=PaginatedResponse[TransaccionOut])
def listar_transacciones(
    page: int = 1,
    limit: int = 10,
    estado: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return pasarela_service.get_transacciones(db, page=page, limit=limit, estado=estado)


@router.post("/", response_model=TransaccionOut, status_code=201)
def crear_intencion(
    datos: IntencionPagoCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """RF-064: crea la intención de pago; aún no descuenta saldo."""
    transaccion = pasarela_service.crear_intencion_pago(
        db, datos.cuota_id, get_usuario_id(current_user)
    )
    registrar_auditoria(
        db,
        usuario_id=get_usuario_id(current_user),
        tabla_afectada="transacciones_pasarela",
        tipo_operacion="CREATE",
        registro_id=transaccion.id,
        valores_nuevos={"cuota_id": transaccion.cuota_id, "monto": transaccion.monto},
        descripcion=f"Intención de pago en línea #{transaccion.id}",
        ip_address=_ip(request),
    )
    return transaccion


@router.get("/{transaccion_id}", response_model=TransaccionOut)
def obtener_transaccion(
    transaccion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return pasarela_service.get_transaccion(db, transaccion_id)


@router.post("/{transaccion_id}/confirmar", response_model=TransaccionOut)
def confirmar_transaccion(
    transaccion_id: int,
    datos: ConfirmacionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Confirmación de la pasarela (webhook en piloto externo, manual en piloto).

    Solo una confirmación exitosa registra el pago y descuenta saldo.
    """
    transaccion = pasarela_service.confirmar_transaccion(
        db,
        transaccion_id,
        exito=datos.exito,
        referencia_externa=datos.referencia_externa,
        usuario_id=get_usuario_id(current_user),
        ip_address=_ip(request),
    )
    if transaccion.estado == "confirmada":
        registrar_auditoria(
            db,
            usuario_id=get_usuario_id(current_user),
            tabla_afectada="transacciones_pasarela",
            tipo_operacion="UPDATE",
            registro_id=transaccion.id,
            valores_nuevos={
                "estado": transaccion.estado,
                "pago_id": transaccion.pago_id,
                "referencia_externa": transaccion.referencia_externa,
            },
            descripcion=f"Transacción #{transaccion.id} confirmada por pasarela",
            ip_address=_ip(request),
        )
    return transaccion
