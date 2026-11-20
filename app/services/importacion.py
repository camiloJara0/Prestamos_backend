"""Importación masiva de datos desde Excel/CSV (Fase 4).

Entidades: clientes, préstamos, pagos y cuotas. Estrategia:
1. `columnas`        → lee el archivo y expone columnas + valores únicos
                       (para el mapeo manual y la homologación de catálogos).
2. `previsualizar`   → valida TODAS las filas contra la BD y devuelve
                       resumen, vista previa y reporte de errores.
3. `ejecutar`        → revalida, importa las filas válidas de forma PARCIAL
                       (cada fila es su propia transacción) y registra la
                       bitácora en `importaciones_log`.

Consistencia de negocio: los préstamos se crean con `services.prestamo
.crear_prestamo` (cuotas, interés, capital y auditoría reales) y los pagos
con `services.pago.registrar_pago` (cuadre exacto por cuota). Las filas
que violen reglas (capital insuficiente, cliente con vencidas, valor que
excede la deuda) se reportan en el reporte de errores sin abortar el lote.
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime

import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.context import aplicar_filtro_usuario, usuario_actual_id
from app.models.models import (
    Cliente,
    HistorialImportacion,
    Pago,
    Prestamo,
    PrestamoCuota,
    TipoPago,
    TipoPrestamo,
)
from app.schemas.importacion import (
    ColumnaDetectada,
    ColumnasOut,
    ImportacionBitacoraOut,
    ImportacionErrorItem,
    ImportacionItemVista,
    ImportacionResultado,
)

MAX_FILAS = 5000
MAX_VISTA_PREVIA = 30
MAX_ERRORES_REPORTADOS = 50
MAX_VALORES_UNICOS = 50

CAMPOS_POR_ENTIDAD: dict[str, list[str]] = {
    "clientes": ["documento", "nombre", "telefono", "direccion", "correo"],
    "prestamos": [
        "cliente", "valor_desembolsado", "fecha_desembolso",
        "tasa", "plazo", "tipo_prestamo",
    ],
    "pagos": ["prestamo", "fecha_pago", "valor", "medio_pago"],
    "cuotas": ["prestamo", "numero_cuota", "fecha_vencimiento", "valor"],
}

CAMPOS_REQUERIDOS: dict[str, set[str]] = {
    "clientes": {"documento", "nombre"},
    "prestamos": {"cliente", "valor_desembolsado", "fecha_desembolso", "tasa", "plazo", "tipo_prestamo"},
    "pagos": {"prestamo", "fecha_pago", "valor", "medio_pago"},
    "cuotas": {"prestamo", "numero_cuota", "fecha_vencimiento", "valor"},
}

# Campos cuyo valor externo se homologa a un id de catálogo (valor → id).
CAMPOS_CATALOGO = {"tipo_prestamo", "medio_pago", "prestamo"}


# ---------------------------------------------------------------------------
# Lectura del archivo
# ---------------------------------------------------------------------------
def leer_dataframe(contenido: bytes, nombre_archivo: str) -> pd.DataFrame:
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(contenido), sheet_name=0)
    else:
        try:
            df = pd.read_csv(
                io.BytesIO(contenido), sep=None, engine="python", encoding="utf-8-sig"
            )
        except UnicodeDecodeError:
            df = pd.read_csv(
                io.BytesIO(contenido), sep=None, engine="python", encoding="latin-1"
            )
    df.columns = [str(c).strip() for c in df.columns]
    return df.head(MAX_FILAS) if len(df) > MAX_FILAS else df


def obtener_columnas(contenido: bytes, nombre_archivo: str) -> ColumnasOut:
    df = leer_dataframe(contenido, nombre_archivo)
    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas.")
    columnas = []
    for c in df.columns:
        valores = [
            v for v in (
                str(x).strip() for x in df[c].tolist() if pd.notna(x)
            ) if v != ""
        ]
        unicos = list(dict.fromkeys(valores))[:MAX_VALORES_UNICOS]
        columnas.append(ColumnaDetectada(nombre=str(c), valores_unicos=unicos))
    return ColumnasOut(columnas=columnas, total_filas=int(len(df)))


# ---------------------------------------------------------------------------
# Normalización de valores
# ---------------------------------------------------------------------------
def _a_float(texto) -> float | None:
    if texto is None or str(texto).strip() == "":
        return None
    s = str(texto).strip().replace("$", "").replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.000.000,50
        else:
            s = s.replace(",", "")  # 1,000,000.50
    elif "," in s:
        parte = s.rsplit(",", 1)[-1]
        s = s.replace(",", ".") if len(parte) in (1, 2) else s.replace(",", "")
    elif "." in s:
        if s.count(".") > 1:
            s = s.replace(".", "")  # 2.350.000 → miles
        else:
            parte = s.rsplit(".", 1)[-1]
            # Heurística COP: un único punto con 3 dígitos tras él es miles (1.500 → 1500)
            if len(parte) == 3 and len(s.split(".")[0]) <= 3:
                s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _a_int(texto) -> int | None:
    valor = _a_float(texto)
    if valor is None or valor != int(valor):
        return None
    return int(valor)


def _a_fecha(texto) -> date | None:
    if texto is None or str(texto).strip() == "":
        return None
    s = str(texto).strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, formato).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(str(texto), dayfirst=True).date()
    except Exception:  # noqa: BLE001
        return None


def _valor_fila(fila: pd.Series, campo: str, mapeo: dict) -> str | None:
    columna = mapeo.get(campo)
    if not columna or columna not in fila.index:
        return None
    valor = fila[columna]
    if pd.isna(valor):
        return None
    return str(valor).strip()


def _homologar(campo: str, valor: str | None, mapeo_catalogos: dict) -> tuple[int | None, str | None]:
    """Valor externo → id de catálogo según el mapeo manual del usuario."""
    if campo not in CAMPOS_CATALOGO:
        return None, None  # campo no homologable (p. ej. cliente por documento)
    if valor in (None, ""):
        return None, None
    mapa = mapeo_catalogos.get(campo) or {}
    id_valor = mapa.get(str(valor)) or mapa.get(str(valor).upper())
    if id_valor is None:
        return None, f"Valor '{valor}' sin homologación para '{campo}'"
    try:
        return int(id_valor), None
    except (TypeError, ValueError):
        return None, f"Homologación inválida para '{campo}': {id_valor}"


# ---------------------------------------------------------------------------
# Validación por fila
# ---------------------------------------------------------------------------
def _validar_clientes(db, fila, n, mapeo, mapeo_catalogos, cedulas_vistas):
    errores: list[ImportacionErrorItem] = []
    documento = _valor_fila(fila, "documento", mapeo)
    nombre = _valor_fila(fila, "nombre", mapeo)
    telefono = _valor_fila(fila, "telefono", mapeo)
    direccion = _valor_fila(fila, "direccion", mapeo)
    correo = _valor_fila(fila, "correo", mapeo)

    if not documento:
        errores.append(ImportacionErrorItem(fila=n, campo="documento", mensaje="El documento es obligatorio"))
    elif documento in cedulas_vistas:
        errores.append(ImportacionErrorItem(fila=n, campo="documento", mensaje="Cédula duplicada en el archivo"))
    else:
        cedulas_vistas.add(documento)
        existente = (
            aplicar_filtro_usuario(db.query(Cliente), Cliente)
            .filter(Cliente.cedula == documento)
            .first()
        )
        if existente:
            errores.append(ImportacionErrorItem(
                fila=n, campo="documento", mensaje="Ya existe un cliente con esa cédula en tu portafolio"
            ))
    if not nombre:
        errores.append(ImportacionErrorItem(fila=n, campo="nombre", mensaje="El nombre es obligatorio"))

    return {
        "documento": documento, "nombre": nombre, "telefono": telefono,
        "direccion": direccion, "correo": correo,
    }, errores


def _validar_prestamos(db, fila, n, mapeo, mapeo_catalogos):
    errores: list[ImportacionErrorItem] = []
    documento_cliente = _valor_fila(fila, "cliente", mapeo)
    cliente_id, error = _homologar("cliente", documento_cliente, mapeo_catalogos)
    if error is None and cliente_id is None and documento_cliente:
        cliente = (
            aplicar_filtro_usuario(db.query(Cliente), Cliente)
            .filter(Cliente.cedula == documento_cliente, Cliente.estado == "activo")
            .first()
        )
        cliente_id = cliente.id if cliente else None
        if cliente_id is None:
            error = f"No existe un cliente activo con documento '{documento_cliente}'"
    if error:
        errores.append(ImportacionErrorItem(fila=n, campo="cliente", mensaje=error))

    valor = _a_float(_valor_fila(fila, "valor_desembolsado", mapeo))
    if valor is None or valor <= 0:
        errores.append(ImportacionErrorItem(fila=n, campo="valor_desembolsado", mensaje="El valor desembolsado debe ser mayor a 0"))

    fecha = _a_fecha(_valor_fila(fila, "fecha_desembolso", mapeo))
    if fecha is None:
        errores.append(ImportacionErrorItem(fila=n, campo="fecha_desembolso", mensaje="Fecha de desembolso inválida (use dd/mm/aaaa)"))

    tasa = _a_float(_valor_fila(fila, "tasa", mapeo))
    if tasa is None or tasa < 0:
        errores.append(ImportacionErrorItem(fila=n, campo="tasa", mensaje="La tasa debe ser un porcentaje válido"))

    plazo = _a_int(_valor_fila(fila, "plazo", mapeo))
    if plazo is None or plazo < 1:
        errores.append(ImportacionErrorItem(fila=n, campo="plazo", mensaje="El plazo debe ser un número de cuotas >= 1"))

    tipo_id, error = _homologar("tipo_prestamo", _valor_fila(fila, "tipo_prestamo", mapeo), mapeo_catalogos)
    if error:
        errores.append(ImportacionErrorItem(fila=n, campo="tipo_prestamo", mensaje=error))
    elif tipo_id is not None:
        tipo = (
            aplicar_filtro_usuario(db.query(TipoPrestamo), TipoPrestamo)
            .filter(TipoPrestamo.id == tipo_id, TipoPrestamo.estado == "activo")
            .first()
        )
        if not tipo:
            errores.append(ImportacionErrorItem(fila=n, campo="tipo_prestamo", mensaje="El tipo de préstamo homologado no existe o está inactivo"))

    return {
        "cliente_id": cliente_id, "capital_prestado": valor, "fecha_desembolso": fecha,
        "porcentaje_interes": tasa, "numero_cuotas": plazo, "tipo_prestamo_id": tipo_id,
    }, errores


def _cuota_para_pago(db, prestamo: Prestamo) -> PrestamoCuota | None:
    """Primera cuota sin pagar del préstamo (por número ascendente)."""
    return (
        db.query(PrestamoCuota)
        .filter(PrestamoCuota.prestamo_id == prestamo.id, PrestamoCuota.estado != "pagado")
        .order_by(PrestamoCuota.numero_cuota.asc())
        .first()
    )


def _preparar_pago(db, datos: dict) -> tuple[dict, list[ImportacionErrorItem]]:
    """Resuelve la cuota vigente y calcula el desglose exacto del pago.

    El desglose (capital/interés/mora) suma EXACTAMENTE el valor del archivo
    para cumplir el cuadre de `registrar_pago` (±0.01). La mora se calcula
    en vivo con la configuración vigente del usuario.
    """
    errores: list[ImportacionErrorItem] = []
    prestamo_id = datos.get("prestamo_id")
    prestamo = (
        aplicar_filtro_usuario(db.query(Prestamo), Prestamo)
        .filter(Prestamo.id == prestamo_id)
        .first()
    )
    if not prestamo:
        errores.append(ImportacionErrorItem(fila=datos["fila"], campo="prestamo", mensaje="El préstamo homologado no existe en tu portafolio"))
        return {}, errores

    from app.services.pago import resumen_deuda_cuota

    cuota = _cuota_para_pago(db, prestamo)
    if not cuota:
        errores.append(ImportacionErrorItem(fila=datos["fila"], campo="prestamo", mensaje=f"El préstamo #{prestamo.id} no tiene cuotas sin pagar"))
        return {}, errores

    resumen = resumen_deuda_cuota(db, cuota)
    valor = datos["valor"] or 0.0
    total = resumen["total_a_pagar"]
    if valor > total + 0.01:
        errores.append(ImportacionErrorItem(
            fila=datos["fila"], campo="valor",
            mensaje=f"El valor excede la deuda de la cuota N° {cuota.numero_cuota} (deuda vigente: ${total:,.2f})",
        ))
        return {}, errores

    capital = round(min(valor, resumen["capital_pendiente"]), 2)
    resto = round(valor - capital, 2)
    interes = round(min(resto, resumen["interes_pendiente"]), 2)
    resto = round(resto - interes, 2)
    mora = round(min(resto, resumen["mora_pendiente"]), 2)

    pago = {
        "prestamo_id": prestamo.id,
        "cliente_id": prestamo.cliente_id,
        "cuota_id": cuota.id,
        "tipo_pago_id": datos.get("tipo_pago_id"),
        "fecha_pago": datos.get("fecha_pago"),
        "valor_pagado": valor,
        "capital_pagado": capital,
        "interes_pagado": interes,
        "mora_pagada": mora,
        "observaciones": "Importado masivamente",
    }
    return pago, errores


def _validar_pagos(db, fila, n, mapeo, mapeo_catalogos):
    errores: list[ImportacionErrorItem] = []
    prestamo_id, error = _homologar("prestamo", _valor_fila(fila, "prestamo", mapeo), mapeo_catalogos)
    if error:
        errores.append(ImportacionErrorItem(fila=n, campo="prestamo", mensaje=error))

    fecha = _a_fecha(_valor_fila(fila, "fecha_pago", mapeo))
    if fecha is None:
        errores.append(ImportacionErrorItem(fila=n, campo="fecha_pago", mensaje="Fecha de pago inválida (use dd/mm/aaaa)"))

    valor = _a_float(_valor_fila(fila, "valor", mapeo))
    if valor is None or valor <= 0:
        errores.append(ImportacionErrorItem(fila=n, campo="valor", mensaje="El valor del pago debe ser mayor a 0"))

    tipo_id, error = _homologar("medio_pago", _valor_fila(fila, "medio_pago", mapeo), mapeo_catalogos)
    if error:
        errores.append(ImportacionErrorItem(fila=n, campo="medio_pago", mensaje=error))
    elif tipo_id is not None:
        tipo = db.query(TipoPago).filter(TipoPago.id == tipo_id, TipoPago.estado == "activo").first()
        if not tipo:
            errores.append(ImportacionErrorItem(fila=n, campo="medio_pago", mensaje="El medio de pago homologado no existe o está inactivo"))

    datos = {
        "fila": n, "prestamo_id": prestamo_id, "fecha_pago": fecha,
        "valor": valor, "tipo_pago_id": tipo_id,
    }
    # Chequeo de deuda en seco (sin insertar): la vista previa refleja el
    # mismo criterio que usará la ejecución (desglose exacto + tope de deuda).
    if not errores:
        _, errores_deuda = _preparar_pago(db, {**datos, "fila": n})
        errores.extend(errores_deuda)
    return datos, errores


def _validar_cuotas(db, fila, n, mapeo, mapeo_catalogos, plan_por_prestamo):
    errores: list[ImportacionErrorItem] = []
    prestamo_id, error = _homologar("prestamo", _valor_fila(fila, "prestamo", mapeo), mapeo_catalogos)
    if error is None and prestamo_id is not None:
        prestamo = (
            aplicar_filtro_usuario(db.query(Prestamo), Prestamo)
            .filter(Prestamo.id == prestamo_id)
            .first()
        )
        if not prestamo:
            error = f"El préstamo #{prestamo_id} no existe en tu portafolio"
        else:
            tiene_cuotas = (
                db.query(PrestamoCuota)
                .filter(PrestamoCuota.prestamo_id == prestamo_id)
                .count()
            )
            if tiene_cuotas:
                error = f"El préstamo #{prestamo_id} ya tiene plan de cuotas generado"
            else:
                clave = plan_por_prestamo.setdefault(prestamo_id, set())
                numero = _a_int(_valor_fila(fila, "numero_cuota", mapeo))
                if numero in clave:
                    error = f"Cuota N° {numero} duplicada para el préstamo #{prestamo_id}"
                else:
                    clave.add(numero)
    if error:
        errores.append(ImportacionErrorItem(fila=n, campo="prestamo", mensaje=error))

    numero = _a_int(_valor_fila(fila, "numero_cuota", mapeo))
    if numero is None or numero < 1:
        errores.append(ImportacionErrorItem(fila=n, campo="numero_cuota", mensaje="El número de cuota debe ser entero >= 1"))

    fecha = _a_fecha(_valor_fila(fila, "fecha_vencimiento", mapeo))
    if fecha is None:
        errores.append(ImportacionErrorItem(fila=n, campo="fecha_vencimiento", mensaje="Fecha de vencimiento inválida (use dd/mm/aaaa)"))

    valor = _a_float(_valor_fila(fila, "valor", mapeo))
    if valor is None or valor <= 0:
        errores.append(ImportacionErrorItem(fila=n, campo="valor", mensaje="El valor de la cuota debe ser mayor a 0"))

    return {
        "prestamo_id": prestamo_id, "numero_cuota": numero,
        "fecha_vencimiento": fecha, "valor": valor,
    }, errores


def _validar_lote(db, entidad, df, mapeo, mapeo_catalogos):
    """Valida todas las filas. Devuelve (datos_por_fila, errores)."""
    requeridos = CAMPOS_REQUERIDOS.get(entidad, set())
    faltantes = [c for c in requeridos if not mapeo.get(c)]
    if faltantes:
        raise HTTPException(
            status_code=400,
            detail=f"Falta mapear la(s) columna(s) para: {', '.join(faltantes)}",
        )

    resultados: list[tuple[int, dict]] = []
    errores: list[ImportacionErrorItem] = []
    cedulas_vistas: set[str] = set()
    plan_por_prestamo: dict[int, set] = {}

    for n, (_, fila) in enumerate(df.iterrows(), start=2):  # fila 1 = encabezados
        if entidad == "clientes":
            datos, errs = _validar_clientes(db, fila, n, mapeo, mapeo_catalogos, cedulas_vistas)
        elif entidad == "prestamos":
            datos, errs = _validar_prestamos(db, fila, n, mapeo, mapeo_catalogos)
        elif entidad == "pagos":
            datos, errs = _validar_pagos(db, fila, n, mapeo, mapeo_catalogos)
        else:
            datos, errs = _validar_cuotas(db, fila, n, mapeo, mapeo_catalogos, plan_por_prestamo)
        errores.extend(errs)
        resultados.append((n, datos))

    return resultados, errores


def _armar_resultado(
    entidad: str, total: int, resultados, errores, bitacora_id: int | None = None, mensaje: str | None = None
) -> ImportacionResultado:
    con_error = {e.fila for e in errores}
    validas = sum(1 for n, _ in resultados if n not in con_error)
    vista = []
    for n, datos in resultados[:MAX_VISTA_PREVIA]:
        vista.append(ImportacionItemVista(
            fila=n,
            datos={k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in datos.items()},
            valido=n not in con_error,
            errores=[e.mensaje for e in errores if e.fila == n],
            homologaciones={k: v for k, v in datos.items() if k.endswith("_id") and v is not None},
        ))
    return ImportacionResultado(
        entidad=entidad,
        total_filas=total,
        validas=validas,
        con_error=len(con_error),
        vista_previa=vista,
        errores=errores[:MAX_ERRORES_REPORTADOS],
        bitacora_id=bitacora_id,
        mensaje=mensaje,
    )


def previsualizar(db: Session, entidad: str, contenido: bytes, nombre: str, mapeo: dict, mapeo_catalogos: dict) -> ImportacionResultado:
    if entidad not in CAMPOS_POR_ENTIDAD:
        raise HTTPException(status_code=400, detail="Entidad inválida; use clientes, prestamos, pagos o cuotas")
    df = leer_dataframe(contenido, nombre)
    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas.")
    resultados, errores = _validar_lote(db, entidad, df, mapeo, mapeo_catalogos)
    return _armar_resultado(entidad, int(len(df)), resultados, errores)


# ---------------------------------------------------------------------------
# Ejecución de la importación
# ---------------------------------------------------------------------------
def _importar_fila(db: Session, entidad: str, datos: dict, usuario_id: int, ip: str | None) -> None:
    if entidad == "clientes":
        from app.schemas.clientes import ClienteCreate
        from app.services.clientes import create_cliente

        create_cliente(db, ClienteCreate(
            cedula=datos["documento"],
            nombre=datos["nombre"] or "",
            telefono=datos.get("telefono"),
            email=datos.get("correo"),
            direccion=datos.get("direccion"),
        ))
    elif entidad == "prestamos":
        from app.schemas.prestamo import PrestamoCreate
        from app.services.prestamo import crear_prestamo

        crear_prestamo(db, PrestamoCreate(
            cliente_id=datos["cliente_id"],
            tipo_prestamo_id=datos["tipo_prestamo_id"],
            capital_prestado=datos["capital_prestado"],
            porcentaje_interes=datos["porcentaje_interes"],
            numero_cuotas=datos["numero_cuotas"],
            fecha_prestamo=datos["fecha_desembolso"],
            observaciones="Importado masivamente",
        ), usuario_id=usuario_id, ip_address=ip)
    elif entidad == "pagos":
        pago_preparado, errores = _preparar_pago(db, datos)
        if errores:
            raise HTTPException(status_code=400, detail=errores[0].mensaje)
        from app.schemas.pago import PagoCreate
        from app.services.pago import registrar_pago

        registrar_pago(db, PagoCreate(**pago_preparado), usuario_id=usuario_id, ip_address=ip)
    else:  # cuotas
        _importar_cuotas_prestamo(db, datos)


def _importar_cuotas_prestamo(db: Session, datos: dict) -> None:
    """Crea la cuota importada; el plan se consolida al final del lote."""
    from app.services.prestamo import generar_referencia_unica_cuota

    cuota = PrestamoCuota(
        prestamo_id=datos["prestamo_id"],
        numero_cuota=datos["numero_cuota"],
        fecha_vencimiento=datos["fecha_vencimiento"],
        valor_cuota=datos["valor"],
        monto_interes=0.0,
        capital=datos["valor"],
        interes=0.0,
        mora=0.0,
        referencia_pago=generar_referencia_unica_cuota(datos["prestamo_id"], datos["numero_cuota"]),
        estado="pendiente",
    )
    db.add(cuota)
    db.commit()


def _consolidar_planes(db: Session, prestamos_con_cuotas: set[int]) -> None:
    """Tras importar cuotas, recalcula los totales de cada préstamo afectado."""

    for prestamo_id in prestamos_con_cuotas:
        cuotas = (
            db.query(PrestamoCuota)
            .filter(PrestamoCuota.prestamo_id == prestamo_id)
            .order_by(PrestamoCuota.numero_cuota.asc())
            .all()
        )
        if not cuotas:
            continue
        prestamo = db.query(Prestamo).filter(Prestamo.id == prestamo_id).first()
        if not prestamo:
            continue
        prestamo.numero_cuotas = len(cuotas)
        prestamo.valor_cuota = cuotas[0].valor_cuota
        prestamo.monto_total = round(sum(c.valor_cuota or 0 for c in cuotas), 2)
        prestamo.interes_total = round(sum(c.interes or 0 for c in cuotas), 2)
        prestamo.saldo_pendiente = round(sum(
            max(0.0, (c.valor_cuota or 0)) for c in cuotas if c.estado != "pagado"
        ), 2)
    db.commit()


def ejecutar(
    db: Session, entidad: str, contenido: bytes, nombre: str, mapeo: dict,
    mapeo_catalogos: dict, usuario_id: int, ip: str | None = None,
) -> ImportacionResultado:
    if entidad not in CAMPOS_POR_ENTIDAD:
        raise HTTPException(status_code=400, detail="Entidad inválida; use clientes, prestamos, pagos o cuotas")
    df = leer_dataframe(contenido, nombre)
    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas.")

    resultados, errores_prevalidacion = _validar_lote(db, entidad, df, mapeo, mapeo_catalogos)
    con_error = {e.fila for e in errores_prevalidacion}

    exitosos = 0
    errores: list[ImportacionErrorItem] = list(errores_prevalidacion)
    planes_afectados: set[int] = set()

    for n, datos in resultados:
        if n in con_error:
            continue
        try:
            if entidad == "cuotas" and datos.get("prestamo_id"):
                planes_afectados.add(datos["prestamo_id"])
            _importar_fila(db, entidad, datos, usuario_id, ip)
            exitosos += 1
        except HTTPException as exc:
            errores.append(ImportacionErrorItem(fila=n, campo=None, mensaje=str(exc.detail)))
        except Exception as exc:  # noqa: BLE001 - la fila falla, el lote continúa
            errores.append(ImportacionErrorItem(fila=n, campo=None, mensaje=f"Error inesperado: {exc}"))

    if planes_afectados:
        _consolidar_planes(db, planes_afectados)

    fila_bitacora = HistorialImportacion(
        usuario_id=usuario_id or usuario_actual_id.get(),
        entidad=entidad,
        archivo_nombre=nombre or None,
        total_filas=int(len(df)),
        exitosos=exitosos,
        errores=len(errores),
        bitacora=json.dumps([e.model_dump() for e in errores], ensure_ascii=False),
    )
    db.add(fila_bitacora)
    db.commit()
    db.refresh(fila_bitacora)

    mensaje = (
        f"Importación completada: {exitosos} filas importadas, {len(errores)} con error."
        if exitosos else "Ninguna fila pudo importarse; revisa el reporte de errores."
    )
    return _armar_resultado(entidad, int(len(df)), resultados, errores, fila_bitacora.id, mensaje)


def listar_bitacoras(db: Session, limite: int = 50) -> list[ImportacionBitacoraOut]:
    filas = (
        aplicar_filtro_usuario(db.query(HistorialImportacion), HistorialImportacion)
        .order_by(HistorialImportacion.created_at.desc())
        .limit(limite)
        .all()
    )
    return [ImportacionBitacoraOut.model_validate(f) for f in filas]
