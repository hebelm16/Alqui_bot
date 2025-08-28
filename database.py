import os
import aiopg
import logging
from urllib.parse import urlparse
from config import COMMISSION_RATE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)

pool = None

async def init_pool():
    """Inicializa el pool de conexiones a la base de datos."""
    global pool
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        url = urlparse(database_url)
        dsn = f"dbname={url.path[1:]} user={url.username} password={url.password} host={url.hostname} port={url.port}"
    else:
        dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"

    try:
        pool = await aiopg.create_pool(dsn)
        logger.info("Pool de conexiones a la base de datos inicializado.")
    except Exception as e:
        logger.error(f"Error al inicializar el pool de conexiones: {e}")
        raise

async def close_pool():
    """Cierra el pool de conexiones."""
    global pool
    if pool:
        pool.close()
        await pool.wait_closed()
        logger.info("Pool de conexiones cerrado.")

async def inicializar_db():
    """Crea las tablas de la base de datos si no existen."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS pagos (
                    id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    inquilino TEXT NOT NULL,
                    monto REAL NOT NULL
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    descripcion TEXT NOT NULL,
                    monto REAL NOT NULL
                )
            """)
            logger.info("Base de datos inicializada correctamente.")

# --- Funciones para registrar ---

async def registrar_pago(fecha: str, inquilino: str, monto: float) -> int:
    """Registra un nuevo pago en la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO pagos (fecha, inquilino, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, inquilino, monto))
            pago_id = await cur.fetchone()
            logger.info(f"Pago registrado con ID: {pago_id[0]}")
            return pago_id[0]

async def registrar_gasto(fecha: str, descripcion: str, monto: float) -> int:
    """Registra un nuevo gasto en la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO gastos (fecha, descripcion, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, descripcion, monto))
            gasto_id = await cur.fetchone()
            logger.info(f"Gasto registrado con ID: {gasto_id[0]}")
            return gasto_id[0]

# --- Funciones para deshacer ---

async def deshacer_ultimo_pago() -> tuple:
    """Elimina el último pago registrado y devuelve sus detalles."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Primero, obtenemos el último pago
            await cur.execute("SELECT id, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 1")
            ultimo_pago = await cur.fetchone()
            if ultimo_pago:
                pago_id, inquilino, monto = ultimo_pago
                # Ahora, lo eliminamos
                await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
                logger.info(f"Pago con ID {pago_id} eliminado.")
                return inquilino, monto
            return None, None

async def deshacer_ultimo_gasto() -> tuple:
    """Elimina el último gasto registrado y devuelve sus detalles."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Primero, obtenemos el último gasto
            await cur.execute("SELECT id, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 1")
            ultimo_gasto = await cur.fetchone()
            if ultimo_gasto:
                gasto_id, descripcion, monto = ultimo_gasto
                # Ahora, lo eliminamos
                await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
                logger.info(f"Gasto con ID {gasto_id} eliminado.")
                return descripcion, monto
            return None, None

# --- Funciones para informes ---

async def obtener_resumen() -> dict:
    """Calcula el resumen de ingresos, gastos, comisión y neto."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Total Ingresos
            await cur.execute("SELECT SUM(monto) FROM pagos")
            total_pagos = (await cur.fetchone())[0] or 0.0

            # Total Gastos
            await cur.execute("SELECT SUM(monto) FROM gastos")
            total_gastos = (await cur.fetchone())[0] or 0.0

            # Últimos 3 pagos
            await cur.execute("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
            ultimos_pagos = await cur.fetchall()

            # Últimos 3 gastos
            await cur.execute("SELECT fecha, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 3")
            ultimos_gastos = await cur.fetchall()

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

async def obtener_informe_mensual(mes: int, anio: int) -> dict:
    """Calcula el informe mensual de ingresos, gastos, comisión y neto para un mes y año específicos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Total Ingresos para el mes/año
            await cur.execute("SELECT SUM(monto) FROM pagos WHERE DATE_PART('month', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s AND DATE_PART('year', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s", (mes, anio))
            total_pagos_mes = (await cur.fetchone())[0] or 0.0

            # Total Gastos para el mes/año
            await cur.execute("SELECT SUM(monto) FROM gastos WHERE DATE_PART('month', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s AND DATE_PART('year', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s", (mes, anio))
            total_gastos_mes = (await cur.fetchone())[0] or 0.0

            # Pagos del mes
            await cur.execute("SELECT fecha, inquilino, monto FROM pagos WHERE DATE_PART('month', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s AND DATE_PART('year', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s ORDER BY id ASC", (mes, anio))
            pagos_mes = await cur.fetchall()

            # Gastos del mes
            await cur.execute("SELECT fecha, descripcion, monto FROM gastos WHERE DATE_PART('month', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s AND DATE_PART('year', TO_TIMESTAMP(fecha, 'DD/MM/YYYY HH24:MI')) = %s ORDER BY id ASC", (mes, anio))
            gastos_mes = await cur.fetchall()

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