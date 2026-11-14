# 0011. Límite de peticiones en memoria, por proceso y con reloj inyectado

## Contexto

Sin límite, un cliente con clave válida puede gastar toda la cuota del modelo. El producto es sin estado (ADR 0001)
y sus métricas ya son por proceso (ADR 0005). Agregar Redis para un límite exacto complicaría el despliegue gratuito.

## Decisión

`ratelimit.py` cuenta las peticiones de cada cliente autenticado en la última ventana de un minuto, en memoria. Si
pasan de `RATE_LIMIT_PER_MINUTE` (30 por omisión) responde `429 {"detail": "rate limit exceeded"}` con
`Retry-After` en segundos. Se evalúa después de la clave, así que una clave inválida no crea registros. El reloj se
inyecta (como en el ADR 0004) para probarlo sin esperar.

## Consecuencias

- Con N copias el límite efectivo es N veces mayor; es aceptable con una copia en Render free y se documenta.
- Al reiniciar el proceso los contadores vuelven a cero.
- Se purgan las marcas vencidas para que la memoria quede acotada.
- Si se necesita un límite global, habrá que moverlo a un almacén compartido con otro ADR.
