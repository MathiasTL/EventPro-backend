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
  El frontend de EventPro debe atender dos audiencias distintas: los 2 encargados (panel administrativo complejo, cronograma con visualización de observaciones, overrides de movilidad, balances financieros) y los clientes finales (interfaz móvil ligera para revisión de cotización y firma electrónica de contratos). Estructuras convencionales por tipo técnico (`/components`, `/hooks`, `/pages`) provocan espagueti de dependencias e inconsistencias.
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
  * *Positivas:* Garantía de integridad referencial, soporte para bloqueos de fila (`SELECT ... FOR UPDATE`), restricciones `CHECK` e índices únicos parciales para modelar las reglas de negocio en el esquema. `JSONB` se usa únicamente en la bitácora de auditoría (`audit_logs`) y en la cola de mensajes (`outbox_messages`); los paquetes y el catálogo son columnas relacionales.
  * *Negativas:* Es necesario mantener mappers para transformar modelos ORM de SQLAlchemy a entidades puras de dominio y viceversa.

---

## ADR-05: Desacoplamiento de APIs Externas (WhatsApp Cloud API y Google Maps)

* **Estado:** Aceptado.
* **Fecha:** 2026-09-23.
* **Contexto:**
  Tanto la API de WhatsApp como Google Maps son servicios externos sujetos a latencia de red, límites de cuota (rate limits) y costos por consumo.
* **Decisión:**
  Aislar el consumo de estas APIs tras puertos secundarios abstractos (`IWhatsAppServicePort`, `IMapsServicePort`). Los mensajes de WhatsApp se encolan en `outbox_messages` con reintentos, de modo que una caída de Meta no bloquea las transacciones de negocio.
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
