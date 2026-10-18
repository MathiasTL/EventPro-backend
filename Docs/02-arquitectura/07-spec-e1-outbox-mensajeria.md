# 07. Especificación: Cola de Mensajes Salientes de E1 (Bloque 2)

* **Estado:** Propuesto (pendiente de revisión).
* **Fecha:** 2026-10-09.
* **Épica:** E1 — Bot de WhatsApp, Cotizador y Bandeja de Conversaciones (dueño: Mathias).
* **Requerimientos:** RNF-03.2 (caídas de la mensajería), RF-05 (envío de la cotización), RF de contratos de E2 (envío del contrato firmado y del OTP), avisos de pago de E5.
* **Decisiones relacionadas:** [ADR-08](04-adr-decisiones-arquitectura.md#adr-08-tareas-programadas-y-reintentos-con-arq) (arq), [05. Gateway Chatwoot](05-spec-chatwoot-gateway.md), [06. Núcleo de Cotización de E1](06-spec-e1-nucleo-cotizacion.md).

---

## 1. Contexto y objetivo

Varias épicas envían mensajes de WhatsApp: E1 (cotizaciones), E2 (contrato y OTP), E5 (avisos de pago) y la bandeja (respuestas del encargado). Si cada caso de uso llamara directamente al gateway, una caída de Chatwoot bloquearía la operación de negocio o perdería el mensaje sin rastro. RNF-03.2 prohíbe ambas cosas.

Este bloque implementa el patrón *outbox*: el caso de uso **encola** el mensaje en `outbox_messages` dentro de su propia transacción, y un **despachador** (worker de arq) lo entrega a Chatwoot mediante `IMessagingPort`, con reintentos. Además, registra el **estado de entrega** que informa WhatsApp, para saber si el mensaje llegó al cliente.

### 1.1 Criterios de éxito

* Un mensaje encolado se persiste en la misma transacción que la operación de negocio: se guardan ambos o ninguno.
* El despachador entrega los mensajes pendientes; ante la caída del gateway reintenta con espera creciente de 30 s, 2 min, 10 min, 30 min y 2 h, y al agotar los intentos el mensaje queda `FAILED`.
* Dos workers concurrentes nunca toman el mismo mensaje.
* Cada mensaje enviado guarda el identificador de Chatwoot, de modo que un aviso de entrega (`DELIVERED`, `READ`, `FAILED`) puede asociarse a su mensaje.
* Un mensaje `FAILED`, ya sea por envío o por rechazo de WhatsApp, puede reintentarse.
* El servicio `worker` de Docker Compose arranca con `WorkerSettings` reales.

### 1.2 Fuera de alcance

* Webhook de Chatwoot (`/webhooks/chatwoot`) y `ChatwootMessagingAdapter`. Este bloque usa el adaptador falso; el caso de uso `RecordDeliveryStatus` queda listo para que el webhook lo invoque.
* Endpoints de la bandeja (`/conversations`) y el endpoint de «Reintentar». El caso de uso `RetryMessage` queda listo.
* Flujo conversacional del bot y job de reconciliación de mensajes entrantes.
* Reenvío automático con plantilla cuando la ventana de 24 h está cerrada (requiere plantillas aprobadas por Meta).
* Migración de los envíos existentes de otras épicas al outbox; cada épica adopta `EnqueueMessage` en su propio PR.

---

## 2. Decisiones

### 2.1 Envío y entrega son estados separados

* `status` (`PENDING`, `SENT`, `FAILED`) responde: **¿se entregó el mensaje a Chatwoot?** `SENT` significa que Chatwoot lo aceptó.
* `delivery_status` (nulo, `DELIVERED`, `READ`, `FAILED`) responde: **¿WhatsApp lo entregó al cliente?** Lo actualiza el webhook (bloque siguiente).

Cuando WhatsApp rechaza un mensaje (por ejemplo, ventana de 24 h cerrada o número que no recibe mensajes), el mensaje queda con `delivery_status = FAILED` y el motivo en `delivery_error`; la bandeja lo muestra al encargado, que decide la acción. No hay reenvío automático.

### 2.2 Despacho por sondeo de la base de datos

Un cron de arq ejecuta el despacho cada 5 segundos. La base de datos es la única fuente de verdad: si Redis se reinicia, no se pierde ningún mensaje. Se descartaron un job de arq por mensaje (requiere igualmente el sondeo como respaldo) y `LISTEN/NOTIFY` de PostgreSQL (conexión dedicada y mayor complejidad sin beneficio para este volumen).

La reserva usa una transacción corta: `SELECT … FOR UPDATE SKIP LOCKED` sobre los mensajes `PENDING` con `next_attempt_at <= ahora`, y adelanta su `next_attempt_at` en `OUTBOX_LEASE_SECONDS` (reserva con vencimiento). El envío ocurre **fuera** de esa transacción, y el resultado se guarda en otra transacción corta por mensaje.

**Garantía: entrega al menos una vez.** Si el worker termina después de que Chatwoot aceptó el mensaje y antes de marcarlo `SENT`, la reserva vence y el mensaje se envía de nuevo. Se acepta porque un duplicado es preferible a una pérdida.

### 2.3 Número de intentos

RNF-03.2 define cinco reintentos (30 s, 2 min, 10 min, 30 min y 2 h). Con el primer envío suman **seis intentos**, por lo que el valor por defecto de `max_attempts` pasa de 5 a **6**.

| Intento fallido | Próximo intento tras |
| :---: | :--- |
| 1 | 30 s |
| 2 | 2 min |
| 3 | 10 min |
| 4 | 30 min |
| 5 | 2 h |
| 6 | — (`FAILED`) |

### 2.4 Clasificación de errores

| Error | Tratamiento |
| :--- | :--- |
| `MessagingUnavailableError` | Transitorio: reintento según la tabla anterior. |
| `ServiceWindowClosedError` | Permanente: `FAILED` inmediato con el motivo; reintentar no cambia el resultado. |
| Cualquier otro error | Transitorio: reintento. Se registra en el log **sin el contenido** del mensaje. |

### 2.5 Contenido sensible y documentos

* Los mensajes con OTP se encolan con `redact_after_send = true`; al marcarse `SENT`, su `payload` se anula, como exige el diccionario de datos.
* Los mensajes `DOCUMENT` no guardan bytes en la tabla: el `payload` guarda la ruta del archivo en el almacenamiento, el nombre, el tipo de contenido y el pie. El despachador lee el archivo mediante `IDocumentSourcePort` al momento del envío.

---

## 3. Diseño

### 3.1 Componentes

```text
app/
├── domain/
│   ├── entities/outbox_message.py          # Agregado OutboxMessage: envío, reintentos, entrega
│   └── value_objects/outbox.py             # OutboxStatus, DeliveryStatus, MessageType, RetrySchedule
├── application/
│   ├── ports/output/
│   │   ├── outbox_repository_port.py       # IOutboxRepositoryPort
│   │   └── document_source_port.py         # IDocumentSourcePort
│   └── use_cases/messaging/
│       ├── enqueue_message.py              # EnqueueMessage
│       ├── dispatch_due_messages.py        # DispatchDueMessages
│       ├── record_delivery_status.py       # RecordDeliveryStatus
│       └── retry_message.py                # RetryMessage
└── infrastructure/
    └── adapters/
        ├── primary/jobs/worker.py          # WorkerSettings de arq (cron de despacho)
        └── secondary/persistence/
            ├── models/outbox_message_model.py
            └── outbox_repository.py        # SqlAlchemyOutboxRepository (sin commit)
```

Los nombres exactos de los módulos siguen las convenciones existentes del árbol hexagonal y pueden ajustarse en el plan.

### 3.2 Agregado `OutboxMessage`

| Operación | Precondición | Efecto |
| :--- | :--- | :--- |
| `create(...)` | Teléfono válido (`PhoneNumber`) y `payload` coherente con `message_type` | `PENDING`, `attempts = 0`, `next_attempt_at = ahora` |
| `mark_sent(receipt, now)` | `PENDING` | `SENT`, `sent_at`, `external_message_id`, `conversation_id`; anula `payload` si `redact_after_send` |
| `register_failure(error, permanent, now)` | `PENDING` | Suma un intento y guarda `last_error`; si es permanente o se agotaron los intentos, `FAILED`; si no, reprograma según §2.3 |
| `record_delivery(status, error, at)` | `SENT` | Actualiza `delivery_status` sin retroceder: `READ` no vuelve a `DELIVERED`; `FAILED` no sobrescribe `DELIVERED` ni `READ` |
| `retry(now)` | `status = FAILED` o `delivery_status = FAILED` | `PENDING`, `attempts = 0`, `next_attempt_at = ahora`; limpia errores y datos de entrega |

Una transición inválida lanza un error de dominio tipado.

### 3.3 Casos de uso

* **`EnqueueMessage`:** construye el `OutboxMessage` y lo agrega con el repositorio sobre la sesión del llamador; no hace `commit`.
* **`DispatchDueMessages`:** reserva hasta `OUTBOX_BATCH_SIZE` mensajes y, para cada uno, llama al método de `IMessagingPort` según el tipo (`send_text`, `send_template`, `send_interactive_list`, `send_attachment`) y guarda el resultado en su propia transacción. Un fallo en un mensaje no afecta a los demás.
* **`RecordDeliveryStatus`:** busca por `external_message_id` y aplica `record_delivery`. Un identificador desconocido se ignora y se registra en el log (puede ser un mensaje enviado manualmente desde Chatwoot).
* **`RetryMessage`:** aplica `retry` a un mensaje existente; lanza `ResourceNotFoundError` si no existe.

### 3.4 Worker

`jobs/worker.py` define `WorkerSettings` con un `cron` cada 5 segundos (`unique=True`, para que dos ciclos del mismo worker no se superpongan) que invoca `DispatchDueMessages`. El adaptador de mensajería se elige por configuración; en este bloque es el adaptador falso. Un error de base de datos aborta el ciclo y el siguiente lo reintenta.

### 3.5 Persistencia: migración `0004_outbox_delivery_tracking`

Encadenada a `0003_manual_booking_documents`. Solo agrega columnas y cambia un valor por defecto:

| Columna | Tipo | Nulo | Default | Restricciones |
| :--- | :--- | :---: | :--- | :--- |
| `external_message_id` | `VARCHAR(64)` | SÍ | `NULL` | UNIQUE |
| `conversation_id` | `BIGINT` | SÍ | `NULL` | - |
| `delivery_status` | `VARCHAR(20)` | SÍ | `NULL` | CHECK in (`DELIVERED`, `READ`, `FAILED`) |
| `delivery_error` | `TEXT` | SÍ | `NULL` | - |
| `delivered_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - |
| `read_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - |
| `redact_after_send` | `BOOLEAN` | NO | `false` | - |
| `max_attempts` (existente) | `INTEGER` | NO | `5` → **`6`** | - |

El `downgrade` elimina las columnas nuevas y restaura el default de `max_attempts` a 5.

### 3.6 Configuración

| Variable | Valor por defecto | Uso |
| :--- | :--- | :--- |
| `OUTBOX_BATCH_SIZE` | `20` | Mensajes reservados por ciclo |
| `OUTBOX_LEASE_SECONDS` | `60` | Vencimiento de la reserva; debe superar el tiempo máximo de un envío |
| `OUTBOX_MAX_ATTEMPTS` | `6` | Intentos por mensaje (§2.3) |

---

## 4. Pruebas

| Nivel | Cobertura | Herramienta |
| :--- | :--- | :--- |
| Dominio | Espera creciente, error permanente vs. transitorio, agotamiento de intentos, entrega fuera de orden, `retry`, anulación del OTP | Pruebas puras |
| Casos de uso | Despacho con éxito, caída del gateway, ventana cerrada, aislamiento entre mensajes, `DOCUMENT` con `IDocumentSourcePort`, identificador de entrega desconocido | Adaptador falso de mensajería, repositorio en memoria y reloj fijo |
| Integración | `claim_due` con dos sesiones concurrentes sin solapamiento, vencimiento de la reserva, encolado y rollback en la misma transacción, migración `0004` (`upgrade`/`downgrade`) | Testcontainers (PostgreSQL) |
| Worker | `WorkerSettings` se importa y registra el cron | Prueba de humo |

---

## 5. Pendientes abiertos

1. **Webhook de entrega:** el mapeo de `message_updated` de Chatwoot a `RecordDeliveryStatus` se define en el bloque del webhook.
2. **Avisos al encargado:** la bandeja mostrará los mensajes con `status = FAILED` o `delivery_status = FAILED`; el contrato del endpoint se define en el bloque de la bandeja.
3. **Retención:** no se define una purga de mensajes `SENT` antiguos; se revisará si el volumen lo requiere.

---

## 6. Impacto en la documentación

| Documento | Cambio |
| :--- | :--- |
| `03-datos/02-diccionario-de-datos.md` | §2.19: columnas nuevas y `max_attempts = 6`. |
| `03-datos/01-diagrama-entidad-relacion.md` | Columnas nuevas de `OUTBOX_MESSAGES`. |
| `03-datos/03-estrategia-migraciones-y-seeds.md` | Revisión `0004_outbox_delivery_tracking`. |
| `02-arquitectura/02-backend-arquitectura-hexagonal.md` | `IOutboxRepositoryPort`, `IDocumentSourcePort`, casos de uso de mensajería y `jobs/worker.py`. |
| `05-operaciones/01-guia-entorno-y-configuracion.md` | Variables `OUTBOX_*`. |
| `Docs/README.md` | Enlace a esta especificación. |
