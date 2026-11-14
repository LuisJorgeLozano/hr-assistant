# HR Assistant

Asistente de recursos humanos con una API web y una página. Responde preguntas sobre
empleados y departamentos con un agente de bucle acotado que usa dos herramientas de
solo lectura. Desde la sesión 2 permite responder, con datos, qué pasó con cualquier
petición: id por petición, log JSON, métricas y trazas opcionales en LangSmith.

## Cómo correrlo

Desde la carpeta `product/`:

```
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

- Página: `http://localhost:8000/`
- `POST /ask` con `{"question": "...", "history": [...]}`.
- `GET /health` y `GET /metrics`.

Pruebas, con cobertura:

```
pytest --cov=app
```

## Observabilidad

- **Id por petición.** Se usa `X-Request-ID` si el cliente lo manda (1 a 64 caracteres
  de `A-Za-z0-9._-`); si no, o si no es válido, se genera un UUID. Toda respuesta lo
  devuelve en `X-Request-ID`, y `POST /ask` también como `request_id` en el cuerpo. La
  página lo muestra para pasarlo a soporte.
- **Log JSON** en la salida estándar, una línea por evento, con `ts` (ISO 8601 UTC),
  `service`, `event` y `request_id`:
  - `request`: `method`, `path`, `status`, `latency_ms`.
  - `agent_run`: `question_chars`, `history_messages`, `steps`, `tools`,
    `input_tokens`, `output_tokens`, `stopped`, `model`, `route`, `cached_calls` y
    `cost_usd`. Nunca el texto de la pregunta ni de la respuesta.
  - `audit`: `action: "tool_call"` y `tool`, por cada herramienta llamada. `args` solo
    aparece si el argumento ya fue validado (id `EMP-dddd` o departamento conocido).
  - `error`: `error_type`. La respuesta es `500` con
    `{"detail": "internal error", "request_id": ...}`.
- **`GET /metrics`**: `pid`, `requests`, `error_rate`, `latency_ms` (`p50`, `p95`),
  `tokens`, `cost_usd` y `slo` (`p95_ms_target`, `met`). Son las métricas de este proceso: con
  varias copias, cada una reporta lo suyo. Cuenta todas las peticiones, incluidas las
  de `/metrics`, y guarda una ventana acotada de latencias.
- **Trazas en LangSmith (opcional).** Con `LANGSMITH_TRACING=true` y
  `LANGSMITH_API_KEY`, cada corrida del agente, llamada al modelo y herramienta queda
  como traza con el `request_id` en sus metadatos. Sin la clave no se conecta a nada.

## Variables de entorno

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Modelo a usar (`fake` o `gateway`) |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del agente |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta |
| `EMPLOYEES_PATH` | `data/employees.json` | Archivo de empleados |
| `SERVICE_NAME` | `hr-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas |
| `LANGSMITH_API_KEY` | (vacía) | Clave de LangSmith; solo se lee del entorno |
| `HIDE_INPUTS` / `HIDE_OUTPUTS` | `true` | No mandar a LangSmith preguntas ni respuestas |
| `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_API_TOKEN` | vacías, `default`, vacía | Cuenta, gateway y token de Cloudflare (el token es secreto) |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento por pregunta |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz |
| `HISTORY_WINDOW` | `6` | Mensajes de historial que se mandan al modelo |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida |
| `MODEL_TEMPERATURE` | `0` | Con 0 las evaluaciones son repetibles |
| `CACHE_TTL_SECONDS` | `0` | Caché del gateway (0: apagada) |
| `PRICES_PATH` | `data/model_prices.json` | Precios por modelo |
| `ENVIRONMENT` | `development` | Con `production` se aplican las reglas de compliance |
| `API_KEYS` | (vacía) | Clientes y claves, `cliente:clave,cliente2:clave2` (secreto) |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto |

Un valor inválido impide arrancar. La clave nunca se escribe en el código ni en el log.
`.env.example` lista todas las variables sin valores secretos.

## Costos

Cada respuesta de `POST /ask` agrega `model`, `route`, `cached_calls` y `cost_usd`;
`GET /metrics` agrega el `cost_usd` acumulado. Cuatro palancas, cada una medible:

1. **Enrutamiento.** Una regla en código elige `MODEL_LARGE` si `ROUTING=false`, si la
   pregunta pasa de `ROUTER_MAX_CHARS` o si contiene «compara», «resume», «explica»,
   «por qué», «analiza» o «todos»; si no, `MODEL_SMALL`. `route` dice el motivo.
2. **Ventana de historial.** Solo se mandan los últimos `HISTORY_WINDOW` mensajes.
3. **Tope de salida.** `MODEL_MAX_TOKENS` en cada llamada.
4. **Caché de AI Gateway.** Con `CACHE_TTL_SECONDS` mayor que 0 se manda
   `cf-aig-cache-ttl`; una llamada con `cf-aig-cache-status: HIT` no cuesta. Cuidado:
   tras cambiar los datos, una respuesta en caché puede estar vieja.

Con `MODEL_PROVIDER=gateway` hacen falta las tres variables `CF_*`. Si el gateway
falla, la API responde `502 {"detail": "model unavailable", "request_id": ...}`. Con
`fake` hay dos modelos simulados con el nombre y el precio de `MODEL_SMALL` y
`MODEL_LARGE`, para medir las palancas sin red.

## Seguridad y producción

- **Una clave por cliente.** `POST /ask` y `GET /metrics` exigen el encabezado
  `X-API-Key`; sin clave o con una inválida responden
  `401 {"detail": "invalid or missing API key"}`. `GET /`, `GET /health` y `/docs` no
  piden clave. Las claves se comparan con `hmac.compare_digest`. Con `API_KEYS` vacía
  nadie entra a las rutas protegidas. Revocar a un cliente es quitar su entrada y
  reiniciar.
- **Nombre del cliente.** Va como `client` en los eventos `request`, `agent_run`,
  `audit` y `error`, y en los metadatos de la traza. La clave nunca se escribe en el
  log, en la traza ni en un error. Si `API_KEYS` está mal formada el producto no
  arranca y el error dice la entrada y su largo, nunca su valor.
- **Límite de peticiones.** Más de `RATE_LIMIT_PER_MINUTE` peticiones de un cliente en
  un minuto dan `429 {"detail": "rate limit exceeded"}` con `Retry-After` (segundos
  que faltan). El límite es por proceso y en memoria.
- **Compliance.** Con `ENVIRONMENT=production` el producto se niega a arrancar si
  `MODEL_PROVIDER` es `fake`, si `API_KEYS` está vacía o tiene una clave de menos de
  16 caracteres, o si las trazas están encendidas y `HIDE_INPUTS` o `HIDE_OUTPUTS` no
  valen `true`. Ver `doc/compliance-checklist.md`.
- **Página.** Tiene un campo de clave (`data-testid="api-key"`). La clave se guarda en
  `sessionStorage` (se pierde al cerrar la pestaña) y se manda en `X-API-Key`. Con
  `401` muestra «Clave inválida» y con `429`, «Demasiadas preguntas; espera N
  segundos».

Ejemplo local con claves:

```
API_KEYS=acme:una-clave-larga-de-prueba uvicorn app.main:app --port 8000
curl -H "X-API-Key: una-clave-larga-de-prueba" localhost:8000/metrics
```

## Documentación

La arquitectura y las decisiones están en `doc/architecture.md` y `doc/adr/`.
