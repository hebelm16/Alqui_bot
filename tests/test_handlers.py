import pytest
import psycopg2
from psycopg2.errors import UniqueViolation
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from telegram.ext import ContextTypes
from decimal import Decimal

from handlers import (
    MENU,
    INQUILINO_MENU,
    ver_resumen,
    add_inquilino_save,
    list_inquilinos
)

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

    with (patch("handlers.obtener_resumen", new_callable=AsyncMock, return_value=mock_resumen_data),
          patch("tempfile.NamedTemporaryFile"),
          patch("os.remove")):

        result = await ver_resumen(mock_update, mock_context)

        mock_update.message.reply_document.assert_called_once()
        _, call_kwargs = mock_update.message.reply_document.call_args
        
        assert "Aquí está tu resumen general." in call_kwargs['caption']
        assert "resumen_general.txt" in call_kwargs['document'].filename
        assert result == MENU

@pytest.mark.asyncio
async def test_ver_resumen_db_error():
    """Verifica el manejo de errores si la base de datos falla."""
    mock_update = AsyncMock(spec=Update)
    mock_update.message = AsyncMock()
    mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    with (patch("handlers.obtener_resumen", new_callable=AsyncMock, side_effect=psycopg2.Error("DB Error")),
          patch("tempfile.NamedTemporaryFile"),
          patch("os.remove")):

        result = await ver_resumen(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        assert "Hubo un error con la base de datos" in mock_update.message.reply_text.call_args[0][0]
        assert result == MENU

@pytest.mark.asyncio
class TestGestionarInquilinos:
    """Tests para el flujo de gestión de inquilinos."""

    async def test_add_inquilino_save_success(self):
        """Verifica que se puede añadir un inquilino correctamente."""
        mock_update = AsyncMock(spec=Update)
        mock_update.message = AsyncMock()
        mock_update.message.text = "Nuevo Inquilino"
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch("handlers.crear_inquilino", new_callable=AsyncMock) as mock_crear_inquilino:
            result = await add_inquilino_save(mock_update, mock_context)

            mock_crear_inquilino.assert_called_once_with("Nuevo Inquilino")
            mock_update.message.reply_text.assert_called_once()
            assert "añadido correctamente" in mock_update.message.reply_text.call_args[0][0]
            assert result == INQUILINO_MENU

    async def test_add_inquilino_save_duplicate(self):
        """Verifica el manejo de error al añadir un inquilino duplicado."""
        mock_update = AsyncMock(spec=Update)
        mock_update.message = AsyncMock()
        mock_update.message.text = "Inquilino Existente"
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch("handlers.crear_inquilino", new_callable=AsyncMock, side_effect=UniqueViolation):
            result = await add_inquilino_save(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            assert "ya existe" in mock_update.message.reply_text.call_args[0][0]
            assert result == INQUILINO_MENU

    async def test_list_inquilinos_with_tenants(self):
        """Verifica que se listan los inquilinos existentes."""
        mock_update = AsyncMock(spec=Update)
        mock_update.message = AsyncMock()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        mock_inquilinos = [
            (1, "Inquilino Activo", True),
            (2, "Inquilino Inactivo", False),
        ]

        with patch("handlers.obtener_inquilinos", new_callable=AsyncMock, return_value=mock_inquilinos):
            result = await list_inquilinos(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            text_result = mock_update.message.reply_text.call_args[0][0]
            assert "Inquilino Activo" in text_result
            assert "\\(✅ Activo\\)" in text_result
            assert "Inquilino Inactivo" in text_result
            assert "\\(❌ Inactivo\\)" in text_result
            assert result == INQUILINO_MENU

    async def test_list_inquilinos_no_tenants(self):
        """Verifica el mensaje cuando no hay inquilinos."""
        mock_update = AsyncMock(spec=Update)
        mock_update.message = AsyncMock()
        mock_context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

        with patch("handlers.obtener_inquilinos", new_callable=AsyncMock, return_value=[]):
            result = await list_inquilinos(mock_update, mock_context)

            mock_update.message.reply_text.assert_called_once()
            assert "No hay inquilinos registrados" in mock_update.message.reply_text.call_args[0][0]
            assert result == INQUILINO_MENU