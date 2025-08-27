import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from handlers import MENU, ver_resumen # Assuming MENU and ver_resumen are imported from handlers
from datetime import date, datetime

@pytest.mark.asyncio
async def test_ver_resumen_reply_text():
    # Mock Update and Context objects
    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Mock the obtener_resumen function to return some data
    mock_resumen_data = {
        "total_ingresos": 1000.0,
        "total_comision": 100.0,
        "total_gastos": 50.0,
        "monto_neto": 850.0,
        "ultimos_pagos": [],
        "ultimos_gastos": []
    }
    # Mock obtener_resumen to return the mock data
    with pytest.MonkeyPatch.context() as m:
        m.setattr("handlers.obtener_resumen", MagicMock(return_value=mock_resumen_data))

        # Call the function under test
        result = await ver_resumen(mock_update, mock_context)

        # Assert that reply_text was called with the correct arguments
        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args

        # Assert the message content (basic check, full content can be complex)
        assert "📊 *RESUMEN DE ALQUILERES*" in args[0]
        assert "💰 *Total Ingresos:* RD\$1000.00" in args[0]
        assert "💼 *Comisión Total:* RD\$100.00" in args[0]
        assert "💸 *Total Gastos:* RD\$50.00" in args[0]
        assert "🏦 *Monto Neto:* RD\$850.00" in args[0]
        assert "📥 *Últimos Pagos:*\nNo hay pagos registrados" in args[0]
        assert "💸 *Últimos Gastos:*\nNo hay gastos registrados" in args[0]


        # Assert parse_mode
        assert kwargs["parse_mode"].__str__() == "ParseMode.MARKDOWN_V2"

        # Assert reply_markup structure
        reply_markup = kwargs["reply_markup"]
        assert isinstance(reply_markup, ReplyKeyboardMarkup)
        assert len(reply_markup.keyboard) == 1
        assert len(reply_markup.keyboard[0]) == 1
        assert reply_markup.keyboard[0][0].text == "⬅️️ Volver al menú"

        # Assert the return value
        assert result == MENU

@pytest.mark.asyncio
async def test_ver_resumen_with_payments_and_expenses():
    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Mock data with payments and expenses
    mock_resumen_data = {
        "total_ingresos": 2000.0,
        "total_comision": 200.0,
        "total_gastos": 150.0,
        "monto_neto": 1650.0,
        "ultimos_pagos": [
            ("01/01/2025", "Inquilino A", 500.0),
            ("02/01/2025", "Inquilino B", 1500.0)
        ],
        "ultimos_gastos": [
            ("03/01/2025", "Electricidad", 100.0),
            ("04/01/2025", "Agua", 50.0)
        ]
    }

    with pytest.MonkeyPatch.context() as m:
        m.setattr("handlers.obtener_resumen", MagicMock(return_value=mock_resumen_data))

        result = await ver_resumen(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        
        assert "📥 *Últimos Pagos:*" in args[0]
        assert "1. Inquilino A: RD\$500.00 (01/01/2025)" in args[0]
        assert "2. Inquilino B: RD\$1500.00 (02/01/2025)" in args[0]

        assert "💸 *Últimos Gastos:*" in args[0]
        assert "1. Electricidad: RD\$100.00 (03/01/2025)" in args[0]
        assert "2. Agua: RD\$50.00 (04/01/2025)" in args[0]

        assert result == MENU

@pytest.mark.asyncio
async def test_ver_resumen_error_obtener_resumen():
    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    with pytest.MonkeyPatch.context() as m:
        m.setattr("handlers.obtener_resumen", MagicMock(side_effect=Exception("DB Error")))

        result = await ver_resumen(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        args, kwargs = mock_update.message.reply_text.call_args
        assert "❌ Hubo un error al obtener el resumen." in args[0]
        assert result == MENU
