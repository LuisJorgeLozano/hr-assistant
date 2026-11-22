# Lista de compliance

Cada regla se revisa sola al arrancar o en cada petición. Una regla nueva exige una fila aquí y una prueba.

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| En producción `MODEL_PROVIDER` no es `fake` | `app/compliance.py`, `check_compliance` | `tests/test_compliance.py`; escenario «Production refuses to start» en `tests/features/production.feature` |
| En producción `API_KEYS` no está vacía | `app/compliance.py`, `check_compliance` | `tests/test_compliance.py`; escenario «Production refuses to start» |
| En producción cada clave tiene 16 o más caracteres | `app/compliance.py`, `check_compliance` | `tests/test_compliance.py`; escenario «Production refuses to start» |
| Con trazas encendidas, `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` | `app/compliance.py`, `check_compliance` | `tests/test_compliance.py`; escenario «Production refuses to start» |
| El mensaje de compliance nombra la regla, nunca un valor | `app/compliance.py`, `check_compliance` | `tests/test_compliance.py`, `test_every_broken_rule_is_reported_together_without_values` |
| `API_KEYS` mal formada impide arrancar y solo dice entrada y largo | `app/config.py`, `parse_api_keys` | `tests/test_production_config.py`; escenario «A malformed API_KEYS prevents startup» |
| `POST /ask` y `GET /metrics` exigen `X-API-Key` | `app/main.py`, dependencia `protected`; `app/auth.py` | `tests/test_auth.py`; `tests/features/production.feature` |
| Las claves se comparan en tiempo constante | `app/auth.py`, `find_client` (`hmac.compare_digest`) | `tests/test_auth.py` (claves casi iguales) |
| La clave nunca aparece en el log, la traza ni un error | `app/config.py` (`repr=False`), `app/observability.py`, `app/tracing.py` | escenario «The client name is logged and the key never is»; `test_repr_of_the_config_never_shows_the_keys` |
| Cada cliente tiene su límite de peticiones por minuto | `app/ratelimit.py`, `RateLimiter`; `app/main.py` | `tests/test_ratelimit.py`; escenarios de límite en `production.feature` |
| El nombre del cliente va en log, auditoría y traza | `app/main.py`, `app/observability.py` (`client_var`), `app/tracing.py` | escenario «The client name is logged and the key never is» |
| La página guarda la clave en `sessionStorage` y no en `localStorage` | `app/static/index.html` | `e2e/test_chat.py` (clave escrita en el campo y clave equivocada) |
| Los secretos no se escriben en el repositorio | `.env.example` sin valores; `render.yaml` con `sync: false` | revisión de `qa-style` y `verification qa` |
| La pregunta y el historial no llevan PII ni secretos al modelo | `app/guardrails.py`, `redact`; `app/main.py`, `_answer` y `_clean_history` | `tests/test_guardrails.py`; `tests/test_security_api.py` |
| Un intento de inyección de prompt se rechaza con `400` antes de llamar al modelo | `app/guardrails.py`, `looks_like_injection` | `tests/test_security_api.py`, `test_prompt_injection_is_blocked_before_calling_the_model` |
| El historial solo admite `user` y `assistant`, máximo 50 mensajes | `app/main.py`, `HistoryMessage` y `_clean_history` | `tests/test_security_api.py` (422) |
| La respuesta sale sin HTML, sin PII y con largo máximo `MAX_ANSWER_CHARS` | `app/guardrails.py`, `sanitize_output` | `tests/test_security_api.py` |
| Cada intervención de seguridad queda auditada sin valores sensibles | `app/main.py`, evento `security` | `tests/test_security_api.py` |
