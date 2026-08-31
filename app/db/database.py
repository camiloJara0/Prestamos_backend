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
    """Mini-migración de desarrollo: añade columnas faltantes y actualiza ENUMs en MySQL."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                if DATABASE_URL.startswith("mysql") and hasattr(
                    column.type, "enums"
                ):
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
            nullable = "" if column.nullable else " NOT NULL"

            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"ALTER TABLE {table.name} ADD COLUMN {column.name} {coltype}{default}{nullable}"
                    )
                )
            print(f"Migración: columna {table.name}.{column.name} añadida")


def init_db():
    Base.metadata.create_all(bind=engine)
    _apply_simple_migrations()
    
# --- FUNCIÓN REQUERIDA PARA INYECCIÓN DE DEPENDENCIAS ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()