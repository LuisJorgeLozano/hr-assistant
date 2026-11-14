# Arquitectura del HR Assistant

API FastAPI sin estado con un agente que usa un modelo (interfaz) y dos herramientas de solo lectura.
La sesión 2 agrega observabilidad: id por petición, log JSON, métricas por proceso y trazas opcionales.
La sesión 3 agrega el modelo real por AI Gateway y cuatro palancas de costo: enrutamiento, ventana de historial,
tope de salida y caché del gateway.
La sesión 4 lo publica de forma segura: clave por cliente, límite de peticiones, compliance al arrancar,
contenedor, CI y Render.

```mermaid
flowchart LR
    Web[Pagina web index.html] -->|POST /ask con X-API-Key e history| MW[Middleware request_id y latencia]
    Web -->|GET /, GET /health| MW
    Web -->|GET /metrics con X-API-Key| MW
    MW --> API[main.py create_app]
    API -->|al arrancar| Comp[compliance.py reglas de produccion]
    Comp --> Cfg[config.py ENVIRONMENT, API_KEYS, RATE_LIMIT]
    API --> Cfg
    API -->|1 clave| Auth[auth.py compare_digest]
    Auth -->|cliente| RL[ratelimit.py ventana por cliente, reloj inyectado]
    Auth -.->|401| MW
    RL -.->|429 con Retry-After| MW
    RL --> Agent[agent.py bucle con tope]
    Agent -->|1 recorta historial HISTORY_WINDOW| Agent
    Agent -->|2 elige modelo| Router[router.py regla en codigo]
    Agent -->|3 complete messages, model| LLM[llm.py interfaz]
    LLM --> Fake[FakeModel precio por nombre]
    LLM -->|max_tokens, cf-aig-cache-ttl| GW[GatewayModel httpx]
    GW --> CF[(AI Gateway y Workers AI)]
    LLM -->|tool o answer, tokens, cached| Agent
    Agent -->|costo por llamada| Price[pricing.py]
    Price --> Prices[(data/model_prices.json)]
    Agent -->|get_employee, search_by_department| Dir[directory.py]
    Dir --> Data[(data/employees.json)]
    API -->|ModelUnavailable: 502| MW
    MW --> Obs[observability.py reloj, log JSON con client, Metrics con cost_usd]
    Agent -->|agent_run y audit con client| Obs
    Obs -->|una linea JSON por evento| Stdout[(salida estandar)]
    API -->|GET /metrics con cost_usd| Obs
    Agent -.->|opcional, solo con clave| Trace[tracing.py]
    LLM -.-> Trace
    Trace -.-> LS[(LangSmith)]

    Dev[Push o pull request] --> CI[GitHub Actions: style, unit, e2e, docker]
    CI -->|checksPass| Render[Render: Dockerfile, healthCheckPath /health]
    Render --> API
    Smoke[scripts/smoke.py con SMOKE_API_KEY] -->|health, ask sin clave, ask con clave| Render
```

## Decisiones

- 0001: API sin estado.
- 0002: modelo detrás de una interfaz.
- 0003: un solo agente con bucle acotado.
- 0004: id por petición y log JSON con reloj inyectado.
- 0005: métricas en memoria por proceso.
- 0006: trazas opcionales en LangSmith, ocultas por omisión.
- 0007: enrutamiento por regla en código.
- 0008: modelo real por AI Gateway y fallo como 502.
- 0009: costo por respuesta desde una tabla de precios.
- 0010: una clave por cliente en un encabezado.
- 0011: límite de peticiones en memoria, por proceso y con reloj inyectado.
- 0012: compliance como código que impide arrancar.

## Notas

- `create_app()` recibe configuración, modelo, directorio, reloj y logger, para que las pruebas inyecten los suyos.
- El historial vive en el navegador y viaja en cada petición; el agente solo manda los últimos `HISTORY_WINDOW` mensajes.
- El log nunca incluye el texto de preguntas ni de respuestas, ni el token de Cloudflare, ni las claves de cliente;
  las trazas ocultan entradas y salidas por omisión.
- El evento `agent_run` registra además `model`, `route`, `cached_calls` y `cost_usd`.
- `GET /metrics` incluye `cost_usd`, el costo acumulado del proceso, y exige clave.
- El evento `audit` registra `args` solo si ya están validados (`employee_id` con patrón `EMP-dddd`, `department`
  dentro de la lista conocida); si no, registra solo el nombre de la herramienta.
- El modelo se elige una vez por pregunta y se usa en todas las vueltas del bucle.
- Los eventos del log llevan `client` (el nombre, nunca la clave) cuando la petición está autenticada.
- Se evalúa primero la clave y después el límite: una clave inválida nunca consume límite ni crea registros.
- El límite es por proceso, igual que las métricas; con varias copias cada una cuenta lo suyo.
