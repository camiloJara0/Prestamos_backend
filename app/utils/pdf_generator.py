import io
from datetime import datetime, date
from reportlab.lib.pagesizes import letter, portrait
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def _dibujar_marca_agua_devuelto(canvas, doc):
    """
    Dibuja la marca de agua 'ANULADO / DEVUELTO' en diagonal
    únicamente cuando el pago se encuentra revertido.
    """
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 45)
    canvas.setFillColor(colors.HexColor("#DC2626"), alpha=0.18)  # Rojo semitransparente
    canvas.translate(300, 380)
    canvas.rotate(30)
    canvas.drawCentredString(0, 0, "ANULADO / DEVUELTO")
    canvas.restoreState()


def generar_recibo_pdf_bytes(datos: dict) -> io.BytesIO:
    """
    Genera un recibo oficial de pago en PDF y lo retorna en memoria.
    
    Estructura esperada en 'datos':
    - cliente_nombre, cliente_cedula
    - referencia_recibo (Nuevo: REC-YYYYMMDD-XXXXXX)
    - referencia_pago (Referencia de la Cuota)
    - prestamo_id, cuota_numero
    - monto_pagado, fecha_pago, metodo_pago
    - estado_pago (confirmado / devuelto)
    - fecha_devolucion, motivo_devolucion (opcionales)
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
        alignment=1,  # Centrado
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
    story.append(Spacer(1, 5))

    # Formatear el monto en formato moneda ($100.000)
    monto_fmt = f"${datos['monto_pagado']:,.0f}".replace(",", ".")
    
    # Manejo seguro e inmune a desfases de zona horaria (UTC)
    fecha_val = datos['fecha_pago']
    if isinstance(fecha_val, (datetime, date)):
        fecha_pago_str = fecha_val.strftime("%d/%m/%Y")
    elif isinstance(fecha_val, str):
        partes_fecha = fecha_val.split("T")[0].split(" ")[0].split("-")
        if len(partes_fecha) == 3:
            fecha_pago_str = f"{partes_fecha[2]}/{partes_fecha[1]}/{partes_fecha[0]}"
        else:
            fecha_pago_str = fecha_val
    else:
        fecha_pago_str = str(fecha_val)

    estado_pago = datos.get("estado_pago", "confirmado").lower()
    es_devuelto = estado_pago == "devuelto"

    # Banner superior en caso de estar anulado
    if es_devuelto:
        banner_data = [[
            Paragraph("<font color='#DC2626'><b>ESTADO: ESTE PAGO HA SIDO ANULADO / DEVUELTO</b></font>", subtitulo_style)
        ]]
        banner_table = Table(banner_data, colWidths=[480])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FEE2E2")),
            ('BORDER', (0, 0), (-1, -1), 1, colors.HexColor("#FCA5A5")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 10))

    # Tabla con los detalles del pago (incluyendo ambas referencias)
    ref_recibo = datos.get("referencia_recibo", "N/A")
    ref_cuota = datos.get("referencia_pago", "N/A")

    tabla_data = [
        [Paragraph("<b>Referencia Recibo:</b>", label_style), Paragraph(f"<b>{ref_recibo}</b>", val_style)],
        [Paragraph("<b>Referencia Cuota:</b>", label_style), Paragraph(f"<b>{ref_cuota}</b>", val_style)],
        [Paragraph("<b>Fecha de Pago:</b>", label_style), Paragraph(fecha_pago_str, val_style)],
        [Paragraph("<b>Cliente / Titular:</b>", label_style), Paragraph(f"{datos['cliente_nombre']}", val_style)],
        [Paragraph("<b>Documento C.C.:</b>", label_style), Paragraph(f"{datos['cliente_cedula']}", val_style)],
        [Paragraph("<b>Préstamo ID:</b>", label_style), Paragraph(f"#{datos['prestamo_id']}", val_style)],
        [Paragraph("<b>Cuota Cancelada:</b>", label_style), Paragraph(f"Cuota N° {datos['cuota_numero']}", val_style)],
        [Paragraph("<b>Medio de Pago:</b>", label_style), Paragraph(f"{str(datos['metodo_pago']).upper()}", val_style)],
        [
            Paragraph("<b>Valor Recibido:</b>", label_style), 
            Paragraph(
                f"<font color='#DC2626'><b><s>{monto_fmt} COP</s> (DEVUELTO)</b></font>" if es_devuelto 
                else f"<font color='#047857'><b>{monto_fmt} COP</b></font>", 
                val_style
            )
        ],
    ]

    # Si está devuelto, agregamos la información del reverso a la tabla
    if es_devuelto and datos.get("motivo_devolucion"):
        fecha_dev_val = datos.get("fecha_devolucion", "N/A")
        tabla_data.append([
            Paragraph("<b>Fecha Anulación:</b>", label_style), 
            Paragraph(f"{fecha_dev_val}", val_style)
        ])
        tabla_data.append([
            Paragraph("<b>Motivo Devolución:</b>", label_style), 
            Paragraph(f"<font color='#B91C1C'>{datos.get('motivo_devolucion')}</font>", val_style)
        ])

    t = Table(tabla_data, colWidths=[160, 320])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]))

    story.append(t)
    story.append(Spacer(1, 15))

    # Pie de página sobre validez fiscal
    nota_pie = ParagraphStyle('NotaPie', fontSize=8, textColor=colors.HexColor('#94A3B8'), alignment=1)
    story.append(Paragraph("Este documento es un soporte digital permanente de pago de obligación. Consérvelo para control contable.", nota_pie))

    # Generación con o sin marca de agua según el estado del pago
    if es_devuelto:
        doc.build(
            story, 
            onFirstPage=_dibujar_marca_agua_devuelto, 
            onLaterPages=_dibujar_marca_agua_devuelto
        )
    else:
        doc.build(story)

    buffer.seek(0)
    return buffer