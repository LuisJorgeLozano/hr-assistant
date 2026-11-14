"""Limite de peticiones por cliente, en memoria y con reloj inyectado."""
import math
import threading
from collections import deque
from datetime import timedelta
from typing import Dict

WINDOW = timedelta(minutes=1)


class RateLimiter:
    """Ventana deslizante de un minuto por cliente.

    :param limit: peticiones permitidas por minuto
    :param clock: reloj con ``now()``
    """

    def __init__(self, limit: int, clock):
        self._limit = limit
        self._clock = clock
        self._hits: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def check(self, client: str) -> int:
        """Cuenta una peticion del cliente si cabe en el minuto.

        :param client: nombre del cliente ya autenticado
        :return: 0 si cabe; si no, los segundos (al menos 1) que faltan
        """
        now = self._clock.now()
        with self._lock:
            hits = self._hits.setdefault(client, deque())
            while hits and now - hits[0] >= WINDOW:
                hits.popleft()
            if len(hits) >= self._limit:
                remaining = (hits[0] + WINDOW - now).total_seconds()
                return max(1, math.ceil(remaining))
            hits.append(now)
            return 0
