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
* `SECRET_KEY`: Cadena criptográfica de al menos 32 caracteres para firma de tokens JWT.
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
* `WHATSAPP_VERIFY_TOKEN`: Token secreto configurado para el handshake del Webhook.

### 2.5 Integración con Google Maps Platform
* `GOOGLE_MAPS_API_KEY`: Clave de API de Google Cloud con permisos para Directions API y Distance Matrix API.
* `PROMOTORA_BASE_LATITUDE`: Latitud del almacén/base de operaciones de la promotora en Lima (`-12.0864`).
* `PROMOTORA_BASE_LONGITUDE`: Longitud de la base de operaciones en Lima (`-77.0328`).

### 2.6 Parámetros Configurables de Reglas de Negocio
* `SIMULTANEOUS_SHOWS_THRESHOLD`: Cantidad máxima de shows simultáneos antes de exigir aprobación manual del encargado (por defecto `3`).
* `MOBILITY_MARGIN_PERCENT`: Margen comercial porcentual sobre el costo base de traslado (por defecto `15`).
* `ADVANCE_PERCENTAGE`: Porcentaje del adelanto sobre servicios base (por defecto `10`).
* `TRANSIT_REST_BUFFER_MINUTES`: Minutos mínimos de margen para descanso y desarme entre shows sucesivos (por defecto `30`).

### 2.7 Repositorio de Archivos y Documentos
* `STORAGE_BACKEND`: Tipo de almacenamiento (`local` o `s3`).
* `LOCAL_STORAGE_PATH`: Directorio en disco para comprobantes y contratos PDF (por defecto `./uploads`).
