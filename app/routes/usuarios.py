from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.schemas import usuarios as schemas
from app.schemas.pagination import PaginatedResponse
from app.services import usuarios as service
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verificar_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requieren permisos de administrador."
        )
    return current_user

@router.get("/", response_model=PaginatedResponse[schemas.UsuarioOut])
def listar_usuarios(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(10, ge=1, le=100, description="Elementos por página"),
    db: Session = Depends(get_db),
    admin: dict = Depends(verificar_admin)
):
    return service.get_usuarios(db, page=page, limit=limit)

@router.post("/", response_model=schemas.UsuarioOut, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    usuario: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(verificar_admin)
):
    return service.create_usuario(db, usuario)

@router.get("/{usuario_id}", response_model=schemas.UsuarioOut)
def obtener_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verificar_admin)
):
    usuario = service.get_usuario(db, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return usuario

@router.put("/{usuario_id}", response_model=schemas.UsuarioOut)
def actualizar_usuario(
    usuario_id: int,
    usuario: schemas.UsuarioUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(verificar_admin)
):
    return service.update_usuario(db, usuario_id, usuario)

@router.delete("/{usuario_id}")
def eliminar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(verificar_admin)
):
    service.delete_usuario(db, usuario_id)
    return {"message": "Usuario desactivado exitosamente."}