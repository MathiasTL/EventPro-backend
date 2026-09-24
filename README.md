# EventPro — Backend API & Documentación de Arquitectura

Sistema integral de automatización y control operativo para la promotora de eventos en Lima, Perú (Shows de Hora Loca, servicios de DJ, ambientación, toldos y muñecos gigantes).

---

## 📖 Documentación del Proyecto

Toda la documentación técnica requerida antes de comenzar a desarrollar se encuentra completamente formalizada en la carpeta **[`Docs/`](Docs/README.md)**:

1. **[01. Especificación de Requerimientos (SRS)](Docs/01-requisitos/):**
   * [Visión, Alcance y Actores](Docs/01-requisitos/01-vision-alcance-y-actores.md)
   * [Catálogo de Requerimientos Funcionales (RF-01 a RF-25)](Docs/01-requisitos/02-requerimientos-funcionales.md)
   * [Requerimientos No Funcionales (RNF)](Docs/01-requisitos/03-requerimientos-no-funcionales.md)
   * [Reglas de Negocio, Procesos de Control y Máquinas de Estado](Docs/01-requisitos/04-reglas-de-negocio-y-control.md)

2. **[02. Arquitectura de Software](Docs/02-arquitectura/):**
   * [Diagramas C4 (Contexto, Contenedores y Componentes)](Docs/02-arquitectura/01-diseno-arquitectonico-c4.md)
   * [Arquitectura Hexagonal en FastAPI (Puertos y Adaptadores)](Docs/02-arquitectura/02-backend-arquitectura-hexagonal.md)
   * [Arquitectura Frontend: Feature-Sliced Design (FSD v2.1)](Docs/02-arquitectura/03-frontend-arquitectura-fsd.md)
   * [Decisiones de Arquitectura (ADR-01 a ADR-06)](Docs/02-arquitectura/04-adr-decisiones-arquitectura.md)

3. **[03. Diseño de Base de Datos y Persistencia](Docs/03-datos/):**
   * [Diagrama Entidad-Relación (DER)](Docs/03-datos/01-diagrama-entidad-relacion.md)
   * [Diccionario de Datos Exhaustivo](Docs/03-datos/02-diccionario-de-datos.md)
   * [Estrategia de Migraciones con Alembic y Datos Semilla](Docs/03-datos/03-estrategia-migraciones-y-seeds.md)

4. **[04. Contratos de API REST y Seguridad](Docs/04-api/):**
   * [Especificación de Endpoints RESTful v1](Docs/04-api/01-especificacion-endpoints-rest.md)
   * [Matriz de Control de Acceso (RBAC), JWT y OWASP](Docs/04-api/02-matriz-rbac-y-seguridad.md)

5. **[05. Operaciones, Entorno y Calidad (DoD)](Docs/05-operaciones/):**
   * [Guía de Variables de Entorno](Docs/05-operaciones/01-guia-entorno-y-configuracion.md)
   * [Infraestructura Local con Docker Compose](Docs/05-operaciones/02-docker-e-infraestructura-local.md)
   * [Gobernanza de Git, Conventional Commits y Definition of Done](Docs/05-operaciones/03-gobernanza-git-y-calidad-dod.md)

---

## 🚀 Inicio Rápido en Desarrollo Local

### Requisitos Previos
* Docker y Docker Compose
* Python 3.12+ (opcional para desarrollo sin contenedor)

### Puesta en Marcha con Docker Compose
```bash
# 1. Clonar variables de entorno
cp .env.example .env

# 2. Levantar la infraestructura completa (FastAPI + PostgreSQL + Redis)
docker compose up -d --build

# 3. Aplicar migraciones
docker compose exec api alembic upgrade head

# 4. Cargar datos iniciales del catálogo
docker compose exec api python -m app.infrastructure.persistence.seed
```

La API estará disponible en `http://localhost:8000` con documentación interactiva Swagger en `http://localhost:8000/docs`.