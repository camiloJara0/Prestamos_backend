import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker, Session as ORMSession

import app.models
from app.models.base import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+psycopg2://",
        1
    )

engine = create_engine(DATABASE_URL, echo=True, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def _apply_simple_migrations():
    """Mini-migración de desarrollo: maneja cambios estructurales específicos y dinámicos."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # ------------------------------------------------------------------
    # Caso puntual: Renombrar prestamista_id a usuario_id si existe
    # ------------------------------------------------------------------
    if "metodos_pago_prestamista" in existing_tables:
        cols = {c["name"] for c in inspector.get_columns("metodos_pago_prestamista")}
        
        if "prestamista_id" in cols and "usuario_id" not in cols:
            with engine.begin() as conn:
                if DATABASE_URL.startswith("mysql"):
                    conn.execute(text(
                        "ALTER TABLE metodos_pago_prestamista CHANGE prestamista_id usuario_id INT NOT NULL"
                    ))
                elif DATABASE_URL.startswith("postgres"):
                    conn.execute(text(
                        "ALTER TABLE metodos_pago_prestamista RENAME COLUMN prestamista_id TO usuario_id"
                    ))
                elif DATABASE_URL.startswith("sqlite"):
                    conn.execute(text(
                        "ALTER TABLE metodos_pago_prestamista RENAME COLUMN prestamista_id TO usuario_id"
                    ))
            print("Migración: Renombrada columna prestamista_id a usuario_id en metodos_pago_prestamista")

    # ------------------------------------------------------------------
    # Bucle dinámico para añadir columnas faltantes
    # ------------------------------------------------------------------
    is_sqlite = DATABASE_URL.startswith("sqlite")

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                if DATABASE_URL.startswith("mysql") and hasattr(column.type, "enums"):
                    enums_str = ", ".join(f"'{e}'" for e in column.type.enums)
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                f"ALTER TABLE {table.name} MODIFY COLUMN {column.name} ENUM({enums_str})"
                            )
                        )
                continue

            coltype = column.type.compile(engine.dialect)
            default = ""
            if column.default is not None and not callable(column.default.arg):
                if isinstance(column.default.arg, str):
                    default = f" DEFAULT '{column.default.arg}'"
                else:
                    default = f" DEFAULT {column.default.arg}"

            # Regla de nulabilidad
            nullable = "" if column.nullable else " NOT NULL"

            if is_sqlite and not column.nullable and not default:
                # Si es una clave foránea o entero, asignamos 1 por defecto
                if "INT" in str(coltype).upper():
                    default = " DEFAULT 1"
                else:
                    default = " DEFAULT ''"

            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {table.name} ADD COLUMN {column.name} {coltype}{default}{nullable}"
                    )
                )
            print(f"Migración: columna {table.name}.{column.name} añadida correctamente")


def _backfill_usuario_id():
    """Asigna usuario_id a registros existentes que no lo tengan (multiusuario).

    Los datos preexistentes de una instancia single-user se atribuyen al primer
    usuario (id=1, el admin del seed). Idempotente: solo toca NULLs.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    try:
        with engine.begin() as conn:
            hay_usuarios = conn.execute(text("SELECT COUNT(*) FROM usuarios")).scalar() or 0
    except Exception:
        return
    if not hay_usuarios:
        return

    tablas = [
        "clientes", "tipos_prestamo", "tipos_pago", "prestamos", "pagos",
        "moras", "capital", "movimientos_capital", "configuracion_sistema",
        "plantillas_mensaje", "tipos_cita", "eventos_agenda", "contratos",
        "prestamos_renovaciones", "prestamos_reestructuraciones",
        "prestamos_perdidos", "envios_mensaje",
    ]
    for tabla in tablas:
        if tabla not in existing_tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(tabla)}
        if "usuario_id" not in cols:
            continue
        with engine.begin() as conn:
            conn.execute(
                text(f"UPDATE {tabla} SET usuario_id = 1 WHERE usuario_id IS NULL")
            )


def _asegurar_parametros_base():
    """Crea los parámetros base de mora si faltan (idempotente, no toca existentes)."""
    from app.models.models import ConfiguracionSistema

    base = [
        ("tasa_mora_diaria", "0.5", "Porcentaje de mora diaria por cuota vencida", "float"),
        ("dias_gracia_mora", "3", "Días de gracia antes de aplicar mora", "int"),
        ("mora_tipo", "porcentaje", "Modo de mora diaria: 'porcentaje' o 'fijo'", "string"),
        ("mora_valor_fijo", "0", "Valor fijo de mora por día cuando mora_tipo = 'fijo'", "float"),
        ("mora_tipo_calculo", "simple", "Tipo de cálculo de mora: 'simple' (lineal) o 'compuesta'", "string"),
    ]
    with SessionLocal() as db:
        existentes = {c.clave for c in db.query(ConfiguracionSistema).all()}
        for clave, valor, descripcion, tipo in base:
            if clave not in existentes:
                db.add(ConfiguracionSistema(
                    clave=clave, valor=valor, descripcion=descripcion, tipo_valor=tipo, activo=1,
                ))
        db.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    _apply_simple_migrations()
    _backfill_usuario_id()
    _asegurar_parametros_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Multiusuario: asigna el dueño (usuario_id) a todo registro nuevo del dominio
# financiero cuando hay un usuario autenticado en el contexto del request.
# ---------------------------------------------------------------------------
_MODELOS_DOMINIO = None


def _modelos_dominio():
    global _MODELOS_DOMINIO
    if _MODELOS_DOMINIO is None:
        from app.models.models import (
            Cliente, TipoPrestamo, TipoPago, Prestamo, Pago, Mora,
            Capital, MovimientoCapital, TipoCita, EventoAgenda, Contrato,
            PrestamoRenovacion, PrestamoReestructuracion, PrestamoPerdido,
        )
        _MODELOS_DOMINIO = (
            Cliente, TipoPrestamo, TipoPago, Prestamo, Pago, Mora,
            Capital, MovimientoCapital, TipoCita, EventoAgenda, Contrato,
            PrestamoRenovacion, PrestamoReestructuracion, PrestamoPerdido,
        )
    return _MODELOS_DOMINIO


@event.listens_for(ORMSession, "before_flush")
def _auto_asignar_usuario_dominio(session, flush_context, instances):
    from app.core.context import usuario_actual_id

    uid = usuario_actual_id.get()
    if not uid:
        return
    dominio = _modelos_dominio()
    for obj in session.new:
        if isinstance(obj, dominio) and getattr(obj, "usuario_id", None) is None:
            obj.usuario_id = uid