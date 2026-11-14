# 0009. Costo por respuesta desde una tabla de precios

## Contexto
Cada palanca solo se justifica si baja el costo sin bajar la calidad, y eso exige medir el costo también sin red ni cuota.

## Decisión
`app/pricing.py` calcula el costo en USD con `data/model_prices.json` (USD por millón de tokens, por nombre de modelo). El agente lo calcula por llamada: una llamada cacheada (`HIT`) cuesta 0. `POST /ask` devuelve `cost_usd` y `/metrics` lo acumula. El modelo simulado usa el nombre de `MODEL_SMALL` o `MODEL_LARGE`, así que tiene el precio de ese modelo.

## Consecuencias
- La verificación `evaluate` compara línea base y palancas sin gastar cuota.
- Los precios cambian sin tocar el código; un modelo sin precio impide arrancar.
- El costo del modelo simulado es aproximado, porque cuenta palabras y no tokens reales.
- El costo acumulado vive en memoria por proceso, como el resto de las métricas (ADR 0005).
