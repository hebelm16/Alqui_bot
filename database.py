import os
import asyncpg
import logging
from decimal import Decimal
from datetime import date, timedelta
from config import COMMISSION_RATE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)

pool = None

async def init_pool(_=None):
    """Inicializa el pool de conexiones a la base de datos usando asyncpg."""
    global pool
    database_url = os.getenv("DATABASE_URL")

    dsn = None
    if database_url:
        # Log para depuración
        from urllib.parse import urlparse
        parsed_url = urlparse(database_url)
        logger.info(f"Conectando a la base de datos con: Usuario='{parsed_url.username}', Host='{parsed_url.hostname}', Puerto='{parsed_url.port}', DB='{parsed_url.path[1:]}'")
        
        # asyncpg puede usar la URL directamente
        dsn = database_url
    else:
        # Fallback para desarrollo local
        logger.info("DATABASE_URL no encontrada. Usando variables de entorno individuales.")
        dsn = f"postgres://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    try:
        pool = await asyncpg.create_pool(dsn)
        logger.info("Pool de conexiones a la base de datos (asyncpg) inicializado.")
    except Exception as e:
        logger.error(f"Error al inicializar el pool de conexiones (asyncpg): {e}")
        raise

async def close_pool(_=None):
    """Cierra el pool de conexiones."""
    global pool
    if pool:
        await pool.close()
        logger.info("Pool de conexiones (asyncpg) cerrado.")

async def inicializar_db():
    """Crea las tablas de la base de datos si no existen y realiza migraciones."""
    async with pool.acquire() as conn:
        # Crear tabla de inquilinos
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inquilinos (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                activo BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)

        # Crear tablas de pagos y gastos
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pagos (
                id SERIAL PRIMARY KEY,
                fecha DATE NOT NULL,
                inquilino TEXT NOT NULL,
                monto NUMERIC(10, 2) NOT NULL,
                UNIQUE(inquilino, fecha)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gastos (
                id SERIAL PRIMARY KEY,
                fecha DATE NOT NULL,
                descripcion TEXT NOT NULL,
                monto NUMERIC(10, 2) NOT NULL
            )
        """)

        # --- Migración para añadir columna dia_pago a inquilinos ---
        if not await conn.fetchrow("SELECT column_name FROM information_schema.columns WHERE table_name='inquilinos' AND column_name='dia_pago'"):
            logger.info("Añadiendo columna 'dia_pago' a la tabla 'inquilinos'...")
            await conn.execute("ALTER TABLE inquilinos ADD COLUMN dia_pago INTEGER;")
            logger.info("Columna 'dia_pago' añadida.")

        # --- Migración para cambiar REAL a NUMERIC ---
        pagos_monto_type = await conn.fetchval("SELECT data_type FROM information_schema.columns WHERE table_name = 'pagos' AND column_name = 'monto';")
        if pagos_monto_type == 'real':
            logger.info("Migrando tipo de dato de 'monto' en la tabla 'pagos' de REAL a NUMERIC(10, 2)...")
            await conn.execute("ALTER TABLE pagos ALTER COLUMN monto TYPE NUMERIC(10, 2);")
            logger.info("Migración de 'pagos' completada.")

        gastos_monto_type = await conn.fetchval("SELECT data_type FROM information_schema.columns WHERE table_name = 'gastos' AND column_name = 'monto';")
        if gastos_monto_type == 'real':
            logger.info("Migrando tipo de dato de 'monto' en la tabla 'gastos' de REAL a NUMERIC(10, 2)...")
            await conn.execute("ALTER TABLE gastos ALTER COLUMN monto TYPE NUMERIC(10, 2);")
            logger.info("Migración de 'gastos' completada.")

        logger.info("Base de datos inicializada y/o migrada correctamente.")

# --- Funciones para registrar ---

async def registrar_pago(fecha: str, inquilino: str, monto: Decimal) -> int:
    """Registra un nuevo pago en la base de datos."""
    async with pool.acquire() as conn:
        pago_id = await conn.fetchval("INSERT INTO pagos (fecha, inquilino, monto) VALUES ($1, $2, $3) RETURNING id", fecha, inquilino, monto)
        logger.info(f"Pago registrado con ID: {pago_id}")
        return pago_id

async def registrar_gasto(fecha: str, descripcion: str, monto: Decimal) -> int:
    """Registra un nuevo gasto en la base de datos."""
    async with pool.acquire() as conn:
        gasto_id = await conn.fetchval("INSERT INTO gastos (fecha, descripcion, monto) VALUES ($1, $2, $3) RETURNING id", fecha, descripcion, monto)
        logger.info(f"Gasto registrado con ID: {gasto_id}")
        return gasto_id

# --- Funciones para deshacer ---

async def deshacer_ultimo_pago() -> tuple:
    """Elimina el último pago registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            ultimo_pago = await conn.fetchrow("SELECT id, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 1 FOR UPDATE")
            if ultimo_pago:
                await conn.execute("DELETE FROM pagos WHERE id = $1", ultimo_pago['id'])
                logger.info(f"Pago con ID {ultimo_pago['id']} eliminado.")
                return ultimo_pago['inquilino'], ultimo_pago['monto']
            return None, None

async def deshacer_ultimo_gasto() -> tuple:
    """Elimina el último gasto registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            ultimo_gasto = await conn.fetchrow("SELECT id, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 1 FOR UPDATE")
            if ultimo_gasto:
                await conn.execute("DELETE FROM gastos WHERE id = $1", ultimo_gasto['id'])
                logger.info(f"Gasto con ID {ultimo_gasto['id']} eliminado.")
                return ultimo_gasto['descripcion'], ultimo_gasto['monto']
            return None, None

# --- Funciones para informes ---

async def obtener_resumen() -> dict:
    """Calcula el resumen de ingresos, gastos, comisión y neto."""
    async with pool.acquire() as conn:
        total_pagos = await conn.fetchval("SELECT SUM(monto) FROM pagos") or Decimal('0.0')
        total_gastos = await conn.fetchval("SELECT SUM(monto) FROM gastos") or Decimal('0.0')
        ultimos_pagos = await conn.fetch("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
        ultimos_gastos = await conn.fetch("SELECT fecha, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 3")

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
        total_pagos_mes = await conn.fetchval("SELECT SUM(monto) FROM pagos WHERE EXTRACT(MONTH FROM fecha::date) = $1 AND EXTRACT(YEAR FROM fecha::date) = $2", mes, anio) or Decimal('0.0')
        total_gastos_mes = await conn.fetchval("SELECT SUM(monto) FROM gastos WHERE EXTRACT(MONTH FROM fecha::date) = $1 AND EXTRACT(YEAR FROM fecha::date) = $2", mes, anio) or Decimal('0.0')
        pagos_mes = await conn.fetch("SELECT id, fecha, inquilino, monto FROM pagos WHERE EXTRACT(MONTH FROM fecha::date) = $1 AND EXTRACT(YEAR FROM fecha::date) = $2 ORDER BY id ASC", mes, anio)
        gastos_mes = await conn.fetch("SELECT id, fecha, descripcion, monto FROM gastos WHERE EXTRACT(MONTH FROM fecha::date) = $1 AND EXTRACT(YEAR FROM fecha::date) = $2 ORDER BY id ASC", mes, anio)

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
        inquilino_id = await conn.fetchval("INSERT INTO inquilinos (nombre) VALUES ($1) RETURNING id", nombre)
        logger.info(f"Inquilino '{nombre}' creado con ID: {inquilino_id}")
        return inquilino_id

async def obtener_inquilinos(activos_only: bool = True) -> list:
    """Obtiene una lista de inquilinos con su día de pago. Por defecto, solo los activos."""
    query = "SELECT id, nombre, activo, dia_pago FROM inquilinos"
    if activos_only:
        query += " WHERE activo = TRUE"
    query += " ORDER BY nombre ASC"
    
    async with pool.acquire() as conn:
        return await conn.fetch(query)

async def obtener_inquilino_por_id(inquilino_id: int) -> tuple:
    """Obtiene un inquilino por su ID."""
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT id, nombre, activo, dia_pago FROM inquilinos WHERE id = $1", inquilino_id)

async def cambiar_estado_inquilino(inquilino_id: int, estado: bool) -> bool:
    """Cambia el estado de un inquilino (activo/inactivo)."""
    async with pool.acquire() as conn:
        status = await conn.execute("UPDATE inquilinos SET activo = $1 WHERE id = $2", estado, inquilino_id)
        return status.endswith("1")

async def actualizar_dia_pago_inquilino(inquilino_id: int, dia_pago: int) -> bool:
    """Actualiza el día de pago para un inquilino específico."""
    async with pool.acquire() as conn:
        status = await conn.execute("UPDATE inquilinos SET dia_pago = $1 WHERE id = $2", dia_pago, inquilino_id)
        if status.endswith("1"):
            logger.info(f"Día de pago actualizado para inquilino ID {inquilino_id}.")
            return True
        return False

# --- Funciones para Borrar Específicos ---

async def delete_pago_by_id(pago_id: int) -> bool:
    """Elimina un pago específico por su ID."""
    async with pool.acquire() as conn:
        status = await conn.execute("DELETE FROM pagos WHERE id = $1", pago_id)
        if status.endswith("1"):
            logger.info(f"Pago con ID {pago_id} eliminado.")
            return True
        return False

async def delete_gasto_by_id(gasto_id: int) -> bool:
    """Elimina un gasto específico por su ID."""
    async with pool.acquire() as conn:
        status = await conn.execute("DELETE FROM gastos WHERE id = $1", gasto_id)
        if status.endswith("1"):
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
        # 1. Encontrar inquilinos activos cuyo día de pago es el día del recordatorio
        inquilinos_con_vencimiento = await conn.fetch(
            "SELECT nombre FROM inquilinos WHERE activo = TRUE AND dia_pago = $1",
            dia_recordatorio
        )

        if not inquilinos_con_vencimiento:
            return []

        # 2. Para cada inquilino, verificar si ya pagó este mes
        for inquilino in inquilinos_con_vencimiento:
            nombre_inquilino = inquilino['nombre']
            pago_este_mes = await conn.fetchrow("""
                SELECT 1 FROM pagos
                WHERE inquilino = $1
                AND EXTRACT(MONTH FROM fecha) = $2
                AND EXTRACT(YEAR FROM fecha) = $3
            """, nombre_inquilino, mes_actual, anio_actual)

            if not pago_este_mes:
                inquilinos_a_notificar.append(nombre_inquilino)

    return inquilinos_a_notificar