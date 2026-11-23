# Observabilidad: cómo depurar una petición en producción

## Las tres señales

| Señal | Dónde se ve | Qué trae |
| --- | --- | --- |
| **Logs JSON** | Render > servicio > **Logs** (salida estándar) | Una línea por evento: `request`, `agent_run`, `audit`, `security`, `error`, todas con `ts`, `service`, `request_id` y `client` |
| **Métricas** | `GET /metrics` (con `X-API-Key`) | `requests`, `error_rate`, `latency_ms.p50/p95`, `tokens`, `cost_usd` y si se cumple el SLO de p95 |
| **Trazas** | LangSmith, proyecto `LANGSMITH_PROJECT` | Árbol `agent_run` → `model_call` → `tool:*` con latencia de cada paso y `request_id` y `client` en los metadatos |

## Correlation ID

- El cliente puede mandar `X-Request-ID`; si no, el servidor genera un UUID.
- El mismo id vuelve en el encabezado `X-Request-ID`, en el cuerpo (`request_id`), en cada línea del log y en los
  metadatos de la traza. La página lo muestra para pasarlo a soporte.

## Receta de depuración

1. La persona reporta un problema y da el `request_id` que ve en la página.
2. En Render > Logs, buscar ese id: aparece el `request` (estado y latencia), el `agent_run` (modelo, ruta,
   pasos, tokens, costo, si se detuvo por el tope), los `audit` (herramientas) y, si hubo, `security` o `error`.
3. En LangSmith, filtrar por metadato `request_id = <id>` para ver qué paso tardó o falló.
4. En `GET /metrics` revisar si es un caso aislado o si subió `error_rate` o el p95.

## Dashboard

LangSmith > proyecto > **Monitor** muestra conteo de trazas, latencia (p50 y p99) y tasa de error a lo largo del tiempo. Para el costo en USD por petición se usa `cost_usd` de `agent_run` y de `/metrics`, que sale de la tabla de
precios del producto.

## Privacidad

El log nunca guarda el texto de la pregunta ni de la respuesta, ni claves. En producción `HIDE_INPUTS` y
`HIDE_OUTPUTS` valen `true` (compliance): LangSmith ve la forma de la ejecución y los tiempos, no el contenido.
