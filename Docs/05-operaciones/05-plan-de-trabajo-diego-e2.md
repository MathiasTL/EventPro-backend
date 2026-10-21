# Plan de trabajo de Diego — Épica E2

**Corte de revisión:** 20 de octubre de 2026 · rama `develop` (`97835c1`).

Diego es responsable de **identidad, seguridad, usuarios, auditoría, plataforma común, contratos y firma electrónica**. Los PR de plataforma, US-23 y US-24 ya están integrados en `develop`; las historias de usuarios y bitácora quedaron marcadas como **Finalizado** en Jira a solicitud de Diego. También provee servicios transversales al equipo y revisa los cambios en `app/core/` y en `shared/` del frontend.

**Asignación confirmada por el historial:** el commit `df8d4d2` trasladó expresamente US-13, US-14 y US-15 de Christian a Diego. La [división de épicas vigente](04-division-de-epicas-del-equipo.md#e2--identidad-seguridad-contratos-y-firma-electrónica--diego) recoge esa decisión: 13 SP de contratos/firma más 7 SP de US-23/US-24. Las épicas [E2](https://eventprofessional.atlassian.net/browse/SCRUM-6) y [E5](https://eventprofessional.atlassian.net/browse/SCRUM-9) de Jira conservan la división anterior y necesitan alineación; ese desfase no elimina las responsabilidades documentadas de Diego.

**Entrega preparada para PR:** implementados los puntos 1–4 en backend: emisión PDF, gestión administrativa, `POST /contracts/manual` atómico y API pública de firma con OTP, PAdES, auditoría, transición del evento y copia encolada. Véase [alcance, configuración y comandos de validación](../02-arquitectura/09-spec-e2-contratos-pdf.md). Diego confirma las pruebas ejecutadas desde su terminal; el agente no volvió a ejecutarlas. La firma real con certificado y gateway sigue pendiente de integración sobre los contratos existentes de E2. El frontend está fuera del alcance solicitado. Las casillas indican implementación local, no fusión ni despliegue.

## PR integrados y estado de Jira

| Trabajo | Rama real | PR y commit de fusión | Estado de seguimiento |
| :--- | :--- | :--- | :--- |
| Plataforma y autenticación | `feat/e2-auth-platform` | [PR #11](https://github.com/MathiasTL/EventPro-backend/pull/11) · `573c73d` | [SCRUM-44](https://eventprofessional.atlassian.net/browse/SCRUM-44): Finalizado. |
| Gestión de usuarios · US-23 | `feat/us-23-users` | [PR #20](https://github.com/MathiasTL/EventPro-backend/pull/20) · `17ae2ff` | [SCRUM-58](https://eventprofessional.atlassian.net/browse/SCRUM-58): Finalizado; transición confirmada por Jira. |
| Bitácora · US-24 | `feat/us-24-audit-logs` | [PR #19](https://github.com/MathiasTL/EventPro-backend/pull/19) · `895e12f` | [SCRUM-59](https://eventprofessional.atlassian.net/browse/SCRUM-59): Finalizado; transición confirmada por Jira. |

La comprobación del historial local confirmó que las tres puntas registradas en `origin/feat/*` están incluidas en `develop`, con **0 commits exclusivos pendientes de integrar**. En ese corte, `develop` y la referencia local `origin/develop` apuntan a `97835c1`; no se verificó de nuevo el remoto de GitHub. Los nombres `feat/e2auth-platform` y `feat/us-24-logs` mencionados inicialmente corresponden aquí a `feat/e2-auth-platform` y `feat/us-24-audit-logs`.

La base del frontend ([SCRUM-53](https://eventprofessional.atlassian.net/browse/SCRUM-53)) y sus subtareas de estructura FSD, cliente HTTP, layout y login/guards también figuran **Finalizado en Jira**. Su código no se revisó en este checkout.

## Cómo leer los estados

- **Finalizado / integrado:** entrega fusionada o cerrada en Jira, según la evidencia indicada. No implica que se haya vuelto a ejecutar toda la suite en esta revisión documental.
- **Implementado en código:** existe la pieza; cuando no hay evidencia de cierre, aún debe comprobarse la [Definition of Done](03-gobernanza-git-y-calidad-dod.md#3-criterios-de-aceptación-definition-of-done-dod).
- **Parcial:** existe una parte utilizable, pero falta comportamiento exigido por la historia o integración con otra épica.
- **Pendiente:** no se encontró la implementación prevista al revisar el árbol actual.
- **No verificable aquí:** el componente está fuera de este checkout o no se pudo ejecutar la comprobación. Las casillas indican trabajo por cerrar o verificar; el estado refleja la evidencia actual, no una aprobación de entrega.

## Estado del proyecto relacionado con E2

| Área | Estado | Evidencia y límite |
| :--- | :--- | :--- |
| Base backend, Alembic y CI | Integrado / Finalizado | Plataforma fusionada por PR #11 y SCRUM-44 finalizado. Existen `app/`, migraciones `0001` a `0005` y [CI](../../.github/workflows/ci.yml). Las revisiones locales `0007`/`0008` están pendientes de despliegue. README actualizado. |
| Salud, autenticación y RBAC | Integrado / Finalizado | PR #11 incluye [`/health`](../../app/infrastructure/adapters/primary/web/health_router.py), [login/refresh/logout](../../app/infrastructure/adapters/primary/web/auth_router.py), [`require_role(...)`](../../app/infrastructure/adapters/primary/web/deps.py) y bootstrap de [`SUPERADMIN`](../../app/infrastructure/adapters/secondary/persistence/bootstrap_superadmin.py). La integración de cada nueva épica sigue requiriendo sus pruebas. |
| Usuarios, revocación y bitácora | Integrado / Finalizado en Jira | PR #20 y #19 fusionados; SCRUM-58 y SCRUM-59 finalizados. Hay [router de usuarios](../../app/infrastructure/adapters/primary/web/v1/users_router.py), [servicio de auditoría](../../app/application/services/audit_service.py), [consulta de bitácora](../../app/infrastructure/adapters/primary/web/v1/audit_logs_router.py) y pruebas. Las pantallas de usuarios y bitácora quedan fuera del alcance de esos PR según sus historias de Jira. |
| Contingencia manual · US-14 backend | Implementado localmente; pruebas confirmadas por Diego | `/contracts/manual` crea cliente/cotización/pago/evento/reservas/contrato de manera atómica, con evidencia e idempotencia. Reutiliza el almacén de `/manual-bookings`, cuya revisión separada se conserva. |
| Contratos PDF y gestión | Implementado localmente; pendiente de PR/despliegue | Agregado y repositorio `Contract`, correlativo, generación PDF, API administrativa, rotación de enlaces, anulación, regeneración de observaciones y auditoría. La integración exige el evento existente de E5; no crea reservas en la verificación genérica. |
| Firma electrónica · US-15 backend | Implementado localmente; pruebas confirmadas por Diego; firma real pendiente | Rutas públicas, OTP, validación PNG, sello PAdES, auditoría, consumo único, evento `SCHEDULED` y copia encolada; pendiente validar en Docker y con gateway real. |
| Frontend E2 | Base finalizada según Jira; código no verificable aquí | SCRUM-53 y sus subtareas figuran finalizados. `../frontend` no está presente en este entorno; las pantallas específicas de usuarios, bitácora y contratos requieren revisión separada. |
| Entorno de pruebas E2 | Dependencias restauradas | Instaladas las dependencias declaradas de runtime/desarrollo, incluidos `openai` y ReportLab. Las nuevas pruebas comprueban texto PDF, API, transacciones, concurrencia y migración en PostgreSQL/Redis efímeros. Los resultados de esta entrega se registran en su validación final; no se migra la base compartida. |

## Lista de tareas de Diego, en orden recomendado

### 1. Base común y seguridad — Sprint 0

| Tarea y resultado comprobable | Estado | Dependencia / evidencia |
| :--- | :--- | :--- |
| [x] Entregar el esqueleto hexagonal, configuración, inyección de dependencias y base de Alembic. | Integrado por PR #11; SCRUM-44 finalizado | Con David. [Arquitectura backend](../02-arquitectura/02-backend-arquitectura-hexagonal.md), [estrategia de migraciones](../03-datos/03-estrategia-migraciones-y-seeds.md). |
| [x] Entregar CI para ruff, mypy, pytest y cobertura. | Integrado por PR #11; SCRUM-52 finalizado | [CI](../../.github/workflows/ci.yml). Dependencias locales restauradas durante la entrega de contratos PDF/gestión. |
| [x] Entregar `GET /health`, bootstrap del `SUPERADMIN`, login, refresh rotativo y logout. | Integrado por PR #11; SCRUM-44 finalizado | [API de salud y autenticación](../04-api/01-especificacion-endpoints-rest.md#20-módulo-salud-del-servicio-health). |
| [ ] Validar JWT, contraseñas Argon2id, cuenta/rol vigentes en BD, `require_role(...)`, revocación y límites de peticiones en todos los puntos administrativos. | Base implementada; cobertura transversal por comprobar | Todos consumen E2. [Matriz RBAC y políticas OWASP](../04-api/02-matriz-rbac-y-seguridad.md). |
| [ ] Mantener el servicio de auditoría invocable por las demás épicas y comprobar el registro de cada acción crítica prevista en la matriz. | Servicio implementado; integración transversal por comprobar | Renzo, Christian, Mathias, David y Nicolas producen acciones auditables. [Contratos entre épicas](04-division-de-epicas-del-equipo.md#4-contratos-entre-épicas). |
| [ ] Verificar logs JSON, trazas, manejo seguro de secretos, TLS/proxy y políticas OWASP aplicables a E2. | Parcial / por comprobar en despliegue | [RNF de seguridad y trazabilidad](../01-requisitos/03-requerimientos-no-funcionales.md), [matriz de seguridad](../04-api/02-matriz-rbac-y-seguridad.md#4-políticas-de-seguridad-de-la-api-owasp-top-10). |
| [x] Entregar el esqueleto FSD, router, providers, `shared/`, cliente HTTP, manejo de sesión, guards por rol y layout. | Finalizado según SCRUM-53 y subtareas; código no revisado aquí | Con David; [SCRUM-53](https://eventprofessional.atlassian.net/browse/SCRUM-53), [arquitectura FSD](../02-arquitectura/03-frontend-arquitectura-fsd.md). |

### 2. Usuarios y bitácora — US-23 y US-24

| Tarea y resultado comprobable | Estado | Dependencia / evidencia |
| :--- | :--- | :--- |
| [x] Entregar US-23 backend: crear, listar, consultar, editar, activar y desactivar usuarios; asignar roles; rechazar duplicados y ocultar contraseñas. | PR #20 integrado; SCRUM-58 Finalizado | [PR #20](https://github.com/MathiasTL/EventPro-backend/pull/20), [SCRUM-58](https://eventprofessional.atlassian.net/browse/SCRUM-58). |
| [x] Entregar revocación atómica de refresh tokens, protección del propio acceso y autorización con el rol vigente. | Incluido en PR #20 | Punta `bfff8c2` incluida en `develop`; [pruebas de integración](../../tests/integration/test_users.py). |
| [x] Entregar US-24 backend: bitácora paginada, orden estable, filtros, valores anteriores/nuevos, solo lectura y permisos. | PR #19 integrado; SCRUM-59 Finalizado | [PR #19](https://github.com/MathiasTL/EventPro-backend/pull/19), [SCRUM-59](https://eventprofessional.atlassian.net/browse/SCRUM-59). |
| [ ] Revisar y, si faltan, completar las pantallas de gestión de usuarios y visor de auditoría, incluidos errores y permisos. | No verificable aquí; fuera del alcance de los PR #20 y #19 | Repositorio frontend. Login y guards ya figuran finalizados en [SCRUM-57](https://eventprofessional.atlassian.net/browse/SCRUM-57). |

### 3. Contrato PDF y modo manual — US-13 y US-14

**Responsable: Diego**, según la redistribución explícita de `df8d4d2`. Generación, gestión y contingencia manual están implementadas localmente en backend; Diego confirma las pruebas y queda pendiente la firma real.

| Tarea y resultado comprobable | Estado | Dependencia / evidencia |
| :--- | :--- | :--- |
| [x] Modelar `Contract`, estados administrativos, repositorio, correlativo y un solo contrato vigente por evento. | Implementado localmente, incluida transición de firma | [Especificación E2](../02-arquitectura/09-spec-e2-contratos-pdf.md), migraciones `0007_contract_management` y `0008_contract_signature`. |
| [x] Integrar emisión PDF tras el adelanto verificado, con datos, importes, extras y observaciones; regenerar al editar notas antes de firmar. | Implementado localmente | Christian debe entregar el evento existente en la verificación genérica. El flujo manual ya lo crea. [Especificación E2](../02-arquitectura/09-spec-e2-contratos-pdf.md). |
| [ ] Acordar con Nicolas quién copia `quotes.observations` a `events.client_observations`; incluir el mismo texto literal en el PDF y cronograma. | Decisión de integración pendiente | [Pregunta abierta de E1](../02-arquitectura/08-spec-e1-contrato-cotizacion.md#6-preguntas-abiertas). |
| [x] Implementar listado, detalle, PDF, reenvío y anulación con permisos y auditoría; agregar emisión administrativa idempotente y edición de observaciones. | Implementado localmente | [Contrato REST `/contracts`](../04-api/01-especificacion-endpoints-rest.md#210-módulo-contratos-y-firma-electrónica-contracts). |
| [x] Implementar `POST /contracts/manual`: cliente, cotización `MANUAL`, adelanto con evidencia, evento, reservas, borrador/emisión y auditoría atómicos. | Backend implementado localmente; pruebas confirmadas por Diego. Formulario fuera de alcance | Reutiliza el almacén de `/manual-bookings`; cabecera `Idempotency-Key` UUID. [API manual](../04-api/01-especificacion-endpoints-rest.md#post-contractsmanual). |
| [x] Integrar la plantilla PDF con ReportLab, el motor portable ya usado por el flujo manual; verificar contenido extraído del PDF y ejecución fuera del event loop. | Implementado localmente | [Decisión y plantilla de esta entrega](../02-arquitectura/09-spec-e2-contratos-pdf.md). Mantener revisión del texto por el negocio antes del uso real. |
| [ ] Verificar o completar las pantallas de listado/detalle, PDF, anulación, reenvío y contrato manual. | No verificable aquí | Repositorio frontend. |

### 4. Enlace público y firma — US-15

**Responsable: Diego.** API pública, OTP y sello PAdES implementados en backend; pruebas confirmadas por Diego; pendiente integración real de certificado, worker y gateway.

| Tarea y resultado comprobable | Estado | Dependencia / evidencia |
| :--- | :--- | :--- |
| [ ] Validar certificado PKCS#12 y PDF sellado dentro de Docker. | Adaptador y prueba con certificado efímero escritos; ejecución pendiente | [Implementación y configuración](../02-arquitectura/09-spec-e2-contratos-pdf.md). |
| [x] Completar validación pública y consumo único del token, con bloqueo por evento. | Backend implementado localmente; pruebas confirmadas por Diego | [API de firma](../04-api/01-especificacion-endpoints-rest.md#get-contractssigntoken). |
| [x] Implementar resumen público y PDF con token: `GET /contracts/sign/{token}` y `/pdf`. | Backend implementado localmente; sin frontend | Respuestas sin caché y redacción del access log. |
| [x] Generar OTP de 6 dígitos, guardar HMAC, limitar solicitudes e intentos, verificar y emitir `otp_proof` breve; encolar código redactable. | Backend implementado localmente; pruebas confirmadas por Diego | Contadores persistentes en `0008_contract_signature`; integración con outbox de Mathias. |
| [x] Validar PNG y aceptación, estampar firma, sellar PAdES, guardar SHA-256/IP/User-Agent/fecha; contrato `SIGNED` y evento `SCHEDULED` atómicos. | Backend implementado localmente; requiere certificado configurado y validación | Nicolas consume el nuevo estado. [ADR-07](../02-arquitectura/04-adr-decisiones-arquitectura.md). |
| [x] Auditar `CONTRACT_SIGNED` y encolar copia del PDF sellado como `DOCUMENT`. | Backend implementado localmente; entrega WhatsApp por validar | Worker y gateway de Mathias. |
| [x] Ejecutar casos de expiración, OTP incorrecto, repetición, concurrencia y rollback. | Pruebas confirmadas por Diego desde su terminal | [Comandos](../02-arquitectura/09-spec-e2-contratos-pdf.md#comandos-para-diego-powershell). |
| [ ] Construir la página pública móvil de revisión, OTP, trazo de firma y aceptación, usable desde 360 px y sin cuenta de panel. | No verificable aquí | Repositorio frontend; [RNF-06](../01-requisitos/03-requerimientos-no-funcionales.md#6-rnf-06-usabilidad-y-dispositivos). |

### 5. Cierre de cada historia

| Tarea y resultado comprobable | Estado |
| :--- | :--- |
| [ ] Restaurar las dependencias locales y ejecutar las comprobaciones de regresión necesarias para el siguiente cambio; aplicar la [DoD](03-gobernanza-git-y-calidad-dod.md#3-criterios-de-aceptación-definition-of-done-dod) a las nuevas entregas de contrato/firma. | Verificación local parcial; no reabre los PR #11, #20 y #19 ya integrados. |
| [ ] Verificar migraciones `upgrade()`/`downgrade()` en entorno efímero, un solo `head`, esquemas OpenAPI, logs estructurados y permisos de la matriz RBAC para cada ruta nueva. | Pendiente por cada cambio nuevo. |
| [x] Actualizar README, plan y documentación de API/datos/configuración para contratos y firma backend, incluida la diferencia entre los dos flujos manuales. | Actualizado localmente. |
| [ ] Obtener revisión de una persona de otra épica antes de fusionar cada PR. | Pendiente por entrega; [regla del equipo](04-division-de-epicas-del-equipo.md#5-reglas-de-trabajo-en-equipo). |

## Integraciones con otros integrantes

Los puntos de conexión y tareas están en la [guía de coordinación E2](coordinaciones-e2/README.md), con un archivo por integrante. Cada responsable adapta su módulo a los contratos existentes de Diego en E2. El seguimiento recoge los PR y las evidencias de compatibilidad de cada integración.

**No trabajas solo.** E2 entrega seguridad, auditoría y contratos; E5 entrega pagos. La redistribución está confirmada en el historial y falta reflejarla en Jira. Acordar datos y puertos de cada frontera; usar fakes mientras el proveedor no esté integrado. Fuente: [contratos entre épicas](04-division-de-epicas-del-equipo.md#4-contratos-entre-épicas).

| Integrante / épica | Lo que Diego recibe | Lo que Diego entrega o revisa | Estado actual de la frontera |
| :--- | :--- | :--- | :--- |
| **David · E3** | Base de Alembic y datos/catálogo usados por cotización y contrato. | Coordinación del arranque Sprint 0 y revisión de cambios compartidos. | Base de Alembic presente; validar integración final. |
| **Mathias · E1** | Modelo/estados de `Quote`, `IMessagingPort`, outbox y Chatwoot. | Enlace, OTP y PDF firmado; seguridad y auditoría de sus rutas. | Enlaces, OTP y PDF firmado encolados en código; entrega real y plantilla fuera de 24 h pendientes. |
| **Christian · E5** | Adelanto verificado y evento existente. | Generación PDF y auditoría transaccional con el pago. | Integrado a verificación y aprobación; el genérico requiere `event_id` de la misma cotización. La creación/reserva del evento pertenece a E5. |
| **Nicolas · E6** | Evento y observaciones operativas; acuerdo de copia desde la cotización. | Contrato firmado que lleva el evento a `SCHEDULED` y lo muestra en el cronograma. | Transición implementada localmente; copia inicial de observaciones del flujo conversacional por acordar. |
| **Renzo · E4** | Acciones de *override* que deben registrarse. | Servicio de auditoría y control de roles. | Servicio disponible; comprobar cada integración de E4. |
| **Todo el equipo** | Revisión cruzada de PR y aviso de cambios del agregado `Quote`. | `require_role(...)`, servicio de auditoría y revisión de `app/core/` y `shared/`. | Servicios backend presentes; cobertura transversal y frontend por comprobar. |

**Frontera adicional del flujo manual:** la [documentación de `/manual-bookings`](../04-api/03-flujo-manual-entregable.md#alineación-pendiente-con-el-núcleo-de-cotización-e1) asigna a **su autor** el PR que reemplaza SQL directo por los repositorios de E1, usa `FinancialEngine` y corrige `pending_balance`. Diego debe coordinar la reutilización de ese flujo y revisar su impacto en `Contract`; esas tres correcciones no se reasignan aquí a Diego.

## Siguiente secuencia práctica

1. Pruebas confirmadas por Diego desde terminal. Conservar los comandos documentados para regresiones posteriores; el agente no vuelve a ejecutar pruebas por indicación expresa.
2. Configurar certificado PKCS#12, dominio del enlace y worker/gateway; verificar la entrega de OTP y PDF con Mathias, incluida la plantilla fuera de ventana.
3. Revisar el PR de backend y coordinar migraciones E2 `0007` y `0008`, despliegue y alineación del backlog de Jira con la asignación a Diego.
4. Coordinar con Christian la creación de eventos del flujo conversacional y con Nicolas la copia inicial de observaciones. La contingencia manual ya crea el evento y sus notas; la firma ya implementa `SCHEDULED`.

El frontend queda fuera de esta continuación por indicación de Diego; sus tareas se conservan como referencia, sin tratarlas como trabajo de backend pendiente.
