# 0006. Trazas opcionales en LangSmith, ocultas por omisión

## Contexto

Las trazas ayudan a depurar corridas del agente, pero mandan datos a un servicio externo. El producto debe
funcionar sin clave, sin red y sin exponer preguntas o respuestas de personas.

## Decisión

Un módulo `tracing.py` envuelve `@traceable` de `langsmith` en la corrida del agente, la llamada al modelo y
cada herramienta, con `request_id` en los metadatos. Solo se activa con `LANGSMITH_TRACING=true` y
`LANGSMITH_API_KEY`; en otro caso es un no-op que no se conecta. `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true`
por omisión. La clave se lee del entorno y nunca se escribe en el log ni en el código.

## Consecuencias

- Sin clave, el comportamiento es idéntico al de la sesión 1 más el log.
- Para ver entradas y salidas en LangSmith hay que desactivar los ocultamientos de forma explícita.
- Se agrega la dependencia `langsmith` a `requirements.txt`.
- Un fallo del servicio de trazas no debe afectar la respuesta.
