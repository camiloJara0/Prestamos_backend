import json
from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.models import IdempotencyKey
from app.schemas.pago import PagoCreate, PagoOut
from app.schemas.pagination import PaginatedResponse
from app.services.pago import get_pagos, registrar_pago

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

    # 2. Obtener usuario de manera segura
    usuario_id = int(current_user.get("sub") or current_user.get("id"))

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