from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from typing import Optional
from app.models.models import MovimientoCapital, Prestamo, PrestamoPerdido, Pago, PrestamoCuota, Cliente, TipoPago
from datetime import date, timedelta
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

def _filtrar_movimientos(query, desde, hasta):
    if desde:
        query = query.filter(MovimientoCapital.fecha >= desde)
    if hasta:
        query = query.filter(MovimientoCapital.fecha <= hasta)
    return query

def _filtrar_pagos(query, desde, hasta):
    if desde:
        query = query.filter(Pago.fecha_pago >= desde)
    if hasta:
        query = query.filter(Pago.fecha_pago <= hasta)
    return query

def _filtrar_perdidos(query, desde, hasta):
    if desde:
        query = query.filter(PrestamoPerdido.fecha >= desde)
    if hasta:
        query = query.filter(PrestamoPerdido.fecha <= hasta)
    return query

def _label_periodo(desde, hasta):
    if desde and hasta:
        return f"{desde} a {hasta}"
    elif desde:
        return f"Desde {desde}"
    elif hasta:
        return f"Hasta {hasta}"
    return "Todos los periodos"

def get_reporte_ganancias(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None):
    inversiones = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "inversion"), desde, hasta).all()
    total_invertido = sum(m.valor for m in inversiones)

    prestamos = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "prestamo_otorgado"), desde, hasta).all()
    total_prestado = sum(m.valor for m in prestamos)

    pagos = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "pago_recibido"), desde, hasta).all()
    total_pagos_recibidos = sum(m.valor for m in pagos)

    pagos_detalle = _filtrar_pagos(db.query(Pago), desde, hasta).all()
    total_intereses = sum(p.interes_pagado for p in pagos_detalle)

    ganancia_neta = round(total_pagos_recibidos - total_prestado + total_invertido, 2)

    return {
        "periodo": _label_periodo(desde, hasta),
        "total_invertido": total_invertido,
        "total_prestado": total_prestado,
        "total_pagos_recibidos": total_pagos_recibidos,
        "total_intereses": total_intereses,
        "ganancia_neta": ganancia_neta
    }

def get_reporte_perdidas(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None):
    perdidas = _filtrar_movimientos(
        db.query(MovimientoCapital).filter(MovimientoCapital.tipo_movimiento == "perdida"), desde, hasta).all()
    total_perdidas = sum(m.valor for m in perdidas)

    prestamos_perdidos = _filtrar_perdidos(db.query(PrestamoPerdido), desde, hasta).all()
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
        "periodo": _label_periodo(desde, hasta),
        "total_perdidas": total_perdidas,
        "cantidad_prestamos_perdidos": len(prestamos_perdidos),
        "detalle": detalle
    }

def get_reporte_cobranza(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None):
    """Genera reporte de cobranza: agenda de cuotas y lo cobrado en el periodo (RF-047/RF-054)."""
    
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
    query_pagadas = db.query(PrestamoCuota).join(Prestamo).join(Cliente).filter(
        PrestamoCuota.estado == "pagado"
    )
    if desde:
        query_pagadas = query_pagadas.filter(PrestamoCuota.fecha_vencimiento >= desde)
    if hasta:
        query_pagadas = query_pagadas.filter(PrestamoCuota.fecha_vencimiento <= hasta)
    cuotas_pagadas = query_pagadas.all()
    
    # Aplicar filtros de fecha a la agenda
    if desde:
        cuotas_por_vencer = [c for c in cuotas_por_vencer if c.fecha_vencimiento >= desde]
        cuotas_vencidas = [c for c in cuotas_vencidas if c.fecha_vencimiento >= desde]
    
    if hasta:
        cuotas_por_vencer = [c for c in cuotas_por_vencer if c.fecha_vencimiento <= hasta]
        cuotas_vencidas = [c for c in cuotas_vencidas if c.fecha_vencimiento <= hasta]
    
    # Monto pagado sobre cada cuota vencida para conocer su saldo real (RF-047)
    ids_vencidas = [c.id for c in cuotas_vencidas]
    pagado_por_cuota = dict(
        db.query(Pago.cuota_id, func.coalesce(func.sum(Pago.capital_pagado + Pago.interes_pagado), 0.0))
        .filter(Pago.cuota_id.in_(ids_vencidas))
        .group_by(Pago.cuota_id)
        .all()
    ) if ids_vencidas else {}

    # Lo cobrado en el periodo con su desglose, solo pagos confirmados (RF-054)
    query_cobros = db.query(Pago).filter(Pago.estado_pago != "devuelto")
    if desde:
        query_cobros = query_cobros.filter(func.date(Pago.fecha_pago) >= desde)
    if hasta:
        query_cobros = query_cobros.filter(func.date(Pago.fecha_pago) <= hasta)
    cobros_periodo = query_cobros.all()

    totales_cobrados = {
        "capital": round(sum(p.capital_pagado for p in cobros_periodo), 2),
        "interes": round(sum(p.interes_pagado for p in cobros_periodo), 2),
        "mora": round(sum(p.mora_pagada for p in cobros_periodo), 2),
        "total": round(sum(p.valor_pagado for p in cobros_periodo), 2),
    }

    acumulado_por_dia: dict = {}
    for p in cobros_periodo:
        dia = str(p.fecha_pago).split("T")[0].split(" ")[0]
        fila = acumulado_por_dia.setdefault(
            dia, {"fecha": dia, "cantidad_pagos": 0, "capital": 0.0, "interes": 0.0, "mora": 0.0, "total": 0.0}
        )
        fila["cantidad_pagos"] += 1
        fila["capital"] = round(fila["capital"] + p.capital_pagado, 2)
        fila["interes"] = round(fila["interes"] + p.interes_pagado, 2)
        fila["mora"] = round(fila["mora"] + p.mora_pagada, 2)
        fila["total"] = round(fila["total"] + p.valor_pagado, 2)

    nota = None
    if not cobros_periodo:
        nota = "Sin cobros registrados en el periodo seleccionado."

    return {
        "periodo": _label_periodo(desde, hasta),
        "nota": nota,
        "totales_cobrados": totales_cobrados,
        "detalle_por_dia": sorted(acumulado_por_dia.values(), key=lambda f: f["fecha"]),
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
                "dias_atraso": (today - c.fecha_vencimiento).days,
                "mora": float(c.mora or 0.0),
                "saldo": max(float(c.valor_cuota) - float(pagado_por_cuota.get(c.id, 0.0)), 0.0)
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

def get_reporte_cartera(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None):
    """Estado de la cartera: saldos por préstamo, antigüedad y distribución por estado (RF-053)."""

    query = db.query(Prestamo)
    if desde:
        query = query.filter(Prestamo.fecha_prestamo >= desde)
    if hasta:
        query = query.filter(Prestamo.fecha_prestamo <= hasta)
    prestamos = query.order_by(Prestamo.fecha_prestamo.desc()).all()

    def _de_estado(estado: str):
        return [p for p in prestamos if p.estado == estado]

    prestamos_activos = _de_estado("activo")
    prestamos_renovados = _de_estado("renovado")
    prestamos_perdidos = _de_estado("perdido")
    prestamos_pagados = _de_estado("pagado")

    # Distribución por tipo de préstamo
    distribucion = {}
    for p in prestamos:
        tipo = p.tipo_prestamo.nombre if p.tipo_prestamo else "Desconocido"
        if tipo not in distribucion:
            distribucion[tipo] = {"cantidad": 0, "monto": 0}
        distribucion[tipo]["cantidad"] += 1
        distribucion[tipo]["monto"] += p.capital_prestado

    distribucion_por_estado = {
        estado: {"cantidad": len(_de_estado(estado)), "monto": sum(p.capital_prestado for p in _de_estado(estado))}
        for estado in ("activo", "pagado", "perdido", "renovado")
    }

    # Antigüedad de la cartera vigente (préstamos con saldo pendiente)
    hoy = date.today()
    rangos = [
        ("0-30 días", 0, 30),
        ("31-60 días", 31, 60),
        ("61-90 días", 61, 90),
        ("Más de 90 días", 91, None),
    ]
    antiguedad = {nombre: {"cantidad": 0, "saldo": 0.0} for nombre, _, _ in rangos}
    for p in prestamos:
        if p.saldo_pendiente <= 0:
            continue
        dias = max((hoy - p.fecha_prestamo).days, 0)
        for nombre, min_dias, max_dias in rangos:
            if dias >= min_dias and (max_dias is None or dias <= max_dias):
                antiguedad[nombre]["cantidad"] += 1
                antiguedad[nombre]["saldo"] = round(antiguedad[nombre]["saldo"] + p.saldo_pendiente, 2)
                break

    nota = None
    if not prestamos:
        nota = "Sin cartera vigente en el periodo seleccionado."

    return {
        "periodo": _label_periodo(desde, hasta),
        "nota": nota,
        "total_prestamos": len(prestamos),
        "saldo_pendiente_total": round(sum(p.saldo_pendiente for p in prestamos), 2),
        "total_activos": len(prestamos_activos),
        "monto_activos": sum(p.capital_prestado for p in prestamos_activos),
        "saldo_activos": round(sum(p.saldo_pendiente for p in prestamos_activos), 2),
        "total_renovados": len(prestamos_renovados),
        "monto_renovados": sum(p.capital_prestado for p in prestamos_renovados),
        "total_perdidos": len(prestamos_perdidos),
        "monto_perdidos": sum(p.capital_prestado for p in prestamos_perdidos),
        "total_pagados": len(prestamos_pagados),
        "monto_pagados": sum(p.capital_prestado for p in prestamos_pagados),
        "distribucion_por_tipo": distribucion,
        "distribucion_por_estado": distribucion_por_estado,
        "antiguedad": antiguedad,
        "detalle": [
            {
                "prestamo_id": p.id,
                "cliente": p.cliente.nombre if p.cliente else "Sin cliente",
                "estado": p.estado,
                "fecha_prestamo": str(p.fecha_prestamo),
                "capital_prestado": p.capital_prestado,
                "saldo_pendiente": p.saldo_pendiente,
                "dias_antiguedad": max((hoy - p.fecha_prestamo).days, 0),
            }
            for p in prestamos
        ],
    }

def get_reporte_pagos(db: Session, desde: Optional[date] = None, hasta: Optional[date] = None, tipo_pago_id: Optional[int] = None):
    """RF-077: pagos del periodo agrupados por método de pago para conciliar la caja por canal."""

    def _filtros(query):
        query = query.filter(Pago.estado_pago != "devuelto")
        if desde:
            query = query.filter(func.date(Pago.fecha_pago) >= desde)
        if hasta:
            query = query.filter(func.date(Pago.fecha_pago) <= hasta)
        if tipo_pago_id:
            query = query.filter(Pago.tipo_pago_id == tipo_pago_id)
        return query

    pagos = _filtros(db.query(Pago)).order_by(Pago.fecha_pago.asc(), Pago.id.asc()).all()

    filas_totales = _filtros(
        db.query(
            TipoPago.id,
            TipoPago.nombre,
            func.count(Pago.id),
            func.coalesce(func.sum(Pago.capital_pagado), 0.0),
            func.coalesce(func.sum(Pago.interes_pagado), 0.0),
            func.coalesce(func.sum(Pago.mora_pagada), 0.0),
            func.coalesce(func.sum(Pago.valor_pagado), 0.0),
        )
        .join(TipoPago, Pago.tipo_pago_id == TipoPago.id)
    ).group_by(TipoPago.id, TipoPago.nombre).order_by(TipoPago.nombre).all()

    totales_por_metodo = [
        {
            "tipo_pago_id": tid,
            "metodo": nombre,
            "cantidad": cantidad,
            "capital": round(capital, 2),
            "interes": round(interes, 2),
            "mora": round(mora, 2),
            "total": round(total, 2),
        }
        for tid, nombre, cantidad, capital, interes, mora, total in filas_totales
    ]

    total_general = {
        "cantidad": sum(f["cantidad"] for f in totales_por_metodo),
        "capital": round(sum(f["capital"] for f in totales_por_metodo), 2),
        "interes": round(sum(f["interes"] for f in totales_por_metodo), 2),
        "mora": round(sum(f["mora"] for f in totales_por_metodo), 2),
        "total": round(sum(f["total"] for f in totales_por_metodo), 2),
    }

    # Pagos devueltos en el periodo: identificados aparte para no des cuadrar la caja
    query_dev = db.query(func.count(Pago.id), func.coalesce(func.sum(Pago.valor_pagado), 0.0)).filter(Pago.estado_pago == "devuelto")
    if desde:
        query_dev = query_dev.filter(func.date(Pago.fecha_pago) >= desde)
    if hasta:
        query_dev = query_dev.filter(func.date(Pago.fecha_pago) <= hasta)
    if tipo_pago_id:
        query_dev = query_dev.filter(Pago.tipo_pago_id == tipo_pago_id)
    cantidad_devueltos, total_devueltos = query_dev.one()
    devueltos = {"cantidad": cantidad_devueltos or 0, "total": round(total_devueltos or 0.0, 2)}

    filas_detalle = (
        db.query(Pago, TipoPago.nombre, Cliente.nombre, PrestamoCuota.numero_cuota)
        .join(TipoPago, Pago.tipo_pago_id == TipoPago.id, isouter=True)
        .join(Cliente, Pago.cliente_id == Cliente.id, isouter=True)
        .join(PrestamoCuota, Pago.cuota_id == PrestamoCuota.id, isouter=True)
        .filter(Pago.estado_pago != "devuelto")
    )
    if desde:
        filas_detalle = filas_detalle.filter(func.date(Pago.fecha_pago) >= desde)
    if hasta:
        filas_detalle = filas_detalle.filter(func.date(Pago.fecha_pago) <= hasta)
    if tipo_pago_id:
        filas_detalle = filas_detalle.filter(Pago.tipo_pago_id == tipo_pago_id)
    filas_detalle = filas_detalle.order_by(Pago.fecha_pago.asc(), Pago.id.asc()).all()

    detalle = [
        {
            "fecha": str(pago.fecha_pago).split("T")[0].split(" ")[0],
            "referencia_recibo": pago.referencia_recibo,
            "cliente": cliente or "Sin cliente",
            "prestamo_id": pago.prestamo_id,
            "numero_cuota": numero_cuota,
            "metodo": metodo or "Sin método",
            "capital": round(pago.capital_pagado or 0.0, 2),
            "interes": round(pago.interes_pagado or 0.0, 2),
            "mora": round(pago.mora_pagada or 0.0, 2),
            "total": round(pago.valor_pagado or 0.0, 2),
        }
        for pago, metodo, cliente, numero_cuota in filas_detalle
    ]

    nota = None
    if not pagos:
        nota = "Sin cobros registrados en el periodo seleccionado."

    return {
        "periodo": _label_periodo(desde, hasta),
        "nota": nota,
        "totales_por_metodo": totales_por_metodo,
        "total_general": total_general,
        "devueltos": devueltos,
        "detalle": detalle,
    }


def exportar_excel(db: Session, tipo: str, desde: Optional[date] = None, hasta: Optional[date] = None, tipo_pago_id: Optional[int] = None):
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

    wb = Workbook()
    ws = wb.active
    fecha_hoy = date.today().strftime("%d/%m/%Y %H:%M")
    periodo = _label_periodo(desde, hasta)

    if tipo == "ganancias":
        ws.title = "Reporte de Ganancias"
        datos = get_reporte_ganancias(db, desde=desde, hasta=hasta)

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

    elif tipo == "cartera":
        ws.title = "Reporte de Cartera"
        datos = get_reporte_cartera(db, desde=desde, hasta=hasta)

        for col, ancho in zip("ABCDE", (22, 26, 16, 20, 20)):
            ws.column_dimensions[col].width = ancho

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1, cols=5)
        ws.row_dimensions[2].height = 10

        resumen = [
            ("Total Préstamos", datos["total_prestamos"], NEGRO),
            ("Saldo Pendiente Total", datos["saldo_pendiente_total"], ROJO),
            ("Préstamos Activos", datos["total_activos"], VERDE),
            ("Saldo por Cobrar (Activos)", datos["saldo_activos"], VERDE),
            ("Préstamos Pagados", datos["total_pagados"], NEGRO),
            ("Préstamos Renovados", datos["total_renovados"], NEGRO),
            ("Préstamos Perdidos", datos["total_perdidos"], ROJO),
        ]

        for celda, texto in [("A3", "CONCEPTO"), ("B3", "VALOR")]:
            estilo_encabezado(ws[celda])
            ws[celda] = texto
        ws.row_dimensions[3].height = 22

        for i, (concepto, valor, color) in enumerate(resumen, start=4):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            cell_a = ws[f'A{i}']
            cell_b = ws[f'B{i}']
            cell_a.value = concepto
            cell_b.value = valor
            estilo_dato(cell_a, par)
            if isinstance(valor, float):
                estilo_monto(cell_b, par, color)
            else:
                estilo_monto(cell_b, par, color)

        fila_base = 4 + len(resumen) + 1
        encabezados = ["PRÉSTAMO", "CLIENTE", "ESTADO", "SALDO PENDIENTE (COP)", "ANTIGÜEDAD (DÍAS)"]
        for col, texto in enumerate(encabezados, start=1):
            estilo_encabezado(ws.cell(row=fila_base, column=col, value=texto))
        ws.row_dimensions[fila_base].height = 22

        for i, d in enumerate(datos["detalle"], start=fila_base + 1):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            valores = [
                f"Préstamo #{d['prestamo_id']}",
                d["cliente"],
                d["estado"].upper(),
                d["saldo_pendiente"],
                d["dias_antiguedad"],
            ]
            for col, valor in enumerate(valores, start=1):
                cell = ws.cell(row=i, column=col, value=valor)
                if col == 4:
                    estilo_monto(cell, par, ROJO)
                else:
                    estilo_dato(cell, par)

        ultima = fila_base + len(datos["detalle"]) + 2
        ws.cell(row=ultima, column=1).value = f"Periodo: {periodo}  |  Generado: {fecha_hoy}"
        ws.cell(row=ultima, column=1).font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    elif tipo == "cobranza":
        ws.title = "Reporte de Cobranza"
        datos = get_reporte_cobranza(db, desde=desde, hasta=hasta)
        totales = datos["totales_cobrados"]

        for col, ancho in zip("ABCDEF", (22, 22, 16, 18, 16, 20)):
            ws.column_dimensions[col].width = ancho

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1, cols=6)
        ws.row_dimensions[2].height = 10

        for celda, texto in [("A3", "CONCEPTO"), ("B3", "VALOR (COP)")]:
            estilo_encabezado(ws[celda])
            ws[celda] = texto
        ws.row_dimensions[3].height = 22

        filas = [
            ("Capital Cobrado", totales["capital"], NEGRO),
            ("Interés Cobrado", totales["interes"], VERDE),
            ("Mora Cobrada", totales["mora"], VERDE),
            ("Total Cobrado", totales["total"], VERDE),
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

        fila_base = 9
        encabezados = ["FECHA", "PAGOS", "CAPITAL (COP)", "INTERÉS (COP)", "MORA (COP)", "TOTAL (COP)"]
        for col, texto in enumerate(encabezados, start=1):
            estilo_encabezado(ws.cell(row=fila_base, column=col, value=texto))
        ws.row_dimensions[fila_base].height = 22

        for i, d in enumerate(datos["detalle_por_dia"], start=fila_base + 1):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            valores = [d["fecha"], d["cantidad_pagos"], d["capital"], d["interes"], d["mora"], d["total"]]
            for col, valor in enumerate(valores, start=1):
                cell = ws.cell(row=i, column=col, value=valor)
                if col >= 3:
                    estilo_monto(cell, par, VERDE if col != 5 else NEGRO)
                else:
                    estilo_dato(cell, par)

        ultima = fila_base + len(datos["detalle_por_dia"]) + 2
        ws.cell(row=ultima, column=1).value = f"Periodo: {periodo}  |  Generado: {fecha_hoy}"
        ws.cell(row=ultima, column=1).font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    elif tipo == "pagos":
        ws.title = "Reporte de Pagos"
        datos = get_reporte_pagos(db, desde=desde, hasta=hasta, tipo_pago_id=tipo_pago_id)
        total = datos["total_general"]

        for col, ancho in zip("ABCDEF", (24, 16, 16, 16, 14, 18)):
            ws.column_dimensions[col].width = ancho

        estilo_titulo(ws, "SISTEMA DE GESTIÓN DE PRÉSTAMOS", 1, cols=6)
        ws.row_dimensions[2].height = 10

        for celda, texto in [("A3", "CONCEPTO"), ("B3", "VALOR (COP)")]:
            estilo_encabezado(ws[celda])
            ws[celda] = texto
        ws.row_dimensions[3].height = 22

        resumen = [
            ("Pagos en el periodo", total["cantidad"], NEGRO),
            ("Capital Cobrado", total["capital"], NEGRO),
            ("Interés Cobrado", total["interes"], VERDE),
            ("Mora Cobrada", total["mora"], VERDE),
            ("Total Cobrado", total["total"], VERDE),
            ("Pagos Devueltos (aparte)", datos["devueltos"]["total"], ROJO),
        ]
        for i, (concepto, valor, color) in enumerate(resumen, start=4):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            cell_a = ws[f'A{i}']
            cell_b = ws[f'B{i}']
            cell_a.value = concepto
            cell_b.value = valor
            estilo_dato(cell_a, par)
            if concepto == "Pagos en el periodo":
                estilo_monto(cell_b, par, color)
                cell_b.number_format = '#,##0'
            else:
                estilo_monto(cell_b, par, color)

        fila_base = 11
        encabezados = ["MÉTODO DE PAGO", "PAGOS", "CAPITAL (COP)", "INTERÉS (COP)", "MORA (COP)", "TOTAL (COP)"]
        for col, texto in enumerate(encabezados, start=1):
            estilo_encabezado(ws.cell(row=fila_base, column=col, value=texto))
        ws.row_dimensions[fila_base].height = 22

        for i, d in enumerate(datos["totales_por_metodo"], start=fila_base + 1):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            valores = [d["metodo"], d["cantidad"], d["capital"], d["interes"], d["mora"], d["total"]]
            for col, valor in enumerate(valores, start=1):
                cell = ws.cell(row=i, column=col, value=valor)
                if col >= 3:
                    estilo_monto(cell, par, VERDE if col != 5 else NEGRO)
                else:
                    estilo_dato(cell, par)

        fila_detalle = fila_base + len(datos["totales_por_metodo"]) + 2
        encabezados_det = ["FECHA", "REFERENCIA", "CLIENTE", "MÉTODO", "CAPITAL (COP)", "TOTAL (COP)"]
        for col, texto in enumerate(encabezados_det, start=1):
            estilo_encabezado(ws.cell(row=fila_detalle, column=col, value=texto))
        ws.row_dimensions[fila_detalle].height = 22

        for i, d in enumerate(datos["detalle"], start=fila_detalle + 1):
            par = i % 2 == 0
            ws.row_dimensions[i].height = 20
            valores = [d["fecha"], d["referencia_recibo"], d["cliente"], d["metodo"], d["capital"], d["total"]]
            for col, valor in enumerate(valores, start=1):
                cell = ws.cell(row=i, column=col, value=valor)
                if col >= 5:
                    estilo_monto(cell, par, VERDE)
                else:
                    estilo_dato(cell, par)

        ultima = fila_detalle + len(datos["detalle"]) + 2
        ws.cell(row=ultima, column=1).value = f"Periodo: {periodo}  |  Generado: {fecha_hoy}"
        ws.cell(row=ultima, column=1).font = Font(name='Arial', size=8, color="AAAAAA", italic=True)

    else:
        ws.title = "Reporte de Pérdidas"
        datos = get_reporte_perdidas(db, desde=desde, hasta=hasta)

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

def exportar_pdf(db: Session, tipo: str, desde: Optional[date] = None, hasta: Optional[date] = None, tipo_pago_id: Optional[int] = None):
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
    fecha_hoy = date.today().strftime("%d/%m/%Y %H:%M")
    periodo = _label_periodo(desde, hasta)

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
        datos = get_reporte_ganancias(db, desde=desde, hasta=hasta)

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

    elif tipo == "cartera":
        datos = get_reporte_cartera(db, desde=desde, hasta=hasta)

        story.append(Paragraph("Estado de la Cartera", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        resumen_data = [
            [Paragraph("<b>CONCEPTO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>VALOR</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER))],
            ["Total Préstamos", f"{datos['total_prestamos']}"],
            ["Saldo Pendiente Total", f"$ {datos['saldo_pendiente_total']:,.2f}"],
            ["Préstamos Activos", f"{datos['total_activos']} ($ {datos['saldo_activos']:,.2f} por cobrar)"],
            ["Préstamos Pagados", f"{datos['total_pagados']}"],
            ["Préstamos Renovados", f"{datos['total_renovados']}"],
            ["Préstamos Perdidos", f"{datos['total_perdidos']}"],
        ]
        tabla = Table(resumen_data, colWidths=[3.5*inch, 3.5*inch])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(tabla)
        story.append(Spacer(1, 16))

        story.append(Paragraph("Antigüedad del Saldo Pendiente", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))
        ant_data = [[
            Paragraph("<b>RANGO</b>", ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>PRÉSTAMOS</b>", ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>SALDO (COP)</b>", ParagraphStyle('h4', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
        ]]
        for nombre, info in datos["antiguedad"].items():
            ant_data.append([nombre, str(info["cantidad"]), f"$ {info['saldo']:,.2f}"])
        tabla_ant = Table(ant_data, colWidths=[2.5*inch, 2*inch, 2.5*inch])
        tabla_ant.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(tabla_ant)

        if datos["nota"]:
            story.append(Spacer(1, 12))
            story.append(Paragraph(datos["nota"], estilo_pie))

    elif tipo == "cobranza":
        datos = get_reporte_cobranza(db, desde=desde, hasta=hasta)
        totales = datos["totales_cobrados"]

        story.append(Paragraph("Lo Cobrado en el Periodo", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        cob_data = [
            [Paragraph("<b>CONCEPTO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>VALOR (COP)</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER))],
            ["Capital Cobrado", f"$ {totales['capital']:,.2f}"],
            ["Interés Cobrado", f"$ {totales['interes']:,.2f}"],
            ["Mora Cobrada", f"$ {totales['mora']:,.2f}"],
            ["Total Cobrado", f"$ {totales['total']:,.2f}"],
        ]
        tabla = Table(cob_data, colWidths=[4*inch, 3*inch])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(tabla)
        story.append(Spacer(1, 16))

        story.append(Paragraph("Detalle por Día", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        dia_data = [[
            Paragraph("<b>FECHA</b>", ParagraphStyle('d1', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>PAGOS</b>", ParagraphStyle('d2', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>CAPITAL</b>", ParagraphStyle('d3', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>INTERÉS</b>", ParagraphStyle('d4', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>MORA</b>", ParagraphStyle('d5', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>TOTAL</b>", ParagraphStyle('d6', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
        ]]
        for d in datos["detalle_por_dia"]:
            dia_data.append([
                d["fecha"], str(d["cantidad_pagos"]),
                f"$ {d['capital']:,.0f}", f"$ {d['interes']:,.0f}",
                f"$ {d['mora']:,.0f}", f"$ {d['total']:,.0f}",
            ])
        tabla_dias = Table(dia_data, colWidths=[1.3*inch, 0.9*inch, 1.2*inch, 1.2*inch, 1.1*inch, 1.3*inch])
        tabla_dias.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(tabla_dias)

        if datos["nota"]:
            story.append(Spacer(1, 12))
            story.append(Paragraph(datos["nota"], estilo_pie))

    elif tipo == "pagos":
        datos = get_reporte_pagos(db, desde=desde, hasta=hasta, tipo_pago_id=tipo_pago_id)
        total = datos["total_general"]

        story.append(Paragraph("Pagos por Método de Cobro", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        resumen_data = [
            [Paragraph("<b>CONCEPTO</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER)),
             Paragraph("<b>VALOR (COP)</b>", ParagraphStyle('h', fontName='Helvetica-Bold', fontSize=11, textColor=BLANCO, alignment=TA_CENTER))],
            ["Pagos en el periodo", f"{total['cantidad']}"],
            ["Capital Cobrado", f"$ {total['capital']:,.2f}"],
            ["Interés Cobrado", f"$ {total['interes']:,.2f}"],
            ["Mora Cobrada", f"$ {total['mora']:,.2f}"],
            ["Total Cobrado", f"$ {total['total']:,.2f}"],
            ["Pagos Devueltos (aparte)", f"$ {datos['devueltos']['total']:,.2f}"],
        ]
        tabla = Table(resumen_data, colWidths=[4*inch, 3*inch])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(tabla)
        story.append(Spacer(1, 16))

        story.append(Paragraph("Totales por Método de Pago", estilo_seccion))
        story.append(HRFlowable(width="100%", thickness=2, color=MORADO_OSCURO, spaceAfter=10))

        met_data = [[
            Paragraph("<b>MÉTODO</b>", ParagraphStyle('m1', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>PAGOS</b>", ParagraphStyle('m2', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>CAPITAL</b>", ParagraphStyle('m3', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>INTERÉS</b>", ParagraphStyle('m4', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>MORA</b>", ParagraphStyle('m5', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
            Paragraph("<b>TOTAL</b>", ParagraphStyle('m6', fontName='Helvetica-Bold', fontSize=10, textColor=BLANCO, alignment=TA_CENTER)),
        ]]
        for d in datos["totales_por_metodo"]:
            met_data.append([
                d["metodo"], str(d["cantidad"]),
                f"$ {d['capital']:,.0f}", f"$ {d['interes']:,.0f}",
                f"$ {d['mora']:,.0f}", f"$ {d['total']:,.0f}",
            ])
        tabla_met = Table(met_data, colWidths=[1.6*inch, 0.8*inch, 1.2*inch, 1.2*inch, 1.0*inch, 1.2*inch])
        tabla_met.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), MORADO_MEDIO),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [MORADO_CLARO, BLANCO]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(tabla_met)

        if datos["nota"]:
            story.append(Spacer(1, 12))
            story.append(Paragraph(datos["nota"], estilo_pie))

    else:
        datos = get_reporte_perdidas(db, desde=desde, hasta=hasta)

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