from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import gspread
from google.oauth2.service_account import Credentials
import datetime
import os
import logging
import time

# Intentar cargar dotenv si está disponible
try:
    from dotenv import load_dotenv
    load_dotenv()  # Carga variables desde .env
    print("Variables de entorno cargadas desde .env")
except ImportError:
    print("Módulo python-dotenv no encontrado. Usando variables de entorno del sistema.")

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Google Sheets Setup ===
try:
    # Ruta al archivo de credenciales
    CREDS_FILE = "creds.json"
    
    # Verificar si existe el archivo de credenciales
    if not os.path.exists(CREDS_FILE):
        logger.error(f"Archivo de credenciales {CREDS_FILE} no encontrado. Revisa la documentación para crear este archivo.")
        exit(1)
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scope)
    client = gspread.authorize(creds)
    
    # Nombre de la hoja de cálculo
    SPREADSHEET_NAME = "Registro de Alquileres"
    
    # Intentar abrir la hoja de cálculo
    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
        logger.info(f"Conexión exitosa a la hoja de cálculo: {SPREADSHEET_NAME}")
        
        # Obtener las hojas
        sheet_pagos = spreadsheet.worksheet("Pagos")
        sheet_gastos = spreadsheet.worksheet("Gastos")
        
        # Verificar si las hojas tienen los encabezados correctos
        pagos_headers = sheet_pagos.row_values(1)
        gastos_headers = sheet_gastos.row_values(1)
        
        # Si no hay encabezados, agregarlos
        if not pagos_headers:
            sheet_pagos.append_row(["Fecha", "Inquilino", "Monto"])
            logger.info("Encabezados añadidos a la hoja Pagos")
        
        if not gastos_headers:
            sheet_gastos.append_row(["Fecha", "Descripción", "Monto"])
            logger.info("Encabezados añadidos a la hoja Gastos")
            
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"No se encontró la hoja de cálculo: {SPREADSHEET_NAME}. Asegúrate de haberla creado y compartido con la cuenta de servicio.")
        exit(1)
    except gspread.exceptions.WorksheetNotFound as e:
        logger.error(f"No se encontró alguna de las hojas necesarias: {e}. Asegúrate de que existan las hojas 'Pagos' y 'Gastos'.")
        exit(1)
        
except Exception as e:
    logger.error(f"Error al configurar Google Sheets: {e}")
    exit(1)

# Verificar si existe la hoja Resumen
try:
    sheet_resumen = spreadsheet.worksheet("Resumen")
    logger.info("Hoja Resumen encontrada")
    
    # Verificar si la hoja Resumen tiene los encabezados correctos
    resumen_headers = sheet_resumen.row_values(1)
    
    # Si no hay encabezados o no son los correctos, configurar la hoja
    if not resumen_headers or "Concepto" not in resumen_headers:
        # Configurar encabezados
        sheet_resumen.update('A1:B1', [["Concepto", "Monto"]])
        
        # Configurar filas principales
        sheet_resumen.update('A2:A5', [
            ["Total Ingresos"], 
            ["Total Comisión (5%)"], 
            ["Total Gastos"], 
            ["Monto Neto"]
        ])
        
        # Inicializar con valores cero
        sheet_resumen.update('B2:B5', [["RD$0.00"], ["RD$0.00"], ["RD$0.00"], ["RD$0.00"]])
        
        logger.info("Hoja Resumen configurada con estructura inicial")
    
except gspread.exceptions.WorksheetNotFound:
    # Crear la hoja Resumen si no existe
    sheet_resumen = spreadsheet.add_worksheet(title="Resumen", rows=100, cols=20)
    logger.info("Hoja Resumen creada")
    
    # Configurar encabezados
    sheet_resumen.update('A1:B1', [["Concepto", "Monto"]])
    
    # Configurar filas principales
    sheet_resumen.update('A2:A5', [
        ["Total Ingresos"], 
        ["Total Comisión (5%)"], 
        ["Total Gastos"], 
        ["Monto Neto"]
    ])
    
    # Inicializar con valores cero
    sheet_resumen.update('B2:B5', [["RD$0.00"], ["RD$0.00"], ["RD$0.00"], ["RD$0.00"]])
    
    logger.info("Hoja Resumen configurada con estructura inicial")

# === Estados de conversación ===
MENU, PAGO_MONTO, PAGO_NOMBRE, GASTO_MONTO, GASTO_DESC = range(5)

# === Estado temporal ===
ultimo_registro = {}

# === Funciones ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

# === Flujo de Pago ===
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
        # Convertir texto a número y manejar diferentes formatos (con comas, puntos, etc.)
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
        # Agregar el registro a la hoja de cálculo
        sheet_pagos.append_row([fecha, nombre, monto])
        
        # Guardar referencia al último registro para poder deshacerlo
        ultimo_registro[update.effective_user.id] = ('pago', len(sheet_pagos.get_all_values()))
        
        # Actualizar resumen
        await actualizar_resumen()
        
        # Confirmar al usuario
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
        await update.message.reply_text(
            "❌ Hubo un error al registrar el pago. Inténtalo de nuevo más tarde.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        return MENU

# === Flujo de Gasto ===
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
        # Convertir texto a número y manejar diferentes formatos
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
        # Agregar el registro a la hoja de cálculo
        sheet_gastos.append_row([fecha, descripcion, monto])
        
        # Guardar referencia al último registro para poder deshacerlo
        ultimo_registro[update.effective_user.id] = ('gasto', len(sheet_gastos.get_all_values()))
        
        # Actualizar resumen
        await actualizar_resumen()
        
        # Confirmar al usuario
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
        await update.message.reply_text(
            "❌ Hubo un error al registrar el gasto. Inténtalo de nuevo más tarde.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        return MENU

# === Ver Resumen ===
async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        # Actualizar resumen primero para asegurar datos actualizados
        await actualizar_resumen()
        
        # Obtener datos actualizados
        datos_resumen = sheet_resumen.get_all_values()
        
        # Extraer datos del resumen
        total_ingresos = "0.00"
        total_comision = "0.00"
        total_gastos = "0.00"
        monto_neto = "0.00"
        
        for fila in datos_resumen:
            if len(fila) >= 2:
                if fila[0].strip() == "Total Ingresos":
                    total_ingresos = fila[1].replace("RD$", "").replace(",", "").strip()
                elif fila[0].strip() == "Total Comisión (5%)":
                    total_comision = fila[1].replace("RD$", "").replace(",", "").strip()
                elif fila[0].strip() == "Total Gastos":
                    total_gastos = fila[1].replace("RD$", "").replace(",", "").strip()
                elif fila[0].strip() == "Monto Neto":
                    monto_neto = fila[1].replace("RD$", "").replace(",", "").strip()
        
        # Convertir a números
        try:
            total_ingresos = float(total_ingresos)
            total_comision = float(total_comision)
            total_gastos = float(total_gastos)
            monto_neto = float(monto_neto)
        except ValueError as e:
            logger.error(f"Error al convertir valores a números: {e}")
            total_ingresos = 0.0
            total_comision = 0.0
            total_gastos = 0.0
            monto_neto = 0.0
        
        # Obtener últimos pagos y gastos
        pagos_datos = sheet_pagos.get_all_values()[1:] if len(sheet_pagos.get_all_values()) > 1 else []
        gastos_datos = sheet_gastos.get_all_values()[1:] if len(sheet_gastos.get_all_values()) > 1 else []
        
        # Últimos 3 pagos (más reciente primero)
        ultimos_pagos = pagos_datos[-3:][::-1] if pagos_datos else []
        
        # Últimos 3 gastos (más reciente primero)
        ultimos_gastos = gastos_datos[-3:][::-1] if gastos_datos else []
        
        # Preparar mensaje de resumen
        mensaje = "📊 *RESUMEN DE ALQUILERES*\n\n"
        mensaje += f"💰 *Total Ingresos:* RD${total_ingresos:.2f}\n"
        mensaje += f"💼 *Total Comisión:* RD${total_comision:.2f}\n"
        mensaje += f"💸 *Total Gastos:* RD${total_gastos:.2f}\n"
        mensaje += f"🏦 *Monto Neto:* RD${monto_neto:.2f}\n\n"
        
        # Agregar últimos pagos
        mensaje += "📥 *Últimos Pagos:*\n"
        if ultimos_pagos:
            for i, pago in enumerate(ultimos_pagos, 1):
                try:
                    fecha = pago[0] if len(pago) > 0 else "N/A"
                    inquilino = pago[1] if len(pago) > 1 else "N/A"
                    monto = float(pago[2].replace(',', '').strip()) if len(pago) > 2 and pago[2].strip() else 0.0
                    mensaje += f"{i}. {inquilino}: RD${monto:.2f} ({fecha})\n"
                except Exception as e:
                    logger.error(f"Error procesando pago {i}: {e}")
                    mensaje += f"{i}. Error mostrando pago\n"
        else:
            mensaje += "No hay pagos registrados\n"
        
        mensaje += "\n💸 *Últimos Gastos:*\n"
        if ultimos_gastos:
            for i, gasto in enumerate(ultimos_gastos, 1):
                try:
                    fecha = gasto[0] if len(gasto) > 0 else "N/A"
                    desc = gasto[1] if len(gasto) > 1 else "N/A"
                    monto = float(gasto[2].replace(',', '').strip()) if len(gasto) > 2 and gasto[2].strip() else 0.0
                    mensaje += f"{i}. {desc}: RD${monto:.2f} ({fecha})\n"
                except Exception as e:
                    logger.error(f"Error procesando gasto {i}: {e}")
                    mensaje += f"{i}. Error mostrando gasto\n"
        else:
            mensaje += "No hay gastos registrados\n"
        
        # Enviar mensaje
        try:
            await update.message.reply_text(
                mensaje,
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
            )
        except Exception as e:
            logger.error(f"Error con Markdown, intentando sin formato: {e}")
            await update.message.reply_text(
                mensaje.replace("*", ""),
                reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
            )
        
        return MENU
    except Exception as e:
        logger.error(f"Error al generar resumen: {e}")
        await update.message.reply_text(
            "❌ Hubo un error al generar el resumen. Inténtalo de nuevo más tarde.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        return MENU

# === Deshacer ===
async def deshacer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    if user_id not in ultimo_registro:
        await update.message.reply_text("No hay ningún registro reciente para deshacer.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
        return MENU
    
    try:
        tipo, fila = ultimo_registro[user_id]
        
        if tipo == 'pago':
            # Obtener detalles del pago antes de eliminarlo
            datos_pago = sheet_pagos.row_values(fila)
            sheet_pagos.delete_rows(fila)
            
            # Actualizar resumen
            await actualizar_resumen()
            
            await update.message.reply_text(
                f"❌ Pago eliminado:\n👤 {datos_pago[1]}: RD${float(datos_pago[2]):.2f}", 
                reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
            )
        else:
            # Obtener detalles del gasto antes de eliminarlo
            datos_gasto = sheet_gastos.row_values(fila)
            sheet_gastos.delete_rows(fila)
            
            # Actualizar resumen
            await actualizar_resumen()
            
            await update.message.reply_text(
                f"❌ Gasto eliminado:\n📝 {datos_gasto[1]}: RD${float(datos_gasto[2]):.2f}", 
                reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
            )
        
        del ultimo_registro[user_id]
        return MENU
    except Exception as e:
        logger.error(f"Error al deshacer registro: {e}")
        await update.message.reply_text(
            "❌ Hubo un error al deshacer el registro. Inténtalo de nuevo más tarde.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )
        return MENU

# === Volver al menú ===
async def volver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await start(update, context)

# === Cancelar ===
async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True))
    return MENU

# === Actualizar Resumen ===
async def actualizar_resumen():
    """Actualiza la hoja Resumen basado en los datos de Pagos y Gastos"""
    try:
        # Pequeño retraso para evitar límites de tasa
        time.sleep(1)
        
        # Obtener todos los datos de pagos y gastos (excluyendo la fila de encabezados)
        pagos_datos = sheet_pagos.get_all_values()[1:] if len(sheet_pagos.get_all_values()) > 1 else []
        gastos_datos = sheet_gastos.get_all_values()[1:] if len(sheet_gastos.get_all_values()) > 1 else []
        
        # Calcular totales con manejo de errores
        total_pagos = 0.0
        for fila in pagos_datos:
            if len(fila) >= 3 and fila[2].strip():
                try:
                    total_pagos += float(fila[2].replace(',', '').replace('RD$', '').strip())
                except ValueError:
                    logger.warning(f"Valor no numérico en pagos: {fila[2]}")
        
        total_gastos = 0.0
        for fila in gastos_datos:
            if len(fila) >= 3 and fila[2].strip():
                try:
                    total_gastos += float(fila[2].replace(',', '').replace('RD$', '').strip())
                except ValueError:
                    logger.warning(f"Valor no numérico en gastos: {fila[2]}")
        
        # Calcular comisión y neto
        total_comision = total_pagos * 0.05  # 5% de comisión
        monto_neto = total_pagos - total_comision - total_gastos
        
        # Pequeño retraso antes de actualizar
        time.sleep(1)
        
        # Actualizar la hoja Resumen con formato RD$
        sheet_resumen.update('B2:B5', [
            [f"RD${total_pagos:.2f}"],
            [f"RD${total_comision:.2f}"],
            [f"RD${total_gastos:.2f}"],
            [f"RD${monto_neto:.2f}"]
        ])
        
        logger.info("Hoja Resumen actualizada correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al actualizar la hoja Resumen: {e}")
        
        return False

# === Manejar errores ===
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Error: {context.error} - causado por {update}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Por favor, intenta de nuevo más tarde.",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Volver al menú"]], resize_keyboard=True)
        )

# === Main ===
def main():
    # Obtener el token del bot desde variable de entorno
    TOKEN = os.getenv("BOT_TOKEN")
    
    # Verificar si el token es válido
    if not TOKEN:
        print("\n" + "="*50)
        print("ERROR: No se encontró el token del bot.")
        print("Tienes varias opciones para configurarlo:")
        print("1. Edita este archivo y descomenta la OPCIÓN 1, reemplazando con tu token")
        print("2. Crea un archivo .env con BOT_TOKEN=tu_token")
        print("3. Define la variable de entorno BOT_TOKEN antes de ejecutar")
        print("="*50 + "\n")
        exit(1)
    
    try:
        # Crear la aplicación
        app = Application.builder().token(TOKEN).build()
        
        # Agregar manejador de conversación
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                MENU: [
                    MessageHandler(filters.Regex("^📥 Registrar Pago$"), pago_inicio),
                    MessageHandler(filters.Regex("^💸 Registrar Gasto$"), gasto_inicio),
                    MessageHandler(filters.Regex("^📊 Ver Resumen$"), ver_resumen),
                    MessageHandler(filters.Regex("^🗑️ Deshacer último registro$"), deshacer),
                    MessageHandler(filters.Regex("^⬅️ Volver al menú$"), volver),
                ],
                PAGO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_monto)],
                PAGO_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_nombre)],
                GASTO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_monto)],
                GASTO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_desc)]
            },
            fallbacks=[
                CommandHandler("cancel", cancelar),
                MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar)
            ]
        )
        
        app.add_handler(conv_handler)
        
        # Agregar manejador de errores
        app.add_error_handler(error_handler)
        
        # Iniciar el bot
        print("\n" + "="*50)
        print("Bot iniciado correctamente!")
        print("Inicia una conversación con tu bot en Telegram")
        print("Presiona Ctrl+C para detener")
        print("="*50 + "\n")
        app.run_polling()
        
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")

if __name__ == '__main__':
    main()