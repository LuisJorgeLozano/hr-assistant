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
| Línea base | `<<PEGAR quality baseline>>` | `<<PEGAR cost_usd baseline>>` | `<<PEGAR input_tokens baseline>>` |
| Optimizado | `<<PEGAR quality levers>>` | `<<PEGAR cost_usd levers>>` | `<<PEGAR input_tokens levers>>` |
| **Ahorro** | igual o mejor | **`<<CALCULAR (1 - optimizado / base) x 100>>` %** | `<<CALCULAR>>` % |

### 2. Modelo real (Cloudflare Workers AI)

Mismo producto en local con `MODEL_PROVIDER=gateway`, arrancado dos veces, y la misma carga:
`python scripts/load_test.py http://127.0.0.1:8000 --requests 12 --concurrency 4 --history 10`.

| Configuración | Costo total USD | Tokens de entrada | Modelos usados |
| --- | --- | --- | --- |
| Línea base | `<<PEGAR cost_usd_total>>` | `<<PEGAR input_tokens_total>>` | `<<PEGAR models>>` |
| Optimizado | `<<PEGAR cost_usd_total>>` | `<<PEGAR input_tokens_total>>` | `<<PEGAR models>>` |
| **Ahorro** | **`<<CALCULAR>>` %** | `<<CALCULAR>>` % | |

## Conclusión

`<<ESCRIBIR 2 o 3 líneas: cuánto se ahorró, que la calidad no bajó en la evaluación y qué palanca aportó más
(normalmente el routing, porque el modelo pequeño es 6.5 veces más barato).>>`

## Mejoras futuras

- Encender la caché del gateway con un TTL corto para preguntas frecuentes, invalidándola al cambiar los datos.
- Enrutar con un clasificador en lugar de una regla por palabras, midiendo la calidad con un conjunto de
  evaluación más grande.
- Presupuesto diario por cliente con alerta cuando `cost_usd` se acerque al límite.
