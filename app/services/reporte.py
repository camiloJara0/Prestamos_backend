# Servicio de reportes : genera datos de ganancias y perdidas
# y exporta en formato Excel y PDF
# Soporta filtros por mes, anio o ambos

from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import Optional
from app.models.models import MovimientoCapital, Prestamo, PrestamoPerdido, Pago, Cliente, PrestamoCuota
from datetime import date, timedelta

def _filtrar_movimientos(query, mes, anio):
    if mes:
        query = query.filter(extract('month', MovimientoCapital.fecha) == mes)
    if anio:
        query = query.filter(extract('year', MovimientoCapital.fecha) == anio)
    return query

def _filtrar_pagos(query, mes, anio):
    if mes:
        query = query.filter(extract('month', Pago.fecha_pago) == mes)
    if anio:
        query = query.filter(extract('year', Pago.fecha_pago) == anio)
    return query

def _filtrar_perdidos(query, mes, anio):
    if mes:
        query = query.filter(extract('month', PrestamoPerdido.fecha) == mes)
    if anio:
        query = query.filter(extract('year', PrestamoPerdido.fecha) == anio)
    return query

def _label_periodo(mes, anio):
    meses = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
             7:"Julio",8:"Agosto",9:"Septiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}
    if mes and anio:
        return f"{meses[mes]} {anio}"
    elif mes:
        return meses[mes]
    elif anio:
        return str(anio)
    return "Todos los periodos"

def get_reporte_ganancias(db: Session, mes: Optional[int] = None, anio: Optional[int] = None):
    inversiones = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "inversion"), mes, anio).all()
    total_invertido = sum(m.valor for m in inversiones)

    prestamos = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "prestamo_otorgado"), mes, anio).all()
    total_prestado = sum(m.valor for m in prestamos)

    pagos = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "pago_recibido"), mes, anio).all()
    total_pagos_recibidos = sum(m.valor for m in pagos)

    pagos_detalle = _filtrar_pagos(db.query(Pago), mes, anio).all()
    total_intereses = sum(p.interes_pagado for p in pagos_detalle)

    ganancia_neta = round(total_pagos_recibidos - total_prestado + total_invertido, 2)

    return {
        "periodo": _label_periodo(mes, anio),
        "total_invertido": total_invertido,
        "total_prestado": total_prestado,
        "total_pagos_recibidos": total_pagos_recibidos,
        "total_intereses": total_intereses,
        "ganancia_neta": ganancia_neta
    }

def get_reporte_perdidas(db: Session, mes: Optional[int] = None, anio: Optional[int] = None):
    perdidas = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "perdida"), mes, anio).all()
    total_perdidas = sum(m.valor for m in perdidas)

    prestamos_perdidos = _filtrar_perdidos(db.query(PrestamoPerdido), mes, anio).all()
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
        "periodo": _label_periodo(mes, anio),
        "total_perdidas": total_perdidas,
        "cantidad_prestamos_perdidos": len(prestamos_perdidos),
        "detalle": detalle
    }

def exportar_excel(db: Session, tipo: str, mes: Optional[int] = None, anio: Optional[int] = None):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO
    from datetime import datetime

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
    periodo = _label_periodo(mes, anio)

    if tipo == "ganancias":
        ws.title = "Reporte de Ganancias"
        datos = get_reporte_ganancias(db, mes=mes, anio=anio)

        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 25

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1)
        ws.row_dimensions[2].height = 10

        for celda, texto in [("A3", "CONCEPTO"), ("B3", "VALOR (COP)")]:
            estilo_encabezado(ws[celda])
            ws[celda] = texto
        ws.row_dimensions[3].height = 22

        filas = [
            ("Total Invertido", datos["total_invertido"], VERDE),
            ("Total Prestado", datos["total_prestado"], NEGRO),
            ("Total Pagos Recibidos", datos["total_pagos_recibidos"], VERDE),
            ("Total Intereses Ganados", datos["total_intereses"], VERDE),
        ]

        for i, (concepto, valor, color) in enumerate(filas, start=4):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            cell_a = ws[f'A{i}']
            cell_b = ws[f'B{i}']
            cell_a.value = concepto
            cell_b.value = valor
            estilo_dato(cell_a, par)
            estilo_monto(cell_b, par, color)

        ws.row_dimensions[8].height = 10

        ws['A9'].value = "GANANCIA NETA"
        ws['A9'].font = Font(name='Arial', bold=True, size=12, color=BLANCO)
        ws['A9'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['A9'].alignment = Alignment(horizontal='left', vertical='center')
        ws['A9'].border = borde_fino

        ws['B9'].value = datos["ganancia_neta"]
        ws['B9'].font = Font(name='Arial', bold=True, size=12, color=DORADO)
        ws['B9'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['B9'].alignment = Alignment(horizontal='right', vertical='center')
        ws['B9'].number_format = '$#,##0.00'
        ws['B9'].border = borde_fino
        ws.row_dimensions[9].height = 28

        ws.row_dimensions[10].height = 10
        ws['A11'] = f"Periodo: {periodo}  |  Generado: {fecha_hoy}"
        ws['A11'].font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    else:
        ws.title = "Reporte de Pérdidas"
        datos = get_reporte_perdidas(db, mes=mes, anio=anio)

        ws.column_dimensions['A'].width = 18
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 22
        ws.column_dimensions['D'].width = 30

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1, cols=4)
        ws.row_dimensions[2].height = 10

        ws['A3'] = "Total Pérdidas"
        ws['A3'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['A3'].fill = PatternFill("solid", fgColor=ROJO)
        ws['A3'].alignment = Alignment(horizontal='left', vertical='center')
        ws['A3'].border = borde_fino

        ws.merge_cells('B3:D3')
        ws['B3'] = datos["total_perdidas"]
        ws['B3'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['B3'].fill = PatternFill("solid", fgColor=ROJO)
        ws['B3'].alignment = Alignment(horizontal='right', vertical='center')
        ws['B3'].number_format = '$#,##0.00'
        ws['B3'].border = borde_fino
        ws.row_dimensions[3].height = 25

        ws['A4'] = "Préstamos Perdidos"
        ws['A4'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['A4'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['A4'].alignment = Alignment(horizontal='left', vertical='center')
        ws['A4'].border = borde_fino

        ws.merge_cells('B4:D4')
        ws['B4'] = datos["cantidad_prestamos_perdidos"]
        ws['B4'].font = Font(name='Arial', bold=True, size=11, color=BLANCO)
        ws['B4'].fill = PatternFill("solid", fgColor=MORADO_OSCURO)
        ws['B4'].alignment = Alignment(horizontal='right', vertical='center')
        ws['B4'].border = borde_fino
        ws.row_dimensions[4].height = 25

        ws.row_dimensions[5].height = 10

        encabezados = ["PRÉSTAMO ID", "FECHA", "VALOR PERDIDO (COP)", "MOTIVO"]
        for col, texto in enumerate(encabezados, start=1):
            cell = ws.cell(row=6, column=col, value=texto)
            estilo_encabezado(cell)
        ws.row_dimensions[6].height = 22

        for i, d in enumerate(datos["detalle"], start=7):
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

        ultima = 7 + len(datos["detalle"]) + 1
        ws.cell(row=ultima, column=1).value = f"Periodo: {periodo}  |  Generado: {fecha_hoy}"
        ws.cell(row=ultima, column=1).font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

def exportar_pdf(db: Session, tipo: str, mes: Optional[int] = None, anio: Optional[int] = None):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    from datetime import datetime

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
    periodo = _label_periodo(mes, anio)

    estilo_titulo = ParagraphStyle(
        'Titulo',
        fontName='Helvetica-Bold',
        fontSize=20,
        textColor=BLANCO,
        alignment=TA_CENTER,
        spaceAfter=2
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

    # Encabezado solo con titulo
    encabezado_data = [
        [Paragraph("SISTEMA DE GESTION DE PRESTAMOS", estilo_titulo)],
    ]
    tabla_encabezado = Table(encabezado_data, colWidths=[7*inch])
    tabla_encabezado.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), MORADO_OSCURO),
        ('TOPPADDING', (0, 0), (-1, 0), 16),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 16),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(tabla_encabezado)
    story.append(Spacer(1, 20))

    if tipo == "ganancias":
        datos = get_reporte_ganancias(db, mes=mes, anio=anio)

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
        ]))
        story.append(tabla)
        story.append(Spacer(1, 12))

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
        datos = get_reporte_perdidas(db, mes=mes, anio=anio)

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
    story.append(Paragraph(f"Periodo: {periodo}  |  Generado: {fecha_hoy}", estilo_pie))

    doc.build(story)
    buffer.seek(0)
    return buffer

def get_reporte_cobranza(db: Session, mes: Optional[int] = None, anio: Optional[int] = None):
    """Genera reporte de cobranza con cuotas por vencer, vencidas y pagadas"""
    
    today = date.today()
    
    # Cuotas por vencer (próximos 7 días, no vencidas aún)
    fecha_inicio_por_vencer = today
    fecha_fin_por_vencer = today + timedelta(days=7)
    
    cuotas_por_vencer = db.query(PrestamoCuota).join(Prestamo).join(Cliente).filter(
        PrestamoCuota.estado.in_(["pendiente", "parcial"]),
        PrestamoCuota.fecha_vencimiento >= fecha_inicio_por_vencer,
        PrestamoCuota.fecha_vencimiento <= fecha_fin_por_vencer
    ).all()
    
    # Cuotas vencidas (sin pagar, vencidas hace más de 0 días)
    cuotas_vencidas = db.query(PrestamoCuota).join(Prestamo).join(Cliente).filter(
        PrestamoCuota.estado.in_(["vencido", "parcial"]),
        PrestamoCuota.fecha_vencimiento < today
    ).all()
    
    # Cuotas pagadas
    cuotas_pagadas = db.query(PrestamoCuota).join(Prestamo).join(Cliente).filter(
        PrestamoCuota.estado == "pagado"
    ).all()
    
    # Aplicar filtros de fecha si se proporcionan
    if mes or anio:
        cuotas_por_vencer = [c for c in cuotas_por_vencer if (mes is None or c.fecha_vencimiento.month == mes) and (anio is None or c.fecha_vencimiento.year == anio)]
        cuotas_vencidas = [c for c in cuotas_vencidas if (mes is None or c.fecha_vencimiento.month == mes) and (anio is None or c.fecha_vencimiento.year == anio)]
        cuotas_pagadas = [c for c in cuotas_pagadas if (mes is None or c.fecha_vencimiento.month == mes) and (anio is None or c.fecha_vencimiento.year == anio)]
    
    return {
        "periodo": _label_periodo(mes, anio),
        "total_cuotas_por_vencer": len(cuotas_por_vencer),
        "monto_por_vencer": sum(c.valor_cuota for c in cuotas_por_vencer),
        "total_cuotas_vencidas": len(cuotas_vencidas),
        "monto_vencido": sum(c.valor_cuota for c in cuotas_vencidas),
        "total_cuotas_pagadas": len(cuotas_pagadas),
        "monto_pagado": sum(c.valor_cuota for c in cuotas_pagadas),
        "cuotas_por_vencer": [
            {
                "cuota_id": c.id,
                "prestamo_id": c.prestamo_id,
                "cliente_nombre": c.prestamo.cliente.nombre,
                "numero_cuota": c.numero_cuota,
                "fecha_vencimiento": str(c.fecha_vencimiento),
                "valor_cuota": c.valor_cuota,
                "estado": c.estado,
                "dias_atraso": 0
            } for c in cuotas_por_vencer
        ],
        "cuotas_vencidas": [
            {
                "cuota_id": c.id,
                "prestamo_id": c.prestamo_id,
                "cliente_nombre": c.prestamo.cliente.nombre,
                "numero_cuota": c.numero_cuota,
                "fecha_vencimiento": str(c.fecha_vencimiento),
                "valor_cuota": c.valor_cuota,
                "estado": c.estado,
                "dias_atraso": (today - c.fecha_vencimiento).days
            } for c in cuotas_vencidas
        ],
        "cuotas_pagadas": [
            {
                "cuota_id": c.id,
                "prestamo_id": c.prestamo_id,
                "cliente_nombre": c.prestamo.cliente.nombre,
                "numero_cuota": c.numero_cuota,
                "fecha_vencimiento": str(c.fecha_vencimiento),
                "valor_cuota": c.valor_cuota,
                "estado": c.estado,
                "dias_atraso": 0
            } for c in cuotas_pagadas
        ]
    }


def get_reporte_cartera(db: Session, mes: Optional[int] = None, anio: Optional[int] = None):
    """Genera reporte de cartera con distribución de préstamos por estado"""
    
    # Préstamos activos
    prestamos_activos = db.query(Prestamo).filter(Prestamo.estado == "activo").all()
    
    # Préstamos renovados
    prestamos_renovados = db.query(Prestamo).filter(Prestamo.estado == "renovado").all()
    
    # Préstamos perdidos
    prestamos_perdidos = db.query(Prestamo).filter(Prestamo.estado == "perdido").all()
    
    # Distribución por tipo de préstamo
    distribucion = {}
    for p in prestamos_activos + prestamos_renovados + prestamos_perdidos:
        tipo = p.tipo_prestamo.nombre if p.tipo_prestamo else "Desconocido"
        if tipo not in distribucion:
            distribucion[tipo] = {"cantidad": 0, "monto": 0}
        distribucion[tipo]["cantidad"] += 1
        distribucion[tipo]["monto"] += p.capital_prestado
    
    return {
        "periodo": _label_periodo(mes, anio),
        "total_activos": len(prestamos_activos),
        "monto_activos": sum(p.capital_prestado for p in prestamos_activos),
        "total_renovados": len(prestamos_renovados),
        "monto_renovados": sum(p.capital_prestado for p in prestamos_renovados),
        "total_perdidos": len(prestamos_perdidos),
        "monto_perdidos": sum(p.capital_prestado for p in prestamos_perdidos),
        "distribucion_por_tipo": distribucion
    }