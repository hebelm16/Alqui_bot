import os
import psycopg2
import logging
from urllib.parse import urlparse
from config import COMMISSION_RATE

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establece y retorna una conexión a la base de datos PostgreSQL."""
    try:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            logger.info(f"Attempting to connect using DATABASE_URL: {database_url}")
            url = urlparse(database_url)
            conn = psycopg2.connect(
                host=url.hostname,
                port=url.port,
                database=url.path[1:],
                user=url.username,
                password=url.password
            )
        else:
            logger.error("DATABASE_URL environment variable not set.")
            raise ValueError("DATABASE_URL environment variable not set.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error al conectar a la base de datos PostgreSQL: {e}")
        raise

def inicializar_db():
    """Crea las tablas de la base de datos si no existen."""
    try:
        con = get_db_connection()
        cur = con.cursor()

        # Crear tabla de pagos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pagos (
                id SERIAL PRIMARY KEY,
                fecha TEXT NOT NULL,
                inquilino TEXT NOT NULL,
                monto REAL NOT NULL
            )
        """)

        # Crear tabla de gastos
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gastos (
                id SERIAL PRIMARY KEY,
                fecha TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto REAL NOT NULL
            )
        """)

        con.commit()
        con.close()
        logger.info("Base de datos inicializada correctamente.")
    except psycopg2.Error as e: # Changed from sqlite3.Error
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise

# --- Funciones para registrar ---

def registrar_pago(fecha: str, inquilino: str, monto: float) -> int:
    """Registra un nuevo pago en la base de datos."""
    try:
        con = get_db_connection() # Changed
        cur = con.cursor()
        cur.execute("INSERT INTO pagos (fecha, inquilino, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, inquilino, monto)) # Changed placeholders
        pago_id = cur.fetchone()[0]
        con.commit()
        con.close()
        logger.info(f"Pago registrado con ID: {pago_id}")
        return pago_id
    except psycopg2.Error as e: # Changed from sqlite3.Error
        logger.error(f"Error al registrar pago en la DB: {e}")
        raise

def registrar_gasto(fecha: str, descripcion: str, monto: float) -> int:
    """Registra un nuevo gasto en la base de datos."""
    try:
        con = get_db_connection() # Changed
        cur = con.cursor()
        cur.execute("INSERT INTO gastos (fecha, descripcion, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, descripcion, monto)) # Changed placeholders
        gasto_id = cur.fetchone()[0]
        con.commit()
        con.close()
        logger.info(f"Gasto registrado con ID: {gasto_id}")
        return gasto_id
    except psycopg2.Error as e: # Changed from sqlite3.Error
        logger.error(f"Error al registrar gasto en la DB: {e}")
        raise

# --- Funciones para deshacer ---

def deshacer_ultimo_pago(pago_id: int):
    """Elimina un pago por su ID."""
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,)) # Changed placeholder
        con.commit()
        con.close()
        logger.info(f"Pago con ID {pago_id} eliminado.")
    except psycopg2.Error as e: # Changed from sqlite3.Error
        logger.error(f"Error al eliminar pago de la DB: {e}")
        raise

def deshacer_ultimo_gasto(gasto_id: int):
    """Elimina un gasto por su ID."""
    try:
        con = get_db_connection()
        cur = con.cursor()
        cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,)) # Changed placeholder
        con.commit()
        con.close()
        logger.info(f"Gasto con ID {gasto_id} eliminado.")
    except psycopg2.Error as e: # Changed from sqlite3.Error
        logger.error(f"Error al eliminar gasto de la DB: {e}")
        raise

# --- Funciones para informes ---

def obtener_resumen() -> dict:
    """Calcula el resumen de ingresos, gastos, comisión y neto."""
    try:
        con = get_db_connection()
        cur = con.cursor()

        # Total Ingresos
        cur.execute("SELECT SUM(monto) FROM pagos")
        total_pagos = cur.fetchone()[0] or 0.0

        # Total Gastos
        cur.execute("SELECT SUM(monto) FROM gastos")
        total_gastos = cur.fetchone()[0] or 0.0
        
        # Últimos 3 pagos
        cur.execute("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
        ultimos_pagos = cur.fetchall()

        # Últimos 3 gastos
        cur.execute("SELECT fecha, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 3")
        ultimos_gastos = cur.fetchall()

        con.close()

        total_comision = total_pagos * COMMISSION_RATE
        monto_neto = total_pagos - total_comision - total_gastos

        return {
            "total_ingresos": total_pagos,
            "total_comision": total_comision,
            "total_gastos": total_gastos,
            "monto_neto": monto_neto,
            "ultimos_pagos": ultimos_pagos,
            "ultimos_gastos": ultimos_gastos
        }
    except psycopg2.Error as e:
        logger.error(f"Error al obtener resumen de la DB: {e}")
        raise

def obtener_informe_mensual(mes: int, anio: int) -> dict:
    """Calcula el informe mensual de ingresos, gastos, comisión y neto para un mes y año específicos."""
    try:
        con = get_db_connection() # Changed
        cur = con.cursor()

        # Formato de fecha en la DB es "DD/MM/YYYY HH:MM"
        # Necesitamos filtrar por mes y año
        # Usamos substring para buscar el patrón de mes/año en la fecha
        mes_str = f"{mes:02d}" # Asegura que el mes tenga 2 dígitos (ej: 01, 02)

        # Total Ingresos para el mes/año
        cur.execute(f"SELECT SUM(monto) FROM pagos WHERE substring(fecha, 4, 2) = %s AND substring(fecha, 7, 4) = %s", (mes_str, str(anio))) # Changed substring and placeholders
        total_pagos_mes = cur.fetchone()[0] or 0.0

        # Total Gastos para el mes/año
        cur.execute(f"SELECT SUM(monto) FROM gastos WHERE substring(fecha, 4, 2) = %s AND substring(fecha, 7, 4) = %s", (mes_str, str(anio))) # Changed substring and placeholders
        total_gastos_mes = cur.fetchone()[0] or 0.0
        
        # Pagos del mes
        cur.execute(f"SELECT fecha, inquilino, monto FROM pagos WHERE substring(fecha, 4, 2) = %s AND substring(fecha, 7, 4) = %s ORDER BY id ASC", (mes_str, str(anio))) # Changed substring and placeholders
        pagos_mes = cur.fetchall()

        # Gastos del mes
        cur.execute(f"SELECT fecha, descripcion, monto FROM gastos WHERE substring(fecha, 4, 2) = %s AND substring(fecha, 7, 4) = %s ORDER BY id ASC", (mes_str, str(anio))) # Changed substring and placeholders
        gastos_mes = cur.fetchall()

        con.close()

        total_comision_mes = total_pagos_mes * COMMISSION_RATE
        monto_neto_mes = total_pagos_mes - total_comision_mes - total_gastos_mes

        return {
            "total_ingresos": total_pagos_mes,
            "total_comision": total_comision_mes,
            "total_gastos": total_gastos_mes,
            "monto_neto": monto_neto_mes,
            "pagos_mes": pagos_mes,
            "gastos_mes": gastos_mes
        }
    except psycopg2.Error as e: # Changed from sqlite3.Error
        logger.error(f"Error al obtener informe mensual de la DB: {e}")
        raise