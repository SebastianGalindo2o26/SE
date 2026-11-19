# Sistema Experto para Monitoreo y Diagnóstico de APIs REST

Implementación de la fase 2 basada en la documentación de fase 1. Incluye FastAPI, SQLAlchemy, HTTPX, PostgreSQL/Neon, interfaz web adaptable a móvil, monitoreo periódico y reglas con encadenamiento hacia adelante. SQLite permite ejecutar una demostración local sin cuenta Neon.

La [arquitectura](ARQUITECTURA.md) describe los módulos, el flujo de razonamiento y las tablas.
La [guía de interfaz](GUIA_INTERFAZ.md) explica cada sección y acción del dashboard desde el punto de vista del usuario.

## Requisitos

- Python 3.11 o superior. En este equipo se detectó Python 3.12.6 de 64 bits.
- Para usar Neon: una URL PostgreSQL de Neon con SSL habilitado.

## Instalación y ejecución en Windows PowerShell

```powershell
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
& .\.venv\Scripts\python.exe -m app
```

Abrir <http://127.0.0.1:8000>. Las tablas y las 15 reglas se inicializan en el primer arranque en la base indicada por `DATABASE_URL`. Si se usa la configuración de `.env.example`, se crea `api_expert.db` (SQLite). Puedes registrar, editar, desactivar y reactivar APIs, monitorearlas a mano y configurar comprobaciones automáticas cada 1, 5 o 10 minutos mientras la aplicación esté abierta.

## Demostración en clase

Usa una API local de prueba en el formulario: `http://127.0.0.1:8000/demo/status/200`, `/demo/status/500`, `/demo/status/503` o `/demo/delay/2200` (antepone `http://127.0.0.1:8000` a cada ruta). Para demostrar R02/R12/R13/R15, registra la URL de estado 500 y pulsa «Monitorear ahora» tres veces. Los endpoints `/demo/*` son solo simuladores de lectura y no escriben en la base.

Para Neon, asigna en `.env` el `DATABASE_URL` del panel de Neon con SSL habilitado. El archivo `.env` se carga automáticamente y no debe compartirse ni subirse al repositorio. `sql/schema.sql` contiene el esquema de referencia; SQLAlchemy crea las tablas al iniciar. La conexión con Neon, las seis tablas, las 15 reglas y los casos C01–C07 se verificaron el 19/11/2026.

## Componentes

- **Ingreso de datos:** formulario web y `POST /apis`.
- **Monitoreo:** HTTP GET con timeout; registra estado, latencia y errores.
- **Base de conocimiento:** `app/infrastructure/knowledge.py` y tabla `reglas`; definición, prioridad y activación persistidas en PostgreSQL/SQLite. La lista puede consultarse en `GET /api/rules`.
- **Motor de inferencia:** `app/domain/rules.py`; propaga conclusiones hasta que no se activa ninguna regla.
- **Resultado y explicación:** dashboard, recomendaciones y vínculo de reglas aplicadas.
- **Historial:** `GET /api/history`; `GET /api/apis`; `GET /health`.

El código está organizado en `app/domain/` (reglas y políticas puras), `app/application/` (caso de uso), `app/infrastructure/` (HTTP, SQLAlchemy y programador) y `app/web/` (rutas e interfaz). `app/main.py` ensambla los componentes. Consulta [arquitectura](ARQUITECTURA.md) para el flujo completo.

## Reglas y alcance de diagnóstico

Incluye R01–R15. R15 cubre la recomendación de revisión inmediata mencionada en la fase 1, aunque no tenía fila en la tabla original. Tres respuestas 5xx o timeouts consecutivos de una misma API activan R12; al combinarse con HTTP 500 o 503 activan R13/R14 y después R15. HTTP 401 y 404 se tratan como posibles resultados esperados según la configuración del endpoint.

## Pruebas

La [matriz de validación](FASE2_VALIDACION.md) relaciona los entregables de fase 2 con los casos C01–C07 y ofrece un guion de presentación.

Con el servidor abierto en otra terminal, ejecuta `& .\.venv\Scripts\python.exe -m scripts.validate_live --cleanup` para recorrer C01–C07 mediante HTTP. El script agrega seis APIs de demostración a la base configurada y las elimina al terminar. Los siete casos pasaron con Neon; la comprobación final dejó 15 reglas y ninguna API o medición de prueba.

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
```

Los destinos con direcciones privadas solo se permiten si el host está incluido en `ALLOWED_PRIVATE_HOSTS`; por defecto se habilita localhost para el servicio de demostración.

## Seguridad local

El dashboard solo escucha en `127.0.0.1`. Los formularios POST exigen un token CSRF; el servidor acepta únicamente los hosts de `ALLOWED_APP_HOSTS`. Para monitorear una API pública autorizada, agrega su nombre de host exacto a `ALLOWED_TARGET_HOSTS` en `.env` y reinicia la aplicación. Los hosts privados requieren además `ALLOWED_PRIVATE_HOSTS`. Para PostgreSQL, `DATABASE_URL` debe incluir `sslmode=require`, `verify-ca` o `verify-full`.

La aplicación está preparada para uso local de clase. Si se publica en internet, se debe añadir autenticación, límites de solicitudes y una política de red de salida más estricta antes de abrirla a otros usuarios.
