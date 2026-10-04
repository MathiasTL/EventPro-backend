# 🎉 EventPro — Backend

> Automatización de cotizaciones por WhatsApp y control operativo para una promotora de eventos en Lima, Perú — Hora Loca, DJ, ambientación, toldos y muñecos gigantes.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Redis 7](https://img.shields.io/badge/Redis-7-DC382D.svg)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docs.docker.com/compose/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-FE5196.svg)](https://www.conventionalcommits.org/)

> [!NOTE]
> **Estado: Definition of Ready.** Diseño, SRS, arquitectura, datos y contratos API están completos en [`Docs/`](Docs/README.md). Aún no existe código `app/` — este README te deja el entorno listo para empezar el scaffold.

---

## ✨ ¿Qué resuelve?

- **Cotización en segundos por WhatsApp:** saludo + catálogo + extras en < 1.5 s, sin depender de un encargado.
- **Control operativo real:** 12 procesos de control (disponibilidad, choques de elenco, movilidad, adelantos, PDFs).
- **Seguridad por rol:** RBAC + JWT + OWASP desde el día uno.

Empieza por la visión de negocio: [Visión, Alcance y Actores](Docs/01-requisitos/01-vision-alcance-y-actores.md) · [Historias US-01 a US-32](Docs/01-requisitos/05-historias-de-usuario.md)

## 🧱 Stack

| Capa | Tecnología | Fuente |
| :--- | :--- | :--- |
| Lenguaje / API | Python 3.12, FastAPI, Pydantic v2, Uvicorn, structlog (logs JSON) | [`requirements.txt`](requirements.txt) |
| Datos | PostgreSQL 16 + SQLAlchemy 2 + Alembic + asyncpg | [`docker-compose.yml`](docker-compose.yml) |
| Caché / Locks / Jobs | Redis 7 + arq (vencimiento de cotizaciones, cola WhatsApp, reportes) | [`docker-compose.yml`](docker-compose.yml), [ADR-08](Docs/02-arquitectura/04-adr-decisiones-arquitectura.md) |
| PDFs / Archivos | WeasyPrint + Jinja2, storage local `./uploads` | [`Dockerfile`](Dockerfile), [`.env.example`](.env.example) |
| Auth y seguridad | PyJWT (JWT), pwdlib (Argon2id), slowapi (rate limiting), filetype (MIME real) | [`requirements.txt`](requirements.txt), [ADR-09](Docs/02-arquitectura/04-adr-decisiones-arquitectura.md) |
| Firma electrónica | pyHanko (PAdES) + certificado PKCS#12 | [ADR-07](Docs/02-arquitectura/04-adr-decisiones-arquitectura.md) |
| Calidad | pytest + pytest-asyncio + pytest-cov, ruff, mypy, Testcontainers | [`requirements-dev.txt`](requirements-dev.txt) |
| Integraciones | Chatwoot (gateway de mensajería) + WhatsApp Cloud API v20, Google Maps Platform | [`.env.example`](.env.example), [Spec del gateway](Docs/02-arquitectura/05-spec-chatwoot-gateway.md) |
| Infra local | Docker multi-stage + Compose (api, worker, db, redis); opcionales: Chatwoot y proxy Caddy | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml), [`docker-compose.chatwoot.yml`](docker-compose.chatwoot.yml), [`docker-compose.proxy.yml`](docker-compose.proxy.yml) |

## 🏛️ Arquitectura en 30 segundos

- **Backend:** Arquitectura Hexagonal (Domain · Application · Ports · Adapters) en FastAPI → [ver diseño](Docs/02-arquitectura/02-backend-arquitectura-hexagonal.md)
- **Frontend (web):** Feature-Sliced Design v2.1, mobile-first para operador y cliente; vive en un repositorio hermano (`../frontend`) → [ver diseño](Docs/02-arquitectura/03-frontend-arquitectura-fsd.md)
- **Sistema:** Diagramas C4 (Contexto, Contenedores, Componentes) → [ver C4](Docs/02-arquitectura/01-diseno-arquitectonico-c4.md)
- **Decisiones:** ADR-01 a ADR-09 → [ver ADRs](Docs/02-arquitectura/04-adr-decisiones-arquitectura.md)

## 🚀 Inicio rápido

### Requisitos

- Docker y Docker Compose
- Python 3.12+ (solo si desarrollarás sin contenedor)

### 1. Levantar lo que hoy sí funciona (infra)

```bash
# 1. Variables de entorno (completa los secretos de .env)
cp .env.example .env

# 2. Certificado de firma electrónica de desarrollo (autofirmado, PKCS#12)
mkdir -p secrets
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -subj "/CN=EventPro Dev/O=EventPro" \
  -addext "keyUsage=critical,digitalSignature,nonRepudiation" \
  -keyout secrets/dev-key.pem -out secrets/dev-cert.pem
openssl pkcs12 -export -inkey secrets/dev-key.pem -in secrets/dev-cert.pem \
  -out secrets/eventpro-signing.p12 -name eventpro-dev -passout pass:change-me-dev
rm secrets/dev-key.pem secrets/dev-cert.pem
# Usa la misma contraseña en SIGNATURE_PKCS12_PASSWORD (.env). `secrets/` no se versiona.

# 3. Infraestructura (PostgreSQL + Redis + API + worker).
#    Aplica docker-compose.override.yml: recarga en caliente y ./app montado.
docker compose up -d --build

# 4. Verificar salud
docker compose ps
docker compose exec db pg_isready -U eventpro_user -d eventpro_db
docker compose exec redis redis-cli ping
curl -s http://localhost:8000/health
```

> [!IMPORTANT]
> Los servicios `api` y `worker` ejecutan `app.main:app` y `WorkerSettings` (ver [`Dockerfile`](Dockerfile) y [`docker-compose.yml`](docker-compose.yml)). Como `app/` aún no existe, esos contenedores reiniciarán hasta el scaffold. `db` y `redis` sí quedan operativos — es el comportamiento esperado en esta fase.

Para producción o staging, sin recarga ni código montado: `docker compose -f docker-compose.yml up -d --build`. Chatwoot (`docker-compose.chatwoot.yml`) y el proxy HTTPS del servidor (`docker-compose.proxy.yml`) son archivos Compose opcionales que se combinan con el base; detalle y comandos en [Docker e infraestructura local](Docs/05-operaciones/02-docker-e-infraestructura-local.md#4-archivos-compose-y-combinaciones).

### 2. Cuando exista `app/` (objetivo inmediato)

```bash
# Migraciones
docker compose exec api alembic upgrade head

# Datos semilla del catálogo
docker compose exec api python -m app.infrastructure.adapters.secondary.persistence.seed

# Primer usuario SUPERADMIN (credenciales por variables de entorno)
docker compose exec -e SUPERADMIN_EMAIL=admin@eventpro.pe -e SUPERADMIN_PASSWORD='<contraseña-segura>' api \
  python -m app.infrastructure.adapters.secondary.persistence.bootstrap_superadmin
```

API: `http://localhost:8000` · Swagger: `http://localhost:8000/docs`

## 📁 Estructura

**Hoy (real):**

```text
.
├── Dockerfile / docker-compose.yml / docker-compose.override.yml
├── docker-compose.chatwoot.yml / docker-compose.proxy.yml / chatwoot.env.example / deploy/Caddyfile
├── requirements.txt / requirements-dev.txt
├── .env.example / .gitignore / .dockerignore
├── secrets/       # Certificado .p12 local (no versionado)
├── Docs/          # SRS + arquitectura + datos + API + operaciones
└── README.md
```

**Objetivo (según arquitectura hexagonal):**

```text
app/
├── core/                   # Configuración, logging estructurado, seguridad
├── domain/                 # Entidades, value objects, reglas de negocio
├── application/            # Casos de uso y puertos (input/output)
├── infrastructure/
│   ├── adapters/
│   │   ├── primary/        # web (routers FastAPI), webhooks, jobs (arq)
│   │   └── secondary/      # persistence (modelos, Alembic, seed), whatsapp, maps, pdf, signature, storage, cache
│   └── di/                 # Inyección de dependencias
└── main.py
```

Detalle completo: [Backend hexagonal](Docs/02-arquitectura/02-backend-arquitectura-hexagonal.md) · [DER](Docs/03-datos/01-diagrama-entidad-relacion.md) · [Diccionario](Docs/03-datos/02-diccionario-de-datos.md)

## 📖 Documentación

Índice completo en [`Docs/README.md`](Docs/README.md). Resumen:

| Fase | Contenido | Estado |
| :--- | :--- | :---: |
| 01 Requisitos | RF-01→RF-32, RNF, reglas, US-01→US-32 | ✅ |
| 02 Arquitectura | C4, Hexagonal, FSD, ADR-01→ADR-09 | ✅ |
| 03 Datos | DER, diccionario, Alembic + seeds | ✅ |
| 04 API | Endpoints REST v1, RBAC + JWT + OWASP | ✅ |
| 05 Operaciones | `.env`, Docker, Git + DoD | ✅ |

## ⚙️ Configuración clave

Agrupado desde [`.env.example`](.env.example) — detalle en [guía de entorno](Docs/05-operaciones/01-guia-entorno-y-configuracion.md):

| Grupo | Variables |
| :--- | :--- |
| App | `APP_ENV`, `APP_NAME`, `API_V1_PREFIX=/api/v1`, `PORT`, `DEBUG`, `LOG_LEVEL`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `CORS_ORIGINS` |
| Postgres | `POSTGRES_*`, `DATABASE_URL` (asyncpg) |
| Redis | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` |
| Chatwoot (gateway) | `CHATWOOT_BASE_URL`, `CHATWOOT_ACCOUNT_ID`, `CHATWOOT_INBOX_ID`, `CHATWOOT_BOT_TOKEN`, `CHATWOOT_AGENT_TOKEN`, `CHATWOOT_WEBHOOK_SECRET` (las credenciales de Meta se configuran dentro de Chatwoot, en `chatwoot.env.example` van los secretos propios de Chatwoot) |
| Maps | `GOOGLE_MAPS_API_KEY`, `PROMOTORA_BASE_LATITUDE/LONGITUDE` |
| Negocio | `SIMULTANEOUS_SHOWS_THRESHOLD=3`, `ADVANCE_DEADLINE_HOURS=24`, `AVAILABILITY_RECHECK_MINUTES=60`, `MOBILITY_MARGIN_PERCENT=15`, `ADVANCE_PERCENT=10`, `TRANSIT_REST_BUFFER_MINUTES=30` |
| Almacenamiento | `STORAGE_BACKEND`, `LOCAL_STORAGE_PATH` |
| Firma electrónica | `SIGNATURE_PKCS12_PATH`, `SIGNATURE_PKCS12_PASSWORD`, `SIGNATURE_TSA_URL`, `SIGNATURE_LINK_TTL_HOURS`, `SIGNATURE_OTP_TTL_MINUTES`, `SIGNATURE_OTP_MAX_ATTEMPTS`, `SIGNATURE_OTP_PROOF_TTL_MINUTES` |
| Pagos (bot) | `PAYMENT_YAPE_NUMBER`, `PAYMENT_PLIN_NUMBER`, `PAYMENT_BANK_NAME`, `PAYMENT_BANK_ACCOUNT`, `PAYMENT_BANK_CCI`, `PAYMENT_ACCOUNT_HOLDER` |
| Arranque | `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD` (solo para el comando de arranque) |

## ✅ Calidad y Git

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime + pruebas y calidad
pytest                 # tests + asyncio + cobertura
ruff check .           # lint
mypy .                 # tipos
```

Flujo: `main` (estable) ← `develop` (integración) ← ramas de trabajo con prefijo `feat/`, `fix/`, `docs/`, `build/` o `chore/`. Commits en [Conventional Commits](https://www.conventionalcommits.org/) y DoD definidos en [gobernanza Git](Docs/05-operaciones/03-gobernanza-git-y-calidad-dod.md).

## 🗺️ Roadmap

- [x] Fase Diseño / Definition of Ready (SRS + arquitectura + datos + API)
- [x] Setup base Docker (FastAPI + Postgres + Redis)
- [ ] Scaffold `app/` hexagonal + `main:app` + Alembic init
- [ ] MVP WhatsApp (US-01→US-05) + RBAC + PDFs

## 🤝 Contribuir

1. Crea rama desde `develop`: `feat/<scope>-<descripcion>` (ej. `feat/whatsapp-webhook`)
2. Abre PR hacia `develop` con descripción + tests
3. Solo `develop` → `main` cuando pase DoD

---

📄 **Licencia:** por definir (no hay `LICENSE` aún). · 📬 **Contacto:** equipo EventPro — abre un issue para dudas de negocio o arquitectura.
