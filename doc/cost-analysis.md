# Análisis de costos y optimizaciones

## Cómo se mide el costo

Cada respuesta de `POST /ask` trae `input_tokens`, `output_tokens`, `model`, `route`, `cached_calls` y `cost_usd`.
El costo sale de `data/model_prices.json` (precio por millón de tokens de Workers AI) y de los tokens que informa el
gateway (ADR 0009). `GET /metrics` acumula `cost_usd` y tokens del proceso, y el evento `agent_run` del log trae el
costo de cada petición con su `request_id`.

| Modelo | Entrada (USD / 1M tokens) | Salida (USD / 1M tokens) |
| --- | --- | --- |
| `@cf/meta/llama-3.1-8b-instruct-fast` (pequeño) | 0.045 | 0.384 |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (grande) | 0.293 | 2.253 |

El modelo grande cuesta unas 6.5 veces más por token de entrada.

## Estrategias aplicadas

| Estrategia | Variable | Cómo ahorra | Trade-off |
| --- | --- | --- | --- |
| **Routing de modelos** | `ROUTING=true`, `ROUTER_MAX_CHARS=80` | Las preguntas cortas y de búsqueda van al modelo pequeño; las que piden comparar, resumir, explicar o analizar van al grande | Una pregunta corta pero difícil puede ir al modelo pequeño y responder peor; la regla es simple y auditable (`route` dice el motivo) |
| **Ventana de historial** | `HISTORY_WINDOW=6` | Solo los últimos 6 mensajes viajan al modelo: los tokens de entrada dejan de crecer con la conversación | El agente olvida lo que se dijo hace más de 6 mensajes |
| **Tope de salida** | `MODEL_MAX_TOKENS=300` | Limita el gasto de salida, la parte más cara | Una respuesta muy larga se corta |
| **Caché de AI Gateway** | `CACHE_TTL_SECONDS` (0 por omisión) | Una pregunta repetida se responde desde el gateway sin costo (`cached_calls`) | Tras cambiar los datos una respuesta puede estar vieja; por eso está apagada por omisión |
| **Prompt compacto y temperatura 0** | `SYSTEM_PROMPT`, `MODEL_TEMPERATURE=0` | Prompt de sistema corto y respuestas repetibles en JSON | Menos flexibilidad de estilo |

## Línea base contra optimizado

**Línea base**: `ROUTING=false` (todo al modelo grande) y `HISTORY_WINDOW=1000` (todo el historial).
**Optimizado**: la configuración por omisión del producto.

### 1. Evaluación automática (modelo simulado con precios reales)

Comando, desde la carpeta de la fábrica: `uv run python -m verification evaluate`. Corre las 8 preguntas de
`verification/eval_set.json` con un historial de 10 mensajes y compara calidad y costo. Pasa solo si la calidad no
baja y el costo sí.

| Configuración | Calidad | Costo USD | Tokens de entrada |
| --- | --- | --- | --- |
| Línea base | `88%` | `0.001234` | `2834` |
| Optimizado | `88%` | `0.000171` | `2264` |
| **Ahorro** | igual | **`86.1` %** | `20.1` % |

### 2. Modelo real (Cloudflare Workers AI)

No ejecutada en esta entrega. La comparación contra el modelo real (Cloudflare Workers AI) con scripts/load_test.py queda como mejora futura; la evidencia de ahorro es la evaluación automática de la sección 1.

## Conclusión

`Con las palancas activas (routing por regla, ventana de historial y tope de pasos), el costo de la evaluación bajó de USD 0.001234 a USD 0.000171, un ahorro del 86.1 %, con la misma calidad (88 %). Los tokens de entrada solo bajaron un 20.1 % (por la ventana de historial): la mayor parte del ahorro viene del routing, que envía las preguntas simples al modelo pequeño, mucho más barato por token.`

## Mejoras futuras

- Encender la caché del gateway con un TTL corto para preguntas frecuentes, invalidándola al cambiar los datos.
- Enrutar con un clasificador en lugar de una regla por palabras, midiendo la calidad con un conjunto de
  evaluación más grande.
- Presupuesto diario por cliente con alerta cuando `cost_usd` se acerque al límite.
