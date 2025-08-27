from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import datetime
import logging
from database import (
    registrar_pago, registrar_gasto, obtener_resumen,
    deshacer_ultimo_pago, deshacer_ultimo_gasto,
    obtener_informe_mensual
)
from config import AUTHORIZED_USERS, COMMISSION_RATE

logger = logging.getLogger(__name__)

# === Estados de conversación ===
MENU, PAGO_MONTO, PAGO_NOMBRE, GASTO_MONTO, GASTO_DESC, INFORME_MES, INFORME_ANIO = range(7)

# === Funciones de Handlers ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("❌ No tienes permiso para usar este bot.")
        return ConversationHandler.END

    keyboard = [[ 
        KeyboardButton("📥 Registrar Pago"),
        KeyboardButton("💸 Registrar Gasto")
    ], [
        KeyboardButton("📊 Ver Resumen"),
        KeyboardButton("📄 Generar Informe Mensual")
    ], [
        KeyboardButton("🗑️ Deshacer último registro")
    ]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Bienvenido al sistema de gestión de alquileres. Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def pago_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Escribe el monto del pago recibido (ej: 3000):", reply_markup=reply_markup)
    return PAGO_MONTO

async def pago_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        return await volver(update, context)
        
    try:
        monto = float(texto.replace(',', '').replace('RD$', '').strip())
        context.user_data['pago_monto'] = monto
        
        keyboard = [[KeyboardButton("❌ Cancelar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"Monto registrado: RD${monto:.2f}\nAhora escribe el nombre del inquilino:", reply_markup=reply_markup)
        return PAGO_NOMBRE
    except ValueError:
        await update.message.reply_text("Monto inválido. Intenta de nuevo con un número válido (ej: 3000):")
        return PAGO_MONTO

async def pago_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        return await volver(update, context)
        
    nombre = texto
    monto = context.user_data['pago_monto']
    fecha = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    
    try:
        pago_id = registrar_pago(fecha, nombre, monto)
        context.user_data['ultimo_registro'] = ('pago', pago_id)
        
        await update.message.reply_text(
            f"✅ Pago registrado correctamente:\n"
            f"📅 Fecha: {fecha}\n"
            f"👤 Inquilino: {nombre}\n"
            f"💵 Monto: RD${monto:.2f}", 
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        return MENU
    except Exception as e:
        logger.error(f"Error al registrar pago: {e}")
        await update.message.reply_text("❌ Hubo un error al registrar el pago.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU

async def gasto_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Escribe el monto del gasto (ej: 500):", reply_markup=reply_markup)
    return GASTO_MONTO

async def gasto_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        return await volver(update, context)
        
    try:
        monto = float(texto.replace(',', '').replace('RD$', '').strip())
        context.user_data['gasto_monto'] = monto
        
        keyboard = [[KeyboardButton("❌ Cancelar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"Monto registrado: RD${monto:.2f}\nAhora escribe la descripción del gasto:", reply_markup=reply_markup)
        return GASTO_DESC
    except ValueError:
        await update.message.reply_text("Monto inválido. Intenta de nuevo con un número válido (ej: 500):")
        return GASTO_MONTO

async def gasto_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    
    if texto == "❌ Cancelar":
        return await volver(update, context)
        
    descripcion = texto
    monto = context.user_data['gasto_monto']
    fecha = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    
    try:
        gasto_id = registrar_gasto(fecha, descripcion, monto)
        context.user_data['ultimo_registro'] = ('gasto', gasto_id)
        
        await update.message.reply_text(
            f"✅ Gasto registrado correctamente:\n"
            f"📅 Fecha: {fecha}\n"
            f"📝 Descripción: {descripcion}\n"
            f"💸 Monto: RD${monto:.2f}", 
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        return MENU
    except Exception as e:
        logger.error(f"Error al registrar gasto: {e}")
        await update.message.reply_text("❌ Hubo un error al registrar el gasto.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU

async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        resumen_data = obtener_resumen()
        
        total_ingresos = resumen_data["total_ingresos"]
        total_comision = resumen_data["total_comision"]
        total_gastos = resumen_data["total_gastos"]
        monto_neto = resumen_data["monto_neto"]
        ultimos_pagos = resumen_data["ultimos_pagos"]
        ultimos_gastos = resumen_data["ultimos_gastos"]
        
        comision_label = f"Total Comisión ({COMMISSION_RATE:.0%})"

        mensaje = f"""📊 *RESUMEN DE ALQUILERES*

💰 *Total Ingresos:* RD${float(total_ingresos):.2f}
💼 *{comision_label}:* RD${float(total_comision):.2f}
💸 *Total Gastos:* RD${float(total_gastos):.2f}
🏦 *Monto Neto:* RD${float(monto_neto):.2f}

📥 *Últimos Pagos:*
"""
        if ultimos_pagos:
            for i, pago in enumerate(ultimos_pagos, 1):
                mensaje += f"{i}. {pago[1]}: RD${float(pago[2]):.2f} ({pago[0]})".replace('\n', '\\n') + "\n"
        else:
            mensaje += "No hay pagos registrados\n"

        mensaje += "\n💸 *Últimos Gastos:*
"
        if ultimos_gastos:
            for i, gasto in enumerate(ultimos_gastos, 1):
                mensaje += f"{i}. {gasto[1]}: RD${float(gasto[2]):.2f} ({gasto[0]})".replace('\n', '\\n') + "\n"
        else:
            mensaje += "No hay gastos registrados\n"

        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU
    except Exception as e:
        logger.error(f"Error al generar resumen: {e}")
        await update.message.reply_text("❌ Hubo un error al generar el resumen.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU


async def informe_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Para generar el informe, por favor, escribe el número del mes (1-12):", reply_markup=reply_markup)
    return INFORME_MES

async def informe_mes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    if texto == "❌ Cancelar":
        return await volver(update, context)
    
    try:
        mes = int(texto)
        if not (1 <= mes <= 12):
            raise ValueError("Mes fuera de rango")
        context.user_data['informe_mes'] = mes
        
        keyboard = [[KeyboardButton("❌ Cancelar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Ahora, escribe el año (ej: 2023):", reply_markup=reply_markup)
        return INFORME_ANIO
    except ValueError:
        await update.message.reply_text("Mes inválido. Por favor, introduce un número entre 1 y 12:")
        return INFORME_MES

async def informe_anio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    if texto == "❌ Cancelar":
        return await volver(update, context)
    
    try:
        anio = int(texto)
        if not (2000 <= anio <= datetime.datetime.now().year + 1): # Rango razonable de años
            raise ValueError("Año fuera de rango")
        context.user_data['informe_anio'] = anio
        
        mes = context.user_data['informe_mes']
        
        # Generar informe
        informe_data = obtener_informe_mensual(mes, anio)
        
        mensaje = f"""📊 *INFORME MENSUAL - {mes}/{anio}*\n\n"""
        mensaje += f"💰 *Total Ingresos:* RD${informe_data['total_ingresos']:.2f}\n"
        mensaje += f"💼 *Total Comisión ({COMMISSION_RATE:.0%}):* RD${informe_data['total_comision']:.2f}\n"
        mensaje += f"💸 *Total Gastos:* RD${informe_data['total_gastos']:.2f}\n"
        mensaje += f"🏦 *Monto Neto:* RD${informe_data['monto_neto']:.2f}\n\n"

        mensaje += "📥 *Pagos del Mes:*\n"
        if informe_data['pagos_mes']:
            for i, pago in enumerate(informe_data['pagos_mes'], 1):
                mensaje += f"{i}. {pago[1]}: RD${pago[2]:.2f} ({pago[0].split(' ')[0]})".replace('\n', '\\n') + "\n" # Solo fecha
        else:
            mensaje += "No hay pagos registrados para este mes.\n"

        mensaje += "\n💸 *Gastos del Mes:*\n"
        if informe_data['gastos_mes']:
            for i, gasto in enumerate(informe_data['gastos_mes'], 1):
                mensaje += f"{i}. {gasto[1]}: RD${gasto[2]:.2f} ({gasto[0].split(' ')[0]})".replace('\n', '\\n') + "\n" # Solo fecha
        else:
            mensaje += "No hay gastos registrados para este mes.\n"
        
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU
    except ValueError:
        await update.message.reply_text("Año inválido. Por favor, introduce un año válido (ej: 2023):\n")
        return INFORME_ANIO
    except Exception as e:
        logger.error(f"Error al generar informe mensual: {e}")
        await update.message.reply_text("❌ Hubo un error al generar el informe mensual.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU


async def deshacer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'ultimo_registro' not in context.user_data:
        await update.message.reply_text("No hay ningún registro reciente para deshacer.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU
    
    try:
        tipo, registro_id = context.user_data['ultimo_registro']
        
        if tipo == 'pago':
            deshacer_ultimo_pago(registro_id)
            label_tipo = "Pago"
            # No hay forma de obtener los datos del pago eliminado directamente desde la DB sin una consulta adicional
            # Por ahora, solo confirmamos la eliminación.
            mensaje_confirmacion = f"❌ {label_tipo} eliminado."
        else: # tipo == 'gasto'
            deshacer_ultimo_gasto(registro_id)
            label_tipo = "Gasto"
            mensaje_confirmacion = f"❌ {label_tipo} eliminado."
        
        await update.message.reply_text(
            mensaje_confirmacion, 
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        del context.user_data['ultimo_registro']
        return MENU
    except Exception as e:
        logger.error(f"Error al deshacer registro: {e}")
        await update.message.reply_text("❌ Hubo un error al deshacer el registro.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU

async def volver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
    return MENU

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Error: {context.error} - causado por {update}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ Ocurrió un error inesperado.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))