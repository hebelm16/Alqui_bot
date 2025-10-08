import os
import aiopg
import logging
from urllib.parse import urlparse
from decimal import Decimal
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
    """Crea las tablas de la base de datos si no existen y migra el tipo de dato de monto si es necesario."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Crear tabla de inquilinos
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS inquilinos (
                    id SERIAL PRIMARY KEY,
                    nombre TEXT NOT NULL UNIQUE,
                    activo BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)

            # Crear tablas con el tipo de dato correcto
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS pagos (
                    id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    inquilino TEXT NOT NULL,
                    monto NUMERIC(10, 2) NOT NULL,
                    UNIQUE(inquilino, fecha)
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    fecha DATE NOT NULL,
                    descripcion TEXT NOT NULL,
                    monto NUMERIC(10, 2) NOT NULL
                )
            """)

            # --- Migración para cambiar REAL a NUMERIC ---
            # Verificar y alterar la tabla de pagos
            await cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'pagos' AND column_name = 'monto';
            """)
            result = await cur.fetchone()
            if result and result[0] == 'real':
                logger.info("Migrando tipo de dato de 'monto' en la tabla 'pagos' de REAL a NUMERIC(10, 2)...")
                await cur.execute("ALTER TABLE pagos ALTER COLUMN monto TYPE NUMERIC(10, 2);")
                logger.info("Migración de 'pagos' completada.")

            # Verificar y alterar la tabla de gastos
            await cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_name = 'gastos' AND column_name = 'monto';
            """)
            result = await cur.fetchone()
            if result and result[0] == 'real':
                logger.info("Migrando tipo de dato de 'monto' en la tabla 'gastos' de REAL a NUMERIC(10, 2)...")
                await cur.execute("ALTER TABLE gastos ALTER COLUMN monto TYPE NUMERIC(10, 2);")
                logger.info("Migración de 'gastos' completada.")

            logger.info("Base de datos inicializada y/o migrada correctamente.")

# --- Funciones para registrar ---

async def registrar_pago(fecha: str, inquilino: str, monto: Decimal) -> int:
    """Registra un nuevo pago en la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO pagos (fecha, inquilino, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, inquilino, monto))
            pago_id = await cur.fetchone()
            logger.info(f"Pago registrado con ID: {pago_id[0]}")
            return pago_id[0]

async def registrar_gasto(fecha: str, descripcion: str, monto: Decimal) -> int:
    """Registra un nuevo gasto en la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO gastos (fecha, descripcion, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, descripcion, monto))
            gasto_id = await cur.fetchone()
            logger.info(f"Gasto registrado con ID: {gasto_id[0]}")
            return gasto_id[0]

# --- Funciones para deshacer ---

async def deshacer_ultimo_pago() -> tuple:
    """Elimina el último pago registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                # Primero, obtenemos y bloqueamos el último pago
                await cur.execute("SELECT id, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 1 FOR UPDATE")
                ultimo_pago = await cur.fetchone()
                if ultimo_pago:
                    pago_id, inquilino, monto = ultimo_pago
                    # Ahora, lo eliminamos
                    await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
                    logger.info(f"Pago con ID {pago_id} eliminado.")
                    return inquilino, monto
                return None, None

async def deshacer_ultimo_gasto() -> tuple:
    """Elimina el último gasto registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                # Primero, obtenemos y bloqueamos el último gasto
                await cur.execute("SELECT id, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 1 FOR UPDATE")
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
            total_pagos = (await cur.fetchone())[0] or Decimal('0.0')

            # Total Gastos
            await cur.execute("SELECT SUM(monto) FROM gastos")
            total_gastos = (await cur.fetchone())[0] or Decimal('0.0')

            # Últimos 3 pagos
            await cur.execute("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
            ultimos_pagos = await cur.fetchall()

            # Últimos 3 gastos
            await cur.execute("SELECT fecha, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 3")
            ultimos_gastos = await cur.fetchall()

    commission_rate_decimal = Decimal(str(COMMISSION_RATE))
    total_comision = total_pagos * commission_rate_decimal
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
            await cur.execute("SELECT SUM(monto) FROM pagos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s", (mes, anio))
            total_pagos_mes = (await cur.fetchone())[0] or Decimal('0.0')

            # Total Gastos para el mes/año
            await cur.execute("SELECT SUM(monto) FROM gastos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s", (mes, anio))
            total_gastos_mes = (await cur.fetchone())[0] or Decimal('0.0')

            # Pagos del mes
            await cur.execute("SELECT id, fecha, inquilino, monto FROM pagos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s ORDER BY id ASC", (mes, anio))
            pagos_mes = await cur.fetchall()

            # Gastos del mes
            await cur.execute("SELECT id, fecha, descripcion, monto FROM gastos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s ORDER BY id ASC", (mes, anio))
            gastos_mes = await cur.fetchall()

    commission_rate_decimal = Decimal(str(COMMISSION_RATE))
    total_comision_mes = total_pagos_mes * commission_rate_decimal
    monto_neto_mes = total_pagos_mes - total_comision_mes - total_gastos_mes

    return {
        "total_ingresos": total_pagos_mes,
        "total_comision": total_comision_mes,
        "total_gastos": total_gastos_mes,
        "monto_neto": monto_neto_mes,
        "pagos_mes": pagos_mes,
        "gastos_mes": gastos_mes
    }

# --- Funciones para Inquilinos ---

async def crear_inquilino(nombre: str) -> int:
    """Crea un nuevo inquilino en la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO inquilinos (nombre) VALUES (%s) RETURNING id", (nombre,))
            inquilino_id = await cur.fetchone()
            logger.info(f"Inquilino '{nombre}' creado con ID: {inquilino_id[0]}")
            return inquilino_id[0]

async def obtener_inquilinos(activos_only: bool = True) -> list:
    """Obtiene una lista de inquilinos. Por defecto, solo los activos."""
    query = "SELECT id, nombre, activo FROM inquilinos"
    if activos_only:
        query += " WHERE activo = TRUE"
    query += " ORDER BY nombre ASC"
    
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query)
            return await cur.fetchall()

async def obtener_inquilino_por_id(inquilino_id: int) -> tuple:
    """Obtiene un inquilino por su ID."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, nombre, activo FROM inquilinos WHERE id = %s", (inquilino_id,))
            return await cur.fetchone()

async def cambiar_estado_inquilino(inquilino_id: int, estado: bool) -> bool:
    """Cambia el estado de un inquilino (activo/inactivo)."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE inquilinos SET activo = %s WHERE id = %s", (estado, inquilino_id))
            return cur.rowcount > 0

# --- Funciones para Borrar Específicos ---

async def delete_pago_by_id(pago_id: int) -> bool:
    """Elimina un pago específico por su ID."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
            if cur.rowcount > 0:
                logger.info(f"Pago con ID {pago_id} eliminado.")
                return True
            return False

async def delete_gasto_by_id(gasto_id: int) -> bool:
    """Elimina un gasto específico por su ID."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
            if cur.rowcount > 0:
                logger.info(f"Gasto con ID {gasto_id} eliminado.")
                return True
            return False