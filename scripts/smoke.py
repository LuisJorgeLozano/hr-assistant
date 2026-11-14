"""Prueba de humo del servicio publicado.

Uso: SMOKE_API_KEY=... python scripts/smoke.py <url>
La clave se lee solo de la variable de entorno y nunca se imprime.
"""
import os
import sys

import httpx

QUESTION = {"question": "How many vacation days does Ana have?", "history": []}


def report(ok: bool, label: str) -> bool:
    """Imprime el resultado de una comprobacion y lo devuelve."""
    print(f"[{'OK' if ok else 'FAIL'}] {label}")
    return ok


def smoke(url: str, api_key: str, client: httpx.Client) -> bool:
    """Corre las tres comprobaciones; True si todas pasan."""
    base = url.rstrip("/")
    results = []
    try:
        health = client.get(f"{base}/health")
        results.append(report(health.status_code == 200, "/health responde 200"))
        anonymous = client.post(f"{base}/ask", json=QUESTION)
        results.append(
            report(anonymous.status_code == 401, "/ask sin clave responde 401")
        )
        keyed = client.post(
            f"{base}/ask", json=QUESTION, headers={"X-API-Key": api_key}
        )
        results.append(report(keyed.status_code == 200, "/ask con clave responde 200"))
    except httpx.HTTPError as error:
        report(False, f"no se pudo conectar ({type(error).__name__})")
        return False
    return all(results)


def main(argv: list[str]) -> int:
    """Punto de entrada: 0 si todo pasa, distinto de 0 si algo falla."""
    if len(argv) != 1:
        print("Uso: SMOKE_API_KEY=... python scripts/smoke.py <url>")
        return 2
    api_key = os.environ.get("SMOKE_API_KEY", "")
    if not api_key:
        print("Falta la variable SMOKE_API_KEY")
        return 2
    with httpx.Client(timeout=60) as client:
        return 0 if smoke(argv[0], api_key, client) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
