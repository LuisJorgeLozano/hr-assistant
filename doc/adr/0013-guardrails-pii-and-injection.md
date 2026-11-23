# 0013. Guardrails de entrada y salida: PII, secretos e inyección de prompt

## Contexto

El HR Assistant recibe texto libre de personas y lo manda a un modelo de un tercero (Cloudflare Workers AI). Una
persona puede escribir su correo, su teléfono, su CURP o pegar un token por error; el modelo también puede devolver
datos así o HTML. Además, alguien puede intentar cambiar las instrucciones del agente («ignora las instrucciones…»)
o colar un mensaje `system` en el historial.

## Decisión

`app/guardrails.py` concentra controles deterministas, sin red y sin dependencias nuevas:

- `redact(text)`: reemplaza correo, teléfono, CURP, RFC, tarjeta (Luhn), número de cuenta o CLABE y secretos
  (`sk-…`, `Bearer …`, `lsv2_…`) por `[REDACTED:<tipo>]`. Devuelve el texto limpio y **solo los tipos**.
- `looks_like_injection(text)`: heurística de frases típicas de inyección de prompt, en español e inglés.
- `sanitize_output(text, max_chars)`: quita caracteres de control y etiquetas HTML, oculta PII y recorta a
  `MAX_ANSWER_CHARS`.

`main.py` los aplica en `POST /ask`, en este orden: largo de la pregunta (422) → historial (solo `user` y
`assistant`, máximo 50 mensajes y cada uno con el largo máximo de la pregunta; 422) → inyección (400
`question rejected by input policy`) → PII de la pregunta y del historial **antes** de llamar al modelo → agente →
saneado de la respuesta. Cada intervención deja un evento `security` en el log con el cliente y los tipos, nunca los
valores. La respuesta agrega `pii_redacted` con los tipos ocultados.

## Consecuencias

- El modelo externo y LangSmith nunca reciben la PII que se detecta; el log tampoco.
- Las expresiones regulares tienen falsos negativos (por ejemplo un teléfono escrito con letras) y algún falso
  positivo (un número largo sin relación). Se prefirió ocultar de más antes que filtrar de menos.
- La detección de inyección es una capa más, no la única: las herramientas siguen siendo de solo lectura, sus
  argumentos se validan y el bucle tiene tope.
- Un servicio de DLP gestionado (por ejemplo Presidio o Cloud DLP) daría mejor cobertura a cambio de latencia,
  costo y una dependencia más; queda como mejora futura.
