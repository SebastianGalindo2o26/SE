# Sistema Experto para Monitoreo y Diagnóstico de APIs REST

Implementación de la fase 2 basada en la documentación de fase 1. Incluye FastAPI, SQLAlchemy, HTTPX, PostgreSQL/Neon, interfaz web adaptable a móvil, monitoreo periódico y reglas con encadenamiento hacia adelante. SQLite permite ejecutar una demostración local sin cuenta Neon.

La [arquitectura](ARQUITECTURA.md) describe los módulos, el flujo de razonamiento y las tablas.
La [guía de interfaz](GUIA_INTERFAZ.md) explica cada sección y acción del dashboard desde el punto de vista del usuario.
La [guía de pruebas locales](PRUEBAS_LOCALES.md) contiene instalación, Docker opcional, flujo de componentes y casos C01–C08 paso a paso.

## Requisitos

- Python 3.11 o superior.
- Para usar Neon: una URL PostgreSQL de Neon con SSL habilitado.

## Instalación y ejecución en Windows PowerShell

```powershell
python --version
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
& .\.venv\Scripts\python.exe -m scripts.setup_credentials
& .\.venv\Scripts\python.exe -m app
```

Abrir <http://127.0.0.1:8000>. Las tablas y las 15 reglas se inicializan en el primer arranque en la base indicada por `DATABASE_URL`. Si se usa la configuración de `.env.example`, se crea `api_expert.db` (SQLite). Puedes registrar, editar, desactivar y reactivar APIs, monitorearlas a mano y configurar comprobaciones automáticas cada 1, 5 o 10 minutos mientras la aplicación esté abierta.

## Docker opcional

Con Docker Desktop iniciado y `.env` preparado, ejecuta `docker compose build`, `docker compose run --rm sentinel python -m scripts.setup_credentials` y `docker compose up -d`. Abre la misma URL local; `docker compose down` detiene la aplicación y conserva la base SQLite del volumen. La [guía de pruebas locales](PRUEBAS_LOCALES.md) explica ambos métodos y cómo verificar C01–C08 desde el contenedor.

## Demostración en clase

Usa una API local de prueba en el formulario: `http://127.0.0.1:8000/demo/status/200`, `/demo/status/500`, `/demo/status/503` o `/demo/delay/2200` (antepone `http://127.0.0.1:8000` a cada ruta). Para demostrar R02/R12/R13/R15, registra la URL de estado 500 y pulsa «Monitorear ahora» tres veces. Para probar una API protegida, registra `http://127.0.0.1:8000/demo/auth`, elige **API key en header**, escribe `X-Demo-Key` y usa `sentinel-demo` como clave de demostración. Los endpoints `/demo/*` son simuladores de lectura y no escriben en la base.

Para Neon, asigna en `.env` el `DATABASE_URL` del panel de Neon con SSL habilitado. El archivo `.env` se carga automáticamente y no debe compartirse ni subirse al repositorio. `sql/schema.sql` contiene el esquema de referencia; SQLAlchemy crea las tablas al iniciar. La conexión con Neon, las siete tablas, las 15 reglas y los casos C01–C08 se verificaron el 20/11/2026.

## APIs con autenticación

En **Conecta un servicio**, selecciona **Sin autenticación**, **Bearer token**, **API key en header** o **Usuario y contraseña (Basic)**. Para API key, indica el nombre del header que exige el proveedor, por ejemplo `X-API-Key`. Para editar una API, deja el campo secreto vacío si quieres conservar su valor, escribe uno nuevo para cambiarlo o selecciona **Sin autenticación** para eliminarlo. El monitoreo manual y el automático usan la misma configuración.

Los secretos se cifran antes de guardarse en `credenciales_api`. La clave de cifrado `CREDENTIALS_ENCRYPTION_KEY` se genera con `python -m scripts.setup_credentials` y queda solo en `.env`; no aparece en el dashboard, en `/api/apis` ni en `/api/history`. Si usas la misma base Neon desde otro equipo, copia **la misma clave de cifrado** de forma segura al `.env` de ese equipo: una clave nueva no descifra credenciales ya guardadas. No coloques claves en la URL. Las APIs protegidas deben usar HTTPS; se permite HTTP solo para localhost en la demostración.

El sistema realiza GET sin seguir redirecciones y cubre esos mecanismos de autenticación comunes. OAuth2 con renovación de token, firmas por solicitud y certificados de cliente requieren una integración específica. Puedes registrar una URL pública HTTP/HTTPS directamente, sin agregar su host a `.env`.

## Componentes

- **Ingreso de datos:** formulario web y `POST /apis`.
- **Monitoreo:** HTTP GET con timeout y autenticación configurada; registra estado, latencia y errores.
- **Base de conocimiento:** `app/infrastructure/knowledge.py` y tabla `reglas`; definición, prioridad y activación persistidas en PostgreSQL/SQLite. La lista puede consultarse en `GET /api/rules`.
- **Motor de inferencia:** `app/domain/rules.py`; propaga conclusiones hasta que no se activa ninguna regla.
- **Resultado y explicación:** dashboard, recomendaciones y vínculo de reglas aplicadas.
- **Historial:** `GET /api/history`; `GET /api/apis`; `GET /health`.

El código está organizado en `app/domain/` (reglas y políticas puras), `app/application/` (caso de uso), `app/infrastructure/` (HTTP, SQLAlchemy y programador) y `app/web/` (rutas e interfaz). `app/main.py` ensambla los componentes. Consulta [arquitectura](ARQUITECTURA.md) para el flujo completo.

## Reglas y alcance de diagnóstico

Incluye R01–R15. R15 cubre la recomendación de revisión inmediata mencionada en la fase 1, aunque no tenía fila en la tabla original. Tres respuestas 5xx o timeouts consecutivos de una misma API activan R12; al combinarse con HTTP 500 o 503 activan R13/R14 y después R15. HTTP 401 y 404 se tratan como posibles resultados esperados según la configuración del endpoint.

## Pruebas

La [matriz de validación](FASE2_VALIDACION.md) relaciona los entregables de fase 2 con los casos C01–C07 de la fase 1 y el caso adicional C08 de autenticación.

Con el servidor abierto en otra terminal, ejecuta `& .\.venv\Scripts\python.exe -m scripts.validate_live --cleanup` para recorrer C01–C08 mediante HTTP. El script agrega siete APIs de demostración a la base configurada y las elimina al terminar. Los ocho casos pasaron con Neon; la comprobación final dejó 15 reglas y ninguna API o medición de prueba.

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
```

Los destinos con direcciones privadas solo se permiten si el host está incluido en `ALLOWED_PRIVATE_HOSTS`; por defecto se habilita localhost para el servicio de demostración.

## Seguridad local

El dashboard solo escucha en `127.0.0.1`. Los formularios POST exigen un token CSRF; el servidor acepta únicamente los hosts de `ALLOWED_APP_HOSTS`. Las APIs públicas se registran con su URL directamente. Los destinos privados requieren incluir su hostname exacto en `ALLOWED_PRIVATE_HOSTS`; la conexión se fija a una IP validada para evitar que una segunda resolución DNS cambie el destino. Para PostgreSQL, `DATABASE_URL` debe incluir `sslmode=require`, `verify-ca` o `verify-full`.

La aplicación está preparada para uso local de clase. Si se publica en internet, se debe añadir autenticación, límites de solicitudes y una política de red de salida más estricta antes de abrirla a otros usuarios.
