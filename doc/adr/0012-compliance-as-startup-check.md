# 0012. Compliance como código que impide arrancar

## Contexto

Las reglas de seguridad escritas solo en un documento se olvidan. Un despliegue con el modelo simulado, sin claves o con
trazas que mandan preguntas de personas a un tercero sería un incidente. Las variables vienen de Render y no se
revisan antes de publicar.

## Decisión

`compliance.py` expone `check_compliance(config)`, que `create_app()` llama al arrancar. Con
`ENVIRONMENT=production` lanza `ConfigError` si `MODEL_PROVIDER` es `fake`, si `API_KEYS` está vacía o tiene una
clave de menos de 16 caracteres, o si las trazas están encendidas y `HIDE_INPUTS` o `HIDE_OUTPUTS` no valen `true`.
Los mensajes nombran la regla, nunca un valor. `doc/compliance-checklist.md` mapea cada regla a su código y a su
prueba. Render publica solo si el CI pasa (`autoDeployTrigger: checksPass`) y `/health` responde
(`healthCheckPath`); `scripts/smoke.py` comprueba el servicio ya publicado.

## Consecuencias

- Una configuración insegura produce un contenedor que no arranca y Render no lo da por bueno: falla cerrado.
- En desarrollo no se bloquea nada, para no estorbar a las pruebas.
- Cada regla nueva exige una fila en la lista de compliance y una prueba.
- La comprobación ocurre al importar `app.main`, así que las pruebas que lo importan deben fijar su entorno.
