import os
import sys
import logging
from datetime import time
from telegram.request import HTTPXRequest

# En Windows, se requiere una política de eventos específica para aiopg
if os.name == 'nt':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
from config import BOT_TOKEN, AUTHORIZED_USERS
from database import inicializar_db, init_pool, close_pool
from handlers import (
    # Handlers principales
    start, volver_menu, error_handler,
    # Pago
    pago_inicio, pago_select_inquilino, pago_nombre_otro, pago_monto,
    # Gasto
    gasto_inicio, gasto_monto, gasto_desc,
    # Inquilinos
    gestionar_inquilinos_menu, add_inquilino_prompt, add_inquilino_save, list_inquilinos,
    deactivate_inquilino_prompt, deactivate_inquilino_update, activate_inquilino_prompt, 
    activate_inquilino_update, set_dia_pago_start, set_dia_pago_select_inquilino, set_dia_pago_save,
    # Editar/Borrar
    editar_inicio, editar_mes_actual, editar_pedir_mes, editar_pedir_anio,
    editar_listar_transacciones_custom, editar_seleccionar_transaccion, editar_ejecutar_borrado,
    # Otros
    ver_resumen, informe_inicio, informe_mes_actual, informe_pedir_mes, informe_pedir_anio,
    generar_informe_mensual_custom, deshacer_menu, deshacer_pago_handler, deshacer_gasto_handler,
    volver_menu_principal, enviar_recordatorios_pago,
    # Estados
    MENU, PAGO_SELECT_INQUILINO, PAGO_MONTO, PAGO_NOMBRE_OTRO, GASTO_MONTO, GASTO_DESC,
    INFORME_MES, INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR,
    INQUILINO_MENU, INQUILINO_ADD_NOMBRE, INQUILINO_DEACTIVATE_SELECT,
    INQUILINO_ACTIVATE_SELECT, EDITAR_INICIO, EDITAR_PEDIR_ANIO, EDITAR_PEDIR_MES,
    EDITAR_SELECCIONAR_TRANSACCION, EDITAR_CONFIRMAR_BORRADO,
    INQUILINO_SET_DIA_PAGO_SELECT, INQUILINO_SET_DIA_PAGO_SAVE
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

    # === HANDLER: /start ===
    application.add_handler(CommandHandler("start", start))

    # === HANDLER: Registrar Pago ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📥 Registrar Pago$"), pago_inicio)],
        states={
            PAGO_SELECT_INQUILINO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_select_inquilino)],
            PAGO_NOMBRE_OTRO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_nombre_otro)],
            PAGO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_monto)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
    ))

    # === HANDLER: Registrar Gasto ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Registrar Gasto$"), gasto_inicio)],
        states={
            GASTO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_monto)],
            GASTO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_desc)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
    ))

    # === HANDLER: Gestionar Inquilinos ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^👤 Gestionar Inquilinos$"), gestionar_inquilinos_menu)],
        states={
            INQUILINO_MENU: [
                MessageHandler(filters.Regex("^➕ Añadir Inquilino$"), add_inquilino_prompt),
                MessageHandler(filters.Regex("^📋 Listar Inquilinos$"), list_inquilinos),
                MessageHandler(filters.Regex("^❌ Desactivar Inquilino$"), deactivate_inquilino_prompt),
                MessageHandler(filters.Regex("^✅ Activar Inquilino$"), activate_inquilino_prompt),
                MessageHandler(filters.Regex("^🗓️ Asignar Día de Pago$"), set_dia_pago_start),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú Principal$"), volver_menu_principal),
            ],
            INQUILINO_ADD_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_inquilino_save)],
            INQUILINO_DEACTIVATE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deactivate_inquilino_update)],
            INQUILINO_ACTIVATE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, activate_inquilino_update)],
            INQUILINO_SET_DIA_PAGO_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_dia_pago_select_inquilino)],
            INQUILINO_SET_DIA_PAGO_SAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_dia_pago_save)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), gestionar_inquilinos_menu)],
    ))

    # === HANDLER: Editar/Borrar ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✏️ Editar/Borrar$"), editar_inicio)],
        states={
            EDITAR_INICIO: [
                MessageHandler(filters.Regex("^Mes Actual$"), editar_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), editar_pedir_mes),
            ],
            EDITAR_PEDIR_ANIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, editar_pedir_anio)],
            EDITAR_PEDIR_MES: [MessageHandler(filters.TEXT & ~filters.COMMAND, editar_listar_transacciones_custom)],
            EDITAR_SELECCIONAR_TRANSACCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, editar_seleccionar_transaccion)],
            EDITAR_CONFIRMAR_BORRADO: [
                MessageHandler(filters.Regex("^Sí, borrar$"), editar_ejecutar_borrado),
                MessageHandler(filters.Regex("^No, cancelar$"), volver_menu),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
    ))

    # === HANDLER: Ver Resumen ===
    application.add_handler(MessageHandler(filters.Regex("^📊 Ver Resumen$"), ver_resumen))

    # === HANDLER: Generar Informe ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📈 Generar Informe$"), informe_inicio)],
        states={
            INFORME_MES: [
                MessageHandler(filters.Regex("^Informe Mes Actual$"), informe_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), informe_pedir_mes),
            ],
            INFORME_ANIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, informe_pedir_anio)],
            INFORME_GENERAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, generar_informe_mensual_custom)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
    ))

    # === HANDLER: Deshacer ===
    application.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑️ Deshacer$"), deshacer_menu)],
        states={
            DESHACER_MENU: [
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Pago$"), deshacer_pago_handler),
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Gasto$"), deshacer_gasto_handler),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú$"), volver_menu),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu)],
    ))

    # === HANDLER DE ERROR ===
    application.add_error_handler(error_handler)

    # === TAREA AUTOMÁTICA: Recordatorios diarios ===
    # Enviar recordatorios de pago a las 08:00 AM
    if AUTHORIZED_USERS:
        application.job_queue.run_daily(
            enviar_recordatorios_pago,
            time=time(hour=8, minute=0),
            job_kwargs={"chat_id": AUTHORIZED_USERS[0]}
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
    except Exception as e:
        logger.error(f"Error en polling: {e}", exc_info=True)
    finally:
        # Cerrar el pool de base de datos
        await close_pool()
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
