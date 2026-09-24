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
- **Control operativo real:** 10 procesos de control (disponibilidad, choques de elenco, movilidad, adelantos, PDFs).
- **Seguridad por rol:** RBAC + JWT + OWASP desde el día uno.

Empieza por la visión de negocio: [Visión, Alcance y Actores](Docs/01-requisitos/01-vision-alcance-y-actores.md) · [Historias US-01 a US-22](Docs/01-requisitos/05-historias-de-usuario.md)

## 🧱 Stack

| Capa | Tecnología | Fuente |
| :--- | :--- | :--- |
| Lenguaje / API | Python 3.12, FastAPI, Pydantic v2, Uvicorn | [`requirements.txt`](requirements.txt) |
| Datos | PostgreSQL 16 + SQLAlchemy 2 + Alembic + asyncpg | [`docker-compose.yml`](docker-compose.yml) |
| Caché / Locks | Redis 7 | [`docker-compose.yml`](docker-compose.yml) |
| PDFs / Archivos | WeasyPrint + Jinja2, storage local `./uploads` | [`Dockerfile`](Dockerfile), [`.env.example`](.env.example) |
| Auth | python-jose (JWT) + passlib (argon2/bcrypt) | [`requirements.txt`](requirements.txt) |
| Calidad | pytest + pytest-asyncio + pytest-cov, ruff, mypy | [`requirements.txt`](requirements.txt) |
| Integraciones | WhatsApp Cloud API v20, Google Maps Platform | [`.env.example`](.env.example) |
| Infra local | Docker multi-stage + Compose (api, db, redis) | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) |

## 🏛️ Arquitectura en 30 segundos

- **Backend:** Arquitectura Hexagonal (Domain · Application · Ports · Adapters) en FastAPI → [ver diseño](Docs/02-arquitectura/02-backend-arquitectura-hexagonal.md)
- **Frontend (web):** Feature-Sliced Design v2.1 → [ver diseño](Docs/02-arquitectura/03-frontend-arquitectura-fsd.md)
- **Sistema:** Diagramas C4 (Contexto, Contenedores, Componentes) → [ver C4](Docs/02-arquitectura/01-diseno-arquitectonico-c4.md)
- **Decisiones:** ADR-01 a ADR-06 → [ver ADRs](Docs/02-arquitectura/04-adr-decisiones-arquitectura.md)

## 🚀 Inicio rápido

### Requisitos

- Docker y Docker Compose
- Python 3.12+ (solo si desarrollarás sin contenedor)

### 1. Levantar lo que hoy sí funciona (infra)

```bash
# 1. Variables de entorno
cp .env.example .env

# 2. Infraestructura (PostgreSQL + Redis + API)
docker compose up -d --build

# 3. Verificar salud
docker compose ps
docker compose exec db pg_isready -U eventpro_user -d eventpro_db
docker compose exec redis redis-cli ping
```

> [!IMPORTANT]
> El servicio `api` espera `main:app` (CMD en [`Dockerfile`](Dockerfile)). Como `app/` aún no existe, el contenedor `api` reiniciará hasta el scaffold. `db` y `redis` sí quedan operativos — es el comportamiento esperado en esta fase.

### 2. Cuando exista `app/` (objetivo inmediato)

```bash
# Migraciones
docker compose exec api alembic upgrade head

# Datos semilla del catálogo
docker compose exec api python -m app.infrastructure.persistence.seed
```

API: `http://localhost:8000` · Swagger: `http://localhost:8000/docs`

## 📁 Estructura

**Hoy (real):**

```text
.
├── Dockerfile / docker-compose.yml / requirements.txt
├── .env.example / .gitignore
├── Docs/          # SRS + arquitectura + datos + API + operaciones
└── README.md
```

**Objetivo (según arquitectura hexagonal):**

```text
app/
├── domain/                 # Entidades, value objects, reglas de negocio
├── application/            # Casos de uso, puertos de entrada
├── infrastructure/         # Adaptadores: persistence, whatsapp, pdf, maps
│   └── persistence/        # Modelos SQLAlchemy, Alembic, seeds
└── interfaces/             # FastAPI routers, schemas, dependencias
```

Detalle completo: [Backend hexagonal](Docs/02-arquitectura/02-backend-arquitectura-hexagonal.md) · [DER](Docs/03-datos/01-diagrama-entidad-relacion.md) · [Diccionario](Docs/03-datos/02-diccionario-de-datos.md)

## 📖 Documentación

Índice completo en [`Docs/README.md`](Docs/README.md). Resumen:

| Fase | Contenido | Estado |
| :--- | :--- | :---: |
| 01 Requisitos | RF-01→RF-25, RNF, reglas, US-01→US-22 | ✅ |
| 02 Arquitectura | C4, Hexagonal, FSD, ADR-01→ADR-06 | ✅ |
| 03 Datos | DER, diccionario, Alembic + seeds | ✅ |
| 04 API | Endpoints REST v1, RBAC + JWT + OWASP | ✅ |
| 05 Operaciones | `.env`, Docker, Git + DoD | ✅ |

## ⚙️ Configuración clave

Agrupado desde [`.env.example`](.env.example) — detalle en [guía de entorno](Docs/05-operaciones/01-guia-entorno-y-configuracion.md):

| Grupo | Variables |
| :--- | :--- |
| App | `APP_ENV`, `API_V1_PREFIX=/api/v1`, `SECRET_KEY`, `CORS_ORIGINS` |
| Postgres | `POSTGRES_*`, `DATABASE_URL` (asyncpg) |
| Redis | `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` |
| WhatsApp | `WHATSAPP_API_URL`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN` |
| Maps | `GOOGLE_MAPS_API_KEY`, `PROMOTORA_BASE_LATITUDE/LONGITUDE` |
| Negocio | `SIMULTANEOUS_SHOWS_THRESHOLD=3`, `MOBILITY_MARGIN_PERCENT=15`, `ADVANCE_PERCENT=10`, `TRANSIT_REST_BUFFER_MINUTES=30` |

## ✅ Calidad y Git

```bash
pytest                 # tests + asyncio + cobertura
ruff check .           # lint
mypy .                 # tipos
```

Flujo: `main` (estable) ← `develop` (integración) ← `feat/*` (trabajo). Commits en [Conventional Commits](https://www.conventionalcommits.org/) y DoD definidos en [gobernanza Git](Docs/05-operaciones/03-gobernanza-git-y-calidad-dod.md).

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
