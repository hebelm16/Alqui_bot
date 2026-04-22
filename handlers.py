from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import ContextTypes, ConversationHandler
import calendar
from datetime import date, datetime, timedelta
import logging
import psycopg2
from psycopg2.errors import UniqueViolation
from decimal import Decimal, InvalidOperation
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from database import (
    registrar_pago, registrar_gasto, obtener_resumen, obtener_informe_mensual,
    deshacer_ultimo_pago, deshacer_ultimo_gasto, crear_inquilino, obtener_inquilinos,
    cambiar_estado_inquilino, obtener_inquilino_por_id, delete_pago_by_id, delete_gasto_by_id,
    obtener_inquilinos_para_recordatorio, actualizar_dia_pago_inquilino, obtener_mes_pago_pendiente
)
from config import AUTHORIZED_USERS
from pdf_generator import crear_informe_pdf
import os
import tempfile

logger = logging.getLogger(__name__)

# === Estados de conversación ===
(
    MENU, PAGO_SELECT_INQUILINO, PAGO_MONTO, GASTO_MONTO, GASTO_DESC,
    INFORME_MES, INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR,
    INQUILINO_MENU, INQUILINO_ADD_NOMBRE, INQUILINO_DEACTIVATE_SELECT,
    INQUILINO_ACTIVATE_SELECT, EDITAR_INICIO, EDITAR_PEDIR_ANIO, EDITAR_PEDIR_MES,
    EDITAR_SELECCIONAR_TRANSACCION, EDITAR_CONFIRMAR_BORRADO,
    INQUILINO_SET_DIA_PAGO_SELECT, INQUILINO_SET_DIA_PAGO_SAVE
) = range(20)

# === Helpers ===
def format_currency(value: float) -> str:
    """Formatea un valor como moneda (RD$)."""
    try:
        return f"RD${Decimal(value):.2f}"
    except (InvalidOperation, TypeError):
        return "RD$0.00"

def md(text: str) -> str:
    """Escapa caracteres especiales para Markdown V2."""
    return escape_markdown(str(text), version=2)

def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Crea el teclado del menú principal."""
    keyboard = [
        [KeyboardButton("📥 Registrar Pago"), KeyboardButton("💸 Registrar Gasto")],
        [KeyboardButton("👤 Gestionar Inquilinos"), KeyboardButton("✏️ Editar/Borrar")],
        [KeyboardButton("📊 Ver Resumen"), KeyboardButton("📈 Generar Informe")],
        [KeyboardButton("🗑️ Deshacer")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Crea un teclado con opción de cancelar."""
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)

async def _save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, tipo: str):
    """Función genérica para guardar una transacción (pago o gasto) y manejar errores."""
    try:
        monto = context.user_data['monto']
        detalle = context.user_data['detalle']
        fecha_registro = date.today()
        mensaje_adicional = ""

        if tipo == 'pago':
            fecha_pago_efectiva = await obtener_mes_pago_pendiente(detalle)
            if fecha_pago_efectiva:
                fecha_registro = fecha_pago_efectiva
                mensaje_adicional = f"\n\n_Nota: El pago se ha registrado para el período pendiente de {md(fecha_registro.strftime('%B de %Y'))}\._"
            
            await registrar_pago(fecha_registro, detalle, monto)
            mensaje = (
                f"✅ Pago registrado correctamente:\n"
                f"📅 Fecha de Pago: {md(fecha_registro.strftime('%d/%m/%Y'))}\n"
                f"👤 Inquilino: {md(detalle)}\n"
                f"💵 Monto: {md(format_currency(monto))}"
                f"{mensaje_adicional}"
            )
        elif tipo == 'gasto':
            await registrar_gasto(fecha_registro, detalle, monto)
            mensaje = (
                f"✅ Gasto registrado correctamente:\n"
                f"📅 Fecha: {fecha_registro.strftime('%d/%m/%Y')}\n"
                f"📝 Descripción: {md(detalle)}\n"
                f"💸 Monto: {md(format_currency(monto))}"
            )
        else:
            return

        await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_main_menu_keyboard())

    except UniqueViolation as e:
        # ✅ ARREGLADO: Mensaje dinámico según el tipo de transacción
        if tipo == 'pago':
            error_msg = rf"❌ Ya existe un pago registrado para *{md(detalle)}* en la fecha de hoy\. Si quieres modificarlo, usa la opción 'Deshacer'\."
        elif tipo == 'gasto':
            error_msg = rf"❌ Error de duplicado: La descripción *{md(detalle)}* puede estar duplicada\. Intenta nuevamente o usa 'Editar/Borrar'\."
        else:
            error_msg = "❌ Ya existe un registro similar\. Si quieres modificarlo, usa el menú de opciones\."
        
        logger.warning(f"UniqueViolation al registrar {tipo}: {detalle} - {e}")
        await update.message.reply_text(
            error_msg,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=create_main_menu_keyboard()
        )
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al registrar {tipo}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Hubo un error con la base de datos al registrar el {tipo}.", reply_markup=create_main_menu_keyboard())
    # Catching all exceptions to log unexpected errors and notify the user; this ensures the bot does not crash on unforeseen issues.
    except Exception as e:
        logger.error(f"Error inesperado al registrar {tipo}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Hubo un error inesperado al registrar el {tipo}.", reply_markup=create_main_menu_keyboard())
    finally:
        context.user_data.clear()

# === Handlers Principales ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler de /start - Verifica autorización y muestra menú principal."""
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("❌ No tienes permiso para usar este bot.")
        return ConversationHandler.END

    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text("Bienvenido al sistema de gestión de alquileres. Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def volver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para cancelar - Vuelve al menú principal."""
    context.user_data.clear()
    await update.message.reply_text("Operación cancelada. Volviendo al menú principal.", reply_markup=create_main_menu_keyboard())
    return MENU

# === Flujo Registrar Pago ===
async def pago_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de registrar pago - Muestra lista de inquilinos."""
    inquilinos = await obtener_inquilinos(activos_only=True)
    if not inquilinos:
        await update.message.reply_text(
            "No hay inquilinos activos. Por favor, añade un inquilino primero desde el menú 'Gestionar Inquilinos'.",
            reply_markup=create_main_menu_keyboard()
        )
        return MENU

    keyboard = [[KeyboardButton(inquilino[1])] for inquilino in inquilinos]
    keyboard.append([KeyboardButton("❌ Cancelar")])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text("Selecciona el inquilino que realizó el pago:", reply_markup=reply_markup)
    return PAGO_SELECT_INQUILINO