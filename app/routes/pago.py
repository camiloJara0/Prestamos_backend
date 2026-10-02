import json
from datetime import date
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.dependencies.auth import get_current_user, require_rol
from app.models import IdempotencyKey, PrestamoCuota, Prestamo, Cliente, Pago, Usuario
from app.schemas.pago import PagoCreate, PagoOut, PagoDevolucionCreate, PagoHistorialOut
from app.schemas.pagination import PaginatedResponse
from app.services.pago import get_pagos, registrar_pago, devolver_pago
from app.utils.pdf_generator import generar_recibo_pdf_bytes

router = APIRouter(prefix="/pagos", tags=["Pagos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _obtener_usuario_id(current_user: dict, db: Session) -> int:
    val_sub = current_user.get("sub") or current_user.get("id") or current_user.get("email")
    if isinstance(val_sub, int) or (isinstance(val_sub, str) and val_sub.isdigit()):
        return int(val_sub)

    usuario_db = db.query(Usuario).filter(Usuario.email == str(val_sub)).first()
    if not usuario_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario autenticado no se encuentra en el sistema."
        )
    return usuario_db.id


@router.post("/", response_model=PagoOut, status_code=status.HTTP_200_OK)
def crear_pago(
    pago: PagoCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    key = x_idempotency_key or getattr(pago, "idempotency_key", None)

    # 1. Verificar si la clave de idempotencia ya existe
    if key:
        existente = (
            db.query(IdempotencyKey)
            .filter(IdempotencyKey.key == str(key))
            .first()
        )
        if existente:
            return JSONResponse(
                status_code=existente.status_code,
                content=json.loads(existente.response),
            )

    # 2. Obtener el ID del usuario de manera segura
    usuario_id = _obtener_usuario_id(current_user, db)

    # 3. Registrar el pago en la base de datos
    nuevo_pago = registrar_pago(db, pago, usuario_id=usuario_id, ip_address=_ip(request))

    # 4. Convertir a esquema y guardar clave de idempotencia
    pago_dict = PagoOut.model_validate(nuevo_pago).model_dump(mode="json")

    if key:
        registro_key = IdempotencyKey(
            key=str(key),
            response=json.dumps(pago_dict),
            status_code=status.HTTP_200_OK,
        )
        db.add(registro_key)
        db.commit()

    return nuevo_pago


@router.get("/", response_model=PaginatedResponse[PagoHistorialOut])
def listar_pagos(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    cliente_id: int | None = Query(None, description="Filtrar pagos por cliente"),
    tipo_pago_id: int | None = Query(None, description="Filtrar pagos por tipo de pago"),
    fecha_desde: date | None = Query(None, description="Fecha inicial (inclusive)"),
    fecha_hasta: date | None = Query(None, description="Fecha final (inclusive)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Historial global de pagos con filtros por cliente, fecha y tipo (RF-041)."""
    return get_pagos(
        db,
        page=page,
        limit=limit,
        cliente_id=cliente_id,
        tipo_pago_id=tipo_pago_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


@router.get("/{pago_id}", response_model=PagoOut)
def obtener_pago(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Obtiene los detalles de un pago específico por su ID.
    """
    pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="El pago especificado no existe.")
    return pago


@router.post("/{pago_id}/devolver", response_model=PagoOut)
def solicitar_devolucion_pago(
    pago_id: int,
    datos_devolucion: PagoDevolucionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("admin")),
):
    """
    Anula/Devuelve un pago previamente registrado dentro del margen máximo de 30 días,
    realizando la reversión en cascada de cuota, préstamo, saldo global y auditoría (RF-042).
    Solo administrador.
    """
    usuario_id = _obtener_usuario_id(current_user, db)
    pago_devuelto = devolver_pago(
        db=db,
        pago_id=pago_id,
        datos_devolucion=datos_devolucion,
        usuario_id=usuario_id,
        ip_address=_ip(request),
    )
    return pago_devuelto


def _construir_datos_recibo(db: Session, cuota: PrestamoCuota, pago_registro: Pago | None) -> dict:
    """Arma los datos del comprobante PDF para una cuota y su pago (RF-043)."""
    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
    cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first()

    metodo_pago_nombre = "Transferencia / Efectivo"

    if pago_registro and pago_registro.fecha_pago:
        fecha_bruta = pago_registro.fecha_pago
    elif cuota.fecha_pago:
        fecha_bruta = cuota.fecha_pago
    else:
        fecha_bruta = cuota.updated_at

    fecha_pago_real = str(fecha_bruta).split("T")[0].split(" ")[0]

    if pago_registro and pago_registro.tipo_pago:
        metodo_pago_nombre = pago_registro.tipo_pago.nombre

    referencia_recibo = pago_registro.referencia_recibo if pago_registro else f"REC-CUOTA-{cuota.id}"

    datos_recibo = {
        "referencia_pago": cuota.referencia_pago or f"REF-P{prestamo.id}C{cuota.numero_cuota}",
        "referencia_recibo": referencia_recibo,
        "estado_pago": pago_registro.estado_pago if pago_registro else "confirmado",
        "fecha_pago": fecha_pago_real,
        "cliente_nombre": cliente.nombre,
        "cliente_cedula": cliente.cedula,
        "prestamo_id": prestamo.id,
        "cuota_numero": cuota.numero_cuota,
        "monto_pagado": pago_registro.valor_pagado if pago_registro else cuota.valor_cuota,
        "metodo_pago": metodo_pago_nombre
    }

    if pago_registro:
        datos_recibo["capital_pagado"] = pago_registro.capital_pagado
        datos_recibo["interes_pagado"] = pago_registro.interes_pagado
        datos_recibo["mora_pagada"] = pago_registro.mora_pagada
        if pago_registro.estado_pago == "devuelto":
            datos_recibo["fecha_devolucion"] = str(pago_registro.fecha_devolucion or "")
            datos_recibo["motivo_devolucion"] = pago_registro.motivo_devolucion

    return datos_recibo


def _responder_pdf(datos_recibo: dict) -> Response:
    pdf_bytes = generar_recibo_pdf_bytes(datos_recibo)
    nombre_archivo = f"Recibo_{datos_recibo['referencia_recibo']}.pdf"
    return Response(
        content=pdf_bytes.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )


@router.get("/cuota/{cuota_id}/recibo-pdf")
def descargar_recibo_cuota_pdf(
    cuota_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Genera y descarga en tiempo real el recibo en PDF de una cuota pagada.
    """
    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="La cuota no existe.")

    pago_registro = db.query(Pago).filter(Pago.cuota_id == cuota.id).order_by(Pago.id.desc()).first()
    return _responder_pdf(_construir_datos_recibo(db, cuota, pago_registro))


@router.get("/{pago_id}/comprobante")
def descargar_comprobante_pago(
    pago_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Comprobante PDF de un pago específico, con su desglose de capital, interés y mora (RF-043).
    Si el pago fue devuelto, el documento incluye la marca de anulación y su motivo.
    """
    pago_registro = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago_registro:
        raise HTTPException(status_code=404, detail="El pago especificado no existe.")

    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == pago_registro.cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="La cuota asociada al pago no existe.")

    return _responder_pdf(_construir_datos_recibo(db, cuota, pago_registro))