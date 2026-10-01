# Repositorio de Documentación Técnica — EventPro

Bienvenido a la documentación técnica, arquitectónica y operativa de **EventPro**, la plataforma de automatización y control para la promotora de eventos en Lima, Perú.

Esta documentación constituye la **Fase de Especificación y Diseño (Definition of Ready)** previa a la etapa de desarrollo de software.

---

## 📚 Estructura Completa de la Documentación

```text
Docs/
├── README.md                                      # Índice general de la documentación
│
├── 01-requisitos/                                 # FASE 1: Especificación de Requerimientos de Software (SRS)
│   ├── 01-vision-alcance-y-actores.md             # Visión del producto, alcance del MVP y actores
│   ├── 02-requerimientos-funcionales.md           # Catálogo formal RF-01 al RF-29 (estándar IEEE 830)
│   ├── 03-requerimientos-no-funcionales.md        # RNF (Rendimiento, Seguridad, Disponibilidad, Usabilidad móvil, etc.)
│   ├── 04-reglas-de-negocio-y-control.md          # Fórmulas, 12 Procesos de Control y Máquinas de Estado
│   └── 05-historias-de-usuario.md                 # 26 Historias de Usuario (US-01 a US-26) con Given-When-Then
│
├── 02-arquitectura/                               # FASE 2: Arquitectura de Software y Diseño de Sistemas
│   ├── 01-diseno-arquitectonico-c4.md             # Diagramas C4 (Contexto, Contenedores y Componentes)
│   ├── 02-backend-arquitectura-hexagonal.md       # Arquitectura Hexagonal en FastAPI (Domain, Ports, Adapters)
│   ├── 03-frontend-arquitectura-fsd.md            # Feature-Sliced Design (FSD v2.1) en Frontend Web
│   └── 04-adr-decisiones-arquitectura.md          # Registros de Decisiones de Arquitectura (ADR-01 a ADR-09)
│
├── 03-datos/                                      # FASE 3: Persistencia y Diseño de Base de Datos
│   ├── 01-diagrama-entidad-relacion.md            # Diagrama Entidad-Relación (DER en Mermaid)
│   ├── 02-diccionario-de-datos.md                 # Diccionario exhaustivo campo por campo e índices
│   └── 03-estrategia-migraciones-y-seeds.md       # Estrategia de migraciones con Alembic y datos semilla
│
├── 04-api/                                        # FASE 4: Contratos de Integración y Seguridad
│   ├── 01-especificacion-endpoints-rest.md        # Catálogo de endpoints v1, schemas JSON y códigos HTTP
│   └── 02-matriz-rbac-y-seguridad.md              # Matriz de permisos por rol (RBAC), JWT y OWASP
│
├── 05-operaciones/                                # FASE 5: Operaciones, Calidad y Gobernanza
│   ├── 01-guia-entorno-y-configuracion.md         # Documentación de variables de entorno (.env)
│   ├── 02-docker-e-infraestructura-local.md       # Orquestación con Docker Compose (API, worker, Postgres, Redis)
│   ├── 03-gobernanza-git-y-calidad-dod.md         # GitFlow, Conventional Commits y Definition of Done
│   └── 04-division-de-epicas-del-equipo.md        # Asignación de épicas por integrante y contratos entre épicas
```

> [!NOTE]
> Los documentos de negocio originales (*«proceso de negocio event pro (1).pdf»* y *«Procesos_Automatizacion_Control_EventPro.pdf»*) son **referencias externas que no se versionan** en este repositorio. La especificación vigente es la de la carpeta `01-requisitos/`. El frontend vive en un repositorio hermano (`../frontend`), fuera de este repositorio.

---

## 🚦 Estado de la Documentación Pre-Desarrollo

| Fase | Título | Estado | Enlaces |
| :---: | :--- | :---: | :--- |
| **01** | **Especificación de Requerimientos (SRS)** | ✅ Completada | [Ver Requisitos](01-requisitos/02-requerimientos-funcionales.md) |
| **02** | **Arquitectura (Hexagonal + FSD)** | ✅ Completada | [Ver Arquitectura](02-arquitectura/01-diseno-arquitectonico-c4.md) |
| **03** | **Persistencia y Modelo de Datos** | ✅ Completada | [Ver DER y Diccionario](03-datos/01-diagrama-entidad-relacion.md) |
| **04** | **Contratos de API REST & RBAC** | ✅ Completada | [Ver Endpoints](04-api/01-especificacion-endpoints-rest.md) |
| **05** | **Infraestructura, DevOps y Calidad (DoD)** | ✅ Completada | [Ver Gobernanza y DoD](05-operaciones/03-gobernanza-git-y-calidad-dod.md) |

---

## 🛠️ Artefactos de Infraestructura en la Raíz del Proyecto

* [`.env.example`](../.env.example): Plantilla documentada de variables de entorno.
* [`docker-compose.yml`](../docker-compose.yml): Orquestación lista para desarrollo local con FastAPI, PostgreSQL y Redis.
* [`Dockerfile`](../Dockerfile): Contenedor optimizado multi-stage para Python 3.12 y librerías de compilación de PDFs.
* [`requirements.txt`](../requirements.txt): Dependencias de runtime fijadas para el backend.
* [`requirements-dev.txt`](../requirements-dev.txt): Dependencias de desarrollo (pytest, Testcontainers, ruff, mypy) sobre las de runtime.
* [`.gitignore`](../.gitignore): Exclusiones estándar para Python, entornos virtuales y binarios.
