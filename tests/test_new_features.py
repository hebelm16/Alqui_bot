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

@pytest.mark.asyncio
async def test_generar_mensaje_pendientes():
    from unittest.mock import patch
    from handlers import _generar_mensaje_pendientes
    with patch('handlers.obtener_inquilinos_pendientes_mes', return_value=[("Carlos", 5), ("Ana", None)]):
        mensaje, markup = await _generar_mensaje_pendientes(6, 2026)
        assert "JUNIO 2026" in mensaje
        assert "Carlos" in mensaje
        assert "Ana" in mensaje
        assert len(markup.inline_keyboard[0]) == 2 # Mes Anterior y Mes Actual buttons

@pytest.mark.asyncio
async def test_save_transaction_pago_real_date():
    from unittest.mock import AsyncMock, patch, MagicMock
    from handlers import _save_transaction
    from telegram import Update
    from telegram.ext import ContextTypes

    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    fecha_real = date(2026, 7, 3)
    mock_context.user_data = {
        'monto': Decimal("15000"),
        'detalle': "Carlos",
        'fecha_custom': fecha_real
    }

    with patch('handlers.obtener_mes_pago_pendiente', return_value=date(2026, 6, 1)), \
         patch('handlers.registrar_pago', return_value=99) as mock_reg:
        await _save_transaction(mock_update, mock_context, 'pago')
        # Verifica que la fecha guardada sea la fecha real (2026-07-03) y el periodo sea mes 6 (Junio) y anio 2026
        mock_reg.assert_called_once_with(fecha_real, "Carlos", Decimal("15000"), 6, 2026)
