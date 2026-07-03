import os
import sys
import logging
import warnings
from datetime import time, timezone, timedelta
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

import asyncio
# En Windows, se requiere una política de eventos específica para aiopg
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from config import BOT_TOKEN, AUTHORIZED_USERS
from database import inicializar_db, init_pool, close_pool
from handlers import (
    # Handlers principales
    start, volver_menu, error_handler,
    # Pago
    pago_inicio, pago_select_inquilino, pago_nombre_otro, pago_monto,
    # Gasto
    gasto_inicio, gasto_monto, gasto_desc, gasto_mes,
    # Inquilinos
    gestionar_inquilinos_menu, add_inquilino_prompt, add_inquilino_save, list_inquilinos,
    deactivate_inquilino_prompt, deactivate_inquilino_update, activate_inquilino_prompt, 
    activate_inquilino_update, set_dia_pago_start, set_dia_pago_select_inquilino, set_dia_pago_save,
    delete_inquilino_prompt, delete_inquilino_update,
    estado_cuenta_prompt, estado_cuenta_show, inquilinos_pendientes_handler, inquilinos_pendientes_callback, descargar_recibo_callback, descargar_excel_callback,
    # Editar/Borrar
    editar_inicio, editar_mes_actual, editar_pedir_mes, editar_pedir_anio,
    editar_listar_transacciones_custom, editar_seleccionar_transaccion, editar_ejecutar_borrado,
    # Otros
    ver_resumen, informe_inicio, informe_mes_actual, informe_mes_anterior, informe_pedir_mes, informe_pedir_anio,
    generar_informe_mensual_custom, deshacer_menu, deshacer_pago_handler, deshacer_gasto_handler,
    volver_menu_principal, enviar_recordatorios_pago,
    # Estados
    MENU, PAGO_SELECT_INQUILINO, PAGO_MONTO, PAGO_NOMBRE_OTRO, GASTO_MONTO, GASTO_DESC, GASTO_MES,
    INFORME_MES, INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR,
    INQUILINO_MENU, INQUILINO_ADD_NOMBRE, INQUILINO_DEACTIVATE_SELECT,
    INQUILINO_ACTIVATE_SELECT, EDITAR_INICIO, EDITAR_PEDIR_ANIO, EDITAR_PEDIR_MES,
    EDITAR_SELECCIONAR_TRANSACCION, EDITAR_CONFIRMAR_BORRADO,
    INQUILINO_SET_DIA_PAGO_SELECT, INQUILINO_SET_DIA_PAGO_SAVE, INQUILINO_DELETE_SELECT,
    INQUILINO_ESTADO_CUENTA_SELECT
)

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Función principal para iniciar el bot."""
    # Inicializar pool de base de datos
    await init_pool()
    await inicializar_db()

    # ✅ CORREGIDO: Configurar HTTPXRequest con timeouts más largos
    request = HTTPXRequest(
        http_version="1.1",
        connect_timeout=20,  # ✅ Aumentado de 5 a 20 segundos
        read_timeout=20,     # ✅ Aumentado de 5 a 20 segundos
        write_timeout=20,    # ✅ Aumentado de 5 a 20 segundos
        pool_timeout=20,     # ✅ Aumentado de 5 a 20 segundos
    )

    # Crear la aplicación
    application = Application.builder()\
        .token(BOT_TOKEN)\
        .request(request)\
        .build()

    # ✅ SEGURIDAD: Filtro global para restringir el uso solo a usuarios autorizados
    auth_filter = filters.User(AUTHORIZED_USERS)
    main_menu_regex = "^(📥 Registrar Pago|💸 Registrar Gasto|👤 Gestionar Inquilinos|✏️ Editar/Borrar|📊 Ver Resumen|📈 Generar Informe|🗑️ Deshacer|❌ Cancelar)$"
    text_filter = filters.TEXT & ~filters.COMMAND & ~filters.Regex(main_menu_regex)

    # === HANDLER: /start ===
    application.add_handler(CommandHandler("start", start, filters=auth_filter))

    # === HANDLER: Registrar Pago ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📥 Registrar Pago$") & auth_filter, pago_inicio)],
        states={
            PAGO_SELECT_INQUILINO: [CallbackQueryHandler(pago_select_inquilino, pattern="^pago_")],
            PAGO_NOMBRE_OTRO: [MessageHandler(text_filter, pago_nombre_otro)],
            PAGO_MONTO: [MessageHandler(text_filter, pago_monto)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
        allow_reentry=True,
        per_message=False,
    ))

    # === HANDLER: Registrar Gasto ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Registrar Gasto$") & auth_filter, gasto_inicio)],
        states={
            GASTO_MONTO: [MessageHandler(text_filter, gasto_monto)],
            GASTO_DESC: [MessageHandler(text_filter, gasto_desc)],
            GASTO_MES: [MessageHandler(text_filter, gasto_mes)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
        allow_reentry=True,
    ))

    # === HANDLER: Gestionar Inquilinos ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👤 Gestionar Inquilinos$") & auth_filter, gestionar_inquilinos_menu)],
        states={
            INQUILINO_MENU: [
                MessageHandler(filters.Regex("^➕ Añadir Inquilino$"), add_inquilino_prompt),
                MessageHandler(filters.Regex("^📋 Listar Inquilinos$"), list_inquilinos),
                MessageHandler(filters.Regex("^📑 Estado de Cuenta$"), estado_cuenta_prompt),
                MessageHandler(filters.Regex("^⏳ Pendientes del Mes$"), inquilinos_pendientes_handler),
                MessageHandler(filters.Regex("^❌ Desactivar Inquilino$"), deactivate_inquilino_prompt),
                MessageHandler(filters.Regex("^✅ Activar Inquilino$"), activate_inquilino_prompt),
                MessageHandler(filters.Regex("^🗓️ Asignar Día de Pago$"), set_dia_pago_start),
                MessageHandler(filters.Regex("^🗑️ Eliminar Inquilino$"), delete_inquilino_prompt),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú Principal$"), volver_menu_principal),
            ],
            INQUILINO_ADD_NOMBRE: [MessageHandler(text_filter, add_inquilino_save)],
            INQUILINO_DEACTIVATE_SELECT: [CallbackQueryHandler(deactivate_inquilino_update, pattern="^(deact_|cancel_inquilino)")],
            INQUILINO_ACTIVATE_SELECT: [CallbackQueryHandler(activate_inquilino_update, pattern="^(act_|cancel_inquilino)")],
            INQUILINO_SET_DIA_PAGO_SELECT: [CallbackQueryHandler(set_dia_pago_select_inquilino, pattern="^(diapago_|cancel_inquilino)")],
            INQUILINO_SET_DIA_PAGO_SAVE: [MessageHandler(text_filter, set_dia_pago_save)],
            INQUILINO_DELETE_SELECT: [CallbackQueryHandler(delete_inquilino_update, pattern="^(delinq_|cancel_inquilino)")],
            INQUILINO_ESTADO_CUENTA_SELECT: [CallbackQueryHandler(estado_cuenta_show, pattern="^(ec_|cancel_inquilino)")],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
        allow_reentry=True,
        per_message=False,
    ))

    # === HANDLERS de Callbacks Globales (Recibos, Excel y Pendientes) ===
    application.add_handler(CallbackQueryHandler(descargar_recibo_callback, pattern="^dl_recibo_"))
    application.add_handler(CallbackQueryHandler(descargar_excel_callback, pattern="^dl_excel_"))
    application.add_handler(CallbackQueryHandler(inquilinos_pendientes_callback, pattern="^pend_"))

    # === HANDLER: Editar/Borrar ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✏️ Editar/Borrar$") & auth_filter, editar_inicio)],
        states={
            EDITAR_INICIO: [
                MessageHandler(filters.Regex("^Mes Actual$"), editar_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), editar_pedir_mes),
            ],
            EDITAR_PEDIR_ANIO: [MessageHandler(text_filter, editar_pedir_anio)],
            EDITAR_PEDIR_MES: [MessageHandler(text_filter, editar_listar_transacciones_custom)],
            EDITAR_SELECCIONAR_TRANSACCION: [CallbackQueryHandler(editar_seleccionar_transaccion, pattern="^del_")],
            EDITAR_CONFIRMAR_BORRADO: [CallbackQueryHandler(editar_ejecutar_borrado, pattern="^del_confirm_")],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
        allow_reentry=True,
        per_message=False,
    ))

    # === HANDLER: Ver Resumen ===
    application.add_handler(MessageHandler(filters.Regex("^📊 Ver Resumen$") & auth_filter, ver_resumen))

    # === HANDLER: Generar Informe ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📈 Generar Informe$") & auth_filter, informe_inicio)],
        states={
            INFORME_MES: [
                MessageHandler(filters.Regex("^Informe Mes Actual$"), informe_mes_actual),
                MessageHandler(filters.Regex("^Informe Mes Anterior$"), informe_mes_anterior),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), informe_pedir_mes),
            ],
            INFORME_ANIO: [MessageHandler(text_filter, informe_pedir_anio)],
            INFORME_GENERAR: [MessageHandler(text_filter, generar_informe_mensual_custom)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
        allow_reentry=True,
    ))

    # === HANDLER: Deshacer ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑️ Deshacer$") & auth_filter, deshacer_menu)],
        states={
            DESHACER_MENU: [
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Pago$"), deshacer_pago_handler),
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Gasto$"), deshacer_gasto_handler),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú$"), volver_menu),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
        allow_reentry=True,
    ))

    # === HANDLER DE ERROR ===
    application.add_error_handler(error_handler)

    # === TAREA AUTOMÁTICA: Recordatorios diarios ===
    # Configurar zona horaria de República Dominicana (UTC-4)
    do_tz = timezone(timedelta(hours=-4))
    if AUTHORIZED_USERS:
        for user_id in AUTHORIZED_USERS:
            application.job_queue.run_daily(
                enviar_recordatorios_pago,
                time=time(hour=8, minute=0, tzinfo=do_tz),
                chat_id=user_id
            )

    logger.info("Bot iniciado correctamente.")

    # Iniciar el bot con reintentos automáticos
    await application.initialize()
    await application.start()
    
    try:
        await application.updater.start_polling(
            allowed_updates=['message', 'callback_query'],
            timeout=30,  # ✅ Timeout de polling aumentado
            read_timeout=20,  # ✅ Timeout de lectura
            write_timeout=20,  # ✅ Timeout de escritura
            connect_timeout=20,  # ✅ Timeout de conexión
        )
        
        # ✅ CORREGIDO: start_polling no bloquea el hilo principal.
        # Necesitamos un evento que espere para que el script no termine y el bot siga escuchando.
        logger.info("El bot está escuchando mensajes...")
        stop_event = asyncio.Event()
        await stop_event.wait()
    except Exception as e:
        logger.error(f"Error en polling: {e}", exc_info=True)
    finally:
        # Cerrar el pool de base de datos
        await close_pool()
        if application.updater and application.updater.running:
            await application.updater.stop()
        await application.stop()

if __name__ == '__main__':
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot detenido por el usuario.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Error crítico al iniciar el bot: {e}", exc_info=True)
        sys.exit(1)
