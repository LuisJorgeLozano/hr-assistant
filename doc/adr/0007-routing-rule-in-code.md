# 0007. Enrutamiento por regla en código

## Contexto
La mayoría de las preguntas son búsquedas simples y un modelo grande cuesta unas 6 veces más por token de entrada y de salida que uno pequeño. Se necesita elegir el modelo por pregunta sin gastar otra llamada.

## Decisión
Una función pura en `app/router.py` elige `MODEL_LARGE` si `ROUTING=false`, si la pregunta pasa de `ROUTER_MAX_CHARS` o si contiene una palabra clave («compara», «resume», «explica», «por qué», «analiza», «todos»). Si no, elige `MODEL_SMALL`. Devuelve también el motivo, que viaja como `route`. El modelo se elige una vez por pregunta y se usa en todas las vueltas del bucle.

## Consecuencias
- Costo cero de decidir y comportamiento determinista y fácil de probar.
- Una regla simple puede equivocarse; el set de evaluación mide si la calidad baja.
- La interfaz `complete(messages, model)` recibe el nombre del modelo, así que un mismo proveedor atiende a ambos.
