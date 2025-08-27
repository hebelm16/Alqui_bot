from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import logging
import asyncio
from config import BOT_TOKEN
from database import inicializar_db, init_pool, close_pool
from handlers import (
    start, pago_inicio, pago_monto, pago_nombre, gasto_inicio, gasto_monto,
    gasto_desc, ver_resumen, informe_inicio, informe_mes_actual, informe_pedir_mes,
    informe_pedir_anio, generar_informe_mensual_custom, deshacer_menu, deshacer_pago_handler,
    deshacer_gasto_handler, volver_menu, error_handler, volver_menu_principal,
    MENU, PAGO_MONTO, PAGO_NOMBRE, GASTO_MONTO, GASTO_DESC, INFORME_MES, INFORME_ANIO, DESHACER_MENU, INFORME_GENERAR
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

    # Configurar la aplicación usando los hooks post_init y post_shutdown
    # para manejar el ciclo de vida de la conexión a la DB.
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
                MessageHandler(filters.Regex("^📊 Ver Resumen$"), ver_resumen),
                MessageHandler(filters.Regex("^📈 Generar Informe$"), informe_inicio),
                MessageHandler(filters.Regex("^🗑️ Deshacer$"), deshacer_menu),
            ],
            PAGO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_monto)],
            PAGO_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pago_nombre)],
            GASTO_MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_monto)],
            GASTO_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, gasto_desc)],
            INFORME_MES: [
                MessageHandler(filters.Regex("^Informe Mes Actual$"), informe_mes_actual),
                MessageHandler(filters.Regex("^Elegir Mes y Año$"), informe_pedir_mes),
                MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu),
            ],
            INFORME_ANIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, informe_pedir_anio),
                MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu),
            ],
            INFORME_GENERAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generar_informe_mensual_custom),
                MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu),
            ],
            DESHACER_MENU: [
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Pago$"), deshacer_pago_handler),
                MessageHandler(filters.Regex("^🗑️ Deshacer Último Gasto$"), deshacer_gasto_handler),
                MessageHandler(filters.Regex("^⬅️ Volver al Menú$"), volver_menu_principal),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", volver_menu),
            MessageHandler(filters.Regex("^❌ Cancelar$"), volver_menu),
            MessageHandler(filters.Regex("^⬅️ Volver al menú$"), volver_menu_principal),
        ]
    )

    app.add_handler(conv_handler)
    app.add_error_handler(error_handler)

    print("Bot iniciado correctamente! Presiona Ctrl+C para detener.")
    
    # run_polling en un contexto síncrono maneja el loop de asyncio internamente.
    app.run_polling()

if __name__ == '__main__':
    main()
