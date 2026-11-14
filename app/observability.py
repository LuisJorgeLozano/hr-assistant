"""Reloj inyectable, log JSON por evento y metricas del proceso."""
import json
import os
import sys
import threading
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Optional

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
client_var: ContextVar[Optional[str]] = ContextVar("client", default=None)


class SystemClock:
    """Reloj real; las pruebas lo reemplazan por uno fijo."""

    def now(self) -> datetime:
        """Devuelve la hora actual en UTC.

        :return: la fecha y hora con zona UTC
        """
        return datetime.now(timezone.utc)


def elapsed_ms(start: datetime, end: datetime) -> int:
    """Calcula los milisegundos entre dos instantes.

    :param start: instante inicial
    :param end: instante final
    :return: la diferencia redondeada a milisegundos
    """
    return round((end - start) / timedelta(milliseconds=1))


class JsonLogger:
    """Escribe una linea JSON por evento.

    :param service: valor del campo ``service``
    :param clock: reloj con ``now()``
    :param stream: destino de las lineas (por omision, la salida estandar)
    """

    def __init__(self, service: str, clock, stream=None):
        self._service = service
        self._clock = clock
        self._stream = stream
        self._lock = threading.Lock()

    def log(self, event: str, **fields) -> None:
        """Escribe un evento con ``ts``, ``service``, ``event`` y ``request_id``.

        Si hay un cliente autenticado en curso, agrega ``client``.

        :param event: nombre del evento
        :param fields: campos adicionales del evento
        """
        line = {
            "ts": self._clock.now().astimezone(timezone.utc).isoformat(),
            "service": self._service,
            "event": event,
            "request_id": request_id_var.get(),
        }
        client = client_var.get()
        if client is not None:
            line["client"] = client
        line.update(fields)
        stream = self._stream or sys.stdout
        with self._lock:
            stream.write(json.dumps(line, ensure_ascii=False) + "\n")
            stream.flush()


class NullLogger:
    """Logger que descarta los eventos (para usar el agente sin log)."""

    def log(self, event: str, **fields) -> None:
        """Ignora el evento.

        :param event: nombre del evento
        :param fields: campos del evento
        """


def _nearest_rank(sorted_values: list, percent: int):
    """Calcula un percentil por rango mas cercano.

    :param sorted_values: muestras ordenadas
    :param percent: percentil entre 1 y 100
    :return: la muestra del percentil, o 0 si no hay muestras
    """
    if not sorted_values:
        return 0
    rank = -(-percent * len(sorted_values) // 100)
    return sorted_values[max(rank, 1) - 1]


class Metrics:
    """Metricas de este proceso, con una ventana acotada de latencias.

    :param max_samples: cantidad maxima de latencias que se conservan
    """

    def __init__(self, max_samples: int = 1000):
        self._latencies: deque = deque(maxlen=max_samples)
        self._requests = 0
        self._failures = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cost_usd = 0.0
        self._lock = threading.Lock()

    def record_request(self, latency_ms: int, failed: bool) -> None:
        """Registra una peticion terminada.

        :param latency_ms: latencia en milisegundos
        :param failed: si la peticion termino en error
        """
        with self._lock:
            self._requests += 1
            self._failures += 1 if failed else 0
            self._latencies.append(latency_ms)

    def add_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Acumula los tokens de una corrida del agente.

        :param input_tokens: tokens de entrada
        :param output_tokens: tokens de salida
        """
        with self._lock:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens

    def add_cost(self, usd: float) -> None:
        """Acumula el costo de una respuesta.

        :param usd: costo en USD
        """
        with self._lock:
            self._cost_usd += usd

    def snapshot(self, slo_p95_ms: int) -> dict:
        """Resume las metricas.

        :param slo_p95_ms: meta de latencia p95 en milisegundos
        :return: el diccionario que devuelve ``GET /metrics``
        """
        with self._lock:
            samples = sorted(self._latencies)
            requests = self._requests
            rate = self._failures / requests if requests else 0
            tokens = {"input": self._input_tokens, "output": self._output_tokens}
            cost = self._cost_usd
        p95 = _nearest_rank(samples, 95)
        return {
            "pid": os.getpid(),
            "requests": requests,
            "error_rate": rate,
            "latency_ms": {"p50": _nearest_rank(samples, 50), "p95": p95},
            "tokens": tokens,
            "cost_usd": cost,
            "slo": {"p95_ms_target": slo_p95_ms, "met": p95 < slo_p95_ms},
        }
