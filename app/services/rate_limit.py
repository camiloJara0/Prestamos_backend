"""Rate limiting en memoria para los endpoints públicos (RF-081 / RR.F).

Ventana deslizante por clave (IP + acción). Sin dependencias externas: la
primera versión protege contra spam de solicitudes y scraping de tasas.
"""

import threading
import time

from fastapi import HTTPException

_MAX_EVENTOS = 200
_ventanas: dict[str, list[float]] = {}
_lock = threading.Lock()


def verificar_rate_limit(clave: str, maximo: int = 5, ventana_segundos: int = 60) -> None:
    """Lanza 429 si la clave superó `maximo` eventos en la ventana."""
    ahora = time.time()
    with _lock:
        eventos = [t for t in _ventanas.get(clave, []) if ahora - t < ventana_segundos]
        if len(eventos) >= maximo:
            raise HTTPException(
                status_code=429,
                detail="Demasiadas solicitudes desde tu conexión. Intenta de nuevo en unos minutos.",
            )
        eventos.append(ahora)
        _ventanas[clave] = eventos
        if len(_ventanas) > _MAX_EVENTOS:
            for k in list(_ventanas):
                if k != clave and all(ahora - t >= ventana_segundos for t in _ventanas[k]):
                    del _ventanas[k]


def limpiar_rate_limits() -> None:
    """Solo para pruebas."""
    with _lock:
        _ventanas.clear()
