# 0003. Un solo agente con bucle acotado

## Contexto
El modelo decide en cada vuelta si pide una herramienta o responde. Sin límite, un modelo defectuoso podría repetir llamadas sin fin.

## Decisión
Un único agente con dos herramientas de solo lectura y un tope `AGENT_MAX_STEPS` (por omisión 3, validado al arrancar). Al agotarlo responde con el mensaje fijo `No pude completar la respuesta. Intenta con una pregunta más concreta.`

## Consecuencias
- Costo y latencia tienen un máximo conocido por petición.
- Preguntas que requieran más de las vueltas permitidas fallan con un mensaje claro en lugar de colgarse.
- Las herramientas de solo lectura limitan el daño de un mal uso del modelo.
