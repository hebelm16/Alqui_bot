import os

# === Configuración de Autenticación ===
# Lista de IDs de usuarios de Telegram autorizados
AUTHORIZED_USERS = [13814098]

# === Configuración del Bot ===
# Token del bot de Telegram, obtenido de una variable de entorno
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === Configuración de Google Sheets ===
# Nombre del archivo de credenciales de Google
CREDS_FILE = "creds.json"

# Nombre de la hoja de cálculo principal
SPREADSHEET_NAME = "Registro de Alquileres"

# Nombres de las hojas individuales
PAGOS_SHEET_NAME = "Pagos"
GASTOS_SHEET_NAME = "Gastos"
RESUMEN_SHEET_NAME = "Resumen"

# === Configuración de Negocio ===
# Tasa de comisión sobre los ingresos (ej: 0.05 para 5%)
COMMISSION_RATE = 0.05
