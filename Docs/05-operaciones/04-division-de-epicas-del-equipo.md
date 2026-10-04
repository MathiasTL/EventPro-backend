# División de Épicas del Equipo — EventPro

Este documento asigna el desarrollo de EventPro en **6 épicas verticales**. Cada integrante es dueño de **backend y frontend** de su épica: dominio, casos de uso, adaptadores, migraciones, endpoints, pantallas y pruebas.

> [!IMPORTANT]
> Ser dueño de una épica significa **responder por ella de punta a punta**, no trabajar aislado. Los contratos entre épicas (sección 4) se acuerdan en equipo antes de implementarse.

---

## 1. Resumen rápido

| # | Épica | Dueño | Historias | Módulos API principales |
| :---: | :--- | :--- | :--- | :--- |
| E1 | Bot de WhatsApp, Cotizador y Bandeja de Conversaciones | **Mathias** | US-01 a US-07, US-25, US-27 a US-32 | `/quotes`, `/clients`, `/webhooks/chatwoot`, `/conversations` |
| E2 | Identidad, Seguridad, Contratos y Firma Electrónica | **Diego** | US-23, US-24, US-13, US-14, US-15 + transversal (RNF, RBAC) | `/health`, `/auth`, `/users`, `/audit-logs`, `/contracts`, `/contracts/sign/*` |
| E3 | Catálogo, Elencos y Motor de Disponibilidad | **David** | US-26, US-08, US-09, US-10 + soporte de US-01, US-02 | `/catalog/*`, `/crews`, `/overrides/payments/*` + motor de disponibilidad |
| E4 | Procesos de Control (*Overrides*) | **Renzo** | US-19, US-20 | `/overrides/quotes/*`, `/overrides/crew-assignments/*` |
| E5 | Pagos y Verificación del Adelanto | **Christian** | US-11, US-12 | `/payments` |
| E6 | Operación del Evento y Analítica | **Nicolas** | US-16, US-17, US-18, US-21, US-22 | `/events`, `/reports` |

**Por qué esta división:** las épicas originales 6 (*overrides*) y 7 (analítica) son pequeñas y dependen de otras, así que se integraron en la épica de la que dependen. Lo transversal (autenticación y catálogo) se separó porque **bloquea a todos los demás**. Las piezas técnicamente más complejas se concentran en quienes tienen menos historias: Diego toma el pipeline completo del contrato (PDF, modo manual y firma PAdES con OTP, un solo agregado) y David toma el motor de disponibilidad (locks en Redis, concurrencia y traslados), que además usa sus datos de catálogo y elencos; las historias de administración (usuarios, auditoría, clientes y elencos, Épica 8 de las historias de usuario) se reparten entre las épicas que son dueñas de esos módulos. La Épica 9 de las historias (atención humana y bandeja de conversaciones, US-27 a US-32) pertenece a E1, porque comparte con el bot el gateway de mensajería (Chatwoot) y la conversación del cliente.

---

## 2. Orden de arranque (olas)

No todas las épicas pueden empezar al mismo tiempo con datos reales. Este es el orden recomendado:

| Ola | Quién | Qué entrega | Desbloquea a |
| :---: | :--- | :--- | :--- |
| **0 — Sprint 0** | Diego + David | Esqueleto hexagonal (`app/`), esqueleto FSD (repositorio hermano `../frontend`), CI (ruff, mypy, pytest), base de Alembic, login funcional, catálogo con seeds | Todos |
| **0 — Sprint 0** | Mathias | Modelo del agregado `Quote` y su máquina de estados, congelado y documentado | David, Diego, Renzo, Christian, Nicolas |
| **1** | Mathias, David (disponibilidad), Christian (pagos) | Cotización end-to-end, verificación de disponibilidad, recepción y verificación de adelanto | Contratos y eventos |
| **2** | Diego (contratos), Renzo (*overrides*), Nicolas | Contrato PDF + firma, *overrides* de control, cronograma, operación en campo, dashboards | Cierre del MVP |

> [!TIP]
> Nadie espera de brazos cruzados. Mientras una dependencia no está lista, se trabaja contra **puertos con implementaciones falsas** (backend) y **mocks de la API** (frontend), usando los contratos de [`04-api/01-especificacion-endpoints-rest.md`](../04-api/01-especificacion-endpoints-rest.md).

---

## 3. Detalle por épica

### E1 — Bot de WhatsApp, Cotizador y Bandeja de Conversaciones · Mathias

**Objetivo:** que el cliente cotice por WhatsApp en segundos, sin depender del encargado, y que un encargado pueda tomar la conversación cuando el bot no basta y responder desde la plataforma de EventPro (el cliente nunca ve Chatwoot; ver [Especificación del gateway](../02-arquitectura/05-spec-chatwoot-gateway.md)).

**Historias:** US-01 Saludo y catálogo · US-02 Paquete, temática y extras · US-03 Datos, ubicación y observaciones · US-04 Movilidad automática · US-05 Exención por transporte propio · US-06 Liquidación (total, adelanto 10 %, saldo) · US-07 Envío del resumen · US-25 Consulta de clientes · US-27 Solicitar hablar con un encargado · US-28 Tomar una conversación y responder desde EventPro · US-29 Devolver la conversación al bot · US-30 Bandeja de conversaciones y motivos de falla de envío · US-31 Bandeja en tiempo real y aviso de nuevas derivaciones · US-32 Reasignación de una conversación por el superadministrador.

**Requerimientos:** RF-01 a RF-08, RF-14 (captura de observaciones en el chat), RF-28, RF-30 (traspaso), RF-31 (bandeja) y RF-32 (tiempo real).

| Capa | Alcance |
| :--- | :--- |
| Dominio | Agregado `Quote` con su máquina de estados, `Client`, cálculo de liquidación determinística, reglas de movilidad |
| Casos de uso | Crear cotización, calcular movilidad, liquidar, enviar resumen, cancelar, vencer cotizaciones (tarea programada), traspasar la conversación a un encargado, tomarla, responder, devolverla al bot, reasignarla, conciliar mensajes perdidos (tarea programada) |
| Adaptadores | Puerto `IMessagingPort` con `ChatwootMessagingAdapter` (entrada y salida de WhatsApp a través de Chatwoot), webhook firmado de Chatwoot, publicación de eventos por SSE, Google Maps (distancias), cola `outbox_messages` con arq, repositorios de cotizaciones, clientes y `conversation_links` |
| Endpoints | `POST /webhooks/chatwoot` (interno), `POST/GET /quotes`, `GET /quotes/{id}`, `POST /quotes/{id}/cancel`, `GET /clients`, `GET /clients/{id}`, `/conversations` (listado, mensajes, adjuntos, `takeover`, `release`, envío, `stream` SSE) |
| Frontend | Bandeja de cotizaciones con filtros y estados, detalle de cotización, listado y ficha de clientes, **bandeja de conversaciones** (`pages/conversations`, `widgets/conversation-inbox`, `widgets/conversation-thread`, `features/conversation-takeover`, `features/send-message`, `features/conversation-stream`, `entities/conversation`, `entities/message`) |

**Entregables clave:**

- [ ] Flujo conversacional completo del bot (saludo → selección → datos → resumen).
- [ ] Respuesta del bot en menos de 1.5 s (RNF de rendimiento).
- [ ] Vencimiento automático de cotizaciones con arq.
- [ ] Modelo `Quote` documentado y compartido con el equipo en el Sprint 0.
- [ ] Puerto `IMessagingPort` publicado en el Sprint 0 con una implementación falsa, para que E2 envíe el enlace de firma y el OTP sin esperar a Chatwoot.
- [ ] Chatwoot operativo según [Docker e infraestructura local, sección 5](02-docker-e-infraestructura-local.md#5-chatwoot-primera-configuración) y webhook interno firmado.
- [ ] Traspaso bot-humano y bandeja de conversaciones con actualización en tiempo real (US-27 a US-32).

---

### E2 — Identidad, Seguridad, Contratos y Firma Electrónica · Diego

**Objetivo:** que todo el sistema sea seguro por rol desde el primer día, que el equipo tenga una base común sobre la cual construir y que el contrato se genere y se firme sin intervención manual.

**Historias:** US-23 Gestión de usuarios y roles · US-24 Consulta de la bitácora de auditoría · US-13 Contrato en PDF · US-14 Contratos en modo manual · US-15 Firma electrónica por el cliente.

**Requerimientos:** RF-26, RF-27, RF-13, RF-14 (observaciones en el contrato), RF-15, RF-23.

**Alcance:** RBAC con los roles `SUPERADMIN`, `ENCARGADO`, `OPERADOR` y acceso por token para `CLIENTE` (ver [`04-api/02-matriz-rbac-y-seguridad.md`](../04-api/02-matriz-rbac-y-seguridad.md)), más el ciclo de vida completo del contrato. El contrato es un solo agregado en manos de una sola persona, porque el PDF y la firma forman un único pipeline.

| Capa | Alcance |
| :--- | :--- |
| Dominio | `User`, roles, `AuditLog`, `Contract` y sus estados, token de firma de un solo uso, OTP |
| Casos de uso | Login, refresh, logout, gestión de usuarios, registro de auditoría, generar contrato, emitir contrato manual, reenviar enlace, anular, firmar con OTP |
| Adaptadores | JWT (PyJWT), hash Argon2id (pwdlib), rate limiting (slowapi), logs estructurados (structlog), bootstrap del `SUPERADMIN`, generación de PDF (WeasyPrint + Jinja2), firma PAdES (pyHanko + PKCS#12) |
| Endpoints | `GET /health`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET/POST /users`, `GET/PATCH /users/{id}`, `GET /audit-logs`, `GET /contracts`, `GET /contracts/{id}`, `GET /contracts/{id}/pdf`, `POST /contracts/manual`, `POST /contracts/{id}/resend-link`, `POST /contracts/{id}/void`, `/contracts/sign/{token}` (ver, PDF, OTP, verificar OTP, firmar) |
| Frontend | Capa `app/` de FSD (router, providers), capa `shared/` (cliente HTTP, UI base, manejo de sesión), login, guards por rol, layout principal, gestión de usuarios, visor de auditoría, gestión de contratos, formulario de contrato manual, **página pública de firma para el cliente** (sin login, móvil; es la única vista web del cliente, ya que la revisión de la cotización ocurre en WhatsApp) |

**Entregables clave:**

- [ ] Esqueleto hexagonal en `app/` y esqueleto FSD en el repositorio hermano `../frontend` (Sprint 0, junto con David).
- [ ] Pipeline de CI con ruff, mypy y pytest.
- [ ] Dependencia reutilizable `require_role(...)` para proteger endpoints.
- [ ] Servicio de auditoría que las demás épicas puedan invocar.
- [ ] Cumplimiento de las políticas OWASP de la matriz de seguridad.
- [ ] PDF firmado con PAdES y verificable.
- [ ] Página pública de firma accesible solo con token válido y no reutilizable.

> [!WARNING]
> La parte de contratos es una de las más pesadas del proyecto. La firma PAdES y el flujo OTP deben prototiparse temprano para detectar problemas con el certificado o con WeasyPrint dentro de Docker, sin esperar a que cierre el Sprint 0.

> [!NOTE]
> Diego es el **guardián de la capa `shared/` del frontend y de `app/core/` del backend**. Los cambios en esas zonas se revisan con él para evitar que cada uno cree su propio cliente HTTP o sus propios componentes base.

---

### E3 — Catálogo, Elencos y Motor de Disponibilidad · David

**Objetivo:** que el encargado administre paquetes, temáticas, extras, inventario y elencos, que el bot tenga datos reales y que nunca se venda un show que no se puede cumplir.

**Historias:** US-26 Gestión de elencos y vinculación con operadores · US-08 Capacidad de elencos e inventario · US-09 Tiempos de traslado entre shows · US-10 Aprobación manual por más de 3 shows simultáneos.

**Requerimientos:** RF-29, RF-09, RF-10, RF-20 (y RF-03/RF-04 como proveedor del catálogo).

**Soporta a:** US-01 y US-02 (catálogo que muestra el bot).

| Capa | Alcance |
| :--- | :--- |
| Dominio | `Package`, `Theme`, `Extra`, `InventoryItem`, `Crew`, reglas de capacidad, cálculo de intervalo de traslado, umbral de shows simultáneos |
| Casos de uso | CRUD de cada entidad, asignación de inventario y temáticas a paquetes, verificar disponibilidad, validar traslado, solicitar y aprobar shows simultáneos |
| Adaptadores | Repositorios, seeds del catálogo, puerto de lectura del catálogo para el bot, locks en Redis para evitar sobreventa concurrente, cliente de tiempos de traslado (Google Maps) |
| Endpoints | `/catalog/packages` (CRUD), `PUT /catalog/packages/{id}/inventory-items`, `PUT /catalog/packages/{id}/themes`, `/catalog/themes` (CRUD), `/catalog/extras` (CRUD), `/catalog/inventory-items` (CRUD), `GET/POST /crews`, `PATCH /crews/{id}`, `POST /overrides/payments/{id}/approve-simultaneous` |
| Frontend | Panel administrativo del catálogo: paquetes, temáticas, extras, inventario y elencos (con vinculación a usuarios operadores), cola de aprobaciones de shows simultáneos |

**Entregables clave:**

- [ ] Seeds del catálogo listos en el Sprint 0 (los necesita Mathias para el bot).
- [ ] Base de Alembic y convención de migraciones (Sprint 0, junto con Diego).
- [ ] Puerto de lectura del catálogo consumible por E1.
- [ ] Puerto de verificación de disponibilidad consumido por el cotizador (E1) y por la asignación de elencos (E6).
- [ ] Prevención de doble reserva bajo concurrencia (pruebas con Testcontainers).

> [!NOTE]
> Revisar las fórmulas y los procesos de control en [`01-requisitos/04-reglas-de-negocio-y-control.md`](../01-requisitos/04-reglas-de-negocio-y-control.md) antes de escribir código: el motor de disponibilidad concentra las reglas de negocio más densas. Renzo apoya con las pruebas de concurrencia.

---

### E4 — Procesos de Control (*Overrides*) · Renzo

**Objetivo:** que el encargado pueda corregir el sistema cuando sea necesario, con trazabilidad completa.

**Historias:** US-19 *Override* de movilidad · US-20 Ajuste manual de intervalos de traslado.

**Requerimientos:** RF-21, RF-22.

| Capa | Alcance |
| :--- | :--- |
| Dominio | *Overrides* auditables sobre la tarifa de movilidad y sobre los intervalos de traslado |
| Casos de uso | Aplicar *override* de movilidad, ajustar el intervalo de traslado de una asignación |
| Adaptadores | Integración con el servicio de auditoría (E2) y con el puerto de disponibilidad (E3) |
| Endpoints | `PATCH /overrides/quotes/{id}/mobility`, `PATCH /overrides/crew-assignments/{id}/transit-interval` |
| Frontend | Formularios de *override* (`features/override-mobility-rate`), ajuste de intervalos |

**Entregables clave:**

- [ ] Todo *override* queda registrado en la auditoría (E2).
- [ ] Apoyo a David (E3) con las pruebas de concurrencia del motor de disponibilidad.
- [ ] Apoyo a Nicolas (E6) con la lógica de cobro y evidencia de US-17.

> [!TIP]
> Es la épica más liviana en alcance. Los *overrides* dependen del cotizador (E1) y de la disponibilidad (E3), así que conviene arrancar con mocks de esos puertos.

---

### E5 — Pagos y Verificación del Adelanto · Christian

**Objetivo:** que el adelanto se valide de forma confiable, desde que el cliente envía la captura hasta que el encargado lo verifica.

**Historias:** US-11 Recepción de captura del adelanto · US-12 Verificación de pago y reintento.

**Requerimientos:** RF-11, RF-12.

| Capa | Alcance |
| :--- | :--- |
| Dominio | `Payment` y sus estados, reglas de reintento |
| Casos de uso | Registrar adelanto, verificar, auditar, reembolsar |
| Adaptadores | Almacenamiento de comprobantes (`./uploads`) con validación de MIME real (filetype) |
| Endpoints | `POST /quotes/{id}/pay-advance`, `POST /payments/advance`, `GET /payments`, `GET /payments/{id}`, `GET /payments/{id}/evidence`, `PATCH /payments/{id}/verify`, `PATCH /payments/{id}/audit`, `PATCH /payments/{id}/refund` |
| Frontend | Bandeja de verificación de pagos con vista del comprobante |

**Entregables clave:**

- [ ] Caso de uso de registro de adelanto invocable desde el bot (E1) cuando el cliente envía la captura.
- [ ] Almacenamiento seguro de comprobantes con validación de MIME real.
- [ ] Apoyo a Mathias (E1) con las pruebas de integración del flujo cotización → adelanto.

---

### E6 — Operación del Evento y Analítica · Nicolas

**Objetivo:** que el día del evento el equipo de campo sepa qué hacer y cobre correctamente, y que el negocio vea sus números reales.

**Historias:** US-16 Cronograma con filtros y observaciones · US-17 Cobro pre-show y bloqueo de inicio · US-18 Extensiones en caliente y cierre · US-21 Consolidación de ingresos vs. costos fijos · US-22 Dashboard ejecutivo.

**Requerimientos:** RF-14 (visualización de observaciones en el cronograma), RF-16 a RF-19, RF-24, RF-25.

| Capa | Alcance |
| :--- | :--- |
| Dominio | `Event`, asignación de elencos, protocolo pre-show, extensiones, liquidación final, consolidación financiera |
| Casos de uso | Consultar cronograma, asignar elencos, registrar llegada, cobrar saldo con evidencia, registrar extensión, liquidar, cancelar, generar reportes |
| Adaptadores | Repositorios de eventos, tareas de reportes en arq, consultas de lectura para analítica |
| Endpoints | `GET /events/schedule`, `GET /events/{id}`, `POST /events/{id}/crew-assignments`, `DELETE /events/{id}/crew-assignments/{assignment_id}`, `POST /events/{id}/arrive`, `POST /events/{id}/check-in-and-collect`, `POST /events/{id}/extensions`, `POST /events/{id}/settle`, `POST /events/{id}/cancel`, `GET /reports/dashboard`, `GET /reports/financial/pnl` |
| Frontend | Cronograma con filtros (`widgets/event-card-with-observations`), **vista móvil del operador, *mobile-first* desde 360 px** (agenda del día, llegada, cobro con foto de evidencia desde la cámara, extensiones), dashboard ejecutivo con indicadores y P&L |

**Entregables clave:**

- [ ] Vista del operador usable en celular y restringida a sus propios eventos.
- [ ] Bloqueo de inicio del show si el saldo no está cobrado.
- [ ] Dashboard con datos consolidados de cotizaciones, pagos y eventos.

> [!TIP]
> Nicolas puede empezar en la ola 0 con la UI del cronograma y el dominio de `Event` contra mocks, mientras E2 termina los contratos que originan los eventos.

---

## 4. Contratos entre épicas

Estos son los puntos donde una épica consume a otra. Cada contrato se define como **puerto** en el backend y se acuerda entre los dos dueños antes de implementarlo.

| Consumidor | Proveedor | Contrato | Cuándo se usa |
| :--- | :--- | :--- | :--- |
| Todas | E2 (Diego) | `require_role(...)` y servicio de auditoría | Proteger endpoints y registrar acciones |
| E1 (Mathias) | E3 (David) | Lectura del catálogo | El bot muestra paquetes, temáticas y extras |
| E1 (Mathias) | E3 (David) | Verificación de disponibilidad | Antes de confirmar una cotización |
| E1 (Mathias) | E5 (Christian) | Registro de adelanto | El cliente envía la captura del pago por WhatsApp |
| E2 (Diego) | E5 (Christian) | Adelanto verificado | Se genera el contrato solo cuando el adelanto está verificado |
| E4 (Renzo) | E1 (Mathias), E3 (David) | Cotizador y puerto de disponibilidad | Aplicar *overrides* sobre cotizaciones y asignaciones de elenco |
| E2 (Diego), E5 (Christian) | E1 (Mathias) | `IMessagingPort` (a través de la cola `outbox_messages`; implementación `ChatwootMessagingAdapter`) | Enviar el enlace de firma, el OTP y avisos de pago |
| E6 (Nicolas) | E2 (Diego) | Contrato firmado → evento confirmado | Un contrato firmado aparece en el cronograma |
| E6 (Nicolas) | E3 (David) | Validación de traslado | Al asignar un elenco a un evento |
| E6 (Nicolas) | E1, E5 | Consultas de lectura | Consolidación financiera y dashboard |

> [!IMPORTANT]
> **El agregado `Quote` es el centro del sistema.** Cualquier cambio en su modelo o en sus estados después del Sprint 0 se avisa a todo el equipo antes de mergearse.

---

## 5. Reglas de trabajo en equipo

| Tema | Regla |
| :--- | :--- |
| Ramas y commits | Seguir [`03-gobernanza-git-y-calidad-dod.md`](03-gobernanza-git-y-calidad-dod.md). Una rama por historia con prefijo de tipo de commit (`feat/`, `fix/`, `docs/`, `build/`, `chore/`), por ejemplo `feat/us-08-capacidad-elencos`. |
| Migraciones de Alembic | Hacer *rebase* sobre la rama principal antes de generar una migración. Debe existir **un solo `head`**; si aparecen dos, se resuelve antes del merge. |
| Zonas compartidas | `app/core/` (backend) y `shared/` (frontend) se modifican con revisión de Diego. |
| Regla de FSD | Respetar la dirección de importación: una feature nunca importa otra feature. Ver [`02-arquitectura/03-frontend-arquitectura-fsd.md`](../02-arquitectura/03-frontend-arquitectura-fsd.md). |
| Regla hexagonal | El dominio no importa FastAPI, SQLAlchemy ni clientes externos. Ver [`02-arquitectura/02-backend-arquitectura-hexagonal.md`](../02-arquitectura/02-backend-arquitectura-hexagonal.md). |
| Revisión de código | Cada PR lo revisa al menos un integrante de **otra** épica, para compartir el conocimiento del sistema. |
| Definition of Done | Una historia está terminada cuando cumple la DoD: pruebas, tipado, lint, endpoint documentado y pantalla funcionando. |

---

## 6. Checklist de arranque para cada integrante

- [ ] Leí las historias de mi épica en [`01-requisitos/05-historias-de-usuario.md`](../01-requisitos/05-historias-de-usuario.md).
- [ ] Revisé mis endpoints en [`04-api/01-especificacion-endpoints-rest.md`](../04-api/01-especificacion-endpoints-rest.md) y sus permisos en la matriz RBAC.
- [ ] Revisé mis tablas en [`03-datos/02-diccionario-de-datos.md`](../03-datos/02-diccionario-de-datos.md).
- [ ] Identifiqué en la sección 4 qué contratos consumo y cuáles proveo, y hablé con los dueños involucrados.
- [ ] Levanté el entorno local siguiendo [`02-docker-e-infraestructura-local.md`](02-docker-e-infraestructura-local.md).
