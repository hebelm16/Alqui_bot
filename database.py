import os
import aiopg
import logging
from urllib.parse import urlparse
from decimal import Decimal
from datetime import date, timedelta
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
    """Crea las tablas de la base de datos si no existen y realiza migraciones."""
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

            # Crear tablas de pagos y gastos
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

            # --- Migración para añadir columna dia_pago a inquilinos ---
            await cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='inquilinos' AND column_name='dia_pago'")
            if not await cur.fetchone():
                logger.info("Añadiendo columna 'dia_pago' a la tabla 'inquilinos'...")
                await cur.execute("ALTER TABLE inquilinos ADD COLUMN dia_pago INTEGER;")
                logger.info("Columna 'dia_pago' añadida.")

            # --- Migración para cambiar REAL a NUMERIC ---
            await cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'pagos' AND column_name = 'monto';")
            if (result := await cur.fetchone()) and result[0] == 'real':
                logger.info("Migrando tipo de dato de 'monto' en la tabla 'pagos' de REAL a NUMERIC(10, 2)...")
                await cur.execute("ALTER TABLE pagos ALTER COLUMN monto TYPE NUMERIC(10, 2);")
                logger.info("Migración de 'pagos' completada.")

            await cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'gastos' AND column_name = 'monto';")
            if (result := await cur.fetchone()) and result[0] == 'real':
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
                await cur.execute("SELECT id, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 1 FOR UPDATE")
                if ultimo_pago := await cur.fetchone():
                    pago_id, inquilino, monto = ultimo_pago
                    await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
                    logger.info(f"Pago con ID {pago_id} eliminado.")
                    return inquilino, monto
                return None, None

async def deshacer_ultimo_gasto() -> tuple:
    """Elimina el último gasto registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute("SELECT id, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 1 FOR UPDATE")
                if ultimo_gasto := await cur.fetchone():
                    gasto_id, descripcion, monto = ultimo_gasto
                    await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
                    logger.info(f"Gasto con ID {gasto_id} eliminado.")
                    return descripcion, monto
                return None, None

# --- Funciones para informes ---

async def obtener_resumen() -> dict:
    """Calcula el resumen de ingresos, gastos, comisión y neto."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT SUM(monto) FROM pagos")
            total_pagos = (await cur.fetchone())[0] or Decimal('0.0')
            await cur.execute("SELECT SUM(monto) FROM gastos")
            total_gastos = (await cur.fetchone())[0] or Decimal('0.0')
            await cur.execute("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
            ultimos_pagos = await cur.fetchall()
            await cur.execute("SELECT fecha, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 3")
            ultimos_gastos = await cur.fetchall()

    total_comision = total_pagos * Decimal(str(COMMISSION_RATE))
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
    """Calcula el informe mensual de ingresos, gastos, comisión y neto."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT SUM(monto) FROM pagos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s", (mes, anio))
            total_pagos_mes = (await cur.fetchone())[0] or Decimal('0.0')
            await cur.execute("SELECT SUM(monto) FROM gastos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s", (mes, anio))
            total_gastos_mes = (await cur.fetchone())[0] or Decimal('0.0')
            await cur.execute("SELECT id, fecha, inquilino, monto FROM pagos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s ORDER BY id ASC", (mes, anio))
            pagos_mes = await cur.fetchall()
            await cur.execute("SELECT id, fecha, descripcion, monto FROM gastos WHERE EXTRACT(MONTH FROM fecha::date) = %s AND EXTRACT(YEAR FROM fecha::date) = %s ORDER BY id ASC", (mes, anio))
            gastos_mes = await cur.fetchall()

    total_comision_mes = total_pagos_mes * Decimal(str(COMMISSION_RATE))
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
    """Obtiene una lista de inquilinos con su día de pago. Por defecto, solo los activos."""
    query = "SELECT id, nombre, activo, dia_pago FROM inquilinos"
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
            await cur.execute("SELECT id, nombre, activo, dia_pago FROM inquilinos WHERE id = %s", (inquilino_id,))
            return await cur.fetchone()

async def cambiar_estado_inquilino(inquilino_id: int, estado: bool) -> bool:
    """Cambia el estado de un inquilino (activo/inactivo)."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE inquilinos SET activo = %s WHERE id = %s", (estado, inquilino_id))
            return cur.rowcount > 0

async def actualizar_dia_pago_inquilino(inquilino_id: int, dia_pago: int) -> bool:
    """Actualiza el día de pago para un inquilino específico."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE inquilinos SET dia_pago = %s WHERE id = %s", (dia_pago, inquilino_id))
            if cur.rowcount > 0:
                logger.info(f"Día de pago actualizado para inquilino ID {inquilino_id}.")
                return True
            return False

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

async def obtener_inquilinos_para_recordatorio() -> list:
    """
    Obtiene una lista de nombres de inquilinos activos que tienen un pago venciéndose en 2 días
    y que aún no han pagado en el mes actual.
    """
    inquilinos_a_notificar = []
    hoy = date.today()
    fecha_recordatorio = hoy + timedelta(days=2)
    dia_recordatorio = fecha_recordatorio.day
    mes_actual = hoy.month
    anio_actual = hoy.year

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            # 1. Encontrar inquilinos activos cuyo día de pago es el día del recordatorio
            await cur.execute(
                "SELECT nombre FROM inquilinos WHERE activo = TRUE AND dia_pago = %s",
                (dia_recordatorio,)
            )
            inquilinos_con_vencimiento = await cur.fetchall()

            if not inquilinos_con_vencimiento:
                return []

            # 2. Para cada inquilino, verificar si ya pagó este mes
            for inquilino in inquilinos_con_vencimiento:
                nombre_inquilino = inquilino[0]
                await cur.execute("""
                    SELECT 1 FROM pagos
                    WHERE inquilino = %s
                    AND EXTRACT(MONTH FROM fecha) = %s
                    AND EXTRACT(YEAR FROM fecha) = %s
                """, (nombre_inquilino, mes_actual, anio_actual))

                if not await cur.fetchone():
                    inquilinos_a_notificar.append(nombre_inquilino)

    return inquilinos_a_notificar
