import io
import re
import pdfplumber
import pandas as pd
from sqlalchemy.orm import Session

from app.models import PrestamoCuota, Cliente, Prestamo
from app.schemas.pago import PagoCreate
from app.services.pago import registrar_pago


def extraer_referencias_de_bytes(contenido: bytes, extension: str) -> set[str]:
    """
    Extrae todas las cadenas que coincidan con el patrón REF-P... 
    desde archivos PDF, Excel (.xlsx/.xls) o CSV.
    """
    referencias = set()
    patron_ref = r"REF-P\d+C\d+(?:-[A-Z0-9]+)?"

    # --- CASO 1: Archivo PDF ---
    if extension == ".pdf":
        with pdfplumber.open(io.BytesIO(contenido)) as pdf:
            for page in pdf.pages:
                texto = page.extract_text()
                if texto:
                    coincidencias = re.findall(patron_ref, texto)
                    referencias.update(coincidencias)

    # --- CASO 2: Archivo Excel (.xlsx, .xls) ---
    elif extension in [".xlsx", ".xls"]:
        # Lee todas las hojas del Excel
        dict_hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, dtype=str)
        for nombre_hoja, df in dict_hojas.items():
            # Convierte toda la tabla a texto plano para buscar el patrón
            texto_completo = df.astype(str).to_string()
            coincidencias = re.findall(patron_ref, texto_completo)
            referencias.update(coincidencias)

    # --- CASO 3: Archivo CSV ---
    elif extension == ".csv":
        df = pd.read_csv(io.BytesIO(contenido), dtype=str)
        texto_completo = df.astype(str).to_string()
        coincidencias = re.findall(patron_ref, texto_completo)
        referencias.update(coincidencias)

    return referencias


def procesar_extracto_bancario(contenido: bytes, nombre_archivo: str, db: Session, usuario_id: int) -> dict:
    """
    Lee el extracto (PDF o Excel), cruza las referencias de pago y 
    liquida de forma automática las cuotas que estaban pendientes.
    """
    ext = "." + nombre_archivo.split(".")[-1].lower() if "." in nombre_archivo else ""
    if ext not in [".pdf", ".xlsx", ".xls", ".csv"]:
        raise ValueError("Formato no soportado. Debe ser un archivo PDF, Excel (.xlsx/.xls) o CSV.")

    # 1. Extraer las referencias únicas encontradas en el documento
    referencias_encontradas = extraer_referencias_de_bytes(contenido, ext)

    pagados_auto = []
    ya_pagados = []
    no_encontrados = []

    # 2. Iterar sobre cada referencia detectada y cruzar con la BD
    for ref in referencias_encontradas:
        cuota = db.query(PrestamoCuota).filter(PrestamoCuota.referencia_pago == ref).first()

        if not cuota:
            no_encontrados.append(ref)
            continue

        # Si ya figura como PAGADO, no duplicamos el registro
        if cuota.estado == "pagado":
            ya_pagados.append({
                "referencia": ref,
                "cuota_id": cuota.id,
                "mensaje": "La cuota ya se encontraba liquidada previamente."
            })
            continue

        # 3. Si está PENDIENTE, registrar el pago automáticamente
        prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
        
        pago_schema = PagoCreate(
            prestamo_id=cuota.prestamo_id,
            cliente_id=prestamo.cliente_id,
            cuota_id=cuota.id,
            tipo_pago_id=1,  # ID correspondiente a Transferencia / Extracto Bancario
            fecha_pago=str(cuota.fecha_vencimiento),
            valor_pagado=cuota.valor_cuota,
            capital_pagado=cuota.valor_cuota,
            interes_pagado=0.0,
            mora_pagada=0.0,
            observaciones=f"Pago automático por conciliación de extracto bancario ({ref})"
        )

        nuevo_pago = registrar_pago(db, pago_schema, usuario_id=usuario_id)

        pagados_auto.append({
            "referencia": ref,
            "cuota_id": cuota.id,
            "monto_pagado": cuota.valor_cuota,
            "pago_id": nuevo_pago.id,
            "estado": "PAGADO_AUTOMATICO"
        })

    return {
        "archivo": nombre_archivo,
        "total_referencias_detectadas": len(referencias_encontradas),
        "pagos_registrados_exitosos": pagados_auto,
        "omitidos_ya_pagados": ya_pagados,
        "referencias_no_encontradas": no_encontrados
    }