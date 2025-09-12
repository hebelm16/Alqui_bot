from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import ContextTypes, ConversationHandler
from datetime import date, datetime
import logging
import psycopg2
from decimal import Decimal, InvalidOperation
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from database import (
    registrar_pago, registrar_gasto, obtener_resumen, obtener_informe_mensual,
    deshacer_ultimo_pago, deshacer_ultimo_gasto
)
from config import AUTHORIZED_USERS
import os
import tempfile

logger = logging.getLogger(__name__)

# === Estados de conversación ===
MENU, PAGO_MONTO, PAGO_NOMBRE, GASTO_MONTO, GASTO_DESC, INFORME_MES, INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR = range(9)

# === Helper ===
def format_currency(value: float) -> str:
    return f"RD${value:,.2f}"

def md(text: str) -> str:
    return escape_markdown(str(text), version=2)

def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📥 Registrar Pago"), KeyboardButton("💸 Registrar Gasto")],
        [KeyboardButton("📊 Ver Resumen"), KeyboardButton("📈 Generar Informe")],
        [KeyboardButton("🗑️ Deshacer")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("❌ No tienes permiso para usar este bot.")
        return ConversationHandler.END

    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text("Bienvenido al sistema de gestión de alquileres. Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def pago_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)
    await update.message.reply_text("Escribe el monto del pago recibido (ej: 3000):", reply_markup=reply_markup)
    return PAGO_MONTO

async def pago_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    if texto == "❌ Cancelar":
        return await volver_menu(update, context)

    try:
        monto = Decimal(texto.replace(",", "").replace("RD$", "").strip())
        context.user_data['pago_monto'] = monto
        reply_markup = ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)
        await update.message.reply_text(f"Monto registrado: {format_currency(monto)}\nAhora escribe el nombre del inquilino:", reply_markup=reply_markup)
        return PAGO_NOMBRE
    except InvalidOperation:
        await update.message.reply_text("Monto inválido. Intenta de nuevo con un número válido (ej: 3000):")
        return PAGO_MONTO

async def pago_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nombre = update.message.text.strip()
    if nombre == "❌ Cancelar":
        return await volver_menu(update, context)

    monto = context.user_data['pago_monto']
    fecha = date.today()

    try:
        await registrar_pago(fecha, nombre, monto)
        await update.message.reply_text(
            f"✅ Pago registrado correctamente:\n"
            f"📅 Fecha: {fecha.strftime('%d/%m/%Y')}\n"
            f"👤 Inquilino: {md(nombre)}\n"
            f"💵 Monto: {md(format_currency(monto))}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=create_main_menu_keyboard()
        )
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al registrar pago: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al registrar el pago.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al registrar pago: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al registrar el pago.", reply_markup=create_main_menu_keyboard())
    return MENU

async def gasto_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)
    await update.message.reply_text("Escribe el monto del gasto (ej: 500):", reply_markup=reply_markup)
    return GASTO_MONTO

async def gasto_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    if texto == "❌ Cancelar":
        return await volver_menu(update, context)

    try:
        monto = Decimal(texto.replace(",", "").replace("RD$", "").strip())
        context.user_data['gasto_monto'] = monto
        reply_markup = ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)
        await update.message.reply_text(f"Monto registrado: {format_currency(monto)}\nAhora escribe la descripción del gasto:", reply_markup=reply_markup)
        return GASTO_DESC
    except InvalidOperation:
        await update.message.reply_text("Monto inválido. Intenta de nuevo con un número válido (ej: 500):")
        return GASTO_MONTO

async def gasto_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    descripcion = update.message.text.strip()
    if descripcion == "❌ Cancelar":
        return await volver_menu(update, context)

    monto = context.user_data['gasto_monto']
    fecha = date.today()

    try:
        await registrar_gasto(fecha, descripcion, monto)
        await update.message.reply_text(
            f"✅ Gasto registrado correctamente:\n"
            f"📅 Fecha: {fecha.strftime('%d/%m/%Y')}\n"
            f"📝 Descripción: {md(descripcion)}\n"
            f"💸 Monto: {md(format_currency(monto))}",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=create_main_menu_keyboard()
        )
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al registrar gasto: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al registrar el gasto.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al registrar gasto: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al registrar el gasto.", reply_markup=create_main_menu_keyboard())
    return MENU

async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    temp_file_path = None
    try:
        resumen_data = await obtener_resumen()
        mensaje = format_summary(resumen_data)

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8', suffix='.txt') as temp_file:
            temp_file.write(mensaje)
            temp_file_path = temp_file.name

        with open(temp_file_path, 'rb') as f:
            await update.message.reply_document(document=InputFile(f, filename='resumen_general.txt'),
                                                caption='Aquí está tu resumen general.')
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al generar resumen: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al generar el resumen.", reply_markup=create_main_menu_keyboard())
    except IOError as e:
        logger.error(f"Error de archivo al generar resumen: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error al crear el archivo de resumen.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al generar resumen: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al generar el resumen.", reply_markup=create_main_menu_keyboard())
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
    return MENU

async def informe_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [KeyboardButton("Informe Mes Actual")],
        [KeyboardButton("Elegir Mes y Año")],
        [KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Selecciona el tipo de informe que deseas generar:", reply_markup=reply_markup)
    return INFORME_MES

async def informe_mes_actual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    hoy = date.today()
    return await generar_informe_mensual(update, context, hoy.month, hoy.year)

async def informe_pedir_mes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Por favor, introduce el número del mes (1-12):")
    return INFORME_ANIO

async def informe_pedir_anio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mes = int(update.message.text.strip())
        if not 1 <= mes <= 12:
            await update.message.reply_text("Mes inválido. Por favor, introduce un número del 1 al 12.")
            return INFORME_ANIO
        context.user_data['report_month'] = mes
        await update.message.reply_text("Ahora, introduce el año (ej: 2023):")
        return INFORME_GENERAR
    except ValueError:
        await update.message.reply_text("Entrada inválida. Por favor, introduce un número para el mes.")
        return INFORME_ANIO

async def generar_informe_mensual_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        anio = int(update.message.text.strip())
        if not 1900 < anio < 2100:
            await update.message.reply_text("Año inválido. Por favor, introduce un año válido (ej: 2023).")
            return INFORME_GENERAR

        mes = context.user_data.get('report_month')
        if not mes:
            await update.message.reply_text("❌ Error: No se encontró el mes para el informe. Volviendo al menú.", reply_markup=create_main_menu_keyboard())
            return MENU

        return await generar_informe_mensual(update, context, mes, anio)
    except (ValueError, KeyError):
        await update.message.reply_text("Año inválido. Por favor, introduce un número para el año (ej: 2023).")
        return INFORME_GENERAR

async def generar_informe_mensual(update: Update, context: ContextTypes.DEFAULT_TYPE, mes: int, anio: int) -> int:
    temp_file_path = None
    try:
        report_data = await obtener_informe_mensual(mes, anio)
        title = f"Informe Mensual - {mes}/{anio}"
        mensaje = format_report(title, report_data)

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8', suffix='.txt') as temp_file:
            temp_file.write(mensaje)
            temp_file_path = temp_file.name

        with open(temp_file_path, 'rb') as f:
            await update.message.reply_document(document=InputFile(f, filename=f'informe_mensual_{mes}_{anio}.txt'),
                                                caption='Aquí está tu informe mensual.')
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al generar informe: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al generar el informe.", reply_markup=create_main_menu_keyboard())
    except IOError as e:
        logger.error(f"Error de archivo al generar informe: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error al crear el archivo de informe.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al generar informe: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al generar el informe.", reply_markup=create_main_menu_keyboard())
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
    return MENU

async def deshacer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [KeyboardButton("🗑️ Deshacer Último Pago"), KeyboardButton("🗑️ Deshacer Último Gasto")],
        [KeyboardButton("⬅️ Volver al Menú")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("¿Qué acción deseas deshacer?", reply_markup=reply_markup)
    return DESHACER_MENU

async def deshacer_pago_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        inquilino, monto = await deshacer_ultimo_pago()
        if inquilino:
            mensaje = f"✅ Último pago de *{md(inquilino)}* por *{md(format_currency(monto))}* ha sido eliminado."
        else:
            mensaje = "No hay pagos para deshacer."
        await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_main_menu_keyboard())
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al deshacer pago: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al deshacer el pago.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al deshacer pago: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al deshacer el pago.", reply_markup=create_main_menu_keyboard())
    return MENU

async def deshacer_gasto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        descripcion, monto = await deshacer_ultimo_gasto()
        if descripcion:
            mensaje = f"✅ Último gasto *{md(descripcion)}* por *{md(format_currency(monto))}* ha sido eliminado."
        else:
            mensaje = "No hay gastos para deshacer."
        await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_main_menu_keyboard())
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al deshacer gasto: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al deshacer el gasto.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al deshacer gasto: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al deshacer el gasto.", reply_markup=create_main_menu_keyboard())
    return MENU

async def volver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operación cancelada.", reply_markup=create_main_menu_keyboard())
    return MENU

async def volver_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text("Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Error: {context.error} - causado por {update}", exc_info=True)
    if update and update.effective_message:
        await update.message.reply_text("❌ Ocurrió un error inesperado.", reply_markup=create_main_menu_keyboard())

def _format_transaction_list(title: str, transactions: list, empty_message: str) -> str:
    """Formats a list of transactions (pagos or gastos) into a string."""
    if not transactions:
        return f"{title}: {empty_message}\n"

    message = f"{title}:\n"
    for i, transaction in enumerate(transactions, 1):
        # transaction is a tuple: (fecha, descripcion/inquilino, monto)
        fecha_dt = datetime.strptime(str(transaction[0]), '%Y-%m-%d').date()
        description = transaction[1]
        amount = transaction[2]
        message += f"{i}. {description}: {format_currency(amount)} ({fecha_dt.strftime('%d/%m/%Y')})\n"
    return message

def format_report(title: str, data: dict) -> str:
    """Formats the monthly report data into a string."""
    mensaje = f"{title}\n\n"

    # Resumen General
    mensaje += "Resumen General:\n"
    mensaje += f"Ingresos Totales: {format_currency(data['total_ingresos'])}\n"
    mensaje += f"Gastos Totales: {format_currency(data['total_gastos'])}\n"
    mensaje += f"Comisión: {format_currency(data['total_comision'])}\n"
    mensaje += f"Monto Neto: {format_currency(data['monto_neto'])}\n\n"

    # Pagos
    pagos = data.get('pagos_mes', [])
    mensaje += _format_transaction_list(
        "Pagos del Mes",
        pagos,
        "No hay pagos registrados para este período."
    )
    mensaje += "\n"

    # Gastos
    gastos = data.get('gastos_mes', [])
    mensaje += _format_transaction_list(
        "Gastos del Mes",
        gastos,
        "No hay gastos registrados para este período."
    )

    return mensaje

def format_summary(data: dict) -> str:
    """Formats the summary data into a string."""
    mensaje = "Resumen General:\n"
    mensaje += f"Ingresos Totales: {format_currency(data['total_ingresos'])}\n"
    mensaje += f"Gastos Totales: {format_currency(data['total_gastos'])}\n"
    mensaje += f"Comisión: {format_currency(data['total_comision'])}\n"
    mensaje += f"Monto Neto: {format_currency(data['monto_neto'])}\n\n"

    # Pagos
    pagos = data.get('ultimos_pagos', [])
    mensaje += _format_transaction_list(
        "Últimos Pagos",
        pagos,
        "No hay pagos recientes."
    )
    mensaje += "\n"

    # Gastos
    gastos = data.get('ultimos_gastos', [])
    mensaje += _format_transaction_list(
        "Últimos Gastos",
        gastos,
        "No hay gastos recientes."
    )

    return mensaje


