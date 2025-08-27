from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
import logging
from config import BOT_TOKEN
from database import inicializar_db
from handlers import (
    start, pago_inicio, pago_monto, pago_nombre, gasto_inicio, gasto_monto, 
    gasto_desc, ver_resumen, deshacer, volver, cancelar, error_handler, 
    MENU, PAGO_MONTO, PAGO_NOMBRE, GASTO_MONTO, GASTO_DESC
)

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    inicializar_db()
    if not BOT_TOKEN:
        logging.critical("ERROR: No se encontró el token del bot. Define la variable de entorno BOT_TOKEN.")
        exit(1)

    try:
        app = Application.builder().token(BOT_TOKEN).build()

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
        app.add_error_handler(error_handler)

        print("Bot iniciado correctamente! Presiona Ctrl+C para detener.")
        app.run_polling()

    except Exception as e:
        logging.critical(f"Error al iniciar el bot: {e}")

if __name__ == '__main__':
    main()
