# 04. Registro de Decisiones de Arquitectura (ADRs)

---

## ADR-01: Adopción de Arquitectura Hexagonal (Ports & Adapters) para el Backend

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:** 
  El sistema EventPro gestiona reglas de negocio críticas con múltiples integraciones externas (mensajería, con WhatsApp vía Chatwoot; Google Maps; motor de PDFs) y mecanismos de control manual (overrides de movilidad, umbral de eventos concurrentes, cobro estricto pre-show). En arquitecturas tradicionales tipo MVC o monolitos acoplados, la lógica de negocio suele dispersarse en controladores HTTP o modelos de base de datos, dificultando las pruebas y el mantenimiento.
* **Decisión:**
  Implementar **Arquitectura Hexagonal (Puertos y Adaptadores)** en el backend:
  * El Dominio es 100% puro y agnóstico de frameworks.
  * La interacción externa se realiza mediante Puertos de Entrada (Casos de uso) y Puertos de Salida (Interfaces abstractas).
  * FastAPI y SQLAlchemy operan como adaptadores periféricos.
* **Consecuencias:**
  * *Positivas:* Pruebas unitarias de la lógica de cotización y liquidación sin requerir base de datos activa (metas de cobertura en [RNF-04.2](../01-requisitos/03-requerimientos-no-funcionales.md): 75% global y 100% en servicios de dominio); aislamiento ante cambios en el gateway de mensajería o en la API de Google; código altamente modular y auditable.
  * *Negativas:* Mayor cantidad inicial de archivos (interfaces, DTOs y mappers entre capas). Se justifica plenamente por la complejidad de las reglas de control.

---

## ADR-02: Adopción de Feature-Sliced Design (FSD v2.1) para el Frontend

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  El frontend de EventPro debe atender tres audiencias distintas: los 2 encargados (panel administrativo complejo, *desktop-first* y responsivo: cronograma con visualización de observaciones, overrides de movilidad, balances financieros), los operadores de elenco (web móvil en el teléfono: agenda del día, cobro del saldo con foto de evidencia y extensiones) y los clientes finales (web móvil ligera, únicamente para revisar y firmar electrónicamente el contrato; la revisión de la cotización ocurre en WhatsApp, no en la web). Las vistas de operador y cliente son *mobile-first* desde 360 px (RNF-06); la instalación como PWA queda diferida. Estructuras convencionales por tipo técnico (`/components`, `/hooks`, `/pages`) provocan espagueti de dependencias e inconsistencias.
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
  Se requiere un backend de alto rendimiento con soporte asíncrono nativo para atender webhooks de mensajería (Chatwoot) concurrentes, validar contratos JSON de forma estricta y exponer documentación OpenAPI en tiempo real.
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
  * *Positivas:* Garantía de integridad referencial, soporte para bloqueos de fila (`SELECT ... FOR UPDATE`), restricciones `CHECK` e índices únicos parciales para modelar las reglas de negocio en el esquema. `JSONB` se usa únicamente en la bitácora de auditoría (`audit_logs`) y en la cola de mensajes (`outbox_messages`); los paquetes y el catálogo son columnas relacionales.
  * *Negativas:* Es necesario mantener mappers para transformar modelos ORM de SQLAlchemy a entidades puras de dominio y viceversa.

---

## ADR-05: Desacoplamiento de APIs Externas (Google Maps)

* **Estado:** Aceptado. Parcialmente reemplazado por ADR-10 (2026-10-03).
* **Fecha:** 2026-09-23.
* **Nota:** *Parcialmente reemplazado por ADR-10 (2026-10-03).* La parte de WhatsApp (puerto `IWhatsAppServicePort` y entrega directa con Meta) fue sustituida por `IMessagingPort` y Chatwoot como gateway; la cola `outbox_messages` y sus reintentos se describen en [ADR-10](#adr-10-chatwoot-como-gateway-de-mensajería-oculto). Este registro conserva únicamente la decisión sobre Google Maps, que sigue vigente.
* **Contexto:**
  Google Maps es un servicio externo sujeto a latencia de red, límites de cuota (rate limits) y costos por consumo.
* **Decisión:**
  Aislar el consumo de esta API tras un puerto secundario abstracto (`IMapsServicePort`).
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

---

## ADR-07: Firma Electrónica Propia con Sello PAdES (pyHanko)

* **Estado:** Aceptado.
* **Fecha:** 2026-09-30.
* **Contexto:**
  El contrato PDF debe ser firmado por el cliente desde su teléfono, tras recibir el enlace por WhatsApp. El negocio es una promotora pequeña de Lima con volumen bajo de contratos, por lo que el costo por firma y la dependencia de terceros pesan más que el alcance legal máximo. En Perú, la «firma digital» de la Ley 27269 exige un certificado emitido por una entidad acreditada ante INDECOPI; una firma electrónica con OTP, evidencia técnica y sello criptográfico es válida como manifestación de voluntad, pero no es una firma digital en sentido legal. Ningún SaaS extranjero evaluado declara acreditación IOFE, y el equipo ya opera un backend Python con WhatsApp como canal.
* **Decisión:**
  Implementar una **firma electrónica propia** detrás del puerto de salida `SignaturePort` (ver [arquitectura hexagonal, sección 3.4](02-backend-arquitectura-hexagonal.md#34-puerto-de-firma-electrónica-signatureport)):
  1. El cliente abre un enlace de un solo uso (entregado por WhatsApp, con expiración) y revisa el PDF.
  2. Ingresa un OTP de 6 dígitos enviado por WhatsApp (con expiración y límite de intentos).
  3. Dibuja su firma manuscrita y acepta los términos.
  4. El backend estampa la firma y sella el PDF con **PAdES** usando **pyHanko** y un certificado **PKCS#12** (`.p12`), con marca de tiempo **RFC 3161** opcional.
  5. Se registra el **SHA-256** del PDF sellado, junto con OTP verificado, IP, agente de usuario y marcas de tiempo, en `contracts` y en `audit_logs`.

  Terminología: en toda la documentación y la interfaz se usa «firma electrónica». En desarrollo se usa un `.p12` autofirmado; un certificado acreditado por INDECOPI puede sustituirlo más adelante sin cambios en el dominio.
* **Alternativas consideradas:**
  * *SaaS de firma (DocuSign, BoldSign, Firma.dev):* integración rápida y evidencia legal, pero costo recurrente por sobre, dependencia de un tercero con datos de clientes, y ninguno ofrece acreditación IOFE peruana. Descartadas por costo y por no resolver la acreditación.
  * *Autoalojados (Documenso, DocuSeal):* sin costo por firma, pero añaden un servicio y, en el caso de Documenso, un *stack* Node; el OTP por SMS/WhatsApp del firmante no está disponible en la edición comunitaria (2FA es de pago). Descartadas por complejidad operativa y por no cubrir el OTP por WhatsApp.
  * *Llama.pe (proveedor acreditado):* es la única vía a una firma digital con validez de la Ley 27269, pero con costo y proceso de contratación que no se justifican hoy. Se documenta como adaptador futuro.
* **Consecuencias:**
  * *Positivas:* Sin costo por firma ni proveedor adicional; control total del flujo y de la evidencia; OTP por el mismo canal del negocio; el puerto permite migrar a Documenso, BoldSign o Llama.pe sin tocar el dominio.
  * *Negativas:* El equipo es responsable de la custodia segura del `.p12` (secreto fuera del repositorio y rotación), del reloj fiable (TSA RFC 3161 opcional) y de la retención de evidencia. La validez legal es la de una firma electrónica, no la de una firma digital acreditada; si un cliente o un trámite exige esta última, se activa el adaptador acreditado.

---

## ADR-08: Tareas Programadas y Reintentos con arq

* **Estado:** Aceptado.
* **Fecha:** 2026-09-30.
* **Contexto:**
  El sistema requiere trabajo fuera del ciclo petición-respuesta: vencimiento de cotizaciones (cada minuto, RN-09), despacho y reintentos de `outbox_messages` hacia el gateway de mensajería (ADR-10), reconciliación de mensajes entrantes, y reportes semanales y mensuales. Ejecutarlo dentro del proceso de la API (`BackgroundTasks` o un planificador embebido) lo pierde al reiniciar y se duplica al escalar a varias instancias. Redis ya forma parte de la infraestructura (ADR-06).
* **Decisión:**
  Usar **arq** (cola de tareas asíncrona respaldada en Redis) como ejecutor de tareas. Un servicio `worker` independiente, con la misma imagen que la API, ejecuta `arq app.infrastructure.adapters.primary.jobs.worker.WorkerSettings`. Las tareas son adaptadores primarios que solo invocan casos de uso; no contienen lógica de negocio. Las tareas periódicas usan `cron_jobs` de arq y los reintentos de la cola outbox usan el mecanismo de reintento con *backoff* de arq.
* **Alternativas consideradas:**
  * *Celery:* más completo, pero con mayor complejidad operativa y sin soporte nativo de `asyncio`. Descartado por desproporcionado para el volumen del negocio.
  * *APScheduler embebido en la API:* no sobrevive a reinicios ni coordina varias instancias. Descartado.
  * *Cron del sistema operativo:* no reintenta ni comparte el contexto de la aplicación. Descartado.
* **Consecuencias:**
  * *Positivas:* Sin dependencias nuevas de infraestructura (reutiliza Redis); soporte `asyncio` nativo, coherente con ADR-03; el worker escala y se reinicia de forma independiente de la API.
  * *Negativas:* Un proceso más que operar y monitorear; arq tiene un ritmo de desarrollo bajo, por lo que el puerto de salida de tareas debe mantenerse delgado para poder sustituirlo.

---

## ADR-09: Bibliotecas de Seguridad (PyJWT, pwdlib, slowapi, filetype)

* **Estado:** Aceptado.
* **Fecha:** 2026-09-30.
* **Contexto:**
  `python-jose` y `passlib` no tienen mantenimiento activo y acumulan vulnerabilidades y advertencias de compatibilidad con versiones recientes de Python. Los requerimientos RNF-02 exigen JWT, hash de contraseñas robusto, límite de peticiones y validación de archivos por contenido.
* **Decisión:**
  * **JWT:** `PyJWT` (algoritmo `HS256` por defecto) en lugar de `python-jose`.
  * **Contraseñas:** `pwdlib[argon2]` con **Argon2id** en lugar de `passlib`. Se elimina Bcrypt como alternativa (RNF-02.2).
  * **Límite de peticiones:** `slowapi` con almacenamiento en Redis (login, cotizaciones, OTP y enlace de firma).
  * **Tipo real de archivo:** `filetype` (Python puro, sin dependencia de `libmagic`) para validar por contenido las subidas.
  * **Logging:** `structlog` con salida JSON y *trace id* (RNF-04.3).
* **Consecuencias:**
  * *Positivas:* Dependencias mantenidas; una única política de hash (Argon2id); imagen sin librerías de sistema adicionales.
  * *Negativas:* `slowapi` limita por clave arbitraria; los límites por contrato (OTP) requieren una clave compuesta definida en el adaptador.

---

## ADR-10: Chatwoot como Gateway de Mensajería Oculto

* **Estado:** Aceptado.
* **Fecha:** 2026-10-03.
* **Especificación:** [05. Chatwoot como Gateway de Mensajería Oculto](05-spec-chatwoot-gateway.md).
* **Contexto:**
  La integración directa con Meta WhatsApp Cloud API (ADR-05) no permite que un encargado tome una conversación cuando el bot no basta ni que lea y responda desde EventPro. Se requieren traspaso bot-humano y una bandeja de conversaciones dentro de la plataforma, sin construir un sistema de mensajería propio. El proyecto es académico: usa el número de prueba de Meta for Developers, debe operar hasta el 2026-12-15 y su infraestructura debe costar US$0 (el presupuesto de US$20 se reserva para OpenAI).
* **Decisión:**
  Adoptar **Chatwoot autoalojado** como gateway de mensajería entre Meta Cloud API y EventPro, **invisible para los usuarios**: ningún encargado ni cliente usa su interfaz y EventPro consume su API.
  1. **Puerto y adaptador:** `IMessagingPort` reemplaza a `IWhatsAppServicePort` (texto, listas interactivas, plantillas, adjuntos, cambio de estado y consulta de conversaciones y mensajes). `ChatwootMessagingAdapter` (`httpx`) lo implementa sobre la Application API de Chatwoot.
  2. **Entrada de eventos:** `POST /api/v1/webhooks/chatwoot` recibe el webhook de cuenta firmado (HMAC-SHA256, ventana de 5 minutos, deduplicación por identificador). Es **solo interno**: el proxy lo bloquea y únicamente es accesible por la red interna de Docker.
  3. **Bandeja en EventPro:** los encargados leen y responden desde la web mediante `/conversations/*` y un flujo SSE; los mensajes se consultan a Chatwoot y no se duplican en la base de datos.
  4. **Vínculo de negocio:** la tabla `conversation_links` relaciona la conversación de Chatwoot con el cliente, la cotización vigente y el encargado asignado, junto con el motivo y el resumen del traspaso.
  5. **Traspaso:** `pending` (responde el bot) y `open` (responde un humano) mediante el cambio de estado de la conversación.
  6. **Resiliencia:** todo envío pasa por `outbox_messages` con reintentos y espera creciente; un job de reconciliación cada 5 minutos recupera los mensajes entrantes no vistos si Chatwoot estuvo caído.
  7. **Canal de prueba:** se permanece en el número de prueba de Meta hasta la presentación; las credenciales de Meta se configuran dentro de Chatwoot, no en EventPro.
* **Alternativas consideradas:**
  * *Meta directo con bandeja propia (espejado de mensajes):* más código propio (medios, estados de entrega, reintentos) y doble fuente de verdad entre Meta, Chatwoot y la base de datos. Descartada.
  * *Puentes no oficiales (Evolution API, WAHA):* riesgo de bloqueo del número y botones interactivos poco fiables. Descartadas.
  * *Chatwoot Captain (agente de IA integrado):* consume presupuesto de OpenAI y cede el control del flujo del bot. Descartada.
* **Consecuencias:**
  * *Positivas:* Traspaso bot-humano y bandeja sin construir un sistema de mensajería; costo de infraestructura US$0 (Oracle Cloud Always Free); volver a Meta directo solo requeriría otro adaptador de `IMessagingPort`, sin cambios en el dominio; Chatwoot es la única fuente de verdad del canal.
  * *Negativas:* Un servicio adicional de cuatro contenedores (~4 GB de memoria) que operar, respaldar y monitorear; dependencia de comportamientos de Chatwoot aún por verificar en la implementación (Agent Bot sin `outgoing_url`, reapertura de conversaciones resueltas); la entrada de eventos exige idempotencia y reconciliación porque no se confirma que Chatwoot reintente sus webhooks.


---

## ADR-11: Orquestación manual atómica y documentos compartidos

* **Estado:** Propuesto para revisión del PR #22.
* **Contexto:** El prototipo necesita solicitud, adelanto, reserva y contrato sin WhatsApp. VerifyPaymentUseCase y ApproveOverbookedPaymentUseCase confirman sus repositorios por separado; el segundo exige evento existente. Invocarlos dentro de la creación conjunta permitiría confirmar un pago dejando inventario/contrato incompletos.
* **Decisión:** La fachada manual usa Payment y sus transiciones, con los mismos estados. Su store es una unidad transaccional: cotización/comprobante en registro; evento, inventario, verificación, conversión y documento en confirmación; bitácora en la misma transacción. Un commit antes de responder. No modifica get_session global.
* **Concurrencia:** Candado existente 180018 y misma sesión por petición: DI cacheada de FastAPI entrega la misma sesión a disponibilidad y persistencia. PDF fuera del candado. Pruebas de 15 confirmaciones y de stock protegen esta decisión.
* **Archivos:** Puerto con adaptador PostgreSQL privado conserva bytes y referencias atómicamente, separando receipts, budgets y contracts. Funciona con conexión directa Supabase sin claves públicas, límite 5 MiB. Archivos heredados requieren migración operativa antes de múltiples instancias.
* **PDF:** ReportLab sustituye la dependencia de runtime WeasyPrint que aún no tenía adaptador implementado. Plantillas manual-v1 en threadpool. Actualiza la selección inicial para el prototipo; no implementa firma. Texto requiere aprobación del negocio.
* **Identidad:** Teléfono normalizado y reconocimiento del formato legado. Se conserva el nombre maestro existente: registrar una solicitud no autoriza reescribir la identidad de un cliente compartido.
* **Consecuencias:** Binarios incrementan tamaño/respaldo de PostgreSQL; almacenamiento de objetos podrá sustituir el adaptador. Array paginado se conserva por compatibilidad con frontend. Corrección de transacciones del catálogo se entrega separada.
