"""RF-075 · CLI de restauración de la base de datos.

Uso:
    python scripts/restore.py --file backups/loan_soft_20261001_003000.sql.gz
    python scripts/restore.py --file backups/otro.db --to sqlite:///./restaurada.db
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.backup import ErrorRespaldo, restaurar_respaldo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura un respaldo de la base de datos")
    parser.add_argument("--file", required=True, help="Archivo de respaldo a restaurar")
    parser.add_argument("--to", default=None, help="DATABASE_URL de destino (opcional)")
    parser.add_argument("--yes", action="store_true", help="Confirma la restauración")
    args = parser.parse_args()

    destino = args.to or settings.DATABASE_URL
    if not args.yes:
        print(f"ADVERTENCIA: la restauración sobrescribe {destino}")
        print("Vuelva a ejecutar con --yes para confirmar.")
        return 2

    try:
        ruta = restaurar_respaldo(Path(args.file), args.to)
    except ErrorRespaldo as error:
        print(f"ERROR: {error}")
        return 1

    print(f"Respaldo restaurado en: {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
