from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import ContextTypes, ConversationHandler
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
    actualizar_dia_pago_inquilino, obtener_inquilinos_para_recordatorio
)
from config import AUTHORIZED_USERS
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
    ASIGNAR_DIA_PAGO_SELECT_INQUILINO, ASIGNAR_DIA_PAGO_SELECT_DIA
) = range(20)

# === Helpers ===
def format_currency(value: float) -> str:
    try:
        # Use non-locale-dependent formatting to avoid thousands separators and potential parentheses.
        return f"RD${Decimal(value):.2f}"
    except (InvalidOperation, TypeError):
        return "RD$0.00"

def md(text: str) -> str:
    return escape_markdown(str(text), version=2)

def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("📥 Registrar Pago"), KeyboardButton("💸 Registrar Gasto")],
        [KeyboardButton("👤 Gestionar Inquilinos"), KeyboardButton("✏️ Editar/Borrar")],
        [KeyboardButton("📊 Ver Resumen"), KeyboardButton("📈 Generar Informe")],
        [KeyboardButton("🗑️ Deshacer")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def create_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True)

async def _save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, tipo: str):
    """Función genérica para guardar una transacción (pago o gasto) y manejar errores."""
    try:
        monto = context.user_data['monto']
        detalle = context.user_data['detalle']
        fecha = date.today()

        if tipo == 'pago':
            await registrar_pago(fecha, detalle, monto)
            mensaje = (
                f"✅ Pago registrado correctamente:\n"
                f"📅 Fecha: {fecha.strftime('%d/%m/%Y')}\n"
                f"👤 Inquilino: {md(detalle)}\n"
                f"💵 Monto: {md(format_currency(monto))}"
            )
        elif tipo == 'gasto':
            await registrar_gasto(fecha, detalle, monto)
            mensaje = (
                f"✅ Gasto registrado correctamente:\n"
                f"📅 Fecha: {fecha.strftime('%d/%m/%Y')}\n"
                f"📝 Descripción: {md(detalle)}\n"
                f"💸 Monto: {md(format_currency(monto))}"
            )
        else:
            return # No debería ocurrir

        await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_main_menu_keyboard())

    except UniqueViolation:
        await update.message.reply_text(
            f"❌ Ya existe un pago registrado para *{md(detalle)}* en la fecha de hoy\\. Si quieres modificarlo, usa la opción 'Deshacer'.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=create_main_menu_keyboard()
        )
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al registrar {tipo}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Hubo un error con la base de datos al registrar el {tipo}.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al registrar {tipo}: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Hubo un error inesperado al registrar el {tipo}.", reply_markup=create_main_menu_keyboard())
    finally:
        context.user_data.clear()

# === Handlers Principales ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in AUTHORIZED_USERS:
        await update.message.reply_text("❌ No tienes permiso para usar este bot.")
        return ConversationHandler.END

    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text("Bienvenido al sistema de gestión de alquileres. Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def volver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Operación cancelada. Volviendo al menú principal.", reply_markup=create_main_menu_keyboard())
    return MENU

# === Flujo Registrar Pago ===
async def pago_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

async def pago_select_inquilino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['detalle'] = update.message.text
    await update.message.reply_text(f"Inquilino seleccionado: {update.message.text}. Ahora, escribe el monto del pago:", reply_markup=create_cancel_keyboard())
    return PAGO_MONTO

async def pago_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    try:
        monto = Decimal(texto.replace(",", "").replace("RD$", "").strip())
        context.user_data['monto'] = monto
        await _save_transaction(update, context, 'pago')
        return MENU
    except InvalidOperation:
        await update.message.reply_text("Monto inválido. Intenta de nuevo con un número válido (ej: 3000):")
        return PAGO_MONTO

# === Flujo Registrar Gasto ===
async def gasto_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Escribe el monto del gasto (ej: 500):", reply_markup=create_cancel_keyboard())
    return GASTO_MONTO

async def gasto_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    try:
        monto = Decimal(texto.replace(",", "").replace("RD$", "").strip())
        context.user_data['monto'] = monto
        await update.message.reply_text(f"Monto registrado: {format_currency(monto)}\nAhora escribe la descripción del gasto:", reply_markup=create_cancel_keyboard())
        return GASTO_DESC
    except InvalidOperation:
        await update.message.reply_text("Monto inválido. Intenta de nuevo con un número válido (ej: 500):")
        return GASTO_MONTO

async def gasto_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['detalle'] = update.message.text.strip()
    await _save_transaction(update, context, 'gasto')
    return MENU

# === Flujo Gestionar Inquilinos ===
def create_inquilinos_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton("➕ Añadir Inquilino"), KeyboardButton("📋 Listar Inquilinos")],
        [KeyboardButton("📅 Asignar Día de Pago")],
        [KeyboardButton("❌ Desactivar Inquilino"), KeyboardButton("✅ Activar Inquilino")],
        [KeyboardButton("⬅️ Volver al Menú Principal")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def gestionar_inquilinos_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Selecciona una opción para gestionar los inquilinos:", reply_markup=create_inquilinos_menu_keyboard())
    return INQUILINO_MENU

async def add_inquilino_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Escribe el nombre completo del nuevo inquilino:", reply_markup=create_cancel_keyboard())
    return INQUILINO_ADD_NOMBRE

async def add_inquilino_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nombre = update.message.text.strip()
    try:
        await crear_inquilino(nombre)
        await update.message.reply_text(f"✅ Inquilino '{nombre}' añadido correctamente.", reply_markup=create_inquilinos_menu_keyboard())
    except UniqueViolation:
        await update.message.reply_text(f"❌ El inquilino '{nombre}' ya existe.", reply_markup=create_inquilinos_menu_keyboard())
    except psycopg2.Error as e:
        logger.error(f"Error de DB al añadir inquilino: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos.", reply_markup=create_inquilinos_menu_keyboard())
    return INQUILINO_MENU

async def list_inquilinos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Assuming obtener_inquilinos will be modified to return dia_pago
    inquilinos = await obtener_inquilinos(activos_only=False)
    if not inquilinos:
        mensaje = "No hay inquilinos registrados."
    else:
        mensaje = "Lista de Inquilinos:\n"
        for _, nombre, activo, dia_pago in inquilinos:
            estado = "✅ Activo" if activo else "❌ Inactivo"
            dia_pago_str = f"Día de pago: {dia_pago}" if dia_pago else "Día de pago: Sin asignar"
            mensaje += f"\\- {md(nombre)} \\({md(estado)}\\) \\- {md(dia_pago_str)}\n"
    
    await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_inquilinos_menu_keyboard())
    return INQUILINO_MENU

async def deactivate_inquilino_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inquilinos = await obtener_inquilinos(activos_only=True)
    if not inquilinos:
        await update.message.reply_text("No hay inquilinos activos para desactivar.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU
    
    context.user_data['inquilinos_list'] = {i[1]: i[0] for i in inquilinos}
    keyboard = [[KeyboardButton(inquilino[1])] for inquilino in inquilinos]
    keyboard.append([KeyboardButton("❌ Cancelar")])
    
    await update.message.reply_text("Selecciona el inquilino que quieres desactivar:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return INQUILINO_DEACTIVATE_SELECT

async def deactivate_inquilino_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nombre = update.message.text.strip()
    inquilino_id = context.user_data.get('inquilinos_list', {}).get(nombre)

    if not inquilino_id:
        await update.message.reply_text("Selección inválida. Por favor, usa el teclado.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

    await cambiar_estado_inquilino(inquilino_id, False)
    await update.message.reply_text(f"Inquilino '{nombre}' ha sido desactivado.", reply_markup=create_inquilinos_menu_keyboard())
    context.user_data.clear()
    return INQUILINO_MENU

async def activate_inquilino_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inquilinos = await obtener_inquilinos(activos_only=False)
    inquilinos_inactivos = [i for i in inquilinos if not i[2]]

    if not inquilinos_inactivos:
        await update.message.reply_text("No hay inquilinos inactivos para activar.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

    context.user_data['inquilinos_list'] = {i[1]: i[0] for i in inquilinos_inactivos}
    keyboard = [[KeyboardButton(i[1])] for i in inquilinos_inactivos]
    keyboard.append([KeyboardButton("❌ Cancelar")])

    await update.message.reply_text("Selecciona el inquilino que quieres activar:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return INQUILINO_ACTIVATE_SELECT

async def activate_inquilino_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nombre = update.message.text.strip()
    inquilino_id = context.user_data.get('inquilinos_list', {}).get(nombre)

    if not inquilino_id:
        await update.message.reply_text("Selección inválida. Por favor, usa el teclado.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

    await cambiar_estado_inquilino(inquilino_id, True)
    await update.message.reply_text(f"Inquilino '{nombre}' ha sido activado.", reply_markup=create_inquilinos_menu_keyboard())
    context.user_data.clear()
    return INQUILINO_MENU

# === Flujo Asignar Día de Pago ===
async def asignar_dia_pago_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    inquilinos = await obtener_inquilinos(activos_only=True)
    if not inquilinos:
        await update.message.reply_text("No hay inquilinos activos.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

    context.user_data['inquilinos_dia_pago_map'] = {i[1]: i[0] for i in inquilinos}
    keyboard_buttons = []
    for _, nombre, _, dia_pago in inquilinos:
        texto_boton = f"{nombre} (Día: {dia_pago or 'N/A'})"
        keyboard_buttons.append([KeyboardButton(texto_boton)])
    
    keyboard_buttons.append([KeyboardButton("❌ Cancelar")])
    reply_markup = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True)
    
    await update.message.reply_text("Selecciona un inquilino para asignarle o cambiarle el día de pago:", reply_markup=reply_markup)
    return ASIGNAR_DIA_PAGO_SELECT_INQUILINO

async def asignar_dia_pago_select_inquilino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Extraer el nombre del texto del botón, que puede tener '(Día: ...)'
    nombre_inquilino = update.message.text.split(' (')[0]
    
    inquilino_id = context.user_data.get('inquilinos_dia_pago_map', {}).get(nombre_inquilino)
    if not inquilino_id:
        await update.message.reply_text("No se pudo encontrar el inquilino. Por favor, intenta de nuevo.", reply_markup=create_inquilinos_menu_keyboard())
        context.user_data.clear()
        return INQUILINO_MENU

    context.user_data['selected_inquilino_id'] = inquilino_id
    context.user_data['selected_inquilino_nombre'] = nombre_inquilino

    await update.message.reply_text(f"Introduce el día del mes (1-31) para el pago de {md(nombre_inquilino)}:", reply_markup=create_cancel_keyboard(), parse_mode=ParseMode.MARKDOWN_V2)
    return ASIGNAR_DIA_PAGO_SELECT_DIA

async def asignar_dia_pago_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        dia_pago = int(update.message.text.strip())
        if not 1 <= dia_pago <= 31:
            await update.message.reply_text("Día inválido. Por favor, introduce un número del 1 al 31.")
            return ASIGNAR_DIA_PAGO_SELECT_DIA

        inquilino_id = context.user_data['selected_inquilino_id']
        nombre_inquilino = context.user_data['selected_inquilino_nombre']

        await actualizar_dia_pago_inquilino(inquilino_id, dia_pago)

        await update.message.reply_text(f"✅ Se asignó el día de pago {dia_pago} para {md(nombre_inquilino)}.", reply_markup=create_inquilinos_menu_keyboard(), parse_mode=ParseMode.MARKDOWN_V2)
        context.user_data.clear()
        return INQUILINO_MENU

    except (ValueError, KeyError):
        await update.message.reply_text("Entrada inválida. Por favor, introduce un número del 1 al 31.")
        return ASIGNAR_DIA_PAGO_SELECT_DIA

# === Flujo Editar/Borrar ===
async def editar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [KeyboardButton("Mes Actual")],
        [KeyboardButton("Elegir Mes y Año")],
        [KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("¿De qué período quieres editar o borrar una transacción?", reply_markup=reply_markup)
    return EDITAR_INICIO

async def editar_mes_actual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    hoy = date.today()
    return await editar_listar_transacciones(update, context, hoy.month, hoy.year)

async def editar_pedir_mes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Por favor, introduce el número del mes (1-12):", reply_markup=create_cancel_keyboard())
    return EDITAR_PEDIR_ANIO

async def editar_pedir_anio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        mes = int(update.message.text.strip())
        if not 1 <= mes <= 12:
            await update.message.reply_text("Mes inválido. Por favor, introduce un número del 1 al 12.")
            return EDITAR_PEDIR_ANIO
        context.user_data['edit_month'] = mes
        await update.message.reply_text("Ahora, introduce el año (ej: 2023):", reply_markup=create_cancel_keyboard())
        return EDITAR_PEDIR_MES
    except ValueError:
        await update.message.reply_text("Entrada inválida. Por favor, introduce un número para el mes.")
        return EDITAR_PEDIR_ANIO

async def editar_listar_transacciones_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        anio = int(update.message.text.strip())
        if not 1900 < anio < 2100:
            await update.message.reply_text("Año inválido. Por favor, introduce un año válido (ej: 2023).")
            return EDITAR_PEDIR_MES

        mes = context.user_data.get('edit_month')
        return await editar_listar_transacciones(update, context, mes, anio)
    except (ValueError, KeyError):
        await update.message.reply_text("Año inválido. Por favor, introduce un número para el año (ej: 2023).")
        return EDITAR_PEDIR_MES

async def editar_listar_transacciones(update: Update, context: ContextTypes.DEFAULT_TYPE, mes: int, anio: int) -> int:
    report_data = await obtener_informe_mensual(mes, anio)
    pagos = report_data.get('pagos_mes', [])
    gastos = report_data.get('gastos_mes', [])

    if not pagos and not gastos:
        await update.message.reply_text("No hay transacciones registradas para este período.", reply_markup=create_main_menu_keyboard())
        return MENU

    mensaje = f"Transacciones para {mes}/{anio}:\n\n"
    transactions_map = {}
    
    if pagos:
        mensaje += "*Pagos*\n"
        for i, (p_id, p_fecha_str, p_inquilino, p_monto) in enumerate(pagos, 1):
            code = f"P{i}"
            transactions_map[code] = {"id": p_id, "tipo": "pago"}
            p_fecha = p_fecha_str if hasattr(p_fecha_str, 'strftime') else datetime.strptime(str(p_fecha_str), '%Y-%m-%d').date()
            mensaje += f"`{code}`: {md(p_inquilino)} \\- {md(format_currency(p_monto))} el {p_fecha.strftime('%d/%m')}\n"
    
    if gastos:
        mensaje += "\n*Gastos*\n"
        for i, (g_id, g_fecha_str, g_desc, g_monto) in enumerate(gastos, 1):
            code = f"G{i}"
            transactions_map[code] = {"id": g_id, "tipo": "gasto"}
            g_fecha = g_fecha_str if hasattr(g_fecha_str, 'strftime') else datetime.strptime(str(g_fecha_str), '%Y-%m-%d').date()
            mensaje += f"`{code}`: {md(g_desc)} \\- {md(format_currency(g_monto))} el {g_fecha.strftime('%d/%m')}\n"

    context.user_data['transactions_map'] = transactions_map
    mensaje += "\nEscribe el código de la transacción que quieres borrar \(ej: P1 o G2\)"
    
    await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_cancel_keyboard())
    return EDITAR_SELECCIONAR_TRANSACCION

async def editar_seleccionar_transaccion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.upper().strip()
    transactions_map = context.user_data.get('transactions_map', {})

    if code not in transactions_map:
        await update.message.reply_text("Código inválido. Por favor, introduce un código de la lista (ej: P1).", reply_markup=create_cancel_keyboard())
        return EDITAR_SELECCIONAR_TRANSACCION

    transaction = transactions_map[code]
    context.user_data['selected_transaction'] = transaction

    keyboard = [[KeyboardButton("Sí, borrar")], [KeyboardButton("No, cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(f"¿Estás seguro de que quieres borrar la transacción `{md(code)}`? Esta acción no se puede deshacer.", parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
    return EDITAR_CONFIRMAR_BORRADO

async def editar_ejecutar_borrado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text != "Sí, borrar":
        await update.message.reply_text("Borrado cancelado.", reply_markup=create_main_menu_keyboard())
        context.user_data.clear()
        return MENU

    transaction = context.user_data.get('selected_transaction')
    if not transaction:
        await update.message.reply_text("Error, no se encontró la transacción seleccionada. Volviendo al menú.", reply_markup=create_main_menu_keyboard())
        context.user_data.clear()
        return MENU

    success = False
    if transaction['tipo'] == 'pago':
        success = await delete_pago_by_id(transaction['id'])
    elif transaction['tipo'] == 'gasto':
        success = await delete_gasto_by_id(transaction['id'])

    if success:
        await update.message.reply_text("✅ Transacción borrada correctamente.", reply_markup=create_main_menu_keyboard())
    else:
        await update.message.reply_text("❌ No se pudo borrar la transacción.", reply_markup=create_main_menu_keyboard())
    
    context.user_data.clear()
    return MENU

# === Tarea Automática de Recordatorios ===
async def enviar_recordatorios_pago(context: ContextTypes.DEFAULT_TYPE):
    """Envía recordatorios de pago para inquilinos cuya fecha de pago se acerca."""
    # Usamos el primer usuario autorizado como destinatario de las notificaciones
    if not AUTHORIZED_USERS:
        logger.warning("No hay usuarios autorizados para enviar recordatorios.")
        return
    chat_id = AUTHORIZED_USERS[0]

    try:
        inquilinos_a_notificar = await obtener_inquilinos_para_recordatorio()

        if inquilinos_a_notificar:
            fecha_recordatorio = date.today() + timedelta(days=2)
            dia_vencimiento = fecha_recordatorio.day

            mensaje = f"🔔 *Recordatorio de Pagos Próximos* 🔔\n\n"
            mensaje += f"Los siguientes inquilinos tienen pagos que vencen en 2 días \(el día {dia_vencimiento}\) y aún no han pagado este mes:\n\n"
            for nombre in inquilinos_a_notificar:
                mensaje += f"\- {md(nombre)}\n"
            
            await context.bot.send_message(chat_id=chat_id, text=mensaje, parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Recordatorios de pago enviados a {chat_id} para: {', '.join(inquilinos_a_notificar)}")

    except Exception as e:
        logger.error(f"Error en la tarea de enviar recordatorios: {e}", exc_info=True)
        # Notificar al admin sobre el error en la tarea
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"Ocurrió un error en la tarea de recordatorios: {md(str(e))}")
        except Exception as send_e:
            logger.error(f"No se pudo notificar al admin sobre el error en la tarea de recordatorios: {send_e}", exc_info=True)

# === Otros Handlers ===
async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    temp_file_path = None
    try:
        resumen_data = await obtener_resumen()
        mensaje = format_summary(resumen_data)
        
        # Si el mensaje es corto, mostrarlo directamente. Si es largo, enviarlo como archivo.
        if len(mensaje) < 3000:
            # Usamos un bloque de código para preservar el formato.
            # El texto dentro de ``` no necesita ser escapado.
            await update.message.reply_text(
                f"```\n{mensaje}```", 
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=create_main_menu_keyboard()
            )
        else:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8', suffix='.txt') as temp_file:
                temp_file.write(mensaje)
                temp_file_path = temp_file.name

            with open(temp_file_path, 'rb') as f:
                await update.message.reply_document(
                    document=InputFile(f, filename='resumen_general.txt'),
                    caption='El resumen es muy largo, por lo que se ha enviado como un archivo.',
                    reply_markup=create_main_menu_keyboard()
                )
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

async def volver_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text("Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Error: {context.error} - causado por {update}", exc_info=True)
    if update and update.effective_message:
        await update.message.reply_text("❌ Ocurrió un error inesperado.", reply_markup=create_main_menu_keyboard())

# === Tarea Automática de Recordatorios ===
async def enviar_recordatorios_pago(context: ContextTypes.DEFAULT_TYPE):
    """Envía recordatorios de pago para inquilinos cuya fecha de pago se acerca."""
    # Usamos el primer usuario autorizado como destinatario de las notificaciones
    if not AUTHORIZED_USERS:
        logger.warning("No hay usuarios autorizados para enviar recordatorios.")
        return
    chat_id = AUTHORIZED_USERS[0]

    try:
        inquilinos_a_notificar = await obtener_inquilinos_para_recordatorio()

        if inquilinos_a_notificar:
            fecha_recordatorio = date.today() + timedelta(days=2)
            dia_vencimiento = fecha_recordatorio.day

            mensaje = f"🔔 *Recordatorio de Pagos Próximos* 🔔\n\n"
            mensaje += f"Los siguientes inquilinos tienen pagos que vencen en 2 días \(el día {dia_vencimiento}\) y aún no han pagado este mes:\n\n"
            for nombre in inquilinos_a_notificar:
                mensaje += f"\- {md(nombre)}\n"
            
            await context.bot.send_message(chat_id=chat_id, text=mensaje, parse_mode=ParseMode.MARKDOWN_V2)
            logger.info(f"Recordatorios de pago enviados a {chat_id} para: {', '.join(inquilinos_a_notificar)}")

    except Exception as e:
        logger.error(f"Error en la tarea de enviar recordatorios: {e}", exc_info=True)
        # Notificar al admin sobre el error en la tarea
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"Ocurrió un error en la tarea de recordatorios: {md(str(e))}")
        except Exception as send_e:
            logger.error(f"No se pudo notificar al admin sobre el error en la tarea de recordatorios: {send_e}", exc_info=True)


def _format_transaction_list(title: str, transactions: list, empty_message: str) -> str:
    if not transactions:
        return f"{title}: {empty_message}\n"

    message = f"{title}:\n"
    for i, transaction in enumerate(transactions, 1):
        fecha_dt = datetime.strptime(str(transaction[0]), '%Y-%m-%d').date()
        description = transaction[1]
        amount = transaction[2]
        message += f"{i}. {description}: {format_currency(amount)} ({fecha_dt.strftime('%d/%m/%Y')})\n"
    return message

def format_report(title: str, data: dict) -> str:
    mensaje = f"{title}\n\n"
    mensaje += "Resumen General:\n"
    mensaje += f"Ingresos Totales: {format_currency(data['total_ingresos'])}\n"
    mensaje += f"Gastos Totales: {format_currency(data['total_gastos'])}\n"
    mensaje += f"Comisión: {format_currency(data['total_comision'])}\n"
    mensaje += f"Monto Neto: {format_currency(data['monto_neto'])}\n\n"
    
    pagos = data.get('pagos_mes', [])
    mensaje += _format_transaction_list("Pagos del Mes", pagos, "No hay pagos registrados para este período.")
    mensaje += "\n"
    
    gastos = data.get('gastos_mes', [])
    mensaje += _format_transaction_list("Gastos del Mes", gastos, "No hay gastos registrados para este período.")
    return mensaje

def format_summary(data: dict) -> str:
    mensaje = "Resumen General:\n"
    mensaje += f"Ingresos Totales: {format_currency(data['total_ingresos'])}\n"
    mensaje += f"Gastos Totales: {format_currency(data['total_gastos'])}\n"
    mensaje += f"Comisión: {format_currency(data['total_comision'])}\n"
    mensaje += f"Monto Neto: {format_currency(data['monto_neto'])}\n\n"

    pagos = data.get('ultimos_pagos', [])
    mensaje += _format_transaction_list("Últimos Pagos", pagos, "No hay pagos recientes.")
    mensaje += "\n"

    gastos = data.get('ultimos_gastos', [])
    mensaje += _format_transaction_list("Últimos Gastos", gastos, "No hay gastos recientes.")
    return mensaje