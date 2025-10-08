import os
import aiopg
import logging
from urllib.parse import urlparse
from decimal import Decimal
from datetime import date, timedelta
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)

class Database:
    """
    Clase para gestionar la conexión y operaciones con la base de datos PostgreSQL.
    Proporciona métodos asíncronos para inicializar el pool de conexiones, crear tablas,
    registrar pagos y gastos, gestionar inquilinos, y realizar consultas y migraciones.
    """
    def __init__(self):
        self.pool = None

    async def init_pool(self):
        """
        Inicializa el pool de conexiones a la base de datos.
        Busca las credenciales en el siguiente orden:
        1. DATABASE_URL (ideal para producción en Railway).
        2. DATABASE_PUBLIC_URL (ideal para desarrollo local).
        3. Variables de entorno individuales (PGHOST, PGUSER, etc.).
        """
        # Prioridad 1: DATABASE_URL (para producción)
        dsn_url = os.getenv("DATABASE_URL")
        
        # Prioridad 2: DATABASE_PUBLIC_URL (para desarrollo local)
        if not dsn_url:
            dsn_url = os.getenv("DATABASE_PUBLIC_URL")

        if dsn_url:
            # Si se encontró una URL, se parsea para construir el DSN
            url = urlparse(dsn_url)
            dsn = f"dbname={url.path[1:]} user={url.username} password={url.password} host={url.hostname} port={url.port}"
            logger.info(f"Conectando a la base de datos usando URL: host={url.hostname}, dbname={url.path[1:]}")
        else:
            # Prioridad 3: Variables de entorno individuales
            dsn = f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD} host={DB_HOST} port={DB_PORT}"
            logger.info(f"Conectando a la base de datos usando variables de entorno individuales: host={DB_HOST}, dbname={DB_NAME}")

        # Validar credenciales antes de construir el DSN
        if dsn_url:
            url = urlparse(dsn_url)
            if not url.username or not url.password or not url.hostname or not url.path[1:]:
                logger.critical("No se encontraron credenciales completas en la URL de la base de datos.")
                raise ValueError("Credenciales de base de datos incompletas en la URL de la base de datos.")
        elif not DB_NAME or not DB_USER or not DB_PASSWORD or not DB_HOST or not DB_PORT:
            logger.critical("No se encontraron credenciales completas en las variables de entorno individuales.")
            raise ValueError("Credenciales de base de datos incompletas en las variables de entorno.")

        minsize = int(os.getenv("DB_POOL_MINSIZE", 1))
        maxsize = int(os.getenv("DB_POOL_MAXSIZE", 10))
        try:
            self.pool = await aiopg.create_pool(dsn, minsize=minsize, maxsize=maxsize)
            logger.info(f"Pool de conexiones a la base de datos inicializado correctamente (minsize={minsize}, maxsize={maxsize}).")
        except Exception as e:
            logger.error(f"Error al inicializar el pool de conexiones: {e}")
            raise

    async def close_pool(self):
        """Cierra el pool de conexiones."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
async def inicializar_db(self):
    """Crea las tablas de la base de datos si no existen y realiza migraciones."""
    if self.pool is None:
        raise RuntimeError("El pool de la base de datos no está inicializado. Llama a init_pool() antes de inicializar la base de datos.")
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            # Crear tabla de inquilinos (agrega columna 'activo' por defecto TRUE)
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

async def registrar_pago(self, fecha: str, inquilino: str, monto: Decimal) -> int:
    """Registra un nuevo pago en la base de datos."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO pagos (fecha, inquilino, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, inquilino, monto))
            pago_id = await cur.fetchone()
            logger.info(f"Pago registrado con ID: {pago_id[0]}")
            return pago_id[0]

async def registrar_gasto(self, fecha: str, descripcion: str, monto: Decimal) -> int:
    """Registra un nuevo gasto en la base de datos."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO gastos (fecha, descripcion, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, descripcion, monto))
            gasto_id = await cur.fetchone()
            logger.info(f"Gasto registrado con ID: {gasto_id[0]}")
            return gasto_id[0]

# --- Funciones para deshacer ---
async def deshacer_ultimo_pago(self) -> tuple:
    """Deshace el último pago registrado y lo elimina de la base de datos."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("BEGIN")
            await cur.execute("SELECT id, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 1 FOR UPDATE")
            if ultimo_pago := await cur.fetchone():
                pago_id, inquilino, monto = ultimo_pago
                await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
                await cur.execute("COMMIT")
                logger.info(f"Pago con ID {pago_id} eliminado.")
                return inquilino, monto
            await cur.execute("ROLLBACK")
            return None, None

async def deshacer_ultimo_gasto(self) -> tuple:
    """Deshace el último gasto registrado en la base de datos."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("BEGIN")
            await cur.execute("SELECT id, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 1 FOR UPDATE")
            if ultimo_gasto := await cur.fetchone():
                gasto_id, descripcion, monto = ultimo_gasto
                await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
                await cur.execute("COMMIT")
                logger.info(f"Gasto con ID {gasto_id} eliminado.")
                return descripcion, monto
            await cur.execute("ROLLBACK")
            return None, None

# --- Funciones para informes ---

async def obtener_resumen(self) -> dict:
    """Calcula el resumen de ingresos, gastos, comisión y neto."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT SUM(monto) FROM pagos")
            total_pagos = (await cur.fetchone())[0] or Decimal('0.0')
            await cur.execute("SELECT SUM(monto) FROM gastos")
            total_gastos = (await cur.fetchone())[0] or Decimal('0.0')
            await cur.execute("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
            ultimos_pagos = await cur.fetchall()
            await cur.execute("SELECT fecha, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 3")
            await cur.execute("SELECT fecha, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 3")
            ultimos_gastos = await cur.fetchall()
    # Define la comisión como el 10% de los ingresos (ajusta según tu lógica)
    total_comision = total_pagos * Decimal('0.10')
    monto_neto = total_pagos - total_comision - total_gastos

    return {
        "total_ingresos": total_pagos,
        "total_comision": total_comision,
        "total_gastos": total_gastos,
        "monto_neto": monto_neto,
        "ultimos_pagos": ultimos_pagos,
        "ultimos_gastos": ultimos_gastos
    }

# --- Funciones para Inquilinos ---

async def crear_inquilino(self, nombre: str) -> int:
    """Crea un nuevo inquilino en la base de datos."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO inquilinos (nombre) VALUES (%s) RETURNING id", (nombre,))
            inquilino_id = await cur.fetchone()
            logger.info(f"Inquilino '{nombre}' creado con ID: {inquilino_id[0]}")
            return inquilino_id[0]

async def obtener_inquilinos(self, only_active: bool = True) -> list:
    """Obtiene una lista de inquilinos con su día de pago. Por defecto, solo los activos."""
    query = "SELECT id, nombre, activo, dia_pago FROM inquilinos"
    if only_active:
        query += " WHERE activo = TRUE"
    query += " ORDER BY nombre ASC"
    
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query)
            return await cur.fetchall()

async def obtener_inquilino_por_id(self, inquilino_id: int) -> tuple:
    """Obtiene un inquilino por su ID."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, nombre, activo, dia_pago FROM inquilinos WHERE id = %s", (inquilino_id,))
            return await cur.fetchone()

async def cambiar_estado_inquilino(self, inquilino_id: int, estado: bool) -> bool:
    """Cambia el estado de un inquilino (activo/inactivo)."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE inquilinos SET activo = %s WHERE id = %s", (estado, inquilino_id))
            return cur.rowcount > 0

async def actualizar_dia_pago_inquilino(self, inquilino_id: int, dia_pago: int) -> bool:
    """Actualiza el día de pago para un inquilino específico."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE inquilinos SET dia_pago = %s WHERE id = %s", (dia_pago, inquilino_id))
            if cur.rowcount > 0:
                logger.info(f"Día de pago actualizado para inquilino ID {inquilino_id}.")
                return True
            return False

# --- Funciones para Borrar Específicos ---

async def delete_pago_by_id(self, pago_id: int) -> bool:
    """Elimina un pago específico por su ID."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
            if cur.rowcount > 0:
                logger.info(f"Pago con ID {pago_id} eliminado.")
                return True
            return False

async def delete_gasto_by_id(self, gasto_id: int) -> bool:
    """Elimina un gasto específico por su ID."""
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
            if cur.rowcount > 0:
                logger.info(f"Gasto con ID {gasto_id} eliminado.")
                return True
            return False

async def obtener_inquilinos_para_recordatorio(self) -> list:
    """
    Obtiene una lista de nombres de inquilinos activos que tienen un pago venciéndose en 2 días
    y que aún no han pagado en el mes actual.

    Returns:
        list: Lista de nombres de inquilinos a notificar.
    """
    inquilinos_a_notificar = []
    hoy = date.today()
    fecha_recordatorio = hoy + timedelta(days=2)
    dia_recordatorio = fecha_recordatorio.day
    mes_actual = hoy.month
    anio_actual = hoy.year
    # Optimizado: Un solo query con LEFT JOIN para encontrar inquilinos activos cuyo día de pago es el día del recordatorio y que no han pagado este mes
    async with self.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                    SELECT i.nombre
                    FROM inquilinos i
                    LEFT JOIN pagos p ON i.nombre = p.inquilino AND EXTRACT(MONTH FROM p.fecha) = %s AND EXTRACT(YEAR FROM p.fecha) = %s
                    WHERE i.activo = TRUE AND i.dia_pago = %s AND p.id IS NULL
                """, (mes_actual, anio_actual, dia_recordatorio))
            return [row[0] for row in await cur.fetchall()]
