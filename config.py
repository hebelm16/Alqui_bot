import os
from dotenv import load_dotenv

load_dotenv()

# === Configuración de Autenticación ===
# Lista de IDs de usuarios de Telegram autorizados
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
