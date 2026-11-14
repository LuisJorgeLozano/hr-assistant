# 0002. Modelo detrás de una interfaz

## Contexto
Hoy solo existe un modelo simulado, pero se espera cambiarlo por uno real sin reescribir el agente.

## Decisión
El agente depende solo de `complete(messages)`, que devuelve un objeto JSON (`tool` o `answer`). La implementación se elige con `MODEL_PROVIDER` y `create_app()` recibe el modelo por inyección. En esta sesión solo existe `fake`.

## Consecuencias
- Las pruebas son deterministas, sin red ni costo.
- Un modelo real exige solo una nueva clase y un valor de `MODEL_PROVIDER`.
- El protocolo JSON es el contrato; un modelo real tendrá que respetarlo o el agente lo tratará como error.
