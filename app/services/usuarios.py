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


def _admins_activos(db: Session) -> list[Usuario]:
    return (
        db.query(Usuario)
        .filter(Usuario.rol == "admin", Usuario.estado == "activo")
        .all()
    )


def _verificar_ultimo_admin(db: Session, usuario: Usuario, nuevo_estado: str | None = None, nuevo_rol: str | None = None):
    """Impide dejar el sistema sin administradores activos."""
    if usuario.rol != "admin":
        return
    estado_resultante = nuevo_estado if nuevo_estado is not None else usuario.estado
    rol_resultante = nuevo_rol if nuevo_rol is not None else usuario.rol
    if estado_resultante == "activo" and rol_resultante == "admin":
        return
    admins = _admins_activos(db)
    restantes = [a for a in admins if a.id != usuario.id]
    if not restantes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Operación no permitida: no puede quedar sin administradores activos.",
        )


def _auditar(db: Session, **kwargs):
    """Auditoría best-effort: un fallo de auditoría no debe romper la operación."""
    try:
        from app.services.auditoria import registrar_auditoria

        registrar_auditoria(db, **kwargs)
    except Exception:  # noqa: BLE001
        db.rollback()


def create_usuario(db: Session, usuario_in: UsuarioCreate, admin_id: int | None = None) -> Usuario:
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

    # Onboarding automático: todo prestamista nuevo recibe su propio juego de
    # plantillas base, asociadas EXCLUSIVAMENTE a él (podrá editarlas o
    # borrarlas sin afectar a otros usuarios).
    if db_usuario.rol == "prestamista":
        try:
            from app.services.plantillas import sembrar_plantillas_base

            sembrar_plantillas_base(db, db_usuario.id)
        except Exception:  # noqa: BLE001 - el onboarding no debe romper el alta
            db.rollback()

    _auditar(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="creacion_usuario",
        usuario_id=admin_id,
        registro_id=db_usuario.id,
        valores_nuevos={"email": db_usuario.email, "rol": db_usuario.rol},
        descripcion=f"Usuario creado: {db_usuario.email}",
        resultado="ok",
    )
    return db_usuario


def update_usuario(
    db: Session, usuario_id: int, usuario_in: UsuarioUpdate, admin_id: int | None = None
) -> Usuario:
    db_usuario = get_usuario(db, usuario_id)
    if not db_usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )

    # Auto-protección: un administrador no puede desactivarse a sí mismo.
    if admin_id is not None and admin_id == usuario_id and usuario_in.estado == "inactivo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrador no puede desactivar su propia cuenta.",
        )

    cambios: dict = {}

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
        cambios["email"] = usuario_in.email

    if usuario_in.nombre is not None and usuario_in.nombre != db_usuario.nombre:
        db_usuario.nombre = usuario_in.nombre
        cambios["nombre"] = usuario_in.nombre

    if usuario_in.rol is not None and usuario_in.rol != db_usuario.rol:
        _verificar_ultimo_admin(db, db_usuario, nuevo_rol=usuario_in.rol)
        cambios["rol"] = {"antes": db_usuario.rol, "despues": usuario_in.rol}
        db_usuario.rol = usuario_in.rol

    if usuario_in.password:
        db_usuario.hashed_password = get_password_hash(usuario_in.password)
        cambios["password"] = "cambiada"

    # 3. Si se inactiva el usuario, revocar sus tokens activos
    if usuario_in.estado is not None and usuario_in.estado != db_usuario.estado:
        if usuario_in.estado == "inactivo":
            _verificar_ultimo_admin(db, db_usuario, nuevo_estado="inactivo")
        estado_anterior = db_usuario.estado
        db_usuario.estado = usuario_in.estado
        cambios["estado"] = {"antes": estado_anterior, "despues": usuario_in.estado}
        if usuario_in.estado == "inactivo":
            db.query(Token).filter(
                Token.usuario_id == usuario_id, Token.activo == 1
            ).update({"activo": 0})

    db.commit()
    db.refresh(db_usuario)

    if cambios:
        _auditar(
            db,
            tabla_afectada="usuarios",
            tipo_operacion="modificacion_usuario",
            usuario_id=admin_id,
            registro_id=db_usuario.id,
            valores_anteriores=None,
            valores_nuevos=cambios,
            descripcion=f"Usuario modificado: {db_usuario.email}",
            resultado="ok",
        )
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

    _verificar_ultimo_admin(db, db_usuario, nuevo_estado="inactivo")

    # Borrado lógico: Cambiar estado a inactivo e invalidar sus tokens
    db_usuario.estado = "inactivo"
    db.query(Token).filter(
        Token.usuario_id == usuario_id, Token.activo == 1
    ).update({"activo": 0})

    db.commit()

    _auditar(
        db,
        tabla_afectada="usuarios",
        tipo_operacion="suspension_usuario",
        usuario_id=admin_id,
        registro_id=db_usuario.id,
        valores_anteriores={"estado": "activo"},
        valores_nuevos={"estado": "inactivo"},
        descripcion=f"Usuario desactivado: {db_usuario.email}",
        resultado="ok",
    )
    return True