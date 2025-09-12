import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from telegram.ext import ContextTypes
from handlers import MENU, ver_resumen
from decimal import Decimal

@pytest.mark.asyncio
async def test_ver_resumen_sends_document():
    """Verifica que ver_resumen envía un documento con el resumen."""
    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    mock_resumen_data = {
        "total_ingresos": Decimal("1000.00"),
        "total_comision": Decimal("100.00"),
        "total_gastos": Decimal("50.00"),
        "monto_neto": Decimal("850.00"),
        "ultimos_pagos": [],
        "ultimos_gastos": []
    }

    # Usamos patch para mockear las funciones de la base de datos y de archivos
    with patch("handlers.obtener_resumen", new_callable=AsyncMock, return_value=mock_resumen_data),
         patch("tempfile.NamedTemporaryFile"),
         patch("os.remove"):

        # Llamamos a la función
        result = await ver_resumen(mock_update, mock_context)

        # Verificamos que se llamó a reply_document
        mock_update.message.reply_document.assert_called_once()
        call_args, call_kwargs = mock_update.message.reply_document.call_args
        
        # Verificamos el caption y el nombre del archivo
        assert "Aquí está tu resumen general." in call_kwargs['caption']
        assert "resumen_general.txt" in call_kwargs['document'].filename

        # Verificamos que el estado de la conversación es correcto
        assert result == MENU

@pytest.mark.asyncio
async def test_ver_resumen_db_error():
    """Verifica el manejo de errores si la base de datos falla."""
    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Simulamos un error en la base de datos
    with patch("handlers.obtener_resumen", new_callable=AsyncMock, side_effect=Exception("DB Error")),
         patch("tempfile.NamedTemporaryFile"),
         patch("os.remove"):

        result = await ver_resumen(mock_update, mock_context)

        # Verificamos que se envió un mensaje de error
        mock_update.message.reply_text.assert_called_once_with(
            "❌ Hubo un error con la base de datos al generar el resumen.",
            reply_markup=MagicMock() # El markup se mockea porque no es el foco del test
        )
        assert result == MENU