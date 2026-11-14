# 0001. API sin estado

## Contexto
El asistente debe poder crecer sin rediseño. Guardar conversaciones en el servidor obligaría a compartir o sincronizar ese estado entre copias.

## Decisión
La API no guarda nada entre peticiones. El cliente envía `history` en cada `POST /ask`. Los datos de empleados se cargan en solo lectura y el agente se crea por petición.

## Consecuencias
- Escalar es correr más copias detrás de un balanceador, sin sesiones.
- Cada petición es más grande porque lleva el historial.
- No hay memoria del lado servidor; el navegador es dueño de la conversación.
