# 0010. Una clave por cliente en un encabezado

## Contexto

El producto se publica en internet. `POST /ask` cuesta dinero y `GET /metrics` revela uso. Hace falta saber
quién llama (para el log, la auditoría y las trazas) y poder revocar a un cliente sin afectar a los demás.

## Decisión

`API_KEYS` tiene la forma `cliente:clave,cliente2:clave2`. Una dependencia de FastAPI (`auth.py`) exige
`X-API-Key` en `POST /ask` y `GET /metrics`, compara con `hmac.compare_digest` y responde
`401 {"detail": "invalid or missing API key"}` si falla. `/`, `/health` y `/docs` quedan abiertos. El nombre del
cliente viaja en `request.state` y se agrega a log, auditoría y trazas. La clave nunca se escribe: ni en el log, ni
en errores, y si `API_KEYS` está mal formada el error dice la posición de la entrada y su largo.

## Consecuencias

- Revocar un cliente es quitar su entrada y reiniciar; no hay base de datos, y la API sigue sin estado.
- Con `API_KEYS` vacía nadie entra a las rutas protegidas (falla cerrado); las pruebas inyectan sus claves.
- Las claves viven en una variable de entorno: rotarlas exige reiniciar el servicio.
- La página guarda la clave solo en `sessionStorage`, así que se pierde al cerrar la pestaña.
