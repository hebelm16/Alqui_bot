import io
from datetime import datetime, date
from decimal import Decimal
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from PIL import Image, ImageDraw, ImageFont

def format_currency_pdf(value: float | Decimal) -> str:
    """Formatea un valor numérico como moneda RD$ para el PDF."""
    try:
        return f"RD${Decimal(value):,.2f}"
    except (ValueError, TypeError):
        return "RD$0.00"

def crear_recibo_pdf(pago_id: int, fecha: datetime | date | str, inquilino: str, monto: Decimal | float) -> io.BytesIO:
    """
    Genera un comprobante digital de pago en formato PDF.
    Devuelve un buffer io.BytesIO con el contenido del archivo.
    """
    buffer = io.BytesIO()
    
    # Documento con márgenes moderados para un recibo elegante
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1a365d'),
        alignment=1 # Centro
    )
    
    sub_header_style = ParagraphStyle(
        'SubHeaderStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#4a5568'),
        alignment=1 # Centro
    )

    title_box_style = ParagraphStyle(
        'TitleBoxStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        textColor=colors.white,
        alignment=1
    )

    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#2d3748')
    )

    value_style = ParagraphStyle(
        'ValueStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1a202c')
    )

    monto_style = ParagraphStyle(
        'MontoStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#2b6cb0')
    )

    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Italic'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#718096'),
        alignment=1
    )

    # Convertir fecha a string formateado
    if isinstance(fecha, (datetime, date)):
        fecha_str = fecha.strftime('%d/%m/%Y')
    else:
        try:
            fecha_obj = datetime.strptime(str(fecha), '%Y-%m-%d')
            fecha_str = fecha_obj.strftime('%d/%m/%Y')
        except ValueError:
            fecha_str = str(fecha)

    elementos = []

    # 1. Encabezado principal
    elementos.append(Paragraph("SISTEMA DE GESTIÓN DE ALQUILERES", header_style))
    elementos.append(Spacer(1, 4))
    elementos.append(Paragraph("Comprobante Digital Oficial de Pago", sub_header_style))
    elementos.append(Spacer(1, 20))

    # 2. Barra de Título / Folio
    folio_data = [[Paragraph(f"RECIBO DE PAGO — FOLIO #{pago_id:04d}", title_box_style)]]
    folio_table = Table(folio_data, colWidths=[6.5 * inch])
    folio_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#2b6cb0')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('CORNERPAD', (0,0), (-1,-1), 4),
    ]))
    elementos.append(folio_table)
    elementos.append(Spacer(1, 20))

    # 3. Detalle Principal en Tabla con Borde
    detalle_data = [
        [Paragraph("Recibido de:", label_style), Paragraph(f"<b>{inquilino}</b>", value_style)],
        [Paragraph("Fecha de Pago:", label_style), Paragraph(fecha_str, value_style)],
        [Paragraph("Concepto:", label_style), Paragraph("Pago de cuota de alquiler", value_style)],
        [Paragraph("Monto Recibido:", label_style), Paragraph(format_currency_pdf(monto), monto_style)],
        [Paragraph("Estado de Operación:", label_style), Paragraph("<font color='#2f855a'><b>APROBADO / REGISTRADO</b></font>", value_style)]
    ]

    detalle_table = Table(detalle_data, colWidths=[2.0 * inch, 4.5 * inch])
    detalle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#edf2f7')),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elementos.append(detalle_table)
    elementos.append(Spacer(1, 40))

    # 4. Línea de firma / Validación
    firma_data = [
        ["", ""],
        ["________________________________________", ""],
        ["Administración — Alqui_bot", "Sello Digital Verificado"]
    ]
    firma_table = Table(firma_data, colWidths=[3.5 * inch, 3.0 * inch])
    firma_table.setStyle(TableStyle([
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 2), (-1, -1), 'Helvetica-Oblique'),
        ('FONTSIZE', (0, 2), (-1, -1), 9),
        ('TEXTCOLOR', (0, 2), (-1, -1), colors.HexColor('#718096')),
    ]))
    elementos.append(firma_table)
    elementos.append(Spacer(1, 40))

    # 5. Pie de página
    elementos.append(Paragraph("Este documento es un comprobante digital emitido automáticamente por Alqui_bot.<br/>Conserve este archivo como constancia de su pago.", footer_style))

    doc.build(elementos)
    buffer.seek(0)
    return buffer

def get_font(size: int, bold: bool = False):
    font_names = [
        'arialbd.ttf' if bold else 'arial.ttf',
        'calibrib.ttf' if bold else 'calibri.ttf',
        'segoeuib.ttf' if bold else 'segoeui.ttf',
        'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    for fn in font_names:
        try:
            return ImageFont.truetype(fn, size)
        except IOError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

def crear_recibo_png(pago_id: int, fecha: datetime | date | str, inquilino: str, monto: Decimal | float) -> io.BytesIO:
    """Genera un recibo de pago profesional en formato de imagen PNG."""
    width, height = 800, 950
    img = Image.new('RGB', (width, height), color='#FFFFFF')
    draw = ImageDraw.Draw(img)

    font_title = get_font(28, bold=True)
    font_sub = get_font(18, bold=False)
    font_banner = get_font(22, bold=True)
    font_label = get_font(18, bold=True)
    font_val = get_font(18, bold=False)
    font_monto = get_font(26, bold=True)
    font_footer = get_font(14, bold=False)

    if isinstance(fecha, (datetime, date)):
        fecha_str = fecha.strftime('%d/%m/%Y')
    else:
        try:
            fecha_obj = datetime.strptime(str(fecha), '%Y-%m-%d')
            fecha_str = fecha_obj.strftime('%d/%m/%Y')
        except ValueError:
            fecha_str = str(fecha)

    # 1. Encabezado
    draw.text((width//2, 50), "SISTEMA DE GESTIÓN DE ALQUILERES", fill='#1a365d', font=font_title, anchor="mm")
    draw.text((width//2, 90), "Comprobante Digital Oficial de Pago", fill='#4a5568', font=font_sub, anchor="mm")

    # 2. Banner de Folio
    draw.rectangle([(50, 130), (width-50, 190)], fill='#2b6cb0', outline=None, width=0)
    draw.text((width//2, 160), f"RECIBO DE PAGO — FOLIO #{pago_id:04d}", fill='#FFFFFF', font=font_banner, anchor="mm")

    # 3. Recuadro exterior de detalle
    box_top, box_bottom = 230, 620
    draw.rounded_rectangle([(50, box_top), (width-50, box_bottom)], radius=12, fill='#f7fafc', outline='#cbd5e0', width=2)

    # Filas de detalle
    items = [
        ("Recibido de:", inquilino, font_val, '#1a202c'),
        ("Fecha de Pago:", fecha_str, font_val, '#1a202c'),
        ("Concepto:", "Pago de cuota de alquiler", font_val, '#1a202c'),
        ("Monto Recibido:", format_currency_pdf(monto), font_monto, '#2b6cb0'),
        ("Estado de Operación:", "APROBADO / REGISTRADO", font_label, '#2f855a')
    ]

    y = box_top + 50
    for label, val, val_f, val_col in items:
        draw.text((90, y), label, fill='#2d3748', font=font_label, anchor="lm")
        draw.text((320, y), val, fill=val_col, font=val_f, anchor="lm")
        y += 70
        if label != items[-1][0]:
            draw.line([(80, y - 25), (width - 80, y - 25)], fill='#e2e8f0', width=1)

    # 4. Firma
    y_firma = 760
    draw.line([(width//2 - 150, y_firma), (width//2 + 150, y_firma)], fill='#718096', width=2)
    draw.text((width//2, y_firma + 25), "Administración — Alqui_bot", fill='#4a5568', font=font_sub, anchor="mm")
    draw.text((width//2, y_firma + 55), "Sello Digital Verificado", fill='#718096', font=font_footer, anchor="mm")

    # 5. Pie de página
    draw.text((width//2, 890), "Este documento es un comprobante digital emitido automáticamente por Alqui_bot.", fill='#a0aec0', font=font_footer, anchor="mm")
    draw.text((width//2, 915), "Conserve este archivo como constancia de su pago.", fill='#a0aec0', font=font_footer, anchor="mm")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
