import logging
import psycopg2
from psycopg2.errors import UniqueViolation
import calendar
import tempfile
import os
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import ContextTypes, ConversationHandler
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

logger = logging.getLogger(__name__)

# === Estados de conversación ===
(
    MENU, PAGO_SELECT_INQUILINO, PAGO_MONTO, GASTO_MONTO, GASTO_DESC,
    INFORME_MES, INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR,
    INQUILINO_MENU, INQUILINO_ADD_NOMBRE, INQUILINO_DEACTIVATE_SELECT,
    INQUILINO_ACTIVATE_SELECT, EDITAR_INICIO, EDITAR_PEDIR_ANIO, EDITAR_PEDIR_MES,
    EDITAR_SELECCIONAR_TRANSACCION, EDITAR_CONFIRMAR_BORRADO,
    INQUILINO_SET_DIA_PAGO_SELECT, INQUILINO_SET_DIA_PAGO_SAVE,
    PAGO_NOMBRE_OTRO
) = range(21)

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
    """
    Función genérica para guardar una transacción (pago o gasto) y manejar errores.
    
    Args:
        update: Update del mensaje de Telegram
        context: Contexto de la conversación
        tipo: 'pago' o 'gasto'
    """
    try:
        monto = context.user_data.get('monto')
        detalle = context.user_data.get('detalle')
        
        if not monto or not detalle:
            logger.warning(f"Datos incompletos para registrar {tipo}")
            await update.message.reply_text(
                "❌ Error: Datos incompletos. Por favor, intenta de nuevo.",
                reply_markup=create_main_menu_keyboard()
            )
            return

        fecha_registro = date.today()
        mensaje_adicional = ""

        # ✅ VALIDACIÓN: Montos negativos o cero
        if monto <= 0:
            await update.message.reply_text(
                "❌ El monto debe ser mayor a cero. Por favor, intenta de nuevo.",
                reply_markup=create_main_menu_keyboard()
            )
            context.user_data.clear()
            return

        try:
            if tipo == 'pago':
                # ✅ CORREGIDO: Manejo seguro de obtener_mes_pago_pendiente
                try:
                    fecha_pago_efectiva = await obtener_mes_pago_pendiente(detalle)
                    if fecha_pago_efectiva:
                        fecha_registro = fecha_pago_efectiva
                        mensaje_adicional = rf"\n\n_Nota: El pago se ha registrado para el período pendiente de {md(fecha_registro.strftime('%B de %Y'))}\._"
                except Exception as e:
                    logger.warning(f"No se pudo obtener mes de pago pendiente para {detalle}: {e}")
                    # Continuar sin mensaje adicional
                
                await registrar_pago(fecha_registro, detalle, monto)
                mensaje = (
                    f"✅ Pago registrado correctamente:\n"
                    f"📅 Fecha de Pago: {md(fecha_registro.strftime('%d/%m/%Y'))}\n"
                    f"👤 Nombre: {md(detalle)}\n"
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
                logger.error(f"Tipo de transacción desconocido: {tipo}")
                await update.message.reply_text(
                    "❌ Error: Tipo de transacción desconocido.",
                    reply_markup=create_main_menu_keyboard()
                )
                context.user_data.clear()
                return

            # ✅ CORREGIDO: Asegurar que el mensaje se envía correctamente
            await update.message.reply_text(
                mensaje, 
                parse_mode=ParseMode.MARKDOWN_V2, 
                reply_markup=create_main_menu_keyboard()
            )
            logger.info(f"{tipo.capitalize()} registrado exitosamente para {detalle}")

        except UniqueViolation as e:
            # ✅ ARREGLADO: Mensaje dinámico según el tipo de transacción
            if tipo == 'pago':
                error_msg = rf"❌ Ya existe un pago registrado para *{md(detalle)}* en la fecha de hoy\. Si quieres modificarlo, usa la opción 'Deshacer'\."
            elif tipo == 'gasto':
                error_msg = rf"❌ Error al registrar el gasto\. Intenta nuevamente o usa la opción 'Editar/Borrar' si necesitas modificarlo\."
            else:
                error_msg = r"❌ Ya existe un registro similar\. Si quieres modificarlo, usa el menú de opciones\."
            
            logger.warning(f"UniqueViolation al registrar {tipo}: {detalle} - {e}")
            await update.message.reply_text(
                error_msg,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=create_main_menu_keyboard()
            )
        except psycopg2.Error as e:
            logger.error(f"Error de base de datos al registrar {tipo}: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Hubo un error con la base de datos al registrar el {tipo}.",
                reply_markup=create_main_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Error inesperado al registrar {tipo}: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Hubo un error inesperado al registrar el {tipo}. Por favor, intenta de nuevo.",
                reply_markup=create_main_menu_keyboard()
            )

    except Exception as e:
        logger.error(f"Error crítico en _save_transaction: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "❌ Ocurrió un error crítico. Volviendo al menú principal.",
                reply_markup=create_main_menu_keyboard()
            )
        except Exception as send_error:
            logger.error(f"No se pudo enviar mensaje de error: {send_error}", exc_info=True)
    
    finally:
        # ✅ IMPORTANTE: Limpiar datos del usuario SIEMPRE
        if 'monto' in context.user_data:
            del context.user_data['monto']
        if 'detalle' in context.user_data:
            del context.user_data['detalle']
        logger.debug(f"Datos de usuario limpios después de registrar {tipo}")
    
    # ✅ CORREGIDO: NO retornar nada - solo await

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
    
    keyboard = [[KeyboardButton(inquilino[1])] for inquilino in inquilinos]
    # ✅ AGREGADO: Opción "Otro" para ingresar nombre personalizado
    keyboard.append([KeyboardButton("🔤 Otro (Nombre personalizado)")])
    keyboard.append([KeyboardButton("❌ Cancelar")])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    if not inquilinos:
        await update.message.reply_text(
            "No hay inquilinos activos. Selecciona 'Otro' para ingresar un nombre personalizado o añade un inquilino desde el menú 'Gestionar Inquilinos'.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("Selecciona el inquilino que realizó el pago:", reply_markup=reply_markup)
    
    return PAGO_SELECT_INQUILINO

async def pago_select_inquilino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler de selección de inquilino para pago."""
    nombre = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if nombre == "❌ Cancelar":
        return await volver_menu(update, context)
    
    # ✅ NUEVO: Detectar si seleccionó "Otro"
    if nombre == "🔤 Otro (Nombre personalizado)":
        await update.message.reply_text(
            "Escribe el nombre de la persona que realizó el pago:",
            reply_markup=create_cancel_keyboard()
        )
        return PAGO_NOMBRE_OTRO
    
    context.user_data['detalle'] = nombre
    await update.message.reply_text(
        f"Inquilino seleccionado: {nombre}. Ahora, escribe el monto del pago:",
        reply_markup=create_cancel_keyboard()
    )
    return PAGO_MONTO

async def pago_nombre_otro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para ingresar nombre personalizado de pagador."""
    nombre = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if nombre == "❌ Cancelar":
        return await volver_menu(update, context)
    
    # ✅ VALIDACIÓN: Nombre no vacío
    if not nombre or len(nombre) < 2:
        await update.message.reply_text(
            "❌ El nombre debe tener al menos 2 caracteres. Intenta de nuevo:",
            reply_markup=create_cancel_keyboard()
        )
        return PAGO_NOMBRE_OTRO
    
    context.user_data['detalle'] = nombre
    await update.message.reply_text(
        f"Nombre registrado: {nombre}. Ahora, escribe el monto del pago:",
        reply_markup=create_cancel_keyboard()
    )
    return PAGO_MONTO

async def pago_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler de monto de pago - Valida y guarda."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await volver_menu(update, context)
    
    try:
        monto = Decimal(texto.replace(",", "").replace("RD$", "").strip())
        
        if monto <= 0:
            await update.message.reply_text(
                "❌ El monto debe ser mayor a cero. Intenta de nuevo:",
                reply_markup=create_cancel_keyboard()
            )
            return PAGO_MONTO
        
        context.user_data['monto'] = monto
        await _save_transaction(update, context, 'pago')
        return MENU
        
    except (InvalidOperation, ValueError, AttributeError) as e:
        logger.warning(f"Error al parsear monto de pago: {e}")
        await update.message.reply_text(
            "❌ Monto inválido. Intenta de nuevo con un número válido (ej: 3000):",
            reply_markup=create_cancel_keyboard()
        )
        return PAGO_MONTO
    except Exception as e:
        logger.error(f"Error inesperado en pago_monto: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ocurrió un error. Volviendo al menú principal.",
            reply_markup=create_main_menu_keyboard()
        )
        context.user_data.clear()
        return MENU

# === Flujo Registrar Gasto ===
async def gasto_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de registrar gasto - Pide el monto."""
    await update.message.reply_text("Escribe el monto del gasto (ej: 500):", reply_markup=create_cancel_keyboard())
    return GASTO_MONTO

async def gasto_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler de monto de gasto - Valida e inicia descripción."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await volver_menu(update, context)
    
    try:
        monto = Decimal(texto.replace(",", "").replace("RD$", "").strip())
        if monto <= 0:
            await update.message.reply_text(
                "❌ El monto debe ser mayor a cero. Intenta de nuevo:",
                reply_markup=create_cancel_keyboard()
            )
            return GASTO_MONTO
        context.user_data['monto'] = monto
        await update.message.reply_text(f"Monto registrado: {format_currency(monto)}\nAhora escribe la descripción del gasto:", reply_markup=create_cancel_keyboard())
        return GASTO_DESC
    except (InvalidOperation, ValueError) as e:
        logger.warning(f"Error al parsear monto de gasto: {e}")
        await update.message.reply_text(
            "❌ Monto inválido. Intenta de nuevo con un número válido (ej: 500):",
            reply_markup=create_cancel_keyboard()
        )
        return GASTO_MONTO
    except Exception as e:
        logger.error(f"Error inesperado en gasto_monto: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ocurrió un error. Volviendo al menú principal.",
            reply_markup=create_main_menu_keyboard()
        )
        context.user_data.clear()
        return MENU

async def gasto_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler de descripción de gasto - Valida y guarda."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await volver_menu(update, context)
    
    try:
        # ✅ VALIDACIÓN: Descripción vacía
        if not texto or len(texto) < 3:
            await update.message.reply_text(
                "❌ La descripción debe tener al menos 3 caracteres. Intenta de nuevo:",
                reply_markup=create_cancel_keyboard()
            )
            return GASTO_DESC
        
        context.user_data['detalle'] = texto
        await _save_transaction(update, context, 'gasto')
        return MENU
        
    except Exception as e:
        logger.error(f"Error inesperado en gasto_desc: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ocurrió un error. Volviendo al menú principal.",
            reply_markup=create_main_menu_keyboard()
        )
        context.user_data.clear()
        return MENU

# === Flujo Gestionar Inquilinos ===
def create_inquilinos_menu_keyboard() -> ReplyKeyboardMarkup:
    """Crea el teclado del menú de inquilinos."""
    keyboard = [
        [KeyboardButton("➕ Añadir Inquilino"), KeyboardButton("📋 Listar Inquilinos")],
        [KeyboardButton("🗓️ Asignar Día de Pago")],
        [KeyboardButton("❌ Desactivar Inquilino"), KeyboardButton("✅ Activar Inquilino")],
        [KeyboardButton("⬅️ Volver al Menú Principal")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def gestionar_inquilinos_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler del menú de gestión de inquilinos."""
    await update.message.reply_text("Selecciona una opción para gestionar los inquilinos:", reply_markup=create_inquilinos_menu_keyboard())
    return INQUILINO_MENU

async def add_inquilino_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para iniciar añadir inquilino."""
    await update.message.reply_text("Escribe el nombre completo del nuevo inquilino:", reply_markup=create_cancel_keyboard())
    return INQUILINO_ADD_NOMBRE

async def add_inquilino_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para guardar nuevo inquilino."""
    nombre = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if nombre == "❌ Cancelar":
        return await gestionar_inquilinos_menu(update, context)
    
    # ✅ VALIDACIÓN: Nombre vacío
    if not nombre or len(nombre) < 3:
        await update.message.reply_text(
            "❌ El nombre debe tener al menos 3 caracteres. Intenta de nuevo:",
            reply_markup=create_cancel_keyboard()
        )
        return INQUILINO_ADD_NOMBRE
    
    try:
        await crear_inquilino(nombre)
        await update.message.reply_text(f"✅ Inquilino '{nombre}' añadido correctamente.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU
    except UniqueViolation:
        await update.message.reply_text(f"❌ El inquilino '{nombre}' ya existe.", reply_markup=create_cancel_keyboard())
        return INQUILINO_ADD_NOMBRE
    except psycopg2.Error as e:
        logger.error(f"Error de DB al añadir inquilino: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

async def list_inquilinos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para listar inquilinos."""
    inquilinos = await obtener_inquilinos(activos_only=False)
    if not inquilinos:
        mensaje = "No hay inquilinos registrados."
    else:
        mensaje = "Lista de Inquilinos:\n"
        for _, nombre, activo, dia_pago in inquilinos:
            estado = "✅ Activo" if activo else "❌ Inactivo"
            dia_pago_str = f"Día de pago: {dia_pago}" if dia_pago else "Día de pago: Sin asignar"
            mensaje += rf"\- {md(nombre)} \({md(estado)}\) \- {md(dia_pago_str)}\n"
    
    await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_inquilinos_menu_keyboard())
    return INQUILINO_MENU

async def deactivate_inquilino_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para iniciar desactivar inquilino."""
    inquilinos = await obtener_inquilinos(activos_only=True)
    if not inquilinos:
        await update.message.reply_text("No hay inquilinos activos para desactivar.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU
    
    context.user_data['inquilinos_list'] = {i[1]: i[0] for i in inquilinos}
    keyboard = [[KeyboardButton(i[1])] for i in inquilinos]
    keyboard.append([KeyboardButton("❌ Cancelar")])
    
    await update.message.reply_text("Selecciona el inquilino que quieres desactivar:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return INQUILINO_DEACTIVATE_SELECT

async def deactivate_inquilino_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para confirmar desactivación de inquilino."""
    nombre = update.message.text.strip()
    inquilino_id = context.user_data.get('inquilinos_list', {}).get(nombre)

    if not inquilino_id:
        await update.message.reply_text("Selección inválida. Por favor, usa el teclado.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

    await cambiar_estado_inquilino(inquilino_id, False)
    await update.message.reply_text(f"✅ Inquilino '{nombre}' ha sido desactivado.", reply_markup=create_inquilinos_menu_keyboard())
    context.user_data.clear()
    return INQUILINO_MENU

async def activate_inquilino_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para iniciar activar inquilino."""
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
    """Handler para confirmar activación de inquilino."""
    nombre = update.message.text.strip()
    inquilino_id = context.user_data.get('inquilinos_list', {}).get(nombre)

    if not inquilino_id:
        await update.message.reply_text("Selección inválida. Por favor, usa el teclado.", reply_markup=create_inquilinos_menu_keyboard())
        return INQUILINO_MENU

    await cambiar_estado_inquilino(inquilino_id, True)
    await update.message.reply_text(f"✅ Inquilino '{nombre}' ha sido activado.", reply_markup=create_inquilinos_menu_keyboard())
    context.user_data.clear()
    return INQUILINO_MENU

# === Flujo Asignar Día de Pago ===

async def set_dia_pago_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo para asignar o actualizar el día de pago de un inquilino."""
    inquilinos = await obtener_inquilinos(activos_only=True)
    if not inquilinos:
        await update.message.reply_text(
            "No hay inquilinos activos. Añade un inquilino primero.",
            reply_markup=create_inquilinos_menu_keyboard()
        )
        return INQUILINO_MENU

    context.user_data['inquilinos_list'] = {i[1]: i[0] for i in inquilinos}
    keyboard = [[KeyboardButton(i[1])] for i in inquilinos]
    keyboard.append([KeyboardButton("❌ Cancelar")])
    
    await update.message.reply_text(
        "Selecciona el inquilino al que quieres asignar/editar el día de pago:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return INQUILINO_SET_DIA_PAGO_SELECT

async def set_dia_pago_select_inquilino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección del inquilino y pide el día de pago."""
    nombre_inquilino = update.message.text
    inquilino_id = context.user_data.get('inquilinos_list', {}).get(nombre_inquilino)

    if not inquilino_id:
        await update.message.reply_text("Selección inválida. Por favor, usa el teclado.", reply_markup=create_inquilinos_menu_keyboard())
        context.user_data.clear()
        return INQUILINO_MENU

    context.user_data['selected_inquilino_id'] = inquilino_id
    context.user_data['selected_inquilino_nombre'] = nombre_inquilino
    
    await update.message.reply_text(
        rf"Introduce el día de pago \(1\-31\) para {md(nombre_inquilino)}:",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=create_cancel_keyboard()
    )
    return INQUILINO_SET_DIA_PAGO_SAVE

async def set_dia_pago_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda el día de pago para el inquilino seleccionado."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        context.user_data.clear()
        return await gestionar_inquilinos_menu(update, context)
    
    try:
        dia_pago = int(texto)
        if not 1 <= dia_pago <= 31:
            raise ValueError("Día fuera de rango")

        inquilino_id = context.user_data['selected_inquilino_id']
        nombre_inquilino = context.user_data['selected_inquilino_nombre']

        success = await actualizar_dia_pago_inquilino(inquilino_id, dia_pago)

        if success:
            await update.message.reply_text(
                rf"✅ Día de pago actualizado a *{dia_pago}* para el inquilino *{md(nombre_inquilino)}\.*",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=create_inquilinos_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Hubo un error y no se pudo actualizar el día de pago.",
                reply_markup=create_inquilinos_menu_keyboard()
            )

    except (ValueError, TypeError):
        await update.message.reply_text(
            "Entrada inválida. Por favor, introduce un número entre 1 y 31.",
            reply_markup=create_cancel_keyboard()
        )
        return INQUILINO_SET_DIA_PAGO_SAVE
    except Exception as e:
        logger.error(f"Error al guardar día de pago: {e}", exc_info=True)
        await update.message.reply_text("❌ Ocurrió un error inesperado.", reply_markup=create_inquilinos_menu_keyboard())
        context.user_data.clear()
        return INQUILINO_MENU

# === Flujo Editar/Borrar ===
async def editar_inicio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para iniciar edición de transacciones."""
    keyboard = [
        [KeyboardButton("Mes Actual")],
        [KeyboardButton("Elegir Mes y Año")],
        [KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("¿De qué período quieres editar o borrar una transacción?", reply_markup=reply_markup)
    return EDITAR_INICIO

async def editar_mes_actual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para editar mes actual."""
    hoy = date.today()
    return await editar_listar_transacciones(update, context, hoy.month, hoy.year)

async def editar_pedir_mes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para pedir mes personalizado de informe."""
    await update.message.reply_text(
        "Por favor, introduce el número del mes (1-12):",
        reply_markup=create_cancel_keyboard()  # ✅ AGREGADO
    )
    return INFORME_ANIO

async def editar_pedir_anio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para validar mes de informe y pedir año."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await editar_inicio(update, context)
    
    try:
        mes = int(texto)
        if not 1 <= mes <= 12:
            await update.message.reply_text(
                "Mes inválido. Por favor, introduce un número del 1 al 12.",
                reply_markup=create_cancel_keyboard()
            )
            return EDITAR_PEDIR_ANIO
        context.user_data['edit_month'] = mes
        await update.message.reply_text("Ahora, introduce el año (ej: 2023):", reply_markup=create_cancel_keyboard())
        return EDITAR_PEDIR_MES
    except ValueError:
        await update.message.reply_text(
            "Entrada inválida. Por favor, introduce un número para el mes.",
            reply_markup=create_cancel_keyboard()
        )
        return EDITAR_PEDIR_ANIO

async def editar_listar_transacciones_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para validar año personalizado."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await editar_inicio(update, context)
    
    try:
        anio = int(texto)
        if not 1900 < anio < 2100:
            await update.message.reply_text(
                "Año inválido. Por favor, introduce un año válido (ej: 2023).",
                reply_markup=create_cancel_keyboard()
            )
            return EDITAR_PEDIR_MES

        mes = context.user_data.get('edit_month')
        return await editar_listar_transacciones(update, context, mes, anio)
    except (ValueError, KeyError):
        await update.message.reply_text(
            "Año inválido. Por favor, introduce un número para el año (ej: 2023).",
            reply_markup=create_cancel_keyboard()
        )
        return EDITAR_PEDIR_MES

async def editar_listar_transacciones(update: Update, context: ContextTypes.DEFAULT_TYPE, mes: int, anio: int) -> int:
    """Handler para listar transacciones del período seleccionado."""
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
            mensaje += rf"`{code}`: {md(p_inquilino)} \- {md(format_currency(p_monto))} el {p_fecha.strftime('%d/%m')}\n"
    
    if gastos:
        mensaje += "\n*Gastos*\n"
        for i, (g_id, g_fecha_str, g_desc, g_monto) in enumerate(gastos, 1):
            code = f"G{i}"
            transactions_map[code] = {"id": g_id, "tipo": "gasto"}
            g_fecha = g_fecha_str if hasattr(g_fecha_str, 'strftime') else datetime.strptime(str(g_fecha_str), '%Y-%m-%d').date()
            mensaje += rf"`{code}`: {md(g_desc)} \- {md(format_currency(g_monto))} el {g_fecha.strftime('%d/%m')}\n"

    context.user_data['transactions_map'] = transactions_map
    mensaje += r"\nEscribe el código de la transacción que quieres borrar \(ej: P1 o G2\)\n"
    
    await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=create_cancel_keyboard())
    return EDITAR_SELECCIONAR_TRANSACCION

async def editar_seleccionar_transaccion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para seleccionar transacción a borrar."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        context.user_data.clear()
        return MENU
    
    code = texto.upper()
    transactions_map = context.user_data.get('transactions_map', {})

    if code not in transactions_map:
        await update.message.reply_text(
            "Código inválido. Por favor, introduce un código de la lista (ej: P1).",
            reply_markup=create_cancel_keyboard()
        )
        return EDITAR_SELECCIONAR_TRANSACCION

    transaction = transactions_map[code]
    context.user_data['selected_transaction'] = transaction

    keyboard = [[KeyboardButton("Sí, borrar")], [KeyboardButton("No, cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        rf"¿Estás seguro de que quieres borrar la transacción `{md(code)}`\? Esta acción no se puede deshacer\.",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=reply_markup
    )
    return EDITAR_CONFIRMAR_BORRADO

async def editar_ejecutar_borrado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para confirmar y ejecutar borrado de transacción."""
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

# === Tareas Automáticas de Recordatorios ===
async def enviar_recordatorios_pago(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tarea automática para enviar recordatorios de pagos vencidos/próximos."""
    try:
        # ✅ CORREGIDO: Obtener chat_id del job context
        job = context.job
        if not job or not hasattr(job, 'chat_id'):
            logger.error("No se pudo obtener chat_id para enviar recordatorios.")
            return
        
        chat_id = job.chat_id
        
        recordatorios = await obtener_inquilinos_para_recordatorio()
        vencidos = recordatorios.get("vencidos", [])
        proximos = recordatorios.get("proximos", [])

        if not vencidos and not proximos:
            logger.info("No hay recordatorios de pago para enviar hoy.")
            return

        # ✅ CORREGIDO: Mensaje sin raw string
        mensaje = "🔔 *Recordatorios de Pago* 🔔\n\n"

        if vencidos:
            mensaje += "*Pagos Vencidos* 😡\n"
            for nombre in vencidos:
                mensaje += f"\\- El pago de *{md(nombre)}* está vencido y no se ha registrado\\.\n"
            mensaje += "\n"

        if proximos:
            mensaje += "*Pagos Próximos a Vencer* ⚠️\n"
            for nombre in proximos:
                mensaje += f"\\- El pago de *{md(nombre)}* está próximo a vencer y no se ha registrado aún\\.\n"
        
        await context.bot.send_message(
            chat_id=chat_id, 
            text=mensaje, 
            parse_mode=ParseMode.MARKDOWN_V2
        )
        logger.info(f"Recordatorios de pago enviados a {chat_id}.")

    except Exception as e:
        logger.error(f"Error en la tarea de enviar recordatorios: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=context.job.chat_id if context.job and hasattr(context.job, 'chat_id') else None,
                text="Ocurrió un error inesperado al procesar los recordatorios de pago."
            )
        except Exception as send_e:
            logger.error(f"No se pudo enviar el mensaje de error de recordatorio: {send_e}", exc_info=True)

# === Otros Handlers ===
async def ver_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para ver resumen general."""
    temp_file_path = None
    try:
        resumen_data = await obtener_resumen()
        mensaje = format_summary(resumen_data)
        
        if len(mensaje) < 3000:
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
    """Handler para iniciar generación de informe."""
    keyboard = [
        [KeyboardButton("Informe Mes Actual")],
        [KeyboardButton("Elegir Mes y Año")],
        [KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Selecciona el tipo de informe que deseas generar:", reply_markup=reply_markup)
    return INFORME_MES

async def informe_mes_actual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para informe del mes actual."""
    hoy = date.today()
    return await generar_informe_mensual(update, context, hoy.month, hoy.year)

async def informe_pedir_mes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para pedir mes personalizado de informe."""
    await update.message.reply_text(
        "Por favor, introduce el número del mes (1-12):",
        reply_markup=create_cancel_keyboard()  # ✅ AGREGADO
    )
    return INFORME_ANIO

async def informe_pedir_anio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para validar mes de informe y pedir año."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await informe_inicio(update, context)
    
    try:
        mes = int(texto)
        if not 1 <= mes <= 12:
            await update.message.reply_text(
                "Mes inválido. Por favor, introduce un número del 1 al 12.",
                reply_markup=create_cancel_keyboard()
            )
            return INFORME_ANIO
        context.user_data['report_month'] = mes
        await update.message.reply_text("Ahora, introduce el año (ej: 2023):", reply_markup=create_cancel_keyboard())
        return INFORME_GENERAR
    except ValueError:
        await update.message.reply_text(
            "Entrada inválida. Por favor, introduce un número para el mes.",
            reply_markup=create_cancel_keyboard()
        )
        return INFORME_ANIO

async def generar_informe_mensual_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para validar año de informe personalizado."""
    texto = update.message.text.strip()
    
    # ✅ VALIDAR CANCELACIÓN PRIMERO
    if texto == "❌ Cancelar":
        return await informe_inicio(update, context)
    
    try:
        anio = int(texto)
        if not 1900 < anio < 2100:
            await update.message.reply_text(
                "Año inválido. Por favor, introduce un año válido (ej: 2023).",
                reply_markup=create_cancel_keyboard()
            )
            return INFORME_GENERAR

        mes = context.user_data.get('report_month')
        if not mes:
            await update.message.reply_text("❌ Error: No se encontró el mes para el informe. Volviendo al menú.", reply_markup=create_main_menu_keyboard())
            return MENU

        return await generar_informe_mensual(update, context, mes, anio)
    except (ValueError, KeyError):
        await update.message.reply_text(
            "Año inválido. Por favor, introduce un número para el año (ej: 2023).",
            reply_markup=create_cancel_keyboard()
        )
        return INFORME_GENERAR

async def generar_informe_mensual(update: Update, context: ContextTypes.DEFAULT_TYPE, mes: int, anio: int) -> int:
    """Handler para generar informe mensual en PDF."""
    try:
        report_data = await obtener_informe_mensual(mes, anio)
        
        # Generar el PDF en memoria
        pdf_buffer = crear_informe_pdf(report_data, mes, anio)
        
        # Obtener el nombre del mes para el archivo
        nombre_mes = calendar.month_name[mes].capitalize()
        nombre_archivo = f"Informe_{nombre_mes}_{anio}.pdf"
        
        await update.message.reply_document(
            document=InputFile(pdf_buffer, filename=nombre_archivo),
            caption=f"📄 Aquí tienes el informe de pagos para {nombre_mes} de {anio}.",
            reply_markup=create_main_menu_keyboard()
        )
    except psycopg2.Error as e:
        logger.error(f"Error de base de datos al generar informe: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error con la base de datos al generar el informe.", reply_markup=create_main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error inesperado al generar informe: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error inesperado al generar el informe.", reply_markup=create_main_menu_keyboard())
    return MENU

async def deshacer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler del menú deshacer."""
    keyboard = [
        [KeyboardButton("🗑️ Deshacer Último Pago"), KeyboardButton("🗑️ Deshacer Último Gasto")],
        [KeyboardButton("⬅️ Volver al Menú")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("¿Qué acción deseas deshacer?", reply_markup=reply_markup)
    return DESHACER_MENU

async def deshacer_pago_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler para deshacer último pago."""
    try:
        inquilino, monto = await deshacer_ultimo_pago()
        if inquilino:
            mensaje = rf"✅ Último pago de *{md(inquilino)}* por *{md(format_currency(monto))}* ha sido eliminado\."
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
    """Handler para deshacer último gasto."""
    try:
        descripcion, monto = await deshacer_ultimo_gasto()
        if descripcion:
            mensaje = rf"✅ Último gasto *{md(descripcion)}* por *{md(format_currency(monto))}* ha sido eliminado\."
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
    """Handler para volver al menú principal."""
    reply_markup = create_main_menu_keyboard()
    await update.message.reply_text("Selecciona una opción:", reply_markup=reply_markup)
    return MENU

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler global para errores no capturados."""
    logger.error(f"Error: {context.error} - causado por {update}", exc_info=True)
    if update and update.effective_message:
        await update.message.reply_text("❌ Ocurrió un error inesperado.", reply_markup=create_main_menu_keyboard())

def _format_transaction_list(title: str, transactions: list, empty_message: str) -> str:
    """Formatea una lista de transacciones para mostrar."""
    if not transactions:
        return f"{title}: {empty_message}\n"

    message = f"{title}:\n"
    for i, transaction in enumerate(transactions, 1):
        if len(transaction) == 4:
            _, fecha_str, description, amount = transaction
        elif len(transaction) == 3:
            fecha_str, description, amount = transaction
        else:
            continue

        fecha_dt = datetime.strptime(str(fecha_str), '%Y-%m-%d').date()
        message += f"{i}. {description}: {format_currency(amount)} ({fecha_dt.strftime('%d/%m/%Y')})\n"
    return message

def format_report(title: str, data: dict) -> str:
    """Formatea un informe mensual completo."""
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
    """Formatea un resumen general."""
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