import os
import aiopg
import logging
from urllib.parse import urlparse
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from config import COMMISSION_RATE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)

pool = None

# === Zona Horaria ===
DO_TZ = timezone(timedelta(hours=-4)) # República Dominicana

async def init_pool():
    """
    Inicializa el pool de conexiones a la base de datos.
    Busca las credenciales en el siguiente orden:
    1. DATABASE_URL (ideal para producción en Railway).
    2. DATABASE_PUBLIC_URL (ideal para desarrollo local).
    3. Variables de entorno individuales (PGHOST, PGUSER, etc.).
    """
    global pool
    
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

    if not dsn or "password=None" in dsn or "host=None" in dsn:
        logger.critical("No se encontraron credenciales de base de datos completas. Defina DATABASE_URL, DATABASE_PUBLIC_URL o las variables PG*.")
        raise ValueError("Credenciales de base de datos incompletas o no encontradas.")

    try:
        pool = await aiopg.create_pool(dsn)
        logger.info("Pool de conexiones a la base de datos inicializado correctamente.")
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
                    descripcion VARCHAR(255) NOT NULL,
                    monto NUMERIC(12, 2) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
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

            # --- Migración para añadir mes_alquiler y anio_alquiler a pagos ---
            await cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='pagos' AND column_name='mes_alquiler'")
            if not await cur.fetchone():
                logger.info("Añadiendo columnas 'mes_alquiler' y 'anio_alquiler' a 'pagos'...")
                await cur.execute("ALTER TABLE pagos ADD COLUMN mes_alquiler INTEGER;")
                await cur.execute("ALTER TABLE pagos ADD COLUMN anio_alquiler INTEGER;")
                await cur.execute("UPDATE pagos SET mes_alquiler = EXTRACT(MONTH FROM fecha::date)::int, anio_alquiler = EXTRACT(YEAR FROM fecha::date)::int WHERE mes_alquiler IS NULL;")
                await cur.execute("ALTER TABLE pagos DROP CONSTRAINT IF EXISTS pagos_inquilino_fecha_key;")
                logger.info("Migración de período en pagos completada.")

            logger.info("Base de datos inicializada y/o migrada correctamente.")

# --- Funciones para registrar ---

async def registrar_pago(fecha: str, inquilino: str, monto: Decimal, mes_alquiler: int = None, anio_alquiler: int = None) -> int:
    """Registra un nuevo pago en la base de datos con fecha real y período adeudado."""
    if mes_alquiler is None or anio_alquiler is None:
        try:
            f_obj = datetime.strptime(str(fecha), '%Y-%m-%d').date()
            mes_alquiler = f_obj.month
            anio_alquiler = f_obj.year
        except Exception:
            mes_alquiler = datetime.now(DO_TZ).month
            anio_alquiler = datetime.now(DO_TZ).year

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO pagos (fecha, inquilino, monto, mes_alquiler, anio_alquiler) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (fecha, inquilino, monto, mes_alquiler, anio_alquiler)
            )
            pago_id = await cur.fetchone()
            await cur.execute("COMMIT")
            logger.info(f"Pago registrado con ID: {pago_id[0]} para período {mes_alquiler}/{anio_alquiler}")
            return pago_id[0]

async def registrar_gasto(fecha: str, descripcion: str, monto: Decimal) -> int:
    """Registra un nuevo gasto en la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("INSERT INTO gastos (fecha, descripcion, monto) VALUES (%s, %s, %s) RETURNING id", (fecha, descripcion, monto))
            gasto_id = await cur.fetchone()
            await cur.execute("COMMIT")
            logger.info(f"Gasto registrado con ID: {gasto_id[0]}")
            return gasto_id[0]

# --- Funciones para deshacer ---

async def deshacer_ultimo_pago() -> tuple:
    """Elimina el último pago registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, inquilino, monto FROM pagos ORDER BY id DESC LIMIT 1")
            ultimo_pago = await cur.fetchone()
            
            if ultimo_pago:
                pago_id, inquilino, monto = ultimo_pago
                await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
                await cur.execute("COMMIT")
                logger.info(f"Pago con ID {pago_id} eliminado.")
                return inquilino, monto
            
            return None, None

async def deshacer_ultimo_gasto() -> tuple:
    """Elimina el último gasto registrado y devuelve sus detalles de forma atómica."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, descripcion, monto FROM gastos ORDER BY id DESC LIMIT 1")
            ultimo_gasto = await cur.fetchone()
            
            if ultimo_gasto:
                gasto_id, descripcion, monto = ultimo_gasto
                await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
                await cur.execute("COMMIT")
                logger.info(f"Gasto con ID {gasto_id} eliminado.")
                return descripcion, monto
            
            return None, None

async def delete_pago_by_id(pago_id: int) -> bool:
    """Elimina un pago específico por su ID."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
            if cur.rowcount > 0:
                await cur.execute("COMMIT")
                logger.info(f"Pago con ID {pago_id} eliminado.")
                return True
            return False

async def delete_gasto_by_id(gasto_id: int) -> bool:
    """Elimina un gasto específico por su ID."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM gastos WHERE id = %s", (gasto_id,))
            if cur.rowcount > 0:
                await cur.execute("COMMIT")
                logger.info(f"Gasto con ID {gasto_id} eliminado.")
                return True
            return False

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
            await cur.execute("COMMIT")
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
            if cur.rowcount > 0:
                await cur.execute("COMMIT")
            return cur.rowcount > 0

async def actualizar_dia_pago_inquilino(inquilino_id: int, dia_pago: int) -> bool:
    """Actualiza el día de pago para un inquilino específico."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE inquilinos SET dia_pago = %s WHERE id = %s", (dia_pago, inquilino_id))
            if cur.rowcount > 0:
                await cur.execute("COMMIT")
                logger.info(f"Día de pago actualizado para inquilino ID {inquilino_id}.")
                return True
            return False

async def eliminar_inquilino(inquilino_id: int) -> bool:
    """Elimina un inquilino permanentemente de la base de datos."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM inquilinos WHERE id = %s", (inquilino_id,))
            if cur.rowcount > 0:
                await cur.execute("COMMIT")
                logger.info(f"Inquilino con ID {inquilino_id} eliminado permanentemente.")
                return True
            return False

async def obtener_mes_pago_pendiente(inquilino_nombre: str) -> date | None:
    """
    Determina la fecha de pago para el próximo mes pendiente de un inquilino.
    Busca el último mes pagado y asigna el pago al mes siguiente.
    """
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT dia_pago FROM inquilinos WHERE nombre = %s",
                (inquilino_nombre,)
            )
            result = await cur.fetchone()
            if not result or not result[0]:
                return None
            dia_pago = result[0]

            hoy = datetime.now(DO_TZ).date()

            await cur.execute(
                "SELECT COALESCE(anio_alquiler, EXTRACT(YEAR FROM fecha::date)::int), COALESCE(mes_alquiler, EXTRACT(MONTH FROM fecha::date)::int) "
                "FROM pagos WHERE inquilino = %s "
                "ORDER BY COALESCE(anio_alquiler, EXTRACT(YEAR FROM fecha::date)::int) DESC, COALESCE(mes_alquiler, EXTRACT(MONTH FROM fecha::date)::int) DESC LIMIT 1",
                (inquilino_nombre,)
            )
            ultimo_pago = await cur.fetchone()

            siguiente_anio, siguiente_mes = hoy.year, hoy.month

            if ultimo_pago:
                ultimo_anio, ultimo_mes = ultimo_pago
                if ultimo_mes == 12:
                    siguiente_mes = 1
                    siguiente_anio = ultimo_anio + 1
                else:
                    siguiente_mes = ultimo_mes + 1
                    siguiente_anio = ultimo_anio
            
            fecha_siguiente_pago = date(siguiente_anio, siguiente_mes, 1)
            if fecha_siguiente_pago > hoy.replace(day=1):
                 await cur.execute(
                    "SELECT 1 FROM pagos WHERE inquilino = %s AND "
                    "COALESCE(anio_alquiler, EXTRACT(YEAR FROM fecha::date)::int) = %s AND COALESCE(mes_alquiler, EXTRACT(MONTH FROM fecha::date)::int) = %s",
                    (inquilino_nombre, hoy.year, hoy.month)
                )
                 if not await cur.fetchone():
                     siguiente_anio, siguiente_mes = hoy.year, hoy.month

            try:
                return date(siguiente_anio, siguiente_mes, dia_pago)
            except ValueError:
                import calendar
                _, ultimo_dia = calendar.monthrange(siguiente_anio, siguiente_mes)
                return date(siguiente_anio, siguiente_mes, ultimo_dia)

# --- Funciones para Borrar Específicos ---

async def borrar_transaccion(trans_id: int, tipo: str) -> bool:
    """Elimina una transacción por su ID y tipo ('pago' o 'gasto')."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            tabla = "pagos" if tipo == "pago" else "gastos"
            await cur.execute(f"DELETE FROM {tabla} WHERE id = %s", (trans_id,))
            if cur.rowcount > 0:
                await cur.execute("COMMIT")
                logger.info(f"Transacción {trans_id} ({tipo}) eliminada.")
                return True
            return False

async def obtener_inquilinos_para_recordatorio(dia_objetivo: int = None) -> dict:
    """Devuelve inquilinos activos categorizados en 'vencidos' y 'proximos' pendientes de pago en el mes actual."""
    hoy = datetime.now(DO_TZ)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT nombre, dia_pago FROM inquilinos
                WHERE activo = TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM pagos
                      WHERE inquilino = inquilinos.nombre
                        AND COALESCE(mes_alquiler, EXTRACT(MONTH FROM fecha::date)::int) = %s
                        AND COALESCE(anio_alquiler, EXTRACT(YEAR FROM fecha::date)::int) = %s
                  )
                """,
                (hoy.month, hoy.year)
            )
            rows = await cur.fetchall()
            
            vencidos = []
            proximos = []
            for nombre, dia_pago in rows:
                if dia_objetivo is not None:
                    if dia_pago == dia_objetivo:
                        proximos.append(nombre)
                else:
                    if dia_pago and dia_pago < hoy.day:
                        vencidos.append(nombre)
                    else:
                        proximos.append(nombre)
            return {
                "vencidos": vencidos,
                "proximos": proximos
            }

async def obtener_estado_cuenta_inquilino(nombre: str, anio: int) -> dict:
    """Obtiene el historial de pagos y estado financiero de un inquilino en un año."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT id, nombre, activo, dia_pago FROM inquilinos WHERE nombre = %s", (nombre,))
            row = await cur.fetchone()
            if not row:
                return {}
            inquilino_info = {"id": row[0], "nombre": row[1], "activo": row[2], "dia_pago": row[3]}

            await cur.execute(
                "SELECT id, fecha, monto FROM pagos WHERE inquilino = %s AND COALESCE(anio_alquiler, EXTRACT(YEAR FROM fecha::date)::int) = %s ORDER BY fecha ASC",
                (nombre, anio)
            )
            pagos_anio = await cur.fetchall()

            await cur.execute("SELECT SUM(monto) FROM pagos WHERE inquilino = %s AND COALESCE(anio_alquiler, EXTRACT(YEAR FROM fecha::date)::int) = %s", (nombre, anio))
            total_pagado_anio = (await cur.fetchone())[0] or Decimal('0.0')

    fecha_pendiente = await obtener_mes_pago_pendiente(nombre)

    return {
        "inquilino": inquilino_info,
        "anio": anio,
        "pagos": pagos_anio,
        "total_pagado": total_pagado_anio,
        "fecha_pendiente": fecha_pendiente
    }

async def obtener_inquilinos_pendientes_mes(mes: int, anio: int) -> list:
    """Devuelve inquilinos activos sin pago registrado para el mes/año adeudado indicado."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT i.nombre, i.dia_pago 
                FROM inquilinos i 
                WHERE i.activo = TRUE 
                  AND NOT EXISTS (
                      SELECT 1 FROM pagos p 
                      WHERE p.inquilino = i.nombre 
                        AND COALESCE(p.mes_alquiler, EXTRACT(MONTH FROM p.fecha::date)::int) = %s 
                        AND COALESCE(p.anio_alquiler, EXTRACT(YEAR FROM p.fecha::date)::int) = %s
                  )
                ORDER BY i.dia_pago ASC NULLS LAST, i.nombre ASC
                """,
                (mes, anio)
            )
            return await cur.fetchall()