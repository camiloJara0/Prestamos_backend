from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.models import Token, Usuario
from app.schemas.usuarios import UsuarioCreate, UsuarioUpdate
from app.utils.pagination import paginate


def get_usuarios(db: Session, page: int = 1, limit: int = 10):
    query = db.query(Usuario).order_by(Usuario.id.asc())
    return paginate(query, page=page, limit=limit)


def get_usuario(db: Session, usuario_id: int) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.id == usuario_id).first()


def create_usuario(db: Session, usuario_in: UsuarioCreate) -> Usuario:
    # 1. Validar que el email no esté registrado
    existente = (
        db.query(Usuario).filter(Usuario.email == usuario_in.email).first()
    )
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya está registrado.",
        )

    db_usuario = Usuario(
        nombre=usuario_in.nombre,
        email=usuario_in.email,
        hashed_password=get_password_hash(usuario_in.password),
        rol=usuario_in.rol,
        estado="activo",
    )
    db.add(db_usuario)
    db.commit()
    db.refresh(db_usuario)
    return db_usuario


def update_usuario(
    db: Session, usuario_id: int, usuario_in: UsuarioUpdate
) -> Usuario:
    db_usuario = get_usuario(db, usuario_id)
    if not db_usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    # 2. Validar email único si intenta cambiarlo
    if usuario_in.email and usuario_in.email != db_usuario.email:
        existente = (
            db.query(Usuario).filter(Usuario.email == usuario_in.email).first()
        )
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El correo electrónico ya pertenece a otro usuario.",
            )
        db_usuario.email = usuario_in.email

    if usuario_in.nombre is not None:
        db_usuario.nombre = usuario_in.nombre

    if usuario_in.rol is not None:
        db_usuario.rol = usuario_in.rol

    if usuario_in.password:
        db_usuario.hashed_password = get_password_hash(usuario_in.password)

    # 3. Si se inactiva el usuario, revocar sus tokens activos
    if usuario_in.estado is not None:
        db_usuario.estado = usuario_in.estado
        if usuario_in.estado == "inactivo":
            db.query(Token).filter(
                Token.usuario_id == usuario_id, Token.activo == 1
            ).update({"activo": 0})

    db.commit()
    db.refresh(db_usuario)
    return db_usuario


def delete_usuario(
    db: Session, usuario_id: int, admin_id: int | None = None
) -> bool:
    if admin_id and usuario_id == admin_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrador no puede desactivar su propia cuenta.",
        )

    db_usuario = get_usuario(db, usuario_id)
    if not db_usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    # Borrado lógico: Cambiar estado a inactivo e invalidar sus tokens
    db_usuario.estado = "inactivo"
    db.query(Token).filter(
        Token.usuario_id == usuario_id, Token.activo == 1
    ).update({"activo": 0})

    db.commit()
    return True