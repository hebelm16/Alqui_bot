import os
from pathlib import Path
from dotenv import load_dotenv

# Construye la ruta al archivo .env en el directorio base del proyecto
dotenv_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

# === Configuración de Autenticación ===
# Lista de IDs de usuarios de Telegram autorizados.
# Se carga desde la variable de entorno AUTHORIZED_USERS_CSV (separados por coma).
# Si no se define, se usa un valor por defecto.
authorized_users_csv = os.getenv("AUTHORIZED_USERS_CSV", "13814098")
try:
    AUTHORIZED_USERS = [int(user_id.strip()) for user_id in authorized_users_csv.split(',')]
except (ValueError, AttributeError):
    print("ADVERTENCIA: La lista de usuarios autorizados (AUTHORIZED_USERS_CSV) no es válida. Usando valor por defecto.")
    AUTHORIZED_USERS = [13814098]

# === Configuración del Bot ===
# Token del bot de Telegram, obtenido de una variable de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === Configuración de la Base de Datos PostgreSQL ===
DB_HOST = os.getenv("PGHOST")
DB_PORT = os.getenv("PGPORT")
DB_NAME = os.getenv("PGDATABASE")
DB_USER = os.getenv("PGUSER")
DB_PASSWORD = os.getenv("PGPASSWORD")

# === Configuración de Negocio ===
# Tasa de comisión sobre los ingresos (ej: 0.05 para 5%)
COMMISSION_RATE = 0.05
#