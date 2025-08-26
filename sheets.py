import gspread
from google.oauth2.service_account import Credentials
import logging
import time
import os
from config import (
    CREDS_FILE, SPREADSHEET_NAME, PAGOS_SHEET_NAME, 
    GASTOS_SHEET_NAME, RESUMEN_SHEET_NAME, COMMISSION_RATE
)

logger = logging.getLogger(__name__)

# === Inicialización de Google Sheets ===
try:
    if not os.path.exists(CREDS_FILE):
        logger.error(f"Archivo de credenciales {CREDS_FILE} no encontrado.")
        exit(1)

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
        logger.info(f"Conexión exitosa a la hoja de cálculo: {SPREADSHEET_NAME}")

        sheet_pagos = spreadsheet.worksheet(PAGOS_SHEET_NAME)
        sheet_gastos = spreadsheet.worksheet(GASTOS_SHEET_NAME)
        sheet_resumen = spreadsheet.worksheet(RESUMEN_SHEET_NAME)

        # Verificar y agregar encabezados si es necesario
        if not sheet_pagos.row_values(1):
            sheet_pagos.append_row(["Fecha", "Inquilino", "Monto"])
            logger.info(f"Encabezados añadidos a la hoja {PAGOS_SHEET_NAME}")
        
        if not sheet_gastos.row_values(1):
            sheet_gastos.append_row(["Fecha", "Descripción", "Monto"])
            logger.info(f"Encabezados añadidos a la hoja {GASTOS_SHEET_NAME}")

        if not sheet_resumen.row_values(1) or "Concepto" not in sheet_resumen.row_values(1):
            sheet_resumen.update('A1:B1', [["Concepto", "Monto"]])
            sheet_resumen.update('A2:A5', [
                ["Total Ingresos"],
                [f"Total Comisión ({COMMISSION_RATE:.0%})"], 
                ["Total Gastos"],
                ["Monto Neto"]
            ])
            sheet_resumen.update('B2:B5', [["RD$0.00"], ["RD$0.00"], ["RD$0.00"], ["RD$0.00"]])
            logger.info(f"Hoja {RESUMEN_SHEET_NAME} configurada con estructura inicial")

    except gspread.exceptions.SpreadsheetNotFound:
        logger.error(f"No se encontró la hoja de cálculo: {SPREADSHEET_NAME}.")
        exit(1)
    except gspread.exceptions.WorksheetNotFound as e:
        logger.error(f"No se encontró alguna de las hojas: {e}.")
        exit(1)

except Exception as e:
    logger.error(f"Error al configurar Google Sheets: {e}")
    exit(1)

# === Funciones de Sheets ===

async def actualizar_resumen():
    """Actualiza la hoja Resumen basado en los datos de Pagos y Gastos"""
    try:
        time.sleep(1) # Pequeño retraso para evitar límites de tasa

        pagos_datos = sheet_pagos.get_all_values()[1:]
        gastos_datos = sheet_gastos.get_all_values()[1:]

        total_pagos = 0.0
        for fila in pagos_datos:
            if len(fila) >= 3 and fila[2].strip():
                try:
                    total_pagos += float(fila[2].replace(',', '').replace('RD$', '').strip())
                except ValueError:
                    logger.warning(f"Valor no numérico en pagos: {fila[2]}")
        
        total_gastos = 0.0
        for fila in gastos_datos:
            if len(fila) >= 3 and fila[2].strip():
                try:
                    total_gastos += float(fila[2].replace(',', '').replace('RD$', '').strip())
                except ValueError:
                    logger.warning(f"Valor no numérico en gastos: {fila[2]}")

        total_comision = total_pagos * COMMISSION_RATE
        monto_neto = total_pagos - total_comision - total_gastos

        time.sleep(1) # Pequeño retraso antes de actualizar

        sheet_resumen.update('A3', f"Total Comisión ({COMMISSION_RATE:.0%})")
        sheet_resumen.update('B2:B5', [
            [f"RD${total_pagos:.2f}"],
            [f"RD${total_comision:.2f}"],
            [f"RD${total_gastos:.2f}"],
            [f"RD${monto_neto:.2f}"]
        ])
        
        logger.info("Hoja Resumen actualizada correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al actualizar la hoja Resumen: {e}")
        return False
