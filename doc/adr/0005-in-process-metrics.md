# 0005. Métricas en memoria por proceso

## Contexto

Se necesita ver conteo, tasa de error, latencia p50/p95, tokens, costo y cumplimiento del SLO. La API es sin
estado (ADR 0001) y no hay base de datos ni servicio de métricas en esta sesión.

## Decisión

`GET /metrics` devuelve los números del proceso que atiende, calculados desde contadores y una ventana acotada
de latencias en memoria. Incluye `pid`, `requests`, `error_rate`, `latency_ms` (p50, p95), `tokens` (entrada y
salida), `cost_usd` y `slo`. `cost_usd` es la suma en USD del costo de las respuestas del proceso (ADR 0009).
`slo.met` es verdadero si el p95 es menor que `SLO_P95_MS`.

## Consecuencias

- No rompe la ausencia de estado compartido: nada se guarda entre procesos ni se persiste.
- Con varias copias cada una reporta lo suyo; agregarlas queda para un sistema externo.
- Al reiniciar el proceso las métricas, incluido `cost_usd`, vuelven a cero.
- La ventana acotada evita crecimiento de memoria a costa de percentiles recientes.
- Las respuestas que terminan en 502 (modelo no disponible) no suman tokens ni costo.
