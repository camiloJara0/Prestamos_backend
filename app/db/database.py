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
        ("mora_tipo", "porcentaje", "Modo de mora: 'porcentaje' o 'fijo'", "string"),
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


# ---------------------------------------------------------------------------
# Backoffice: índices para filtros frecuentes (create_all solo crea índices
# de tablas NUEVAS; estas columnas se agregan a tablas existentes).
# ---------------------------------------------------------------------------
_INDICES_BACKOFFICE = (
    ("tokens", ("usuario_id", "activo"), "idx_tokens_usuario_activo"),
    ("tokens", ("expires_at",), "idx_tokens_expires_at"),
    ("auditoria", ("fecha",), "idx_auditoria_fecha"),
    ("auditoria", ("tipo_operacion", "fecha"), "idx_auditoria_tipo_fecha"),
    ("errores_app", ("ultima_ocurrencia",), "idx_errores_app_ultima"),
    ("ejecuciones_proceso", ("tarea", "fecha_solicitud"), "idx_ejecuciones_tarea_fecha"),
)


def _asegurar_unicidad_cedula():
    """La cédula del cliente deja de ser única GLOBAL: pasa a ser única
    dentro del portafolio de cada prestamista (el servicio valida por
    usuario). Elimina el UNIQUE heredado y deja índice normal."""
    from sqlalchemy.schema import CreateTable

    from app.models.models import Cliente

    inspector = inspect(engine)
    if "clientes" not in inspector.get_table_names():
        return

    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            filas = conn.execute(text(
                "SELECT INDEX_NAME, NON_UNIQUE FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'clientes' "
                "AND SEQ_IN_INDEX = 1"
            )).fetchall()
            indices = {}
            for nombre_idx, non_unique in filas:
                indices.setdefault(nombre_idx, not non_unique)
            unicos = [n for n, u in indices.items() if u and n.lower().endswith("cedula")]
            if not unicos:
                return
            for n in unicos:
                conn.execute(text(f"ALTER TABLE clientes DROP INDEX {n}"))
            conn.execute(text("CREATE INDEX ix_clientes_cedula ON clientes (cedula)"))
        print("Migración: cédula de clientes ya no es única global (MySQL)")
        return

    tiene_global = False
    with engine.begin() as conn:
        for fila in conn.execute(text("PRAGMA index_list('clientes')")).fetchall():
            nombre_idx, es_unique, origen = fila[1], fila[2], fila[3]
            if not es_unique or origen not in ("u", "pk"):
                continue
            cols = {
                c[2]
                for c in conn.execute(text(f"PRAGMA index_info('{nombre_idx}')")).fetchall()
            }
            if cols == {"cedula"}:
                tiene_global = True
                break
    if not tiene_global:
        return

    ddl = str(CreateTable(Cliente.__table__).compile(engine))
    ddl = ddl.replace("CREATE TABLE clientes", "CREATE TABLE clientes__nueva", 1)
    import re as _re2

    ddl = _re2.sub(r",\s*\n?\s*UNIQUE \(cedula\)", "", ddl)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS clientes__nueva"))
        conn.execute(text(ddl))
        conn.execute(text(
            "INSERT INTO clientes__nueva "
            "(id, usuario_id, nombre, cedula, telefono, email, direccion, "
            "persona_referencia, telefono_referencia, observaciones, estado, created_at, updated_at) "
            "SELECT id, usuario_id, nombre, cedula, telefono, email, direccion, "
            "persona_referencia, telefono_referencia, observaciones, estado, created_at, updated_at "
            "FROM clientes"
        ))
        conn.execute(text("DROP TABLE clientes"))
        conn.execute(text("ALTER TABLE clientes__nueva RENAME TO clientes"))
        conn.execute(text("CREATE INDEX ix_clientes_id ON clientes (id)"))
        conn.execute(text("CREATE INDEX ix_clientes_usuario_id ON clientes (usuario_id)"))
        conn.execute(text("CREATE INDEX ix_clientes_cedula ON clientes (cedula)"))
    print("Migración: cédula de clientes ya no es única global (tabla reconstruida)")


def _asegurar_indices_backoffice():
    """Crea los índices del Backoffice si faltan (idempotente, multi-dialecto)."""
    inspector = inspect(engine)
    existentes = set(inspector.get_table_names())
    for tabla, columnas, nombre in _INDICES_BACKOFFICE:
        if tabla not in existentes:
            continue
        actuales = {idx["name"] for idx in inspector.get_indexes(tabla)}
        if nombre in actuales:
            continue
        cols = ", ".join(columnas)
        with engine.begin() as conn:
            conn.execute(text(f"CREATE INDEX {nombre} ON {tabla} ({cols})"))
        print(f"Índice: {nombre} creado en {tabla}")


def _asegurar_uniqueness_plantillas():
    """La clave de plantilla pasa de única global a única por usuario.

    Requiere reconstruir la tabla en SQLite (no se puede eliminar el
    autoindex de un UNIQUE heredado); en MySQL basta DROP INDEX/ADD UNIQUE.
    Idempotente: no hace nada si el constraint compuesto ya existe.
    """
    import re as _re

    from sqlalchemy.schema import CreateTable

    from app.models.models import PlantillaMensaje

    inspector = inspect(engine)
    if "plantillas_mensaje" not in inspector.get_table_names():
        return

    dialecto = engine.dialect.name

    if dialecto == "mysql":
        with engine.begin() as conn:
            filas = conn.execute(text(
                "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'plantillas_mensaje'"
            )).fetchall()
            por_indice: dict[str, dict] = {}
            for nombre_idx, non_unique, seq, col in filas:
                info = por_indice.setdefault(nombre_idx, {"unique": not non_unique, "cols": {}})
                info["cols"][seq] = col
            tiene_global = any(
                i["unique"] and list(i["cols"].values()) == ["clave"] for i in por_indice.values()
            )
            if not tiene_global:
                return
            conn.execute(text("ALTER TABLE plantillas_mensaje DROP INDEX clave"))
            conn.execute(text(
                "ALTER TABLE plantillas_mensaje "
                "ADD UNIQUE KEY uq_plantillas_usuario_clave (usuario_id, clave, canal)"
            ))
        print("Migración: unicidad de plantillas ahora es por usuario (MySQL)")
        return

    # SQLite: detectar UNIQUE(clave) heredado (incluye sqlite_autoindex).
    tiene_global = False
    with engine.begin() as conn:
        for fila in conn.execute(text("PRAGMA index_list('plantillas_mensaje')")).fetchall():
            nombre_idx, es_unique, origen = fila[1], fila[2], fila[3]
            if not es_unique or origen not in ("u", "pk"):
                continue
            cols = {
                c[2]
                for c in conn.execute(text(f"PRAGMA index_info('{nombre_idx}')")).fetchall()
            }
            if cols == {"clave"}:
                tiene_global = True
                break
    if not tiene_global:
        return

    ddl = str(CreateTable(PlantillaMensaje.__table__).compile(engine))
    ddl = ddl.replace("CREATE TABLE plantillas_mensaje", "CREATE TABLE plantillas_mensaje__nueva", 1)
    ddl = _re.sub(r",\s*\n?\s*UNIQUE \(clave\)", "", ddl)
    ddl = ddl.rstrip().rstrip(");") + ",\n\tUNIQUE (usuario_id, clave, canal)\n)"

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS plantillas_mensaje__nueva"))
        conn.execute(text(ddl))
        conn.execute(text(
            "INSERT INTO plantillas_mensaje__nueva "
            "(id, usuario_id, clave, canal, nombre, asunto, cuerpo, activa, created_at, updated_at) "
            "SELECT id, usuario_id, clave, canal, nombre, asunto, cuerpo, activa, created_at, updated_at "
            "FROM plantillas_mensaje"
        ))
        conn.execute(text("DROP TABLE plantillas_mensaje"))
        conn.execute(text("ALTER TABLE plantillas_mensaje__nueva RENAME TO plantillas_mensaje"))
        conn.execute(text("CREATE INDEX ix_plantillas_mensaje_id ON plantillas_mensaje (id)"))
        conn.execute(text("CREATE INDEX ix_plantillas_mensaje_usuario_id ON plantillas_mensaje (usuario_id)"))
    print("Migración: unicidad de plantillas ahora es por usuario (tabla reconstruida)")


def _asegurar_parametros_backoffice():
    """Siembra los parámetros de retención/límites del Backoffice (idempotente)."""
    from app.models.models import ConfiguracionSistema

    base = [
        ("sesiones_maximas", "5", "Sesiones activas simultáneas por usuario", "int"),
        ("login_max_intentos", "10", "Intentos de login permitidos por ventana", "int"),
        ("login_ventana_min", "15", "Ventana (minutos) del rate limit de login", "int"),
        ("tokens_retencion_dias", "30", "Días de retención de tokens revocados", "int"),
        ("errores_retencion_dias", "180", "Días de retención de errores resueltos/ignorados", "int"),
        ("metricas_retencion_dias", "180", "Días de retención de métricas API", "int"),
        ("idempotency_retencion_horas", "48", "Horas de retención de claves de idempotencia", "int"),
        ("notificaciones_retencion_dias", "90", "Días de retención de notificaciones leídas (0=desactivado)", "int"),
        ("envios_retencion_dias", "180", "Días de retención del log de envíos de mensajes", "int"),
        ("auditoria_retencion_dias", "0", "Días de retención de auditoría (0=nunca se elimina)", "int"),
        ("nombre_empresa", "LoanSoft", "Nombre de la empresa usado en PDFs, reportes, contratos, comprobantes y mensajes", "string"),
        ("empresa_telefono", "", "Teléfono de la empresa mostrado en mensajes y documentos (vacío = usar variable de entorno EMPRESA_TELEFONO)", "string"),
        ("whatsapp_max_por_minuto", "60", "Máximo de mensajes WhatsApp por minuto en envíos masivos", "int"),
    ]
    with SessionLocal() as db:
        existentes = {c.clave for c in db.query(ConfiguracionSistema).all()}
        for clave, valor, descripcion, tipo in base:
            if clave not in existentes:
                db.add(ConfiguracionSistema(
                    clave=clave, valor=valor, descripcion=descripcion, tipo_valor=tipo, activo=1,
                ))
        db.commit()


def _asegurar_estados_envio():
    """El estado de envio pasa de ENUM con CHECK a String(30) para admitir los
    estados de entrega de WhatsApp (pendiente/entregado/leido). En SQLite el
    CHECK heredado obliga a reconstruir la tabla; en MySQL basta MODIFY."""
    from sqlalchemy.schema import CreateTable

    from app.models.models import EnvioMensaje

    inspector = inspect(engine)
    if "envios_mensaje" not in inspector.get_table_names():
        return

    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            filas = conn.execute(text(
                "SELECT COLUMN_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'envios_mensaje' "
                "AND COLUMN_NAME = 'estado'"
            )).fetchall()
            tipo = (filas[0][0] if filas else "")
            if "enum" in tipo.lower():
                conn.execute(text(
                    "ALTER TABLE envios_mensaje MODIFY COLUMN estado VARCHAR(30) NOT NULL"
                ))
                print("Migración: estado de envios_mensaje ahora VARCHAR (MySQL)")
        return

    with engine.begin() as conn:
        sql_tabla = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='envios_mensaje'"
        )).scalar() or ""
    if "CHECK (estado IN" not in sql_tabla and "CHECK(estado IN" not in sql_tabla:
        return

    ddl = str(CreateTable(EnvioMensaje.__table__).compile(engine))
    ddl = ddl.replace("CREATE TABLE envios_mensaje", "CREATE TABLE envios_mensaje__nueva", 1)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS envios_mensaje__nueva"))
        conn.execute(text(ddl))
        conn.execute(text(
            "INSERT INTO envios_mensaje__nueva "
            "(id, usuario_id, cliente_id, canal, destinatario, asunto, cuerpo, plantilla_id, "
            "estado, motivo, dedupe_clave, fecha, whatsapp_message_id, respuesta_proveedor, error_detalle) "
            "SELECT id, usuario_id, cliente_id, canal, destinatario, asunto, cuerpo, plantilla_id, "
            "estado, motivo, dedupe_clave, fecha, whatsapp_message_id, respuesta_proveedor, error_detalle "
            "FROM envios_mensaje"
        ))
        conn.execute(text("DROP TABLE envios_mensaje"))
        conn.execute(text("ALTER TABLE envios_mensaje__nueva RENAME TO envios_mensaje"))
        conn.execute(text("CREATE INDEX ix_envios_mensaje_id ON envios_mensaje (id)"))
        conn.execute(text("CREATE INDEX ix_envios_mensaje_usuario_id ON envios_mensaje (usuario_id)"))
        conn.execute(text("CREATE INDEX ix_envios_mensaje_cliente_id ON envios_mensaje (cliente_id)"))
        conn.execute(text("CREATE INDEX ix_envios_mensaje_estado ON envios_mensaje (estado)"))
    print("Migración: envios_mensaje reconstruida sin CHECK de estado (WhatsApp listo)")


def _asegurar_plantillas_whatsapp():
    """Canal principal = WhatsApp.

    - Siembra las plantillas WhatsApp predeterminadas a cada prestamista
      existente que no las tenga.
    - Desactiva (no elimina) las plantillas base de SMS heredadas para que
      los flujos migren a WhatsApp; se pueden reactivar manualmente cuando
      se vuelva a habilitar el canal SMS.
    """
    from app.models.models import PlantillaMensaje, Usuario

    claves_sms = {
        "recordatorio_vencimiento", "solicitud_decidida", "pago_confirmado",
        "mora_aviso", "cliente_bienvenida",
    }
    with SessionLocal() as db:
        prestamistas = (
            db.query(Usuario.id).filter(
                Usuario.rol == "prestamista", Usuario.estado == "activo"
            ).all()
        )
        for (uid,) in prestamistas:
            try:
                from app.services.plantillas import sembrar_plantillas_base

                sembrar_plantillas_base(db, uid)
            except Exception:  # noqa: BLE001
                db.rollback()
        try:
            db.query(PlantillaMensaje).filter(
                PlantillaMensaje.canal == "sms",
                PlantillaMensaje.clave.in_(claves_sms),
                PlantillaMensaje.usuario_id.isnot(None),
            ).update({"activa": False}, synchronize_session=False)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()


def init_db():
    Base.metadata.create_all(bind=engine)
    _apply_simple_migrations()
    _asegurar_uniqueness_plantillas()
    _asegurar_unicidad_cedula()
    _asegurar_estados_envio()
    _asegurar_indices_backoffice()
    _backfill_usuario_id()
    _asegurar_parametros_base()
    _asegurar_parametros_backoffice()
    _asegurar_plantillas_whatsapp()


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