# 0008. Modelo real por AI Gateway y fallo como 502

## Contexto
Se agrega un modelo real (Cloudflare Workers AI) detrás de AI Gateway, que ofrece caché. Las llamadas de red fallan y el token es secreto.

## Decisión
`GatewayModel` en `app/llm.py` implementa la misma interfaz que `FakeModel`, usa httpx y se elige con `MODEL_PROVIDER=gateway`. Manda `max_tokens` y `temperature` en cada llamada y `cf-aig-cache-ttl` solo si `CACHE_TTL_SECONDS` es mayor que 0. Lee tokens de `usage` y la caché de `cf-aig-cache-status`. Cualquier fallo se convierte en `ModelUnavailable` y la API responde `502 {"detail": "model unavailable", "request_id"}`. Sin las tres variables `CF_*` no arranca.

## Consecuencias
- El agente y la API no conocen a Cloudflare; las pruebas usan `httpx.MockTransport`, sin red.
- El token y los mensajes de error de httpx no se registran: el log solo lleva el tipo del error.
- No hay reintentos: un fallo se ve de inmediato y no duplica el costo.
