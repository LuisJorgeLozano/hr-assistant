# 0004. Id por petición y log JSON con reloj inyectado

## Contexto

Para responder qué pasó con una petición hace falta correlacionar todos los eventos con un id y poder leerlos
con herramientas. El log no debe contener datos personales y las pruebas deben ser deterministas.

## Decisión

Un middleware asigna el `request_id` (`X-Request-ID` válido o UUID) y lo guarda en un `contextvar`. El log
escribe una línea JSON por evento (`request`, `agent_run`, `audit`, `error`) en la salida estándar, con `ts`,
`service`, `event` y `request_id`. La hora viene de un reloj inyectado, no de `datetime.now()`. Se registran
longitudes, conteos y nombres de herramienta, nunca el texto de preguntas ni de respuestas.

Campos de los eventos principales:

- `agent_run`: `question_chars`, `history_messages`, `steps`, `tools`, `input_tokens`, `output_tokens`,
  `stopped`, y desde la sesión 3 también `model`, `route`, `cached_calls` y `cost_usd`.
- `audit` (una por herramienta pedida): `action`, `tool` y, solo si el argumento ya está validado, `args`.
  Un `employee_id` se registra únicamente si cumple el patrón `EMP-dddd`; un `department` únicamente si está
  en la lista de departamentos conocidos del directorio (comparación normalizada). Si no, el evento lleva solo
  el nombre de la herramienta y no incluye `args`, de modo que texto libre del modelo o del usuario no llega al log.

## Consecuencias

- Cada petición se reconstruye filtrando por `request_id`.
- Las pruebas usan un reloj fijo y un logger que captura líneas.
- Hay que validar el largo y el contenido del id recibido.
- Cualquier campo nuevo del log debe revisarse contra fugas de datos; `model`, `route`, `cached_calls` y
  `cost_usd` son seguros porque no contienen texto del usuario.
- Un argumento inválido deja una línea `audit` sin `args`: se sabe que se intentó la herramienta, no con qué.
