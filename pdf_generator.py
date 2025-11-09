import io
import locale
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from decimal import Decimal

def format_currency_pdf(value: float) -> str:
    """Formatea un valor numérico como moneda para el PDF."""
    try:
        return f"${Decimal(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

def crear_informe_pdf(datos_informe: dict, mes: int, anio: int):
    """
    Genera un informe mensual en formato PDF.

    Args:
        datos_informe (dict): Diccionario con los datos del informe.
        mes (int): El mes del informe.
        anio (int): El año del informe.

    Returns:
        io.BytesIO: El PDF generado en un buffer de memoria.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    
    styles = getSampleStyleSheet()
    elementos = []

    # --- Configurar locale para nombre del mes en español ---
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, '') # Fallback al locale por defecto del sistema

    from datetime import datetime
    nombre_mes = datetime(anio, mes, 1).strftime('%B').capitalize()

    # --- Título ---
    titulo_str = f"Informe de Gestión Mensual - {nombre_mes} {anio}"
    p_titulo = Paragraph(titulo_str, styles['h1'])
    elementos.append(p_titulo)
    elementos.append(Spacer(1, 0.25*inch))

    # --- Resumen Financiero ---
    p_resumen_titulo = Paragraph("Resumen Financiero", styles['h2'])
    elementos.append(p_resumen_titulo)

    # Usar Paragraph para interpretar las etiquetas <b>
    body_style = styles['BodyText']
    right_align_style = styles['BodyText']
    right_align_style.alignment = 2 # 0=left, 1=center, 2=right

    resumen_data = [
        [Paragraph('<b>Ingresos Totales:</b>', body_style), Paragraph(format_currency_pdf(datos_informe.get('total_ingresos', 0)), right_align_style)],
        [Paragraph('<b>Gastos Totales:</b>', body_style), Paragraph(format_currency_pdf(datos_informe.get('total_gastos', 0)), right_align_style)],
        [Paragraph('<b>Comisión de Hecbel:</b>', body_style), Paragraph(format_currency_pdf(datos_informe.get('total_comision', 0)), right_align_style)],
        [Paragraph('<b>Monto Neto a Entregar:</b>', body_style), Paragraph(f"<b>{format_currency_pdf(datos_informe.get('monto_neto', 0))}</b>", right_align_style)],
    ]
    
    resumen_table = Table(resumen_data, colWidths=[2*inch, 4*inch])
    resumen_table.setStyle(TableStyle([
        ('FONTNAME', (0,3), (1,3), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    elementos.append(resumen_table)
    elementos.append(Spacer(1, 0.3*inch))

    # --- Tabla de Pagos del Mes ---
    pagos = datos_informe.get('pagos_mes', [])
    if pagos:
        elementos.append(Paragraph("Detalle de Pagos Recibidos", styles['h2']))
        data_pagos = [['Fecha', 'Inquilino', 'Monto']]
        for _, fecha, inquilino, monto in pagos:
            # Asegurarse de que la fecha sea un objeto datetime antes de formatear
            fecha_obj = datetime.strptime(str(fecha), '%Y-%m-%d') if isinstance(fecha, str) else fecha
            data_pagos.append([fecha_obj.strftime('%d/%m/%Y'), inquilino, format_currency_pdf(monto)])

        tabla_pagos = Table(data_pagos, colWidths=[1.5*inch, 3*inch, 1.5*inch])
        tabla_pagos.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.lightblue),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elementos.append(tabla_pagos)
        elementos.append(Spacer(1, 0.3*inch))

    # --- Tabla de Gastos del Mes ---
    gastos = datos_informe.get('gastos_mes', [])
    if gastos:
        elementos.append(Paragraph("Detalle de Gastos Realizados", styles['h2']))
        data_gastos = [['Fecha', 'Descripción', 'Monto']]
        for _, fecha, desc, monto in gastos:
            # Asegurarse de que la fecha sea un objeto datetime antes de formatear
            fecha_obj = datetime.strptime(str(fecha), '%Y-%m-%d') if isinstance(fecha, str) else fecha
            data_gastos.append([fecha_obj.strftime('%d/%m/%Y'), Paragraph(desc, styles['BodyText']), format_currency_pdf(monto)])

        tabla_gastos = Table(data_gastos, colWidths=[1.5*inch, 3*inch, 1.5*inch])
        tabla_gastos.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkred),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('ALIGN', (1,1), (1,-1), 'LEFT'), # Alinea la descripción a la izquierda
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.lightcoral),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elementos.append(tabla_gastos)

    doc.build(elementos)
    buffer.seek(0)
    return buffer