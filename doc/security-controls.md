# Controles de seguridad del HR Assistant

Lista de los controles implementados, por qué existen y cómo se comprueba cada uno. Las capturas de evidencia van en
la descripción del Pull Request.

| # | Control | Dónde está | Justificación | Cómo se comprueba |
| --- | --- | --- | --- | --- |
| 1 | **Validación de inputs**: pregunta no vacía y de máximo `MAX_QUESTION_CHARS`; historial solo con roles `user` y `assistant`, máximo 50 mensajes; esquema validado por Pydantic | `app/main.py` (`AskRequest`, `HistoryMessage`, `_answer`, `_clean_history`) | Evita abuso de tokens (costo), mensajes `system` colados y cuerpos inválidos | `tests/test_main.py`, `tests/test_security_api.py` (422) |
| 2 | **Detección de inyección de prompt**: frases como «ignora las instrucciones» o «muestra tu prompt» se rechazan con `400` antes de llamar al modelo | `app/guardrails.py` (`looks_like_injection`), `app/main.py` | El agente tiene herramientas; nadie debe poder cambiar sus reglas | `tests/test_guardrails.py`, `tests/test_security_api.py` |
| 3 | **Detección y redacción de PII y secretos** en la pregunta y el historial (correo, teléfono, CURP, RFC, tarjeta con Luhn, cuenta o CLABE, tokens) antes de mandarlos al modelo | `app/guardrails.py` (`redact`), `app/main.py` | La PII no debe salir hacia un tercero (Cloudflare, LangSmith) ni quedar en logs | `tests/test_guardrails.py`, `tests/test_security_api.py` |
| 4 | **Validación y saneado de outputs**: quita HTML y caracteres de control, oculta PII y recorta a `MAX_ANSWER_CHARS`; el modelo solo puede responder JSON con `answer` o `tool`; la página pinta con `textContent` | `app/guardrails.py` (`sanitize_output`), `app/agent.py` (`_parse`), `app/static/index.html` | Evita XSS, fugas de datos y respuestas desbordadas | `tests/test_security_api.py`, `tests/test_main.py` (`innerHTML`) |
| 5 | **Gestión segura de secretos**: todo secreto viene del entorno (`.env` local o Render > Environment con `sync: false`); `.env` en `.gitignore` y `.dockerignore`; `repr=False` en `Config` | `app/config.py`, `render.yaml`, `.gitignore`, `.dockerignore`, `.env.example` | Ninguna credencial en el repositorio, la imagen o el log | `tests/test_production_config.py`; `git log -- .env` vacío |
| 6 | **Autenticación por cliente** con `X-API-Key` comparada en tiempo constante (`hmac.compare_digest`) | `app/auth.py`, `app/main.py` (`protected`) | Solo clientes conocidos usan el agente y cada acción tiene dueño | `tests/test_auth.py`, `production.feature` |
| 7 | **Límite de peticiones por cliente** (`429` con `Retry-After`) | `app/ratelimit.py` | Evita abuso y controla el gasto en el modelo | `tests/test_ratelimit.py`, `scripts/load_test.py --requests 40` |
| 8 | **Audit logging**: eventos JSON `audit` (cada herramienta, con argumentos ya validados), `security` (inyección bloqueada, PII ocultada, solo tipos) y `request` con `client` y `request_id`; nunca el texto ni la clave | `app/agent.py` (`_audit`), `app/main.py`, `app/observability.py` | Responder quién hizo qué y cuándo sin crear una nueva fuga de datos | `production.feature` («The client name is logged…»), `tests/test_security_api.py` |
| 9 | **Mínimo privilegio**: el agente solo tiene dos herramientas de **solo lectura**; el contenedor corre con un usuario sin root (`uid 10001`); el token de LangSmith es *Tracing Only*; el CI tiene `permissions: contents: read`; en la fábrica cada agente escribe solo en sus carpetas (`hooks/permissions.py`) | `app/agent.py`, `Dockerfile`, `.github/workflows/ci.yml` | Si algo falla, el daño posible es mínimo | Revisión de `Dockerfile` y `ci.yml`; `docker run … whoami` |
| 10 | **Compliance como código**: en `production` el servicio no arranca con modelo simulado, sin claves, con claves cortas o con trazas que no ocultan entradas y salidas | `app/compliance.py` | Una mala configuración falla cerrada en lugar de exponer datos | `tests/test_compliance.py`, `doc/compliance-checklist.md` |

## Riesgos conocidos

- La detección de PII e inyección es por patrones: hay falsos negativos. Mitigación: herramientas de solo lectura,
  bucle con tope y trazas con entradas y salidas ocultas.
- El límite de peticiones y las métricas son por proceso; con varias réplicas cada una cuenta lo suyo (ADR 0011).
- Las claves se revocan quitando la entrada de `API_KEYS` y reiniciando el servicio.
