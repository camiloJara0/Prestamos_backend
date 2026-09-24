import json
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.models import IdempotencyKey, PrestamoCuota, Prestamo, Cliente, Pago, Usuario
from app.schemas.pago import PagoCreate, PagoOut
from app.schemas.pagination import PaginatedResponse
from app.services.pago import get_pagos, registrar_pago
from app.utils.pdf_generator import generar_recibo_pdf_bytes

router = APIRouter(prefix="/pagos", tags=["Pagos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=PagoOut, status_code=status.HTTP_201_CREATED)
def crear_pago(
    pago: PagoCreate,
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
    val_sub = current_user.get("sub") or current_user.get("id") or current_user.get("email")
    
    if isinstance(val_sub, int) or (isinstance(val_sub, str) and val_sub.isdigit()):
        usuario_id = int(val_sub)
    else:
        usuario_db = db.query(Usuario).filter(Usuario.email == str(val_sub)).first()
        if not usuario_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El usuario autenticado no se encuentra en el sistema."
            )
        usuario_id = usuario_db.id

    # 3. Registrar el pago en la base de datos
    nuevo_pago = registrar_pago(db, pago, usuario_id=usuario_id)

    # 4. Convertir a esquema y guardar clave de idempotencia
    pago_dict = PagoOut.model_validate(nuevo_pago).model_dump(mode="json")

    if key:
        registro_key = IdempotencyKey(
            key=str(key),
            response=json.dumps(pago_dict),
            status_code=status.HTTP_201_CREATED,
        )
        db.add(registro_key)
        db.commit()

    return nuevo_pago


@router.get("/", response_model=PaginatedResponse[PagoOut])
def listar_pagos(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return get_pagos(db, page=page, limit=limit)


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
        
    if cuota.estado != "pagado":
        raise HTTPException(
            status_code=400, 
            detail="Solo se pueden generar recibos para cuotas que estén en estado 'PAGADO'."
        )

    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
    cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first()
    pago_registro = db.query(Pago).filter(Pago.cuota_id == cuota.id).order_by(Pago.id.desc()).first()

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

    datos_recibo = {
        "referencia_pago": cuota.referencia_pago or f"REF-P{prestamo.id}C{cuota.numero_cuota}",
        "fecha_pago": fecha_pago_real,
        "cliente_nombre": cliente.nombre,
        "cliente_cedula": cliente.cedula,
        "prestamo_id": prestamo.id,
        "cuota_numero": cuota.numero_cuota,
        "monto_pagado": pago_registro.valor_pagado if pago_registro else cuota.valor_cuota,
        "metodo_pago": metodo_pago_nombre
    }

    pdf_bytes = generar_recibo_pdf_bytes(datos_recibo)
    nombre_archivo = f"Recibo_{datos_recibo['referencia_pago']}.pdf"

    return Response(
        content=pdf_bytes.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"}
    )