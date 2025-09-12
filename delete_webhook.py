import requests
from dotenv import load_dotenv
import os
from pathlib import Path

# Construye la ruta al archivo .env en el directorio base del proyecto
dotenv_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=dotenv_path)
BOT_TOKEN = os.getenv('BOT_TOKEN')

url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
response = requests.get(url)

if response.status_code == 200:
    print("Webhook eliminado exitosamente.")
    print(response.json())
else:
    print(f"Error al eliminar el webhook: {response.status_code}")
    print(response.json())