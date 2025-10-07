from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import logging

from config import BOT_TOKEN
from database import inicializar_db, init_pool, close_pool
from handlers import (
    start, pago_inicio, pago_select_inquilino, pago_monto, gasto_inicio, gasto_monto,
    gasto_desc, ver_resumen, informe_inicio, informe_mes_actual, informe_pedir_mes,
    informe_pedir_anio, generar_informe_mensual_custom, deshacer_menu, deshacer_pago_handler,
    deshacer_gasto_handler, volver_menu, error_handler, volver_menu_principal,
    gestionar_inquilinos_menu, add_inquilino_prompt, add_inquilino_save, list_inquilinos,
    deactivate_inquilino_prompt, deactivate_inquilino_update, activate_inquilino_prompt,
    activate_inquilino_update,
    MENU, PAGO_SELECT_INQUILINO, PAGO_MONTO, GASTO_MONTO, GASTO_DESC, INFORME_MES, 
    INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR, INQUILINO_MENU, INQUILINO_ADD_NOMBRE,
    INQUILINO_DEACTIVATE_SELECT, INQUILINO_ACTIVATE_SELECT
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
                MessageHandler(filters.Regex("^📊 Ver Resumen$"), ver_resumen),
                MessageHandler(filters.Regex("^📈 Generar Informe$"), informe_inicio),
                MessageHandler(filters.Regex("^🗑️ Deshacer$"), deshacer_menu),
            ],
            # Flujo de pago actualizado
            PAGO_SELECT_INQUILINO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_select_inquilino)],
            PAGO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_monto)],
            
            # Flujo de gasto (sin cambios)
            GASTO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_monto)],
            GASTO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_desc)],

            # Flujo de informes (sin cambios)
            INFORME_MES: [
                MessageHandler(filters.Regex("^Informe Mes Actual$"), informe_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), informe_pedir_mes),
            ],
            INFORME_ANIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, informe_pedir_anio)],
            INFORME_GENERAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, generar_informe_mensual_custom)],

            # Flujo de deshacer (sin cambios)
            DESHACER_MENU: [
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Pago$"), deshacer_pago_handler),
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Gasto$"), deshacer_gasto_handler),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú$"), volver_menu_principal),
            ],

            # Flujo de gestión de inquilinos
            INQUILINO_MENU: [
                MessageHandler(filters.Regex("^➕ Añadir Inquilino$"), add_inquilino_prompt),
                MessageHandler(filters.Regex("^📋 Listar Inquilinos$"), list_inquilinos),
                MessageHandler(filters.Regex("^❌ Desactivar Inquilino$"), deactivate_inquilino_prompt),
                MessageHandler(filters.Regex("^✅ Activar Inquilino$"), activate_inquilino_prompt),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú Principal$"), start),
            ],
            INQUILINO_ADD_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_inquilino_save)],
            INQUILINO_DEACTIVATE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deactivate_inquilino_update)],
            INQUILINO_ACTIVATE_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, activate_inquilino_update)],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", volver_menu),
            MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu),
        ]
    )

    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    print("Bot iniciado correctamente! Presiona Ctrl+C para detener.")
    
    app.run_polling()

if __name__ == '__main__':
    main()
