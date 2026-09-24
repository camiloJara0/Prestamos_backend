import io
from datetime import datetime, date
from reportlab.lib.pagesizes import letter, portrait
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def generar_recibo_pdf_bytes(datos: dict) -> io.BytesIO:
    """
    Genera un recibo oficial de pago en PDF y lo retorna en memoria.
    
    Estructura esperada en 'datos':
    - cliente_nombre, cliente_cedula
    - referencia_pago, prestamo_id, cuota_numero
    - monto_pagado, fecha_pago, metodo_pago
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=portrait(letter),
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    story = []
    styles = getSampleStyleSheet()

    # Estilos del documento
    titulo_style = ParagraphStyle(
        'TituloRecibo',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#0F172A'),
        alignment=1, # Centrado
        spaceAfter=5
    )

    subtitulo_style = ParagraphStyle(
        'SubtituloRecibo',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#64748B'),
        alignment=1,
        spaceAfter=15
    )

    label_style = ParagraphStyle('LabelStyle', fontSize=10, textColor=colors.HexColor('#334155'))
    val_style = ParagraphStyle('ValStyle', fontSize=10, textColor=colors.HexColor('#0F172A'))

    # Encabezado del soporte contable
    story.append(Paragraph("<b>COMPROBANTE DE INGRESO / RECIBO DE PAGO</b>", titulo_style))
    story.append(Paragraph("Soporte Oficial de Recaudo — Credifast", subtitulo_style))
    story.append(Spacer(1, 10))

    # Formatear el monto en formato moneda ($100.000)
    monto_fmt = f"${datos['monto_pagado']:,.0f}".replace(",", ".")
    
    # Manejo seguro e inmune a desfases de zona horaria (UTC)
    fecha_val = datos['fecha_pago']
    if isinstance(fecha_val, (datetime, date)):
        fecha_pago_str = fecha_val.strftime("%d/%m/%Y")
    elif isinstance(fecha_val, str):
        # Tomar estrictamente la fecha YYYY-MM-DD ignorando horas o UTC
        partes_fecha = fecha_val.split("T")[0].split(" ")[0].split("-")
        if len(partes_fecha) == 3:
            fecha_pago_str = f"{partes_fecha[2]}/{partes_fecha[1]}/{partes_fecha[0]}"
        else:
            fecha_pago_str = fecha_val
    else:
        fecha_pago_str = str(fecha_val)

    # Tabla con los detalles del pago
    tabla_data = [
        [Paragraph("<b>Referencia Única:</b>", label_style), Paragraph(f"<b>{datos['referencia_pago']}</b>", val_style)],
        [Paragraph("<b>Fecha de Pago:</b>", label_style), Paragraph(fecha_pago_str, val_style)],
        [Paragraph("<b>Cliente / Titular:</b>", label_style), Paragraph(f"{datos['cliente_nombre']}", val_style)],
        [Paragraph("<b>Documento C.C.:</b>", label_style), Paragraph(f"{datos['cliente_cedula']}", val_style)],
        [Paragraph("<b>Préstamo ID:</b>", label_style), Paragraph(f"#{datos['prestamo_id']}", val_style)],
        [Paragraph("<b>Cuota Cancelada:</b>", label_style), Paragraph(f"Cuota N° {datos['cuota_numero']}", val_style)],
        [Paragraph("<b>Medio de Pago:</b>", label_style), Paragraph(f"{datos['metodo_pago'].upper()}", val_style)],
        [Paragraph("<b>Valor Recibido:</b>", label_style), Paragraph(f"<font color='#047857'><b>{monto_fmt} COP</b></font>", val_style)],
    ]

    t = Table(tabla_data, colWidths=[160, 320])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]))

    story.append(t)
    story.append(Spacer(1, 15))

    # Pie de página sobre validez fiscal
    nota_pie = ParagraphStyle('NotaPie', fontSize=8, textColor=colors.HexColor('#94A3B8'), alignment=1)
    story.append(Paragraph("Este documento es un soporte digital permanente de pago de obligación. Consérvelo para control contable.", nota_pie))

    doc.build(story)
    buffer.seek(0)
    return buffer