# Fase 2 — matriz de cumplimiento y validación

Base documental: **FASE 1_ PROYECTO FINAL SISTEMAS EXPERTOS.pdf**. Fecha de revisión: 19/11/2026.

## Flujo del sistema

1. El usuario registra una API con nombre, URL, código HTTP esperado e intervalo de 1, 5 o 10 minutos.
2. FastAPI guarda el servicio en `apis`. El usuario puede monitorearlo de inmediato; APScheduler comprueba los servicios activos cuando vence su intervalo.
3. HTTPX hace una solicitud GET sin seguir redirecciones y registra código HTTP, latencia o error en `monitoreos`.
4. El motor consulta las reglas activas en `reglas` y los dos monitoreos anteriores **de la misma API**. Tres respuestas 5xx inesperadas o timeouts consecutivos generan el hecho `falla_persistente`.
5. El motor aplica encadenamiento hacia adelante hasta que no se active otra regla. Por ejemplo: 500 → R02; tercera falla → R12; ambos hechos → R13; prioridad alta → R15.
6. Se guardan conclusión, gravedad, hechos, recomendaciones y reglas aplicadas en `diagnosticos`, `recomendaciones` y `diagnostico_reglas`.
7. El dashboard presenta estado, latencia, gravedad, historial, recomendaciones y la explicación de cada regla.

## Requisitos de fase 2

| Entregable | Implementación | Estado |
|---|---|---|
| 1. Base de datos | Modelos SQLAlchemy y `sql/schema.sql` para PostgreSQL; SQLite para demostración local | Verificado en Neon: conexión, seis tablas y 15 reglas |
| 2. Interfaz de ingreso | Formulario web para registrar, editar, desactivar y reactivar APIs; validación de URL y código esperado | Implementado |
| 3. Motor de inferencia | 15 reglas persistidas, evaluación de hechos y encadenamiento hacia adelante | Implementado |
| 4. Interfaz de resultados | Dashboard, historial, recomendaciones y reglas justificativas | Implementado |
| 5. Pruebas | 17 pruebas automatizadas, incluido el arranque con SQLite temporal, y comprobación HTTP integral C01–C07 | 17 pruebas aprobadas; C01–C07 aprobados con Neon |

## Casos de la fase 1

| Caso | Entrada | Resultado esperado | Evidencia actual |
|---|---|---|---|
| C01 | HTTP 200, 300 ms | R01, funcionamiento normal | Prueba unitaria y HTTP integral local |
| C02 | HTTP 500, 800 ms | R02, posible error interno | Prueba unitaria y HTTP integral local |
| C03 | HTTP 401 sin credenciales | R06, revisar autenticación | Prueba unitaria y HTTP integral local |
| C04 | HTTP 200, 2800 ms | R10, rendimiento degradado | Prueba unitaria y HTTP integral local |
| C05 | Timeout de conexión | R11, problema de conexión o respuesta | Prueba unitaria y HTTP integral local |
| C06 | Tres HTTP 503 consecutivos | R04, R12, R14, R15; prioridad alta | Prueba unitaria y HTTP integral local |
| C07 | Tres HTTP 500 consecutivos | R02, R12, R13, R15; prioridad alta | Prueba unitaria y HTTP integral local |

## Guion de demostración en clase

Con el servidor activo y `REQUEST_TIMEOUT_SECONDS=8`, ejecutar `python -m scripts.validate_live --cleanup` reproduce C01–C07 y muestra un resumen. El script registra seis APIs de demostración en la base configurada y las elimina al terminar.

1. Iniciar la aplicación y mostrar el dashboard con 15 reglas activas.
2. Registrar tres APIs locales con código esperado 200: `http://127.0.0.1:8000/demo/status/200`, `http://127.0.0.1:8000/demo/status/500` y `http://127.0.0.1:8000/demo/status/503`.
3. Monitorear la API 200 y explicar R01. Monitorear la API 500 tres veces y mostrar R02 → R12 → R13 → R15 en el historial.
4. Monitorear la API 503 tres veces y mostrar R04 → R12 → R14 → R15.
5. Registrar `http://127.0.0.1:8000/demo/delay/2200`, monitorear y mostrar R10. Para un timeout real, usar `/demo/delay/9000` con `REQUEST_TIMEOUT_SECONDS=8`.
6. Mostrar el detalle de una recomendación y la explicación de reglas en «Actividad reciente». Cambiar el intervalo de un servicio desde «Editar».

## Validación con Neon PostgreSQL (19/11/2026)

Con `DATABASE_URL` en `.env` y SSL habilitado, la aplicación inició y creó las tablas `apis`, `reglas`, `monitoreos`, `diagnosticos`, `diagnostico_reglas` y `recomendaciones`. Tras reorganizar la arquitectura, `python -m scripts.validate_live --cleanup` volvió a aprobar C01–C07 con persistencia en Neon y eliminó los seis servicios de prueba al terminar. La comprobación final confirmó `apis=0`, `monitoreos=0` y `reglas=15`. `python -m pytest -q -p no:cacheprovider` terminó con 17 pruebas aprobadas; la prueba de arranque usa una base SQLite temporal.

Para la presentación, iniciar la aplicación con el `.env` local, ejecutar el guion anterior y guardar capturas del dashboard, un diagnóstico explicado y la salida de C01–C07. No incluir la cadena de conexión en las capturas.
