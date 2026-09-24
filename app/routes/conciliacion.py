import io
import re
import pdfplumber
import pandas as pd
from difflib import SequenceMatcher
from datetime import date
from typing import List, Tuple
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models import PrestamoCuota, Prestamo, Cliente, Pago
from app.schemas.conciliacion import ConciliacionResumenResponse, ResultadoItemConciliacion
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/conciliacion", tags=["Conciliación de Extractos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def limpiar_texto(texto: str) -> str:
    """Remueve caracteres especiales y espacios para comparar referencias de forma flexible."""
    if not texto:
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(texto).upper())


def calcular_similitud(s1: str, s2: str) -> float:
    return SequenceMatcher(None, s1, s2).ratio()


def extraer_registros_de_archivo(contenido: bytes, extension: str) -> List[Tuple[int, str]]:
    """
    Convierte el archivo (PDF, Excel o CSV) en una lista de tuplas (num_posicion, texto_plano_de_linea).
    """
    registros = []

    # --- 1. PROCESAR PDF ---
    if extension == ".pdf":
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            for num_pagina, page in enumerate(pdf.pages, start=1):
                texto = page.extract_text()
                if texto:
                    for linea in texto.split("\n"):
                        if linea.strip():
                            registros.append((num_pagina, linea))

    # --- 2. PROCESAR EXCEL (.xlsx, .xls) ---
    elif extension in [".xlsx", ".xls"]:
        dict_hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None)
        fila_contador = 2  # Asumiendo encabezado en fila 1
        for _, df in dict_hojas.items():
            for _, row in df.iterrows():
                texto_fila = " ".join([str(val) for val in row.values if pd.notna(val)])
                if texto_fila.strip():
                    registros.append((fila_contador, texto_fila))
                fila_contador += 1

    # --- 3. PROCESAR CSV ---
    elif extension == ".csv":
        df = pd.read_csv(io.BytesIO(contenido))
        for idx, row in df.iterrows():
            texto_fila = " ".join([str(val) for val in row.values if pd.notna(val)])
            if texto_fila.strip():
                registros.append((idx + 2, texto_fila))

    return registros


@router.post("/procesar-extracto", response_model=ConciliacionResumenResponse)
async def procesar_extracto_bancario(
    file: UploadFile = File(...),
    aplicar_pagos_automaticos: bool = False,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Lee un extracto bancario en PDF, Excel (.xlsx, .xls) o CSV, detecta las referencias de pago
    y concilia los montos ingresados contra las cuotas pendientes.
    """
    nombre_lower = file.filename.lower()
    extensiones_validas = [".pdf", ".xlsx", ".xls", ".csv"]
    ext = next((e for e in extensiones_validas if nombre_lower.endswith(e)), None)

    if not ext:
        raise HTTPException(
            status_code=400, 
            detail="Formato no soportado. Debe adjuntar un archivo .pdf, .xlsx, .xls o .csv"
        )

    contenido = await file.read()

    try:
        registros_extraidos = extraer_registros_de_archivo(contenido, ext)
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Error al parsear el archivo {file.filename}: {str(e)}"
        )

    # Cargar cuotas pendientes con sus relaciones
    cuotas_pendientes = (
        db.query(PrestamoCuota, Prestamo, Cliente)
        .join(Prestamo, PrestamoCuota.prestamo_id == Prestamo.id)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
        .filter(PrestamoCuota.estado == "pendiente")
        .all()
    )

    mapa_cuotas = {limpiar_texto(c[0].referencia_pago): c for c in cuotas_pendientes if c[0].referencia_pago}

    detalles = []
    conciliados_count = 0
    diferencias_count = 0
    no_encontrados_count = 0

    for posicion, texto_linea in registros_extraidos:
        texto_limpio = limpiar_texto(texto_linea)

        # Extraer montos numéricos (se buscan números mayores a 1000)
        numeros = re.findall(r'\d+(?:\.\d+)?', texto_linea.replace(',', '').replace('$', ''))
        monto_extraido = float(max([float(n) for n in numeros if float(n) >= 1000], default=0.0))

        referencia_detectada = None
        cuota_encontrada = None
        mejor_match_score = 0.0

        # Buscar coincidencia exacta o por grados de similitud
        for ref_limpia, data in mapa_cuotas.items():
            if ref_limpia in texto_limpio:
                referencia_detectada = ref_limpia
                cuota_encontrada = data
                mejor_match_score = 1.0
                break
            else:
                score = calcular_similitud(ref_limpia, texto_limpio)
                if score > 0.85 and score > mejor_match_score:
                    mejor_match_score = score
                    referencia_detectada = ref_limpia
                    cuota_encontrada = data

        if cuota_encontrada:
            cuota, prestamo, cliente = cuota_encontrada
            
            # Tolerancia de $10 pesos por comisiones/redondeos
            if abs(monto_extraido - cuota.valor_cuota) <= 10:
                estado = "MATCH_EXACTO"
                mensaje = f"Pago conciliado correctamente con el cliente {cliente.nombre}."
                conciliados_count += 1

                if aplicar_pagos_automaticos:
                    cuota.estado = "pagado"
                    cuota.fecha_pago = date.today()
                    
                    nuevo_pago = Pago(
                        prestamo_id=prestamo.id,
                        cliente_id=cliente.id,
                        cuota_id=cuota.id,
                        fecha_pago=date.today(),
                        valor_pagado=monto_extraido,
                        observaciones=f"Conciliación Automática Extracto. Ref: {cuota.referencia_pago}"
                    )
                    db.add(nuevo_pago)
                    db.commit()
            else:
                estado = "MONTO_DIFERENTE"
                mensaje = f"Referencia hallada pero los montos no coinciden. Archivo: ${monto_extraido} vs Cuota: ${cuota.valor_cuota}"
                diferencias_count += 1

            detalles.append(
                ResultadoItemConciliacion(
                    fila_o_pagina=posicion,
                    referencia_encontrada=referencia_detectada,
                    referencia_coincidente=cuota.referencia_pago,
                    monto_extraido=monto_extraido,
                    monto_cuota=cuota.valor_cuota,
                    cliente_nombre=cliente.nombre,
                    cuota_id=cuota.id,
                    estado_conciliacion=estado,
                    mensaje=mensaje
                )
            )
        else:
            # Solo se agrega a "No Encontrados" si se detectó al menos un patrón de monto válido
            if monto_extraido > 0:
                no_encontrados_count += 1
                detalles.append(
                    ResultadoItemConciliacion(
                        fila_o_pagina=posicion,
                        referencia_encontrada=None,
                        referencia_coincidente=None,
                        monto_extraido=monto_extraido,
                        monto_cuota=None,
                        cliente_nombre=None,
                        cuota_id=None,
                        estado_conciliacion="NO_ENCONTRADO",
                        mensaje="No se encontró ninguna referencia coincidente para esta entrada del extracto."
                    )
                )

    return ConciliacionResumenResponse(
        total_procesados=len(detalles),
        total_conciliados=conciliados_count,
        total_con_diferencia=diferencias_count,
        total_no_encontrados=no_encontrados_count,
        detalles=detalles
    )