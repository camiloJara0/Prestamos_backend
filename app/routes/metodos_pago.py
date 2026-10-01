import os
import shutil
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.models import MetodoPagoPrestamista, PrestamoCuota, Usuario
from app.schemas.metodo_pago import (
    MetodoPagoPrestamistaCreate, 
    MetodoPagoPrestamistaOut, 
    MetodoPagoPrestamistaUpdate
)
from app.dependencies.auth import get_current_user
from app.services.qr_service import obtener_datos_cobro_cuota

router = APIRouter(prefix="/metodos-pago", tags=["Métodos de Pago & Cobros"])

UPLOAD_DIR = "uploads/qr_codes"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Tipos MIME y extensiones soportadas
FORMATOS_IMAGEN_PERMITIDOS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/heic": "heic",
    "image/heif": "heif",
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def obtener_usuario_id_seguro(current_user: dict, db: Session) -> int:
    """Extrae de forma robusta el ID del usuario autenticado."""
    val_sub = current_user.get("sub") or current_user.get("id") or current_user.get("email")
    if isinstance(val_sub, int) or (isinstance(val_sub, str) and val_sub.isdigit()):
        return int(val_sub)
    
    usuario_db = db.query(Usuario).filter(Usuario.email == str(val_sub)).first()
    if not usuario_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario autenticado no existe en el sistema."
        )
    return usuario_db.id


@router.get("/", response_model=List[MetodoPagoPrestamistaOut])
def listar_metodos_pago(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Lista ÚNICAMENTE los métodos de pago activos pertenecientes al usuario autenticado."""
    usuario_id = obtener_usuario_id_seguro(current_user, db)
    return (
        db.query(MetodoPagoPrestamista)
        .filter(
            MetodoPagoPrestamista.usuario_id == usuario_id,
            MetodoPagoPrestamista.activo == True
        )
        .all()
    )


@router.post("/", response_model=MetodoPagoPrestamistaOut, status_code=status.HTTP_201_CREATED)
def crear_metodo_pago(
    metodo: MetodoPagoPrestamistaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Registra un nuevo método de pago asignándolo de forma privada al usuario autenticado."""
    usuario_id = obtener_usuario_id_seguro(current_user, db)
    nuevo_metodo = MetodoPagoPrestamista(
        **metodo.model_dump(),
        usuario_id=usuario_id
    )
    db.add(nuevo_metodo)
    db.commit()
    db.refresh(nuevo_metodo)
    return nuevo_metodo


@router.put("/{metodo_id}", response_model=MetodoPagoPrestamistaOut)
def actualizar_metodo_pago(
    metodo_id: int,
    datos: MetodoPagoPrestamistaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Actualiza datos del método de pago, verificando estricta propiedad del usuario."""
    usuario_id = obtener_usuario_id_seguro(current_user, db)
    metodo = (
        db.query(MetodoPagoPrestamista)
        .filter(
            MetodoPagoPrestamista.id == metodo_id,
            MetodoPagoPrestamista.usuario_id == usuario_id
        )
        .first()
    )
    if not metodo:
        raise HTTPException(status_code=404, detail="El método de pago no existe o no te pertenece.")

    update_data = datos.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(metodo, key, value)

    db.commit()
    db.refresh(metodo)
    return metodo


@router.post("/{metodo_id}/subir-qr", response_model=MetodoPagoPrestamistaOut)
def subir_o_actualizar_qr(
    metodo_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Sube o reemplaza la imagen del código QR personal.
    Soporta los formatos: PNG, JPG, JPEG, WEBP, GIF, HEIC y HEIF.
    """
    usuario_id = obtener_usuario_id_seguro(current_user, db)

    # 1. Verificar que el método de pago le pertenece al usuario
    metodo = (
        db.query(MetodoPagoPrestamista)
        .filter(
            MetodoPagoPrestamista.id == metodo_id,
            MetodoPagoPrestamista.usuario_id == usuario_id
        )
        .first()
    )
    if not metodo:
        raise HTTPException(status_code=404, detail="El método de pago no existe o no te pertenece.")

    # 2. Validar formato de imagen por Content-Type o extensión
    content_type = file.content_type.lower() if file.content_type else ""
    ext_por_nombre = file.filename.split(".")[-1].lower() if "." in file.filename else ""

    extension_final = FORMATOS_IMAGEN_PERMITIDOS.get(content_type)
    if not extension_final:
        if ext_por_nombre in ["png", "jpg", "jpeg", "webp", "gif", "heic", "heif"]:
            extension_final = ext_por_nombre
        else:
            raise HTTPException(
                status_code=400,
                detail="Formato no soportado. Debe adjuntar una imagen válida (PNG, JPG, JPEG, WEBP, GIF, HEIC, HEIF)."
            )

    # 3. Eliminar imagen previa en disco si existía
    if metodo.qr_code_url and os.path.exists(metodo.qr_code_url):
        try:
            os.remove(metodo.qr_code_url)
        except Exception:
            pass

    # 4. Guardar el nuevo archivo asignando usuario y método en el nombre
    filename = f"qr_u{usuario_id}_m{metodo_id}.{extension_final}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    metodo.qr_code_url = filepath
    db.commit()
    db.refresh(metodo)
    return metodo


@router.get("/{metodo_id}/qr")
def obtener_imagen_qr(
    metodo_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Retorna la imagen del QR estático subida previamente por el usuario."""
    usuario_id = obtener_usuario_id_seguro(current_user, db)

    metodo = (
        db.query(MetodoPagoPrestamista)
        .filter(
            MetodoPagoPrestamista.id == metodo_id,
            MetodoPagoPrestamista.usuario_id == usuario_id
        )
        .first()
    )
    if not metodo:
        raise HTTPException(status_code=404, detail="El método de pago no existe o no te pertenece.")

    if metodo.qr_code_url and os.path.exists(metodo.qr_code_url):
        ext = metodo.qr_code_url.split(".")[-1].lower()
        media_type = f"image/{'jpeg' if ext in ['jpg', 'jpeg'] else ext}"
        with open(metodo.qr_code_url, "rb") as f:
            return Response(content=f.read(), media_type=media_type)

    raise HTTPException(
        status_code=404, 
        detail="Este método de pago no tiene una imagen de código QR asignada."
    )


@router.get("/{metodo_id}/datos-pago/cuota/{cuota_id}")
def obtener_datos_para_pago_cuota(
    metodo_id: int,
    cuota_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retorna la información completa formateada para pagar una cuota específica:
    - Datos del banco, titular y número/llave.
    - Monto exacto de la cuota.
    - Referencia Única asignada.
    - Indica si tiene imagen QR disponible.
    """
    usuario_id = obtener_usuario_id_seguro(current_user, db)

    metodo = (
        db.query(MetodoPagoPrestamista)
        .filter(
            MetodoPagoPrestamista.id == metodo_id,
            MetodoPagoPrestamista.usuario_id == usuario_id
        )
        .first()
    )
    if not metodo:
        raise HTTPException(status_code=404, detail="El método de pago no existe o no te pertenece.")

    cuota = db.query(PrestamoCuota).filter(PrestamoCuota.id == cuota_id).first()
    if not cuota:
        raise HTTPException(status_code=404, detail="La cuota especificada no existe.")

    datos = obtener_datos_cobro_cuota(metodo, cuota)
    datos["tiene_imagen_qr"] = bool(metodo.qr_code_url and os.path.exists(metodo.qr_code_url))
    datos["qr_url"] = f"/metodos-pago/{metodo_id}/qr" if datos["tiene_imagen_qr"] else None

    return datos