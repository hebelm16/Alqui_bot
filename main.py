from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import logging
from datetime import time
import asyncio
import os

# En Windows, se requiere una política de eventos específica para aiopg
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config import BOT_TOKEN, AUTHORIZED_USERS
from database import inicializar_db, init_pool, close_pool
from handlers import (
    start, pago_inicio, pago_select_inquilino, pago_monto, gasto_inicio, gasto_monto,
    gasto_desc, ver_resumen, informe_inicio, informe_mes_actual, informe_pedir_mes,
    informe_pedir_anio, generar_informe_mensual_custom, deshacer_menu, deshacer_pago_handler,
    deshacer_gasto_handler, volver_menu, error_handler, volver_menu_principal,
    gestionar_inquilinos_menu, add_inquilino_prompt, add_inquilino_save, list_inquilinos,
    deactivate_inquilino_prompt, deactivate_inquilino_update, activate_inquilino_prompt,
    activate_inquilino_update, set_dia_pago_start, set_dia_pago_select_inquilino, set_dia_pago_save,
    editar_inicio, editar_mes_actual, editar_pedir_mes,
    editar_pedir_anio, editar_listar_transacciones_custom, editar_seleccionar_transaccion,
    editar_ejecutar_borrado, enviar_recordatorios_pago,
    MENU, PAGO_SELECT_INQUILINO, PAGO_MONTO, GASTO_MONTO, GASTO_DESC, INFORME_MES, 
    INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR, INQUILINO_MENU, INQUILINO_ADD_NOMBRE,
    INQUILINO_DEACTIVATE_SELECT, INQUILINO_ACTIVATE_SELECT, EDITAR_INICIO, EDITAR_PEDIR_ANIO,
    EDITAR_PEDIR_MES, EDITAR_SELECCIONAR_TRANSACCION, EDITAR_CONFIRMAR_BORRADO,
    INQUILINO_SET_DIA_PAGO_SELECT, INQUILINO_SET_DIA_PAGO_SAVE
)

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main() -> None:
    """Inicia el bot y configura el manejo del ciclo de vida."""
    if not BOT_TOKEN:
        logging.critical("ERROR: No se encontró el token del bot. Define la variable de entorno BOT_TOKEN.")
        exit(1)

    async def post_init_with_db(application: Application):
        """Función asíncrona para ejecutar después de la inicialización de la aplicación."""
        await init_pool()
        await inicializar_db()
        logging.info("Pool de DB y tablas inicializados.")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init_with_db)
        .post_shutdown(close_pool)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                MessageHandler(filters.Regex("^📥 Registrar Pago$"), pago_inicio),
                MessageHandler(filters.Regex("^💸 Registrar Gasto$"), gasto_inicio),
                MessageHandler(filters.Regex("^👤 Gestionar Inquilinos$"), gestionar_inquilinos_menu),
                MessageHandler(filters.Regex("^✏️ Editar/Borrar$"), editar_inicio),
                MessageHandler(filters.Regex("^📊 Ver Resumen$"), ver_resumen),
                MessageHandler(filters.Regex("^📈 Generar Informe$"), informe_inicio),
                MessageHandler(filters.Regex("^🗑️ Deshacer$"), deshacer_menu),
            ],
            # Flujo de pago
            PAGO_SELECT_INQUILINO: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), pago_select_inquilino)],
            PAGO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), pago_monto)],
            
            # Flujo de gasto
            GASTO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), gasto_monto)],
            GASTO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), gasto_desc)],

            # Flujo de informes
            INFORME_MES: [
                MessageHandler(filters.Regex("^Informe Mes Actual$"), informe_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), informe_pedir_mes),
            ],
            INFORME_ANIO: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), informe_pedir_anio)],
            INFORME_GENERAR: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), generar_informe_mensual_custom)],

            # Flujo de deshacer
            DESHACER_MENU: [
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Pago$"), deshacer_pago_handler),
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Gasto$"), deshacer_gasto_handler),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú$"), volver_menu_principal),
            ],

            # Flujo de gestión de inquilinos
            INQUILINO_MENU: [
                MessageHandler(filters.Regex("^➕ Añadir Inquilino$"), add_inquilino_prompt),
                MessageHandler(filters.Regex("^📋 Listar Inquilinos$"), list_inquilinos),
                MessageHandler(filters.Regex("^🗓️ Asignar Día de Pago$"), set_dia_pago_start),
                MessageHandler(filters.Regex("^❌ Desactivar Inquilino$"), deactivate_inquilino_prompt),
                MessageHandler(filters.Regex("^✅ Activar Inquilino$"), activate_inquilino_prompt),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú Principal$"), start),
            ],
            INQUILINO_ADD_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), add_inquilino_save)],
            INQUILINO_DEACTIVATE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), deactivate_inquilino_update)],
            INQUILINO_ACTIVATE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), activate_inquilino_update)],
            INQUILINO_SET_DIA_PAGO_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), set_dia_pago_select_inquilino)],
            INQUILINO_SET_DIA_PAGO_SAVE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), set_dia_pago_save)],

            # Flujo de editar/borrar
            EDITAR_INICIO: [
                MessageHandler(filters.Regex("^Mes Actual$"), editar_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), editar_pedir_mes),
            ],
            EDITAR_PEDIR_ANIO: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), editar_pedir_anio)],
            EDITAR_PEDIR_MES: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), editar_listar_transacciones_custom)],
            EDITAR_SELECCIONAR_TRANSACCION: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancelar$"), editar_seleccionar_transaccion)],
            EDITAR_CONFIRMAR_BORRADO: [MessageHandler(filters.Regex("^Sí, borrar$"), editar_ejecutar_borrado)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", volver_menu),
            MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu),
            MessageHandler(filters.Regex("^No, cancelar$"), volver_menu),
        ]
    )

    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    # Programar la tarea de recordatorios diarios
    job_queue = app.job_queue
    if job_queue:
        # Tarea temporal para probar los recordatorios al iniciar
        job_queue.run_once(
            enviar_recordatorios_pago,
            when=10,  # 10 segundos
            chat_id=AUTHORIZED_USERS[0],
            name="test_recordatorio_inicio"
        )
        logging.info("Tarea de prueba de recordatorios programada para ejecutarse en 10 segundos.")

        job_queue.run_daily(
            enviar_recordatorios_pago,
            time=time(hour=13, minute=0, second=0),  # 9:00 AM en Santo Domingo (UTC-4)
            chat_id=AUTHORIZED_USERS[0],
            name="recordatorio_pago_diario"
        )
        logging.info("Tarea de recordatorios de pago programada diariamente a las 13:00 UTC.")

    print("Bot iniciado correctamente! Presiona Ctrl+C para detener.")
    
    app.run_polling()

if __name__ == '__main__':
    main()
