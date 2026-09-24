# 04. Registro de Decisiones de Arquitectura (ADRs)

---

## ADR-01: Adopción de Arquitectura Hexagonal (Ports & Adapters) para el Backend

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:** 
  El sistema EventPro gestiona reglas de negocio críticas con múltiples integraciones externas (WhatsApp Business API, Google Maps, motor de PDFs) y mecanismos de control manual (overrides de movilidad, umbral de eventos concurrentes, cobro estricto pre-show). En arquitecturas tradicionales tipo MVC o monolitos acoplados, la lógica de negocio suele dispersarse en controladores HTTP o modelos de base de datos, dificultando las pruebas y el mantenimiento.
* **Decisión:**
  Implementar **Arquitectura Hexagonal (Puertos y Adaptadores)** en el backend:
  * El Dominio es 100% puro y agnóstico de frameworks.
  * La interacción externa se realiza mediante Puertos de Entrada (Casos de uso) y Puertos de Salida (Interfaces abstractas).
  * FastAPI y SQLAlchemy operan como adaptadores periféricos.
* **Consecuencias:**
  * *Positivas:* Cobertura de pruebas unitarias al 100% en lógica de cotización y liquidación sin requerir base de datos activa; aislamiento ante cambios en las APIs de Meta o Google; código altamente modular y auditable.
  * *Negativas:* Mayor cantidad inicial de archivos (interfaces, DTOs y mappers entre capas). Se justifica plenamente por la complejidad de las reglas de control.

---

## ADR-02: Adopción de Feature-Sliced Design (FSD v2.1) para el Frontend

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  El frontend de EventPro debe atender dos audiencias distintas: los 2 encargados (panel administrativo complejo, cronograma con visualización de observaciones, overrides de movilidad, balances financieros) y los clientes finales (interfaz móvil ligera para revisión de cotización y firma digital de contratos). Estructuras convencionales por tipo técnico (`/components`, `/hooks`, `/pages`) provocan espagueti de dependencias e inconsistencias.
* **Decisión:**
  Adoptar **Feature-Sliced Design (FSD v2.1)** organizando el código en 6 capas jerárquicas estrictas (`app`, `pages`, `widgets`, `features`, `entities`, `shared`) con regla de importación unidireccional de arriba hacia abajo.
* **Consecuencias:**
  * *Positivas:* Mapeo directo 1:1 entre los requerimientos funcionales (`features/override-mobility-rate`, `features/check-in-and-collect`) y el código del frontend; acoplamiento mínimo y límites de negocio claros.
  * *Negativas:* Curva de aprendizaje para desarrolladores no familiarizados con FSD sobre la frontera entre `features`, `entities` y `widgets`.

---

## ADR-03: Selección de FastAPI, Python 3.12+ y Pydantic v2

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  Se requiere un backend de alto rendimiento con soporte asíncrono nativo para atender webhooks de WhatsApp concurrentes, validar contratos JSON de forma estricta y exponer documentación OpenAPI en tiempo real.
* **Decisión:**
  Utilizar **FastAPI** montado sobre **Python 3.12+** con **Pydantic v2** para validación y serialización de esquemas.
* **Consecuencias:**
  * *Positivas:* Velocidad de procesamiento cercana a NodeJS/Go gracias a `Starlette` y `uvicorn`; tipado estático estricto y generación automática de contratos OpenAPI / Swagger.
  * *Negativas:* Requiere disciplina en el manejo de código asíncrono (`async/await`) en llamadas de I/O bloqueantes.

---

## ADR-04: Persistencia con PostgreSQL y ORM SQLAlchemy 2.0 Desacoplado

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  Las transacciones de EventPro exigen consistencia ACID estricta para evitar la sobreventa de elencos o asignación duplicada de material de toldos y decoración.
* **Decisión:**
  Utilizar **PostgreSQL** como motor de base de datos relacional y **SQLAlchemy 2.0** como ORM, encapsulado dentro de adaptadores de repositorio (`SqlAlchemyEventRepository`) que implementan puertos del dominio (`IEventRepository`).
* **Consecuencias:**
  * *Positivas:* Garantía de integridad referencial, soporte para bloqueos de fila (`SELECT ... FOR UPDATE`), soporte nativo para campos JSONB (para configuraciones dinámicas de paquetes).
  * *Negativas:* Es necesario mantener mappers para transformar modelos ORM de SQLAlchemy a entidades puras de dominio y viceversa.

---

## ADR-05: Desacoplamiento de APIs Externas (WhatsApp Cloud API y Google Maps)

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  Tanto la API de WhatsApp como Google Maps son servicios externos sujetos a latencia de red, límites de cuota (rate limits) y costos por consumo.
* **Decisión:**
  Aislar el consumo de estas APIs tras puertos secundarios abstractos (`IWhatsAppServicePort`, `IMapsServicePort`).
  * Implementar caché (Redis / en memoria) para consultas repetidas de rutas en Google Maps en un lapso de 24 horas.
  * Implementar política de contingencia: si Google Maps no responde o falla la red, el sistema activa un modo de tarifa plana de contingencia o deriva a cotización manual sin bloquear al usuario.
* **Consecuencias:**
  * *Positivas:* Reducción de costos de API de Google Maps; resiliencia operativa y facilidad de simular respuestas (*mocking*) en entornos de prueba.
  * *Negativas:* Requiere gestionar invalidación de caché y monitoreo de cuotas de servicio.

---

## ADR-06: Gestión de Concurrencia y Locks Distribuidos con Redis

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  Cuando múltiples clientes solicitan cotizaciones simultáneamente para la misma fecha u horario, existe riesgo de reservar el mismo elenco o agotar inventario de toldos en concurrencia (condición de carrera).
* **Decisión:**
  Incorporar **Redis** para:
  1. Sesiones efímeras y estado conversacional del chatbot de WhatsApp.
  2. Implementación de **Locks Distribuidos (Redlock o candados atómicos)** al momento de validar disponibilidad y confirmar pagos de adelanto.
* **Consecuencias:**
  * *Positivas:* Prevención total de sobreventa (*overbooking*) y atención rápida en chats concurrentes.
  * *Negativas:* Añade una dependencia de infraestructura en memoria que debe estar orquestada en local vía `docker-compose`.
