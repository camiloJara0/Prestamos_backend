"""RF-075 · Respaldo y recuperación de la base de datos.

Genera respaldos automáticos con retención configurable y permite restaurarlos.
Compatible con MySQL (mysqldump/mysql) y con SQLite (copia del archivo).
"""
import gzip
import logging
import math
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.config import settings

logger = logging.getLogger("loansoft.backup")

DIRECTORIO_RESPALDOS = Path(os.getenv("BACKUP_DIR", "backups"))
RETENCION_RESPALDOS = int(os.getenv("BACKUP_RETENTION", "30"))
RUTAS_MYSQLDUMP = (
    "mysqldump",
    r"C:\xampp\mysql\bin\mysqldump.exe",
    r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe",
)
RUTAS_MYSQL = (
    "mysql",
    r"C:\xampp\mysql\bin\mysql.exe",
    r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
)


class ErrorRespaldo(Exception):
    pass


def _buscar_ejecutable(rutas):
    for ruta in rutas:
        if os.path.sep in ruta:
            if Path(ruta).exists():
                return ruta
        elif shutil.which(ruta):
            return ruta
    return None


def _conexion_mysql():
    url = urlparse(settings.DATABASE_URL)
    return {
        "host": url.hostname or "localhost",
        "port": str(url.port or 3306),
        "user": unquote(url.username or "root"),
        "password": unquote(url.password or ""),
        "base": (url.path or "/").lstrip("/"),
    }


def _entorno_mysql(conexion):
    entorno = dict(os.environ)
    # Evita exponer la contraseña en la línea de comandos del proceso.
    entorno["MYSQL_PWD"] = conexion["password"]
    return entorno


def aplicar_retencion(directorio: Path | None = None) -> int:
    directorio = directorio or DIRECTORIO_RESPALDOS
    respaldos = sorted(
        (p for p in directorio.glob("loan_soft_*") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    eliminados = 0
    for archivo in respaldos[RETENCION_RESPALDOS:]:
        archivo.unlink()
        eliminados += 1
    return eliminados


def crear_respaldo(directorio: Path | None = None) -> Path:
    directorio = Path(directorio) if directorio else DIRECTORIO_RESPALDOS
    directorio.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    url = settings.DATABASE_URL

    if url.startswith("sqlite"):
        archivo_db = Path(url.split("///", 1)[-1]).resolve()
        if not archivo_db.exists():
            raise ErrorRespaldo(f"No existe la base de datos SQLite: {archivo_db}")
        destino = directorio / f"loan_soft_{marca}.db"
        shutil.copy2(archivo_db, destino)
    else:
        dump = _buscar_ejecutable(RUTAS_MYSQLDUMP)
        if not dump:
            raise ErrorRespaldo("No se encontró mysqldump en el sistema")
        conexion = _conexion_mysql()
        destino = directorio / f"loan_soft_{marca}.sql.gz"
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sql", delete=False, encoding="utf-8"
        ) as temporal:
            ruta_sql = temporal.name
        try:
            comando = [
                dump,
                f"--host={conexion['host']}",
                f"--port={conexion['port']}",
                f"--user={conexion['user']}",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--result-file",
                ruta_sql,
                conexion["base"],
            ]
            resultado = subprocess.run(
                comando,
                env=_entorno_mysql(conexion),
                capture_output=True,
                text=True,
                timeout=1800,
            )
            if resultado.returncode != 0:
                raise ErrorRespaldo(
                    f"mysqldump falló (código {resultado.returncode}): "
                    f"{resultado.stderr.strip()[:500]}"
                )
            with open(ruta_sql, "rb") as origen, gzip.open(destino, "wb") as comprimido:
                shutil.copyfileobj(origen, comprimido)
        finally:
            if os.path.exists(ruta_sql):
                os.remove(ruta_sql)

    if not destino.exists() or destino.stat().st_size == 0:
        raise ErrorRespaldo("El respaldo generado está vacío")

    aplicar_retencion(directorio)
    logger.info("Respaldo creado: %s (%s bytes)", destino, destino.stat().st_size)
    return destino


def restaurar_respaldo(archivo: Path, destino: str | None = None) -> Path:
    archivo = Path(archivo)
    if not archivo.exists():
        raise ErrorRespaldo(f"No existe el respaldo: {archivo}")

    url_destino = destino or settings.DATABASE_URL

    if archivo.suffix == ".db" or url_destino.startswith("sqlite"):
        if not url_destino.startswith("sqlite"):
            raise ErrorRespaldo(
                "Un respaldo SQLite solo puede restaurarse sobre una base SQLite"
            )
        ruta_db = Path(url_destino.split("///", 1)[-1]).resolve()
        ruta_db.parent.mkdir(parents=True, exist_ok=True)
        if archivo.suffix == ".gz":
            with gzip.open(archivo, "rb") as origen, open(ruta_db, "wb") as salida:
                shutil.copyfileobj(origen, salida)
        else:
            shutil.copy2(archivo, ruta_db)
        return ruta_db

    mysql = _buscar_ejecutable(RUTAS_MYSQL)
    if not mysql:
        raise ErrorRespaldo("No se encontró el cliente mysql en el sistema")
    conexion = _conexion_mysql()

    # Crear la base de datos si no existe.
    creacion = subprocess.run(
        [
            mysql,
            f"--host={conexion['host']}",
            f"--port={conexion['port']}",
            f"--user={conexion['user']}",
            "-e",
            f"CREATE DATABASE IF NOT EXISTS `{conexion['base']}`",
        ],
        env=_entorno_mysql(conexion),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if creacion.returncode != 0:
        raise ErrorRespaldo(f"No se pudo crear la base: {creacion.stderr.strip()[:500]}")

    if archivo.suffix == ".gz":
        with gzip.open(archivo, "rb") as comprimido:
            datos = comprimido.read()
    else:
        datos = archivo.read_bytes()

    restauracion = subprocess.run(
        [
            mysql,
            f"--host={conexion['host']}",
            f"--port={conexion['port']}",
            f"--user={conexion['user']}",
            conexion["base"],
        ],
        input=datos,
        env=_entorno_mysql(conexion),
        capture_output=True,
        timeout=3600,
    )
    if restauracion.returncode != 0:
        raise ErrorRespaldo(
            f"mysql falló (código {restauracion.returncode}): "
            f"{restauracion.stderr.decode('utf-8', 'ignore')[:500]}"
        )
    logger.info("Respaldo restaurado: %s -> %s", archivo, conexion["base"])
    return Path(conexion["base"])
