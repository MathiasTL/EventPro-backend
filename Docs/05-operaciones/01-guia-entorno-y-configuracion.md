# 01. Guía de Entorno y Variables de Configuración

---

## 1. Principio de los Doce Factores (Twelve-Factor App)

La configuración del backend de **EventPro** se gestiona estrictamente a través de variables de entorno mediante **Pydantic Settings**, garantizando que el mismo artefacto de código pueda ejecutarse en desarrollo local, pruebas automatizadas (CI/CD) o producción sin requerir cambios en el código fuente.

---

## 2. Especificación Detallada del Archivo `.env.example`

A continuación se detalla cada una de las variables requeridas por el sistema:

### 2.1 Configuración de la Aplicación y Servidor
* `APP_ENV`: Entorno de ejecución (`development`, `staging`, `production`).
* `APP_NAME`: Nombre del servicio (`EventPro-Backend`).
* `API_V1_PREFIX`: Prefijo de rutas (`/api/v1`).
* `PORT`: Puerto de escucha HTTP (por defecto `8000`).
* `DEBUG`: Modo de depuración booleano (`true` en desarrollo, `false` en producción).
* `LOG_LEVEL`: Nivel mínimo de los logs JSON estructurados (`DEBUG`, `INFO`, `WARNING`, `ERROR`; por defecto `INFO`).
* `SECRET_KEY`: Cadena criptográfica de al menos 32 caracteres para firma de tokens JWT (PyJWT).
* `ACCESS_TOKEN_EXPIRE_MINUTES`: Vida del access token (por defecto `60`, ver [RBAC, sección 3.1](../04-api/02-matriz-rbac-y-seguridad.md)).
* `REFRESH_TOKEN_EXPIRE_DAYS`: Vida del refresh token rotativo (por defecto `7`).
* `CORS_ORIGINS`: Lista de orígenes autorizados separados por coma (ej. `http://localhost:3000,https://app.eventpro.pe`).

### 2.2 Base de Datos PostgreSQL
* `POSTGRES_HOST`: Host del servidor de base de datos (`localhost` o `db` en docker-compose).
* `POSTGRES_PORT`: Puerto TCP (`5432`).
* `POSTGRES_USER`: Usuario administrador de la base de datos (`eventpro_user`).
* `POSTGRES_PASSWORD`: Contraseña segura del usuario.
* `POSTGRES_DB`: Nombre de la base de datos relacional (`eventpro_db`).
* `DATABASE_URL`: Cadena de conexión completa (`postgresql+asyncpg://eventpro_user:secret@localhost:5432/eventpro_db`).

### 2.3 Caché y Locks Distribuidos con Redis
* `REDIS_HOST`: Host del servidor Redis (`localhost` o `redis`).
* `REDIS_PORT`: Puerto TCP (`6379`).
* `REDIS_PASSWORD`: Contraseña de autenticación de Redis (opcional en desarrollo).
* `REDIS_DB`: Índice de la base de datos Redis (`0`).

### 2.4 Integración con Meta WhatsApp Cloud API
* `WHATSAPP_API_URL`: URL base de Graph API de Meta (`https://graph.facebook.com/v20.0`).
* `WHATSAPP_PHONE_NUMBER_ID`: Identificador del número de teléfono registrado en WhatsApp Business.
* `WHATSAPP_ACCESS_TOKEN`: Token de acceso permanente o de sistema generado en Meta for Developers.
* `WHATSAPP_VERIFY_TOKEN`: Token secreto configurado para el handshake del Webhook (`GET /webhooks/whatsapp`).
* `WHATSAPP_APP_SECRET`: Secreto de la aplicación de Meta con el que se valida la cabecera `X-Hub-Signature-256` (HMAC-SHA256) de `POST /webhooks/whatsapp`. Obligatorio en `staging` y `production`.

### 2.5 Integración con Google Maps Platform
* `GOOGLE_MAPS_API_KEY`: Clave de API de Google Cloud con permisos para Directions API y Distance Matrix API.
* `PROMOTORA_BASE_LATITUDE`: Latitud del almacén/base de operaciones de la promotora en Lima (`-12.0864`).
* `PROMOTORA_BASE_LONGITUDE`: Longitud de la base de operaciones en Lima (`-77.0328`).

### 2.6 Parámetros Configurables de Reglas de Negocio
* `SIMULTANEOUS_SHOWS_THRESHOLD`: Cantidad máxima de shows simultáneos (solapamiento real de intervalos $[\text{inicio}, \text{fin})$, contando solo eventos con adelanto validado y no cancelados) antes de exigir aprobación manual del encargado (por defecto `3`).
* `ADVANCE_DEADLINE_HOURS`: Horas de vigencia de la cotización para recibir el comprobante del adelanto, contadas desde su envío; al vencer, la cotización pasa a `EXPIRED` (por defecto `24`).
* `AVAILABILITY_RECHECK_MINUTES`: Minutos transcurridos desde el envío de la cotización a partir de los cuales el bot revalida la disponibilidad antes de mostrar los datos de Yape, Plin o cuenta bancaria (por defecto `60`).
* `MOBILITY_MARGIN_PERCENT`: Margen comercial porcentual sobre el costo base de traslado (por defecto `15`).
* `ADVANCE_PERCENT`: Porcentaje del adelanto sobre servicios base (por defecto `10`).
* `TRANSIT_REST_BUFFER_MINUTES`: Minutos mínimos de margen para descanso y desarme entre shows sucesivos (por defecto `30`).

### 2.7 Repositorio de Archivos y Documentos
* `STORAGE_BACKEND`: Tipo de almacenamiento (`local` o `s3`).
* `LOCAL_STORAGE_PATH`: Directorio en disco para comprobantes y contratos PDF (por defecto `./uploads`; en Docker Compose se fija a `/app/uploads`, respaldado por el volumen `uploads_data`).

### 2.8 Firma Electrónica de Contratos (ADR-07)
* `SIGNATURE_PKCS12_PATH`: Ruta al certificado PKCS#12 (`.p12`) con el que se sella el PDF (PAdES). En local se coloca en `./secrets/` (ignorado por git); en Docker Compose se monta en solo lectura y la variable se fija a `/run/secrets/eventpro-signing.p12`.
* `SIGNATURE_PKCS12_PASSWORD`: Contraseña del archivo `.p12`. Es un secreto: nunca se versiona.
* `SIGNATURE_TSA_URL`: URL de la autoridad de sellado de tiempo RFC 3161 (opcional; vacía desactiva la marca de tiempo).
* `SIGNATURE_LINK_TTL_HOURS`: Vigencia del enlace de firma enviado por WhatsApp (por defecto `168`, equivalente a 7 días).
* `SIGNATURE_OTP_TTL_MINUTES`: Vigencia del código OTP de 6 dígitos (por defecto `10`).
* `SIGNATURE_OTP_MAX_ATTEMPTS`: Intentos fallidos permitidos por OTP antes de invalidarlo (por defecto `5`).
* `SIGNATURE_OTP_PROOF_TTL_MINUTES`: Vigencia de la prueba de OTP (`otp_proof`) emitida al verificar el código (por defecto `15`).

### 2.9 Instrucciones de Pago Mostradas por el Bot
Datos que el bot revela al cliente cuando toca «Pagar adelanto» (ver RF-08 y la regla de revalidación de disponibilidad). Se leen de la configuración y no se escriben en el código ni en las plantillas:
* `PAYMENT_YAPE_NUMBER`: Número de Yape de la promotora.
* `PAYMENT_PLIN_NUMBER`: Número de Plin de la promotora.
* `PAYMENT_BANK_NAME`: Nombre del banco para transferencias.
* `PAYMENT_BANK_ACCOUNT`: Número de cuenta bancaria.
* `PAYMENT_BANK_CCI`: Código de cuenta interbancario (CCI).
* `PAYMENT_ACCOUNT_HOLDER`: Titular de las cuentas y billeteras.

### 2.10 Arranque del Usuario `SUPERADMIN`
Variables leídas únicamente por el comando de arranque `python -m app.infrastructure.adapters.secondary.persistence.bootstrap_superadmin` (ver [Estrategia de Migraciones y Seeds, sección 4](../03-datos/03-estrategia-migraciones-y-seeds.md#4-comando-de-arranque-del-usuario-superadmin)):
* `SUPERADMIN_EMAIL`: Correo de inicio de sesión del primer usuario `SUPERADMIN`.
* `SUPERADMIN_PASSWORD`: Contraseña inicial (mínimo 12 caracteres, se almacena como hash Argon2id). Debe retirarse del entorno tras el primer arranque.

---

## 3. Archivos de Entorno y Secretos

* `.env.example` se versiona con valores de ejemplo seguros; `.env` (copia local) **nunca** se versiona.
* Docker Compose carga `.env` mediante `env_file` en los servicios `api` y `worker`, y sobrescribe solo lo que depende de la red interna (`POSTGRES_HOST=db`, `REDIS_HOST=redis`, `DATABASE_URL`, `LOCAL_STORAGE_PATH`, `SIGNATURE_PKCS12_PATH`).
* El certificado `.p12` reside en `secrets/` (ignorado por git, junto con `*.p12` y `*.pfx`). Para generar uno autofirmado de desarrollo, ver el [README](../../README.md#inicio-rápido).
* En producción, los secretos (`SECRET_KEY`, `POSTGRES_PASSWORD`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `SIGNATURE_PKCS12_PASSWORD`, `PAYMENT_*`) se inyectan desde el gestor de secretos de la plataforma de despliegue, no desde un archivo en el repositorio.
