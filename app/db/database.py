import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import app.models
from app.models.base import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

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


def init_db():
    Base.metadata.create_all(bind=engine)
    _apply_simple_migrations()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()