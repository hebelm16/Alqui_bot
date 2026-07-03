import pytest
from decimal import Decimal
from datetime import date
from receipt_generator import crear_recibo_pdf, crear_recibo_png
from export_generator import exportar_informe_excel

def test_crear_recibo_pdf():
    pdf_buffer = crear_recibo_pdf(1, "2026-07-03", "Juan Perez", Decimal("15000.50"))
    assert pdf_buffer is not None
    content = pdf_buffer.getvalue()
    assert len(content) > 1000
    assert content.startswith(b"%PDF")

def test_crear_recibo_png():
    png_buffer = crear_recibo_png(1, "2026-07-03", "Juan Perez", Decimal("15000.50"))
    assert png_buffer is not None
    content = png_buffer.getvalue()
    assert len(content) > 1000
    assert content.startswith(b"\x89PNG")

def test_exportar_informe_excel():
    datos = {
        'total_ingresos': Decimal('25000'),
        'total_gastos': Decimal('5000'),
        'total_comision': Decimal('1250'),
        'monto_neto': Decimal('18750'),
        'pagos_mes': [(1, date(2026, 7, 1), 'Carlos Lopez', Decimal('25000'))],
        'gastos_mes': [(1, date(2026, 7, 2), 'Mantenimiento', Decimal('5000'))]
    }
    excel_buffer = exportar_informe_excel(7, 2026, datos)
    assert excel_buffer is not None
    content = excel_buffer.getvalue()
    assert len(content) > 2000
    # Excel zip header check (PK\x03\x04)
    assert content.startswith(b"PK\x03\x04")
