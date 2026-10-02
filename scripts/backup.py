"""RF-075 · CLI de respaldo de la base de datos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.backup import ErrorRespaldo, crear_respaldo  # noqa: E402


def main() -> int:
    try:
        destino = crear_respaldo()
    except ErrorRespaldo as error:
        print(f"ERROR: {error}")
        return 1
    print(f"Respaldo creado: {destino} ({destino.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
