"""Prueba de carga y de costo: manda peticiones concurrentes a ``POST /ask``.

Uso::

    LOAD_API_KEY=<clave> python scripts/load_test.py <url> [--requests 20]
        [--concurrency 10] [--history 0]

Sirve para dos evidencias del reto:

- **Concurrencia**: varias peticiones al mismo tiempo; se cuentan los codigos
  de respuesta y la latencia p50, p95 y maxima vista por el cliente.
- **Costo**: suma ``cost_usd`` e ``input_tokens`` de todas las respuestas y
  cuenta que modelo eligio el enrutador. Corriendo el mismo comando contra la
  configuracion base (``ROUTING=false``, ``HISTORY_WINDOW=1000``) y contra la
  optimizada se obtiene la comparacion antes y despues.

La clave se lee de ``LOAD_API_KEY`` (o de ``SMOKE_API_KEY``) y nunca se imprime.
Solo usa la biblioteca estandar.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

# Mezcla de preguntas cortas (modelo barato) y de analisis (modelo capaz).
QUESTIONS = [
    "¿Quién es EMP-0004?",
    "¿Qué puesto tiene EMP-0005?",
    "¿Quiénes trabajan en el departamento de Finanzas?",
    "Lista el departamento de Tecnología",
    "¿En qué año ingresó EMP-0002?",
    "Compara los departamentos de Ventas y Tecnología y explica sus diferencias",
]
FILLER = [
    ("user", "Hola, necesito datos de un empleado del directorio de RH."),
    ("assistant", "Claro, dime el número de empleado o el departamento."),
]


def build_history(messages: int) -> list:
    """Arma un historial de relleno, como una conversacion larga.

    :param messages: cantidad de mensajes
    :type messages: int
    :return: lista de mensajes con ``role`` y ``content``
    :rtype: list
    """
    return [
        {"role": FILLER[i % 2][0], "content": FILLER[i % 2][1]}
        for i in range(messages)
    ]


def ask(url: str, key: str, question: str, history: list) -> dict:
    """Manda una pregunta y mide la latencia.

    :param url: URL base del servicio
    :type url: str
    :param key: clave del cliente
    :type key: str
    :param question: pregunta
    :type question: str
    :param history: historial que se manda
    :type history: list
    :return: ``status``, ``latency_ms`` y el cuerpo (vacio si no es JSON)
    :rtype: dict
    """
    data = json.dumps({"question": question, "history": history}).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/ask",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": key},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except (urllib.error.URLError, TimeoutError):
        status, raw = 0, b""
    latency = round((time.perf_counter() - start) * 1000)
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = {}
    return {"status": status, "latency_ms": latency, "body": body}


def percentile(values: list, percent: int) -> int:
    """Percentil por rango mas cercano.

    :param values: muestras
    :type values: list
    :param percent: percentil de 1 a 100
    :type percent: int
    :return: la muestra del percentil (0 sin muestras)
    :rtype: int
    """
    ordered = sorted(values)
    if not ordered:
        return 0
    rank = -(-percent * len(ordered) // 100)
    return ordered[max(rank, 1) - 1]


def summarize(results: list, elapsed_s: float) -> dict:
    """Resume los resultados de la corrida.

    :param results: salida de :func:`ask` por peticion
    :type results: list
    :param elapsed_s: segundos que duro toda la corrida
    :type elapsed_s: float
    :return: codigos, latencias, costo, tokens y modelos usados
    :rtype: dict
    """
    ok = [r["body"] for r in results if r["status"] == 200]
    latencies = [r["latency_ms"] for r in results]
    return {
        "requests": len(results),
        "elapsed_s": round(elapsed_s, 2),
        "status_codes": dict(Counter(r["status"] for r in results)),
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies, default=0),
        },
        "unique_request_ids": len({b.get("request_id") for b in ok}),
        "cost_usd_total": round(sum(b.get("cost_usd", 0) for b in ok), 8),
        "input_tokens_total": sum(b.get("input_tokens", 0) for b in ok),
        "output_tokens_total": sum(b.get("output_tokens", 0) for b in ok),
        "models": dict(Counter(b.get("model", "?") for b in ok)),
    }


def main(args: list) -> int:
    """Corre la prueba y muestra el resumen; 0 si no hubo errores 5xx ni de red.

    :param args: argumentos de la linea de comandos
    :type args: list
    :return: codigo de salida
    :rtype: int
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--history", type=int, default=0)
    options = parser.parse_args(args)
    key = os.environ.get("LOAD_API_KEY") or os.environ.get("SMOKE_API_KEY", "")
    if not key:
        print("Define LOAD_API_KEY (o SMOKE_API_KEY) con la clave del cliente.")
        return 2
    url = options.url.rstrip("/")
    history = build_history(options.history)
    jobs = [QUESTIONS[i % len(QUESTIONS)] for i in range(options.requests)]
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=options.concurrency) as pool:
        results = list(pool.map(lambda q: ask(url, key, q, history), jobs))
    summary = summarize(results, time.perf_counter() - start)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    failed = any(r["status"] == 0 or r["status"] >= 500 for r in results)
    print("[FAIL] load_test" if failed else "[OK] load_test")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
