import io
from datetime import datetime, date
from reportlab.lib.pagesizes import letter, portrait
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib import colors

# Paleta de marca (misma que exportar_pdf de reportes → apariencia del sitio)
MORADO_OSCURO = colors.HexColor("#5B2D8E")
MORADO_MEDIO = colors.HexColor("#7B3FC4")
MORADO_CLARO = colors.HexColor("#F5F0FF")
VERDE = colors.HexColor("#047857")
ROJO = colors.HexColor("#DC2626")
ROJO_SUAVE = colors.HexColor("#FEE2E2")
ROJO_BORDE = colors.HexColor("#FCA5A5")
GRIS_TEXTO = colors.HexColor("#64748B")
GRIS_GRILLA = colors.HexColor("#E2E8F0")
FONDO_TARJETA = colors.HexColor("#F8FAFC")
NARANJA = colors.HexColor("#B45309")
BLANCO = colors.white
NEGRO = colors.HexColor("#0F172A")
GRIS_PIE = colors.HexColor("#94A3B8")


def _dinero(valor) -> str:
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    return f"${numero:,.0f}".replace(",", ".")


def _fecha(valor) -> str:
    if valor is None or valor == "":
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    partes = str(valor).split("T")[0].split(" ")[0].split("-")
    if len(partes) == 3:
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return str(valor)


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
    Genera el comprobante oficial de pago en PDF y lo retorna en memoria.

    Estructura esperada en 'datos':
    - Recibo: referencia_recibo, referencia_pago, fecha_pago, monto_pagado,
      metodo_pago, estado_pago (confirmado/devuelto), cuota_numero,
      capital_pagado/interes_pagado/mora_pagada (opcionales),
      fecha_devolucion/motivo_devolucion (si devuelto)
    - Préstamo: prestamo_id, prestamo_fecha_desembolso,
      prestamo_capital_desembolsado, prestamo_tasa_interes, prestamo_plazo,
      prestamo_valor_cuota, prestamo_estado
    - Cliente: cliente_nombre, cliente_cedula
    - Cuotas: lista de {numero, fecha_cobro, valor_cuota, valor_pagado,
      saldo_pendiente, estado}
    - Totales: total_financiado, total_pagado, total_pendiente,
      total_intereses_cobrados, total_capital_abonado
    - nombre_empresa (opcional; default LoanSoft)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=portrait(letter),
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()
    story = []

    titulo_style = ParagraphStyle(
        'TituloRecibo', fontName='Helvetica-Bold', fontSize=16,
        textColor=BLANCO, alignment=TA_CENTER, spaceAfter=2,
    )
    subtitulo_banner = ParagraphStyle(
        'SubtituloBanner', fontName='Helvetica', fontSize=9,
        textColor=MORADO_CLARO, alignment=TA_CENTER,
    )
    seccion_style = ParagraphStyle(
        'SeccionRecibo', fontName='Helvetica-Bold', fontSize=11.5,
        textColor=MORADO_OSCURO, spaceBefore=12, spaceAfter=4,
    )
    label_style = ParagraphStyle('LabelRecibo', fontName='Helvetica', fontSize=9.5, textColor=colors.HexColor('#334155'))
    val_style = ParagraphStyle('ValRecibo', fontName='Helvetica', fontSize=9.5, textColor=NEGRO)
    th_style = ParagraphStyle(
        'ThRecibo', fontName='Helvetica-Bold', fontSize=9,
        textColor=BLANCO, alignment=TA_CENTER,
    )
    td_style = ParagraphStyle('TdRecibo', fontName='Helvetica', fontSize=9, textColor=NEGRO)
    td_num_style = ParagraphStyle('TdNumRecibo', fontName='Helvetica', fontSize=9, textColor=NEGRO, alignment=TA_RIGHT)
    nota_pie = ParagraphStyle(
        'NotaPie', fontName='Helvetica-Oblique', fontSize=8,
        textColor=GRIS_PIE, alignment=TA_CENTER,
    )

    nombre_empresa = (datos.get("nombre_empresa") or "LoanSoft").strip() or "LoanSoft"

    # --- Encabezado con banner de marca ---
    encabezado = Table(
        [[Paragraph("COMPROBANTE DE PAGO", titulo_style)],
         [Paragraph(f"Soporte oficial de recaudo — {nombre_empresa}", subtitulo_banner)]],
        colWidths=[532],
    )
    encabezado.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), MORADO_OSCURO),
        ('TOPPADDING', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 14),
        ('TOPPADDING', (0, 1), (-1, 1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(encabezado)
    story.append(Spacer(1, 8))

    estado_pago = str(datos.get("estado_pago", "confirmado")).lower()
    es_devuelto = estado_pago == "devuelto"

    if es_devuelto:
        banner = Table(
            [[Paragraph(
                "<font color='#DC2626'><b>ESTADO: ESTE PAGO HA SIDO ANULADO / DEVUELTO</b></font>",
                ParagraphStyle('b', parent=styles['Normal'], alignment=TA_CENTER, fontSize=9),
            )]],
            colWidths=[532],
        )
        banner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), ROJO_SUAVE),
            ('BOX', (0, 0), (-1, -1), 1, ROJO_BORDE),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(banner)
        story.append(Spacer(1, 6))

    def seccion(titulo: str):
        story.append(Paragraph(titulo, seccion_style))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=8))

    estilo_tabla_kv = TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FONDO_TARJETA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, GRIS_GRILLA),
    ])

    # --- Sección 1: Datos del pago ---
    seccion("Datos del pago")
    monto_fmt = _dinero(datos.get("monto_pagado"))
    filas_pago = [
        [Paragraph("<b>Referencia recibo:</b>", label_style), Paragraph(f"<b>{datos.get('referencia_recibo', 'N/A')}</b>", val_style)],
        [Paragraph("<b>Referencia cuota:</b>", label_style), Paragraph(f"{datos.get('referencia_pago', 'N/A')}", val_style)],
        [Paragraph("<b>Fecha de pago:</b>", label_style), Paragraph(_fecha(datos.get('fecha_pago')), val_style)],
        [Paragraph("<b>Cuota cancelada:</b>", label_style), Paragraph(f"Cuota N° {datos.get('cuota_numero', 'N/A')}", val_style)],
        [Paragraph("<b>Medio de pago:</b>", label_style), Paragraph(str(datos.get('metodo_pago', 'N/A')).upper(), val_style)],
        [
            Paragraph("<b>Valor recibido:</b>", label_style),
            Paragraph(
                f"<font color='#DC2626'><b><s>{monto_fmt} COP</s> (DEVUELTO)</b></font>" if es_devuelto
                else f"<font color='#047857'><b>{monto_fmt} COP</b></font>",
                val_style,
            ),
        ],
    ]
    if es_devuelto and datos.get("motivo_devolucion"):
        filas_pago.append([
            Paragraph("<b>Fecha anulación:</b>", label_style),
            Paragraph(_fecha(datos.get("fecha_devolucion")), val_style),
        ])
        filas_pago.append([
            Paragraph("<b>Motivo devolución:</b>", label_style),
            Paragraph(f"<font color='#B91C1C'>{datos.get('motivo_devolucion')}</font>", val_style),
        ])

    # Desglose del pago (capital, interés y mora) cuando el comprobante lo incluye
    for etiqueta, clave in (
        ("Capital del pago:", "capital_pagado"),
        ("Interés del pago:", "interes_pagado"),
        ("Mora del pago:", "mora_pagada"),
    ):
        if clave in datos:
            filas_pago.append([
                Paragraph(f"<b>{etiqueta}</b>", label_style),
                Paragraph(_dinero(datos.get(clave)), val_style),
            ])
    tabla_pago = Table(filas_pago, colWidths=[170, 362])
    tabla_pago.setStyle(estilo_tabla_kv)
    story.append(tabla_pago)

    # --- Sección 2: Información del préstamo ---
    # seccion("Información del préstamo")
    # filas_prestamo = [
    #     [Paragraph("<b>Número de préstamo:</b>", label_style), Paragraph(f"#{datos.get('prestamo_id', 'N/A')}", val_style)],
    #     [Paragraph("<b>Cliente:</b>", label_style), Paragraph(str(datos.get('cliente_nombre', 'N/A')), val_style)],
    #     [Paragraph("<b>Documento:</b>", label_style), Paragraph(str(datos.get('cliente_cedula', 'N/A')), val_style)],
    #     [Paragraph("<b>Fecha de desembolso:</b>", label_style), Paragraph(_fecha(datos.get('prestamo_fecha_desembolso')), val_style)],
    #     [Paragraph("<b>Monto desembolsado:</b>", label_style), Paragraph(_dinero(datos.get('prestamo_capital_desembolsado')), val_style)],
    #     [Paragraph("<b>Tasa de interés:</b>", label_style), Paragraph(f"{datos.get('prestamo_tasa_interes', 'N/A')}%", val_style)],
    #     [Paragraph("<b>Plazo:</b>", label_style), Paragraph(f"{datos.get('prestamo_plazo', 'N/A')} cuotas", val_style)],
    #     [Paragraph("<b>Valor de cuota:</b>", label_style), Paragraph(_dinero(datos.get('prestamo_valor_cuota')), val_style)],
    #     [Paragraph("<b>Estado del préstamo:</b>", label_style), Paragraph(str(datos.get('prestamo_estado', 'N/A')).capitalize(), val_style)],
    # ]
    # tabla_prestamo = Table(filas_prestamo, colWidths=[170, 362])
    # tabla_prestamo.setStyle(estilo_tabla_kv)
    # story.append(tabla_prestamo)

    # --- Sección 3: Estado de cuotas ---
    cuotas = datos.get("cuotas") or []
    if cuotas:
        seccion("Estado de cuotas")
        encabezado_cuotas = [
            Paragraph("<b>N°</b>", th_style),
            Paragraph("<b>Fecha de cobro</b>", th_style),
            Paragraph("<b>Valor cuota</b>", th_style),
            Paragraph("<b>Valor pagado</b>", th_style),
            Paragraph("<b>Saldo pendiente</b>", th_style),
            Paragraph("<b>Estado</b>", th_style),
        ]
        filas_cuotas = [encabezado_cuotas]
        color_estado = {"Pagada": VERDE, "Vencida": ROJO, "Parcial": NARANJA}
        for c in cuotas:
            estado_txt = str(c.get("estado", "")) or "—"
            color_txt = color_estado.get(estado_txt, NEGRO)
            filas_cuotas.append([
                Paragraph(str(c.get("numero", "")), ParagraphStyle('n', parent=td_style, alignment=TA_CENTER)),
                Paragraph(c.get("fecha_cobro") or "—", td_style),
                Paragraph(_dinero(c.get("valor_cuota")), td_num_style),
                Paragraph(_dinero(c.get("valor_pagado")), td_num_style),
                Paragraph(_dinero(c.get("saldo_pendiente")), td_num_style),
                Paragraph(f"<font color='#{color_txt.hexval()[2:]}'><b>{estado_txt}</b></font>", td_style),
            ])
        tabla_cuotas = Table(
            filas_cuotas,
            colWidths=[36, 95, 100, 100, 100, 101],
            repeatRows=1,
        )
        tabla_cuotas.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, GRIS_GRILLA),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(tabla_cuotas)

    # --- Sección 4: Totales ---
    seccion("Resumen del préstamo")
    filas_totales = [
        [Paragraph("<b>Total financiado:</b>", label_style), Paragraph(_dinero(datos.get('total_financiado')), val_style)],
        [Paragraph("<b>Total pagado:</b>", label_style), Paragraph(f"<font color='#047857'>{_dinero(datos.get('total_pagado'))}</font>", val_style)],
        # [Paragraph("<b>Total intereses cobrados:</b>", label_style), Paragraph(_dinero(datos.get('total_intereses_cobrados')), val_style)],
        # [Paragraph("<b>Total capital abonado:</b>", label_style), Paragraph(_dinero(datos.get('total_capital_abonado')), val_style)],
        [
            Paragraph("<b>Total pendiente:</b>", label_style),
            Paragraph(f"<font color='#5B2D8E'><b>{_dinero(datos.get('total_pendiente'))}</b></font>", val_style),
        ],
    ]
    tabla_totales = Table(filas_totales, colWidths=[170, 362])
    tabla_totales.setStyle(estilo_tabla_kv)
    story.append(tabla_totales)
    story.append(Spacer(1, 12))

    # Tarjeta destacada de saldo pendiente
    # tarjeta_saldo = Table(
    #     [[Paragraph("<b>SALDO PENDIENTE ACTUAL</b>", ParagraphStyle('sp', fontName='Helvetica-Bold', fontSize=12, textColor=BLANCO)),
    #       Paragraph(f"<b>{_dinero(datos.get('total_pendiente'))} COP</b>",
    #                 ParagraphStyle('spv', fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#FFD700'), alignment=TA_RIGHT))]],
    #     colWidths=[352, 180],
    # )
    # tarjeta_saldo.setStyle(TableStyle([
    #     ('BACKGROUND', (0, 0), (-1, -1), MORADO_OSCURO),
    #     ('TOPPADDING', (0, 0), (-1, -1), 10),
    #     ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    #     ('LEFTPADDING', (0, 0), (-1, -1), 12),
    #     ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    #     ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    #     ('ROUNDEDCORNERS', [6]),
    # ]))
    # story.append(tarjeta_saldo)
    # story.append(Spacer(1, 14))

    story.append(Paragraph(
        "Este documento es un soporte digital permanente de pago de obligación. Consérvelo para control contable.",
        nota_pie,
    ))

    if es_devuelto:
        doc.build(
            story,
            onFirstPage=_dibujar_marca_agua_devuelto,
            onLaterPages=_dibujar_marca_agua_devuelto,
        )
    else:
        doc.build(story)

    buffer.seek(0)
    return buffer
