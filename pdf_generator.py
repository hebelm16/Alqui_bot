import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from decimal import Decimal

def format_currency_pdf(value: float) -> str:
    """Formatea un valor numérico como moneda para el PDF."""
    try:
        return f"RD$ {Decimal(value):,.2f}"
    except (ValueError, TypeError):
        return "RD$ 0.00"

def crear_informe_pdf(datos_informe: dict, mes: int, anio: int):
    """
    Genera un informe mensual ejecutivo en formato PDF con diseño visual premium.
    """
    buffer = io.BytesIO()
    # Márgenes ejecutivos modernos (0.6 pulgadas)
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=45, leftMargin=45, topMargin=45, bottomMargin=45)
    
    styles = getSampleStyleSheet()
    elementos = []

    meses = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
    ]
    nombre_mes = meses[mes] if 1 <= mes <= 12 else f"Mes {mes}"

    # --- Estilos Personalizados Premium ---
    title_style = ParagraphStyle(
        'HeaderTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=18, leading=22,
        textColor=colors.HexColor('#0F172A')
    )
    subtitle_style = ParagraphStyle(
        'HeaderSubtitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=13, leading=16,
        textColor=colors.HexColor('#4F46E5')
    )
    meta_style = ParagraphStyle(
        'HeaderMeta', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, leading=12,
        textColor=colors.HexColor('#64748B'), alignment=2
    )
    section_style = ParagraphStyle(
        'SectionHeading', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=13, leading=16,
        textColor=colors.HexColor('#1E293B'), spaceBefore=12, spaceAfter=6
    )
    body_style = ParagraphStyle(
        'CustomBody', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=13,
        textColor=colors.HexColor('#334155')
    )
    body_bold = ParagraphStyle(
        'CustomBodyBold', parent=body_style,
        fontName='Helvetica-Bold', textColor=colors.HexColor('#0F172A')
    )
    right_align_style = ParagraphStyle(
        'CustomRight', parent=body_style, alignment=2
    )
    right_align_bold = ParagraphStyle(
        'CustomRightBold', parent=body_bold, alignment=2
    )
    neto_label_style = ParagraphStyle(
        'NetoLabel', parent=body_bold, fontSize=11, leading=14, textColor=colors.HexColor('#1E1B4B')
    )
    neto_val_style = ParagraphStyle(
        'NetoVal', parent=right_align_bold, fontSize=12, leading=15, textColor=colors.HexColor('#4F46E5')
    )

    # --- 1. Bloque de Encabezado Corporativo ---
    fecha_emision = datetime.now().strftime('%d/%m/%Y %H:%M')
    header_data = [
        [
            Paragraph("INFORME FINANCIERO MENSUAL", title_style),
            Paragraph(f"<b>Emisión:</b> {fecha_emision}<br/><b>Sistema:</b> Alqui_bot Pro", meta_style)
        ],
        [
            Paragraph(f"PERÍODO: {nombre_mes.upper()} {anio}", subtitle_style),
            ""
        ]
    ]
    header_table = Table(header_data, colWidths=[4.2*inch, 2.8*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LINEBELOW', (0,1), (-1,1), 2, colors.HexColor('#4F46E5')),
    ]))
    elementos.append(header_table)
    elementos.append(Spacer(1, 16))

    # --- 2. Tabla Resumen Ejecutivo ---
    elementos.append(Paragraph("RESUMEN EJECUTIVO DE BALANCE", section_style))
    elementos.append(Spacer(1, 6))

    resumen_data = [
        [Paragraph('<b>Concepto Financiero</b>', body_bold), Paragraph('<b>Monto Acumulado</b>', right_align_bold)],
        [Paragraph('Ingresos Brutos por Cobros de Alquiler', body_style), Paragraph(format_currency_pdf(datos_informe.get('total_ingresos', 0)), right_align_style)],
        [Paragraph('Gastos Operativos y Mantenimiento', body_style), Paragraph(format_currency_pdf(datos_informe.get('total_gastos', 0)), right_align_style)],
        [Paragraph('Comisión por Gestión Administrativa', body_style), Paragraph(format_currency_pdf(datos_informe.get('total_comision', 0)), right_align_style)],
        [Paragraph('MONTO NETO A ENTREGAR AL PROPIETARIO', neto_label_style), Paragraph(format_currency_pdf(datos_informe.get('monto_neto', 0)), neto_val_style)],
    ]
    
    resumen_table = Table(resumen_data, colWidths=[4.2*inch, 2.8*inch])
    resumen_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,1), (-1,3), colors.white),
        ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0,4), (-1,4), colors.HexColor('#EEF2FF')), # Destacado Índigo Suave para Neto
        ('LINEABOVE', (0,4), (-1,4), 1.5, colors.HexColor('#4F46E5')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
    ]))
    elementos.append(resumen_table)
    elementos.append(Spacer(1, 18))

    # --- 3. Detalle de Pagos Recibidos ---
    pagos = datos_informe.get('pagos_mes', [])
    if pagos:
        th_pago = ParagraphStyle('THPago', parent=body_bold, textColor=colors.white)
        elementos.append(Paragraph("DETALLE DE COBROS Y PAGOS RECIBIDOS", section_style))
        elementos.append(Spacer(1, 6))
        
        data_pagos = [[Paragraph('<b>Fecha Cobro</b>', th_pago), Paragraph('<b>Inquilino / Pagador</b>', th_pago), Paragraph('<b>Monto Recibido</b>', ParagraphStyle('THPagoR', parent=th_pago, alignment=2))]]
        for idx, (_, fecha, inquilino, monto) in enumerate(pagos):
            fecha_obj = datetime.strptime(str(fecha), '%Y-%m-%d') if isinstance(fecha, str) else fecha
            data_pagos.append([
                Paragraph(fecha_obj.strftime('%d/%m/%Y'), body_style),
                Paragraph(inquilino, body_style),
                Paragraph(format_currency_pdf(monto), right_align_bold)
            ])

        tabla_pagos = Table(data_pagos, colWidths=[1.5*inch, 3.8*inch, 1.7*inch])
        t_style = [
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#059669')), # Esmeralda Ejecutivo
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#059669')),
        ]
        for i in range(1, len(data_pagos)):
            bg = colors.white if i % 2 != 0 else colors.HexColor('#F0FDF4')
            t_style.append(('BACKGROUND', (0,i), (-1,i), bg))
            t_style.append(('LINEBELOW', (0,i), (-1,i), 0.5, colors.HexColor('#E2E8F0')))
        tabla_pagos.setStyle(TableStyle(t_style))
        elementos.append(KeepTogether(tabla_pagos))
        elementos.append(Spacer(1, 16))

    # --- 4. Detalle de Gastos Realizados ---
    gastos = datos_informe.get('gastos_mes', [])
    if gastos:
        th_gasto = ParagraphStyle('THGasto', parent=body_bold, textColor=colors.white)
        elementos.append(Paragraph("DETALLE DE GASTOS Y MANTENIMIENTOS", section_style))
        elementos.append(Spacer(1, 6))
        
        data_gastos = [[Paragraph('<b>Fecha</b>', th_gasto), Paragraph('<b>Descripción del Gasto</b>', th_gasto), Paragraph('<b>Monto Gasto</b>', ParagraphStyle('THGastoR', parent=th_gasto, alignment=2))]]
        for idx, (_, fecha, desc, monto) in enumerate(gastos):
            fecha_obj = datetime.strptime(str(fecha), '%Y-%m-%d') if isinstance(fecha, str) else fecha
            data_gastos.append([
                Paragraph(fecha_obj.strftime('%d/%m/%Y'), body_style),
                Paragraph(desc, body_style),
                Paragraph(format_currency_pdf(monto), right_align_bold)
            ])

        tabla_gastos = Table(data_gastos, colWidths=[1.5*inch, 3.8*inch, 1.7*inch])
        t_style_g = [
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E11D48')), # Rose Ejecutivo
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#E11D48')),
        ]
        for i in range(1, len(data_gastos)):
            bg = colors.white if i % 2 != 0 else colors.HexColor('#FFF1F2')
            t_style_g.append(('BACKGROUND', (0,i), (-1,i), bg))
            t_style_g.append(('LINEBELOW', (0,i), (-1,i), 0.5, colors.HexColor('#E2E8F0')))
        tabla_gastos.setStyle(TableStyle(t_style_g))
        elementos.append(KeepTogether(tabla_gastos))

    # --- Pie de página al final del documento ---
    elementos.append(Spacer(1, 25))
    footer_p = Paragraph(
        "Documento confidencial generado automáticamente por Alqui_bot • Sistema de Administración y Control de Propiedades",
        ParagraphStyle('FooterNote', parent=styles['Italic'], fontName='Helvetica-Oblique', fontSize=8, textColor=colors.HexColor('#94A3B8'), alignment=1)
    )
    elementos.append(KeepTogether([footer_p]))

    doc.build(elementos)
    buffer.seek(0)
    return buffer