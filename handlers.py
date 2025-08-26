from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import datetime
import logging
from sheets import (
    sheet_pagos, sheet_gastos, sheet_resumen,
    actualizar_resumen
)
from config import AUTHORIZED_USERS, COMMISSION_RATE

logger = logging.getLogger(__name__)

# === Estados de conversación ===
MENU, PAGO_MONTO, PAGO_NOMBRE, GASTO_MONTO, GASTO_DESC = range(5)

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
        sheet_pagos.append_row([fecha, nombre, monto])
        context.user_data['ultimo_registro'] = ('pago', len(sheet_pagos.get_all_values()))
        await actualizar_resumen()
        
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
        sheet_gastos.append_row([fecha, descripcion, monto])
        context.user_data['ultimo_registro'] = ('gasto', len(sheet_gastos.get_all_values()))
        await actualizar_resumen()
        
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
        await actualizar_resumen()
        datos_resumen = sheet_resumen.get_all_values()
        
        total_ingresos, total_comision, total_gastos, monto_neto = "0.00", "0.00", "0.00", "0.00"
        comision_label = f"Total Comisión ({COMMISSION_RATE:.0%})"
        
        for fila in datos_resumen:
            if len(fila) >= 2:
                if fila[0].strip() == "Total Ingresos":
                    total_ingresos = fila[1].replace("RD$", "").replace(",", "").strip()
                elif comision_label in fila[0]:
                    total_comision = fila[1].replace("RD$", "").replace(",", "").strip()
                elif fila[0].strip() == "Total Gastos":
                    total_gastos = fila[1].replace("RD$", "").replace(",", "").strip()
                elif fila[0].strip() == "Monto Neto":
                    monto_neto = fila[1].replace("RD$", "").replace(",", "").strip()

        pagos_datos = sheet_pagos.get_all_values()[1:]
        gastos_datos = sheet_gastos.get_all_values()[1:]
        ultimos_pagos = pagos_datos[-3:][::-1]
        ultimos_gastos = gastos_datos[-3:][::-1]

        mensaje = f"📊 *RESUMEN DE ALQUILERES*\n\n"
        mensaje += f"💰 *Total Ingresos:* RD${float(total_ingresos):.2f}\n"
        mensaje += f"💼 *{comision_label}:* RD${float(total_comision):.2f}\n"
        mensaje += f"💸 *Total Gastos:* RD${float(total_gastos):.2f}\n"
        mensaje += f"🏦 *Monto Neto:* RD${float(monto_neto):.2f}\n\n"

        mensaje += "📥 *Últimos Pagos:*
"
        if ultimos_pagos:
            for i, pago in enumerate(ultimos_pagos, 1):
                mensaje += f"{i}. {pago[1]}: RD${float(pago[2]):.2f} ({pago[0]})
"
        else:
            mensaje += "No hay pagos registrados\n"

        mensaje += "\n💸 *Últimos Gastos:*
"
        if ultimos_gastos:
            for i, gasto in enumerate(ultimos_gastos, 1):
                mensaje += f"{i}. {gasto[1]}: RD${float(gasto[2]):.2f} ({gasto[0]})
"
        else:
            mensaje += "No hay gastos registrados\n"

        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU
    except Exception as e:
        logger.error(f"Error al generar resumen: {e}")
        await update.message.reply_text("❌ Hubo un error al generar el resumen.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU

async def deshacer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'ultimo_registro' not in context.user_data:
        await update.message.reply_text("No hay ningún registro reciente para deshacer.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU
    
    try:
        tipo, fila = context.user_data['ultimo_registro']
        sheet = sheet_pagos if tipo == 'pago' else sheet_gastos
        datos = sheet.row_values(fila)
        sheet.delete_rows(fila)
        await actualizar_resumen()
        
        label_tipo = "Pago" if tipo == 'pago' else "Gasto"
        await update.message.reply_text(
            f"❌ {label_tipo} eliminado:\n{datos[1]}: RD${float(datos[2]):.2f}", 
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