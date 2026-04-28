# Servicio de reportes : genera datos de ganancias y perdidas
# y exporta en formato Excel y PDF

from sqlalchemy.orm import Session
from app.models.models import MovimientoCapital, Prestamo, PrestamoPerdido, Pago
from datetime import date

def get_reporte_ganancias(db: Session):
    # Total invertido
    inversiones = db.query(MovimientoCapital).filter(
        MovimientoCapital.tipo_movimiento == "inversion"
    ).all()
    total_invertido = sum(m.valor for m in inversiones)

    # Total prestado
    prestamos = db.query(MovimientoCapital).filter(
        MovimientoCapital.tipo_movimiento == "prestamo_otorgado"
    ).all()
    total_prestado = sum(m.valor for m in prestamos)

    # Total pagos recibidos
    pagos = db.query(MovimientoCapital).filter(
        MovimientoCapital.tipo_movimiento == "pago_recibido"
    ).all()
    total_pagos_recibidos = sum(m.valor for m in pagos)

    # Total intereses ganados
    pagos_detalle = db.query(Pago).all()
    total_intereses = sum(p.interes_pagado for p in pagos_detalle)

    # Ganancia neta
    ganancia_neta = round(total_pagos_recibidos - total_prestado + total_invertido, 2)

    return {
        "total_invertido": total_invertido,
        "total_prestado": total_prestado,
        "total_pagos_recibidos": total_pagos_recibidos,
        "total_intereses": total_intereses,
        "ganancia_neta": ganancia_neta
    }

def get_reporte_perdidas(db: Session):
    # Total perdidas
    perdidas = db.query(MovimientoCapital).filter(
        MovimientoCapital.tipo_movimiento == "perdida"
    ).all()
    total_perdidas = sum(m.valor for m in perdidas)

    # Detalle de prestamos perdidos
    prestamos_perdidos = db.query(PrestamoPerdido).all()
    detalle = [
        {
            "prestamo_id": p.prestamo_id,
            "fecha": str(p.fecha),
            "valor_perdido": p.valor_perdido,
            "motivo": p.motivo
        }
        for p in prestamos_perdidos
    ]

    return {
        "total_perdidas": total_perdidas,
        "cantidad_prestamos_perdidos": len(prestamos_perdidos),
        "detalle": detalle
    }

def exportar_excel(db: Session, tipo: str):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO
    from datetime import datetime

    # Paleta morado completa
    MORADO_OSCURO = "5B2D8E"
    MORADO_MEDIO = "7B3FC4"
    MORADO_CLARO = "F5F0FF"
    BLANCO = "FFFFFF"
    DORADO = "FFD700"
    VERDE = "1A7A4A"
    ROJO = "C0392B"
    NEGRO = "1A1A1A"

    borde_fino = Border(
        left=Side(style='thin', color="CCCCCC"),
        right=Side(style='thin', color="CCCCCC"),
        top=Side(style='thin', color="CCCCCC"),
        bottom=Side(style='thin', color="CCCCCC")
    )

    def estilo_titulo(ws, texto, fila, cols=2):
        ws.merge_cells(f'A{fila}:{get_column_letter(cols)}{fila}')
        cell = ws[f'A{fila}']
        cell.value = texto
        cell.font = Font(name='Arial', bold=True, size=16, color=BLANCO)
        cell.fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[fila].height = 35

    def estilo_subtitulo(ws, texto, fila, cols=2):
        ws.merge_cells(f'A{fila}:{get_column_letter(cols)}{fila}')
        cell = ws[f'A{fila}']
        cell.value = texto
        cell.font = Font(name='Arial', size=10, color="CCAAFF", italic=True)
        cell.fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[fila].height = 20

    def estilo_encabezado(cell):
        cell.font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        cell.fill = PatternFill("solid", fgColor=MORADO_MEDIO)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = borde_fino

    def estilo_dato(cell, fila_par=True):
        cell.font = Font(name='Arial', size=10, color=NEGRO)
        cell.fill = PatternFill("solid", fgColor=MORADO_CLARO if fila_par else BLANCO)
        cell.alignment = Alignment(horizontal='left', vertical='center')
        cell.border = borde_fino

    def estilo_monto(cell, fila_par=True, color_texto=NEGRO):
        cell.font = Font(name='Arial', size=10, bold=True, color=color_texto)
        cell.fill = PatternFill("solid", fgColor=MORADO_CLARO if fila_par else BLANCO)
        cell.alignment = Alignment(horizontal='right', vertical='center')
        cell.number_format = '$#,##0.00'
        cell.border = borde_fino

    wb = openpyxl.Workbook()
    ws = wb.active
    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")

    if tipo == "ganancias":
        ws.title = "Reporte de Ganancias"
        datos = get_reporte_ganancias(db)

        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 25

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1)
        estilo_subtitulo(ws, f"Reporte de Ganancias  |  Generado: {fecha_hoy}", 2)

        ws.row_dimensions[3].height = 10

        for celda, texto in [("A4", "CONCEPTO"), ("B4", "VALOR (COP)")]:
            estilo_encabezado(ws[celda])
            ws[celda] = texto
        ws.row_dimensions[4].height = 22

        filas = [
            ("Total Invertido", datos["total_invertido"], VERDE),
            ("Total Prestado", datos["total_prestado"], NEGRO),
            ("Total Pagos Recibidos", datos["total_pagos_recibidos"], VERDE),
            ("Total Intereses Ganados", datos["total_intereses"], VERDE),
        ]

        for i, (concepto, valor, color) in enumerate(filas, start=5):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            cell_a = ws[f'A{i}']
            cell_b = ws[f'B{i}']
            cell_a.value = concepto
            cell_b.value = valor
            estilo_dato(cell_a, par)
            estilo_monto(cell_b, par, color)

        ws.row_dimensions[9].height = 10

        ws['A10'].value = "GANANCIA NETA"
        ws['A10'].font = Font(name='Arial', bold=True, size=12, color=BLANCO)
        ws['A10'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['A10'].alignment = Alignment(horizontal='left', vertical='center')
        ws['A10'].border = borde_fino

        ws['B10'].value = datos["ganancia_neta"]
        ws['B10'].font = Font(name='Arial', bold=True, size=12, color=DORADO)
        ws['B10'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['B10'].alignment = Alignment(horizontal='right', vertical='center')
        ws['B10'].number_format = '$#,##0.00'
        ws['B10'].border = borde_fino
        ws.row_dimensions[10].height = 28

        ws.row_dimensions[11].height = 10
        ws['A12'] = f"Generado por Sistema de Préstamos  |  {fecha_hoy}"
        ws['A12'].font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    else:
        ws.title = "Reporte de Pérdidas"
        datos = get_reporte_perdidas(db)

        ws.column_dimensions['A'].width = 18
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 22
        ws.column_dimensions['D'].width = 30

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1, cols=4)
        estilo_subtitulo(ws, f"Reporte de Pérdidas  |  Generado: {fecha_hoy}", 2, cols=4)

        ws.row_dimensions[3].height = 10

        ws['A4'] = "Total Pérdidas"
        ws['A4'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['A4'].fill = PatternFill("solid", fgColor=ROJO)
        ws['A4'].alignment = Alignment(horizontal='left', vertical='center')
        ws['A4'].border = borde_fino

        ws.merge_cells('B4:D4')
        ws['B4'] = datos["total_perdidas"]
        ws['B4'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['B4'].fill = PatternFill("solid", fgColor=ROJO)
        ws['B4'].alignment = Alignment(horizontal='right', vertical='center')
        ws['B4'].number_format = '$#,##0.00'
        ws['B4'].border = borde_fino
        ws.row_dimensions[4].height = 25

        ws['A5'] = "Préstamos Perdidos"
        ws['A5'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['A5'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['A5'].alignment = Alignment(horizontal='left', vertical='center')
        ws['A5'].border = borde_fino

        ws.merge_cells('B5:D5')
        ws['B5'] = datos["cantidad_prestamos_perdidos"]
        ws['B5'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['B5'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['B5'].alignment = Alignment(horizontal='right', vertical='center')
        ws['B5'].border = borde_fino
        ws.row_dimensions[5].height = 25

        ws.row_dimensions[6].height = 10

        encabezados = ["PRÉSTAMO ID", "FECHA", "VALOR PERDIDO (COP)", "MOTIVO"]
        for col, texto in enumerate(encabezados, start=1):
            cell = ws.cell(row=7, column=col, value=texto)
            estilo_encabezado(cell)
        ws.row_dimensions[7].height = 22

        for i, d in enumerate(datos["detalle"], start=8):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            c1 = ws.cell(row=i, column=1, value=f"Préstamo #{d['prestamo_id']}")
            c2 = ws.cell(row=i, column=2, value=d['fecha'])
            c3 = ws.cell(row=i, column=3, value=d['valor_perdido'])
            c4 = ws.cell(row=i, column=4, value=d['motivo'] or "Sin motivo")
            estilo_dato(c1, par)
            estilo_dato(c2, par)
            estilo_monto(c3, par, ROJO)
            estilo_dato(c4, par)

        ultima = 8 + len(datos["detalle"]) + 1
        ws.cell(row=ultima, column=1).value = f"Generado por Sistema de Préstamos  |  {fecha_hoy}"
        ws.cell(row=ultima, column=1).font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

def exportar_pdf(db: Session, tipo: str):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    from datetime import datetime

    # Paleta morado
    MORADO_OSCURO = colors.HexColor("#5B2D8E")
    MORADO_MEDIO = colors.HexColor("#7B3FC4")
    MORADO_CLARO = colors.HexColor("#F5F0FF")
    DORADO = colors.HexColor("#FFD700")
    VERDE = colors.HexColor("#1A7A4A")
    ROJO = colors.HexColor("#C0392B")
    GRIS = colors.HexColor("#888888")
    BLANCO = colors.white
    NEGRO = colors.HexColor("#1A1A1A")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch
    )

    styles = getSampleStyleSheet()
    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")

    estilo_titulo = ParagraphStyle(
        'Titulo',
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=BLANCO,
        alignment=TA_CENTER,
        spaceAfter=2
    )
    estilo_subtitulo = ParagraphStyle(
        'Subtitulo',
        fontName='Helvetica-Oblique',
        fontSize=10,
        textColor=colors.HexColor("#CCAAFF"),
        alignment=TA_CENTER,
        spaceAfter=6
    )
    estilo_seccion = ParagraphStyle(
        'Seccion',
        fontName='Helvetica-Bold',
        fontSize=12,
        textColor=MORADO_OSCURO,
        spaceBefore=12,
        spaceAfter=6
    )
    estilo_pie = ParagraphStyle(
        'Pie',
        fontName='Helvetica-Oblique',
        fontSize=8,
        textColor=GRIS,
        alignment=TA_CENTER
    )

    story = []

    # Encabezado con fondo morado
    encabezado_data = [
        [Paragraph("SISTEMA DE GESTION DE PRESTAMOS", estilo_titulo)],
        [Paragraph(f"{'Reporte de Ganancias' if tipo == 'ganancias' else 'Reporte de Perdidas'}  |  Generado: {fecha_hoy}", estilo_subtitulo)]
    ]
    tabla_encabezado = Table(encabezado_data, colWidths=[7*inch])
    tabla_encabezado.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), MORADO_OSCURO),
        ('TOPPADDING', (0, 0), (-1, 0), 16),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('TOPPADDING', (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 12),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(tabla_encabezado)
    story.append(Spacer(1, 20))

    if tipo == "ganancias":
        datos = get_reporte_ganancias(db)

        story.append(Paragraph("Resumen Financiero", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        tabla_data = [
            [Paragraph("<b>CONCEPTO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>VALOR (COP)</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER))],
            ["Total Invertido", f"$ {datos['total_invertido']:,.2f}"],
            ["Total Prestado", f"$ {datos['total_prestado']:,.2f}"],
            ["Total Pagos Recibidos", f"$ {datos['total_pagos_recibidos']:,.2f}"],
            ["Total Intereses Ganados", f"$ {datos['total_intereses']:,.2f}"],
        ]

        tabla = Table(tabla_data, colWidths=[4*inch, 3*inch])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TEXTCOLOR', (0, 1), (-1, -1), NEGRO),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TEXTCOLOR', (1, 2), (1, 2), VERDE),
            ('TEXTCOLOR', (1, 3), (1, 3), VERDE),
            ('TEXTCOLOR', (1, 4), (1, 4), VERDE),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ]))
        story.append(tabla)
        story.append(Spacer(1, 12))

        # Ganancia neta destacada
        tabla_neta = Table([
            [Paragraph("<b>GANANCIA NETA</b>", ParagraphStyle('gn', fontName='Helvetica-Bold', fontSize=13, textColor=BLANCO)),
             Paragraph(f"<b>$ {datos['ganancia_neta']:,.2f}</b>", ParagraphStyle('gv', fontName='Helvetica-Bold', fontSize=13, textColor=DORADO, alignment=TA_RIGHT))]
        ], colWidths=[4*inch, 3*inch])
        tabla_neta.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), MORADO_OSCURO),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('ROUNDEDCORNERS', [6]),
        ]))
        story.append(tabla_neta)

    else:
        datos = get_reporte_perdidas(db)

        # Resumen de perdidas
        tabla_resumen = Table([
            [Paragraph("<b>Total Perdidas</b>", ParagraphStyle('tp', fontName='Helvetica-Bold', fontSize=12, textColor=BLANCO)),
             Paragraph(f"<b>$ {datos['total_perdidas']:,.2f}</b>", ParagraphStyle('tv', fontName='Helvetica-Bold', fontSize=12, textColor=BLANCO, alignment=TA_RIGHT))],
            [Paragraph("<b>Prestamos Perdidos</b>", ParagraphStyle('pp', fontName='Helvetica-Bold', fontSize=12, textColor=BLANCO)),
             Paragraph(f"<b>{datos['cantidad_prestamos_perdidos']}</b>", ParagraphStyle('pv', fontName='Helvetica-Bold', fontSize=12, textColor=BLANCO, alignment=TA_RIGHT))],
        ], colWidths=[4*inch, 3*inch])
        tabla_resumen.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), ROJO),
            ('BACKGROUND', (0, 1), (-1, 1), MORADO_OSCURO),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ]))
        story.append(tabla_resumen)
        story.append(Spacer(1, 20))

        story.append(Paragraph("Detalle de Prestamos Perdidos", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        tabla_data = [
            [Paragraph("<b>PRESTAMO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>FECHA</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>VALOR PERDIDO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>MOTIVO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER))],
        ]
        for d in datos["detalle"]:
            tabla_data.append([
                f"Prestamo #{d['prestamo_id']}",
                d['fecha'],
                f"$ {d['valor_perdido']:,.2f}",
                d['motivo'] or "Sin motivo"
            ])

        tabla = Table(tabla_data, colWidths=[1.5*inch, 1.5*inch, 2*inch, 2*inch])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('TEXTCOLOR', (2, 1), (2, -1), ROJO),
            ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(tabla)

    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=1, color=MORADO_CLARO, spaceAfter=8))
    story.append(Paragraph(f"Generado por Sistema de Gestion de Prestamos  |  {fecha_hoy}", estilo_pie))

    doc.build(story)
    buffer.seek(0)
    return buffer