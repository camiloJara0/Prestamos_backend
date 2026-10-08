"""Contrato electrónico del préstamo (RF-066).

Adaptador de firma configurable por variable de entorno:
  FIRMA_PROVIDER: 'piloto' (default) | 'externo'

El proveedor piloto registra la firma con huella (hash) del documento y los
datos del firmante. El proveedor externo se conecta cuando exista contrato.
"""

import hashlib
import io
import os
import uuid
from datetime import datetime

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.models.models import Contrato, SolicitudPrestamo

CONTRATOS_DIR = os.getenv("CONTRATOS_DIR", "contratos_guardados")


def _directorio() -> str:
    os.makedirs(CONTRATOS_DIR, exist_ok=True)
    return CONTRATOS_DIR


def generar_pdf_contrato(datos: dict) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=portrait(letter),
        rightMargin=48,
        leftMargin=48,
        topMargin=48,
        bottomMargin=48,
    )
    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "TituloContrato",
        parent=styles["Heading1"],
        fontSize=15,
        alignment=1,
        spaceAfter=4,
    )
    normal = ParagraphStyle("NormalContrato", parent=styles["Normal"], fontSize=10.5, leading=15)
    etiqueta = ParagraphStyle("EtiquetaContrato", parent=normal, textColor=colors.HexColor("#334155"))

    story = [
        Paragraph("CONTRATO DE PRÉSTAMO", titulo),
        Paragraph(f"N° {datos['referencia']}", ParagraphStyle("Ref", parent=normal, alignment=1, spaceAfter=16)),
        Paragraph(
            f"Entre <b>{datos['prestamista']}</b> (en adelante «el prestamista») y "
            f"<b>{datos['cliente_nombre']}</b>, identificado(a) con cédula {datos['cliente_cedula']} "
            f"(en adelante «el cliente»), se celebró el presente contrato de préstamo.",
            normal,
        ),
        Spacer(1, 12),
        Paragraph("<b>Cláusula 1. Objeto.</b> El prestamista entrega al cliente la suma de "
                  f"${datos['monto']:.2f} por un plazo de {datos['plazo_cuotas']} cuotas mensuales.", normal),
        Spacer(1, 8),
        Paragraph("<b>Cláusula 2. Interés.</b> El préstamo devengará un interés del "
                  f"{datos['porcentaje_interes']:.2f}% sobre el capital solicitado.", normal),
        Spacer(1, 8),
        Paragraph("<b>Cláusula 3. Destino.</b> El cliente declara que el destino del préstamo es: "
                  f"{datos['motivo']}", normal),
        Spacer(1, 8),
        Paragraph("<b>Cláusula 4. Pago.</b> El cliente se obliga a pagar las cuotas en las fechas "
                  "acordadas; el atraso generará los cargos de mora vigentes en el sistema.", normal),
        Spacer(1, 8),
        Paragraph("<b>Cláusula 5. Firma electrónica.</b> Las partes acuerdan que la firma "
                  "electrónica tiene la misma validez que la firma autógrafa.", normal),
        Spacer(1, 28),
        Paragraph(f"Cliente: {datos['cliente_nombre']}", etiqueta),
        Spacer(1, 20),
        Paragraph(f"Fecha de emisión: {datos['fecha_emision']}", etiqueta),
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer


def emitir_contrato(
    db,
    solicitud: SolicitudPrestamo,
    usuario_id: int | None = None,
) -> Contrato:
    """Genera el PDF del contrato, lo archiva y lo deja en estado 'en_firma'."""
    if solicitud.estado != "aprobada":
        raise HTTPException(status_code=400, detail="Solo las solicitudes aprobadas generan contrato")

    existente = (
        db.query(Contrato)
        .filter(Contrato.solicitud_id == solicitud.id, Contrato.estado != "rechazado")
        .first()
    )
    if existente:
        return existente

    cliente = solicitud.cliente
    datos = {
        "referencia": f"SOL-{solicitud.id:06d}",
        "prestamista": os.getenv("PRESTAMISTA_NOMBRE", "LoanSoft"),
        "cliente_nombre": cliente.nombre if cliente else "—",
        "cliente_cedula": cliente.cedula if cliente else "—",
        "monto": solicitud.monto_solicitado,
        "plazo_cuotas": solicitud.plazo_cuotas,
        "porcentaje_interes": solicitud.porcentaje_interes,
        "motivo": solicitud.motivo,
        "fecha_emision": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    pdf = generar_pdf_contrato(datos)
    contenido = pdf.getvalue()
    digest = hashlib.sha256(contenido).hexdigest()

    nombre_archivo = f"CONTRATO-SOL-{solicitud.id:06d}-{uuid.uuid4().hex[:8]}.pdf"
    ruta = os.path.join(_directorio(), nombre_archivo)
    with open(ruta, "wb") as archivo:
        archivo.write(contenido)

    contrato = Contrato(
        solicitud_id=solicitud.id,
        estado="en_firma",
        ruta_archivo=ruta,
        hash_documento=digest,
        fecha_emision=datetime.utcnow(),
    )
    db.add(contrato)
    db.commit()
    db.refresh(contrato)
    return contrato


def firmar_contrato(db, contrato_id: int, firmante_nombre: str, firmante_documento: str) -> Contrato:
    """Firma electrónica del contrato (adaptador piloto)."""
    contrato = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not contrato:
        raise HTTPException(status_code=404, detail="Contrato no encontrado")
    if contrato.estado == "firmado":
        raise HTTPException(status_code=400, detail="El contrato ya está firmado")
    if contrato.estado == "rechazado":
        raise HTTPException(status_code=400, detail="El contrato fue rechazado")

    proveedor = (os.getenv("FIRMA_PROVIDER") or "piloto").lower()
    if proveedor == "ninguno":
        raise HTTPException(status_code=400, detail="Proveedor de firma no configurado")

    # Adaptador piloto: valida la huella del documento y registra la firma.
    if os.path.exists(contrato.ruta_archivo):
        with open(contrato.ruta_archivo, "rb") as archivo:
            digest = hashlib.sha256(archivo.read()).hexdigest()
        if digest != contrato.hash_documento:
            raise HTTPException(status_code=409, detail="El documento cambió desde su emisión; vuelva a emitirlo")
    else:
        raise HTTPException(status_code=410, detail="El archivo del contrato ya no está disponible")

    contrato.estado = "firmado"
    contrato.firmante_nombre = firmante_nombre
    contrato.firmante_documento = firmante_documento
    contrato.fecha_firma = datetime.utcnow()
    db.commit()
    db.refresh(contrato)
    return contrato


def obtener_contrato_solicitud(db, solicitud_id: int) -> Contrato:
    contrato = (
        db.query(Contrato)
        .filter(Contrato.solicitud_id == solicitud_id, Contrato.estado != "rechazado")
        .order_by(Contrato.id.desc())
        .first()
    )
    if not contrato:
        raise HTTPException(status_code=404, detail="La solicitud no tiene contrato emitido")
    return contrato
