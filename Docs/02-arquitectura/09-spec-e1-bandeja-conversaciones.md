# 09. Especificación: Bandeja de Conversaciones de E1 (Backend primero, frontend después)

* **Estado:** Propuesto (pendiente de revisión).
* **Fecha:** 2026-10-20.
* **Épica:** E1 — Bot de WhatsApp, Cotizador y Bandeja de Conversaciones (dueño: Mathias).
* **Rama:** `feat/e1-conversation-inbox` (una sola rama para ambas entregas; sin ramas por tarea).
* **Historias:** US-27, US-28, US-29, US-30, US-31, US-32.
* **Requerimientos y reglas:** RF-30, RF-31, RF-32, RN-10, RN-11, RNF-03.2.
* **Especificaciones relacionadas:** [05. Gateway de Chatwoot](05-spec-chatwoot-gateway.md), [07. Cola de Mensajes Salientes](07-spec-e1-outbox-mensajeria.md), [08. Contrato de Cotización](08-spec-e1-contrato-cotizacion.md), [03. Frontend FSD](03-frontend-arquitectura-fsd.md).

---

## 1. Objetivo y por qué

Los encargados deben atender las conversaciones de WhatsApp **dentro de EventPro y nunca en Chatwoot**, que es infraestructura invisible (ADR-10). El hilo debe mostrar sin ambigüedad qué mensajes escribió el **cliente**, cuáles el **bot** y cuáles un **encargado**.

Las especificaciones 05 y 08 ya dejaron el gateway, la cola de salida y el bot. Esta especificación cierra lo que falta para que la bandeja funcione de extremo a extremo: el vínculo persistente de cada conversación, la derivación del bot hacia ese vínculo, la autoría de los mensajes, el puente de tiempo real, los motivos de falla y los datos que la interfaz necesita (búsqueda, no leídos, estado comercial). La entrega es en dos cortes con el mismo equipo: **slice 1 (backend)** y **slice 2 (frontend)**; el slice 2 empieza cuando el contrato del slice 1 está fusionado en la rama.

No redefine lo que ya está decidido; lo cita (sección 2). Solo documenta los **deltas**, las decisiones nuevas y las brechas del código.

### 1.1 Criterios de éxito

* Un encargado lista, busca, abre, toma, responde y devuelve conversaciones sin abrir Chatwoot.
* Cada burbuja indica su autor (`CLIENT`, `BOT` o `AGENT` con nombre) y el estado de entrega de lo saliente.
* Un mensaje que no llegó muestra un motivo en español y, si procede, permite reintentar sin duplicar filas del *outbox*.
* Los eventos nuevos (mensaje, estado de entrega, derivación) aparecen sin recargar.
* Chatwoot caído produce un estado de error claro, no una pantalla rota.

### 1.2 Alcance

**Dentro:** los 7 endpoints del módulo 2.14 más tres extensiones (sección 7.4); búsqueda por nombre o teléfono; contador de no leídos; filtro por encargado para `SUPERADMIN`; estado comercial derivado de solo lectura; persistencia de `conversation_links`; autoría de mensajes; puente SSE; catálogo de motivos de falla; interfaz de la bandeja (slice 2).

**Fuera de alcance (no objetivos de esta versión):**

* Respuestas rápidas (*quick replies*).
* Citar o responder a un mensaje específico.
* Notas de voz y envío de video (se admiten texto, imagen y PDF).
* Envío de plantillas de WhatsApp desde la bandeja (D20): no hay plantillas propias aprobadas por Meta todavía.
* Bloquear contacto.
* Filtro por número de WhatsApp (hay un solo número).
* Contadores diarios de *leads*.
* Tipificación o etiquetas manuales de *leads*; el estado comercial es derivado, no un *pipeline*.
* Persistir mensajes en EventPro (sección 5.3).
* Mostrar las opciones de las listas interactivas del bot (el hilo muestra solo el texto).
* Cerrar o archivar conversaciones desde la interfaz (pregunta 3).
* El *debounce* de mensajes seguidos del cliente (F1), que es un seguimiento aparte.

---

## 2. Referencias (ya decididas)

| Tema | Fuente |
| :--- | :--- |
| Historias | US-27 a US-32 en [`05-historias-de-usuario.md`](../01-requisitos/05-historias-de-usuario.md) |
| Requerimientos | RF-30, RF-31, RF-32 en [`02-requerimientos-funcionales.md`](../01-requisitos/02-requerimientos-funcionales.md) |
| API | Módulo 2.14 de [`01-especificacion-endpoints-rest.md`](../04-api/01-especificacion-endpoints-rest.md) |
| RBAC | Sección 2.10 y regla 9 de [`02-matriz-rbac-y-seguridad.md`](../04-api/02-matriz-rbac-y-seguridad.md) |
| Datos | `conversation_links` en [`02-diccionario-de-datos.md`](../03-datos/02-diccionario-de-datos.md) (2.22) y migración `0001`; columnas de entrega de `outbox_messages` (migración `0004`) |
| Reglas y etiquetas | RN-10, RN-11 y tabla 3.5 de [`04-reglas-de-negocio-y-control.md`](../01-requisitos/04-reglas-de-negocio-y-control.md) |
| Frontend | Sección 4.3 de [`03-frontend-arquitectura-fsd.md`](03-frontend-arquitectura-fsd.md) |

Puntos que esta especificación **no** cambia: tomar, devolver y reasignar conservan la semántica del módulo 2.14 (devolver solo por el asignado o `SUPERADMIN`, con botón explícito; responder **no** libera; reasignar solo `SUPERADMIN` con auditoría `OVERRIDE_CONVERSATION_ASSIGNMENT`); el modo `BOT`/`HUMAN` se proyecta del `status` de Chatwoot; el envío es `202 QUEUED` por *outbox* con auditoría `SEND_CONVERSATION_MESSAGE`; fuera de la ventana de 24 h solo hay plantillas; los eventos SSE, el `?access_token`, el latido de 25 s, la ausencia de búfer de reenvío y el refetch al reconectar quedan como están; EventPro no almacena mensajes.

---

## 3. Punto de partida: qué hay y qué falta

| Pieza | Hoy | Falta |
| :--- | :--- | :--- |
| Bot | Responde solo si la conversación está en `pending` (`handle_incoming_message.py:121-127`). Deriva con `set_conversation_status(HUMAN)` y no guarda motivo ni resumen (`:266-289`). Los motivos internos son textos libres: `requested`, `chosen`, `not_understood`, `error`, `no_catalog` (`:149,190,218,221,259`) y, en el agente, `client_request` o `bot_not_understood` (`agent_engine.py:429-436`). | Persistir motivo, resumen e instante; emitir `handoff.requested`; vincular la cotización creada (`handle_incoming_message.py:473-497`, `agent_engine.py:257-282`). |
| Eventos del gateway | El parser solo entiende avisos de entrega y mensajes entrantes (`chatwoot_event_gateway.py:38-58`). Los entrantes solo llegan al bot; con la conversación en `open` el bot los ignora (`handle_incoming_message.py:121-127`). Los ecos salientes se registran y se descartan (`process_gateway_event.py:66-74`). | Publicar `message.created`, `message.updated` y `conversation.updated`. |
| `IMessagingPort` | `ConversationStatus` solo tiene `BOT`/`HUMAN` (`messaging_dto.py:11`). `ConversationSummary` no trae nombre, no leídos, vista previa ni estado crudo (`:44`). `ConversationMessage` no trae remitente, estado ni adjuntos (`:53`). El listado descarta las `resolved` (`chatwoot_payloads.py:97-100,265-278`). `before` es una fecha y obliga a recorrer páginas (`messaging_port.py:60`). | Ampliar puerto, DTOs, adaptador real y *fake* (sección 5.4). |
| Autoría | **Todo** mensaje que se crea en Chatwoot usa el token del bot (`chatwoot_messaging_adapter.py:284-293`), incluidos los que escribe un encargado vía *outbox*. Chatwoot no distingue bot de encargado. | Atribución en `outbox_messages` (sección 4.3). La spec 05 (§3.2) lo describía al revés; se corrige ahí. |
| `conversation_links` | Tabla creada en `alembic/versions/0001_initial_schema.py:675-707`. No hay modelo ORM, repositorio ni código que la escriba. | Entidad, repositorio, migración de ajuste (sección 5). |
| Auditoría | `SEND_CONVERSATION_MESSAGE` y `OVERRIDE_CONVERSATION_ASSIGNMENT` ya existen (`audit_log.py:14-15`) y el `CHECK` los admite (`0001:45-46,178-180`). | Nada que agregar al vocabulario (D9). |
| *Outbox* | `RetryMessage` existe (`retry_message.py:11-23`) sin endpoint; la fila no guarda al autor. | Endpoint de reintento y columna de autor. |
| API | `main.py` no registra router de conversaciones (`main.py:70-83`). `get_auth_context` solo lee `Authorization` (`deps.py:61-84`). | Router, dependencia de autenticación del stream. |
| Frontend | Sin *slices* de conversaciones. `client.ts` no renueva sesión (un `401` limpia la sesión) y solo se guarda el *access token* (`auth-storage.ts:5-6`). No hay TanStack Query ni *runner* de pruebas (`package.json`). | Slice 2 (sección 12). |

---

## 4. Modelo y estados

### 4.1 Modo, estado y asignación

> **Decisión de diseño D7.** El API expone el `status` crudo de Chatwoot (`pending`, `open`, `resolved`), el `mode` derivado y `assigned_user_id`; no se agrega un cuarto estado. *Por qué:* el módulo 2.14 ya los define y `ConversationStatus` (`BOT`/`HUMAN`) sigue siendo la entrada de escritura del puerto; las lecturas usan un enumerado nuevo `ConversationLifecycle` (`PENDING`, `OPEN`, `RESOLVED`).

| `status` | `mode` | `assigned_user_id` | Lectura en la interfaz |
| :--- | :--- | :--- | :--- |
| `pending` | `BOT` | `null` | Atendida por el bot |
| `open` | `HUMAN` | `null` | **Sin asignar**: derivación pendiente de toma |
| `open` | `HUMAN` | UUID | Atendida por `assigned_user_name` |
| `resolved` | `BOT` | `null` | Resuelta; oculta salvo `include_resolved=true` |

* **Asignación efectiva:** `assigned_user_id` solo se informa cuando `status = open`. Si el vínculo conserva un asignado pero Chatwoot ya no está en `open` (por ejemplo, se resolvió fuera de EventPro), el API devuelve `null`; el vínculo se corrige en la siguiente escritura.
* **Filtros:** `mode` filtra por `mode`; `assigned=me` es `assigned_user_id = usuario`; `assigned=unassigned` es `status = open` y `assigned_user_id = null`; `assigned_user_id=<uuid>` (solo `SUPERADMIN`) es la asignación efectiva a ese usuario; `q` busca (sin distinguir mayúsculas ni tildes) en nombre y en dígitos del teléfono, mínimo 2 caracteres.
* **Orden y paginación:** `last_message_at` descendente, como en 2.14. Sin filtro de `mode` se devuelven `BOT` y `HUMAN` no resueltas.

### 4.2 Estado comercial derivado (*lead status*)

Etiqueta de solo lectura en la fila y en la cabecera del hilo. No se escribe, no se tipifica a mano y no es un *pipeline*: se calcula con el estado actual de la cotización vinculada (`conversation_links.quote_id`). El enumerado real es `QuoteStatus` (`quote.py:18-23`).

> **Decisión de diseño D14.** `lead_status` es una clave estable calculada en el API; la etiqueta en español vive en el frontend, igual que `handoff_reason`. *Por qué:* mantiene un solo origen de verdad (la cotización) y deja las etiquetas fuera del contrato.

| `quote_status` | `lead_status` | Etiqueta sugerida | Cuándo ocurre |
| :--- | :--- | :--- | :--- |
| `null` | `QUOTING` | Cotizando | Sin cotización vinculada (el bot recoge datos) |
| `SENT` | `QUOTE_SENT` | Cotización enviada | Cotización enviada, sin pago iniciado |
| `PAYMENT_STARTED` | `PAYMENT_STARTED` | Pago iniciado | El cliente pulsó «Pagar adelanto» |
| `CONVERTED` | `CONVERTED` | Convertido | Adelanto validado y evento creado |
| `EXPIRED`, `CANCELLED` | `QUOTE_CLOSED` | Vencida/Cancelada | La cotización terminó sin convertirse |
| `CONVERTED` + evento realizado | `EVENT_DONE` | Evento realizado | El evento de la cotización está `SETTLED`, o un encargado o `SUPERADMIN` lo marcó a mano |

> **Decisión de diseño D25 (acordada con el responsable del producto, 2026-10-20).** Las conversaciones nunca se cierran: un cliente que vuelve a escribir sigue en el mismo chat. El ciclo comercial tiene una etapa final, `EVENT_DONE`, y vuelve al inicio cuando el cliente regresa.
>
> * **Cómo se llega a `EVENT_DONE`:** de las dos formas. (a) Calculado: la cotización vinculada está `CONVERTED` y su evento está `SETTLED` (`event_status.py`), leído por el puerto de consulta de la bandeja; depende de que E6 lleve los eventos a `SETTLED`. (b) Manual: `POST /conversations/{id}/lead/event-done` (7.4), permitido a `ENCARGADO` y `SUPERADMIN` solo cuando `lead_status = CONVERTED`; guarda `conversation_links.event_done_at` y `event_done_by_user_id`. Es solo un cambio de estado: no cambia el modo, la asignación ni el estado de Chatwoot.
> * **Cómo se vuelve al inicio:** cuando llega un mensaje entrante del cliente y el `lead_status` es `EVENT_DONE`, el *worker* (6.1) reinicia el ciclo: `quote_id = NULL`, `event_done_at = NULL`, `event_done_by_user_id = NULL` y `lead_cycle_started_at = now()`. El estado vuelve a `QUOTING` y la cotización nueva que cree el bot se vincula como siempre. Las cotizaciones y eventos anteriores no se tocan; siguen en sus tablas.
> * *Por qué:* el cálculo evita depender de la memoria del encargado; la marca manual cubre el caso en que E6 todavía no lleve el evento a `SETTLED`. Reiniciar al volver el cliente replica el comportamiento de la referencia visual (vuelve a «en trabajo»).

* El vínculo apunta a la cotización más reciente creada en la conversación (sección 6.2); si el bot crea otra, el estado cambia solo.
* Las etiquetas de cotización de la tabla 3.5 de RN («Cotizado», «Convertida», ...) describen a la cotización, no a la conversación. Se evita reutilizarlas para no mezclar conceptos; RN recibe un bloque nuevo (sección 18).

### 4.3 Autoría de cada mensaje (`author_type`)

> **Decisión de diseño D3.** La autoría de un mensaje saliente se resuelve primero por el *outbox* (`outbox_messages.author_user_id`) y solo después por el remitente del *payload* de Chatwoot. *Por qué:* el bot y los encargados crean mensajes con el mismo token (sección 3), así que el remitente de Chatwoot no los distingue.

| Mensaje | Fuente | `author_type` |
| :--- | :--- | :--- |
| Entrante (`message_type` `incoming` / `0`) | Dirección | `CLIENT` |
| Saliente con fila de *outbox* y `author_user_id` | *Outbox* | `AGENT` (con `author_name` del usuario) |
| Saliente con fila de *outbox* sin autor | *Outbox* | `BOT` |
| Saliente sin fila de *outbox* | `sender.type`: `user` → `AGENT`, `agent_bot` → `BOT` | según remitente |
| Saliente sin fila y sin `sender` | Regla de respaldo | `BOT` |

* La regla de respaldo es `BOT` porque un humano solo escribe por EventPro y eso siempre deja fila de *outbox*.
* **Verificado el 2026-10-20 (B2):** en la API, un mensaje del Agent Bot trae `message_type: 1` y `sender.type: "agent_bot"` (`sender.name: "EventPro Bot"`); el del cliente, `message_type: 0` y `sender.type: "contact"`; un aviso de actividad (reapertura, cambio de estado), `message_type: 2` y **sin** `sender`. El adaptador expone el tipo crudo (`MessageSender`: `CONTACT`, `USER`, `AGENT_BOT` o `None`) y marca la actividad como `MessageDirection.ACTIVITY`: nunca es `BOT`, y la interfaz la muestra como aviso del sistema o la oculta. El *payload* de webhook de un mensaje del Agent Bot no se capturó (solo la API).
* **Carrera en tiempo real:** el eco `message_created` de un saliente puede llegar antes de que el despachador confirme `SENT`. El *worker* trata un saliente sin fila de *outbox* como `UNKNOWN_MESSAGE` y reutiliza el reintento acotado de `process_gateway_event` (`worker.py:81-106`); en el último intento publica con la regla de respaldo. El webhook ya espera 2 s antes de encolar (spec 05, §3.3).

### 4.4 Otros datos de la fila

| Dato | Origen | Nota |
| :--- | :--- | :--- |
| Nombre | `clients.full_name` si hay cliente; si no, nombre del contacto de Chatwoot; si no, el teléfono | El adaptador crea el contacto con el teléfono como nombre (`chatwoot_payloads.py:201-202`) |
| Vista previa | Último mensaje no de actividad de la conversación; 120 caracteres; «[Adjunto]» si no hay texto | Verificado el 2026-10-20: `last_non_activity_message` viene poblado en conversaciones reales (`null` solo si la conversación no tiene mensajes). El adaptador calcula la vista previa y `last_message_at` con ese mensaje, de modo que un aviso de actividad no los mueve |
| `unread_count` | `unread_count` de la conversación de Chatwoot (presente en `message_created_incoming.json:110` y `api_conversation_list.json:57`) | Ver D13 |
| `service_window_open` | `can_reply` de Chatwoot (ya verificado, spec 05 §3.6) | Autoritativo |
| `service_window_expires_at` | `conversation_links.last_client_message_at` + 24 h | Ver D15 |

> **Decisión de diseño D13.** El contador de no leídos es el de Chatwoot y se reinicia con `POST /conversations/{id}/read`, que llama a la API de Chatwoot para marcar la conversación como vista por el agente de servicio. *Por qué:* evita almacenar contadores; la consecuencia es que el contador es **compartido** entre encargados (hay un solo agente de servicio). Verificado el 2026-10-20 en v4.18.0: `POST /conversations/{id}/update_last_seen` con el token de agente reinicia `unread_count` (de 10 a 0) y devuelve la conversación.

> **Decisión de diseño D15.** Se agrega `last_client_message_at` a `conversation_links`. *Por qué:* Chatwoot informa si se puede responder, pero no cuándo vence la ventana; recorrer mensajes por cada fila de la bandeja es inviable. Es una marca de tiempo, no contenido de mensajes.

---

## 5. Persistencia

### 5.1 `conversation_links`

> **Decisión de diseño D1.** El vínculo se crea (*upsert* idempotente) al primer evento de la conversación y, si falta, también al tomar, enviar o consultar. El cliente se resuelve por teléfono y **no se crea cliente nuevo**: `client_id` pasa a ser nulo. *Por qué:* `get_or_create` nunca sobrescribe el nombre (`client_repository_port.py:16-17`), así que crear un cliente con el nombre de perfil de WhatsApp impediría que el bot guarde el nombre real; además, `clients` queda solo con quien cotiza.

* **Entidad `ConversationLink`** (`app/domain/entities/conversation_link.py`), con `HandoffReason` (`CLIENT_REQUEST`, `BOT_NOT_UNDERSTOOD`, `MANUAL_TAKEOVER`, `BOT_ERROR`) y operaciones `register_handoff`, `assign`, `unassign`, `link_quote`, `record_client_message`.
* **Puerto `IConversationLinkRepositoryPort`** (`app/application/ports/output/`), sin `commit` como los demás repositorios:

| Método | Uso |
| :--- | :--- |
| `ensure(conversation_id, client_id, now)` | `INSERT ... ON CONFLICT (chatwoot_conversation_id) DO NOTHING` y lectura; seguro ante dos escritores (webhook y bot) |
| `get(conversation_id)` / `get_many(ids)` | Lectura individual y por lote para la bandeja |
| `save(link)` | Persiste cambios del bot y de los comandos |
| `claim(conversation_id, user_id, expected_assignee)` | *Compare-and-set* de la asignación; devuelve si ganó (D11) |
| `release(conversation_id, expected_assignee)` | Limpia la asignación con la misma condición |

* **Modelo, mapper y repositorio SQLAlchemy** siguen el patrón de `outbox_message_model.py`, `outbox_mapper.py` y `sqlalchemy_outbox_repository.py`.
* **Migración** (nombre `<siguiente>_inbox_support`; la 0006 está reservada en la spec 08 y se encadena tras *rebase* sobre `develop`, un solo `head`): `conversation_links.client_id` pasa a `NULL`; `conversation_links.last_client_message_at TIMESTAMPTZ NULL`; `outbox_messages.author_user_id UUID NULL` con FK a `users.id` e índice; `outbox_messages.retried_external_message_id TEXT NULL` con índice (D24); `conversation_links.event_done_at TIMESTAMPTZ NULL`, `event_done_by_user_id UUID NULL` con FK a `users.id` y `lead_cycle_started_at TIMESTAMPTZ NULL` (D25). Actualiza el diccionario (sección 18).
* **Regla de lectura:** sin vínculo, la bandeja arma la fila solo con datos de Chatwoot (`assigned_user_id`, `handoff_reason` y `quote_id` nulos).

### 5.2 Autor en el *outbox*

`EnqueueMessage.execute` recibe `author_user_id: UUID | None = None` (`enqueue_message.py:30-37`), `OutboxMessage` y su mapper lo guardan, y el repositorio gana `get_many_by_external_ids(ids)` y `list_unsent_for_recipient(phone)`. Los envíos del bot siguen sin autor. `OutboxMessage.retry` conserva el autor original (`outbox_message.py:231-256`).

### 5.3 Qué no se guarda

* No se guardan mensajes ni medios en EventPro (RN-10.6). El *outbox* ya conserva el *payload* de lo pendiente hasta enviarlo (y lo anula si `redact_after_send`); eso es una cola, no un archivo.
* `handoff_summary` contiene **solo datos estructurados** de la sesión del bot (paquete, fecha, distrito, nombre y cotización), nunca texto libre del cliente. Máximo 500 caracteres.
* El contenido que viaja por Redis *pub/sub* (sección 8) no se persiste.

### 5.4 Cambios en `IMessagingPort`

Contrato nuevo, con la suite `tests/infrastructure/messaging_port_contract.py` ampliada y pasando contra el *fake* y contra el adaptador con `httpx.MockTransport`:

| Cambio | Detalle |
| :--- | :--- |
| `list_conversations(..., include_resolved)` | `ConversationSummary` suma `lifecycle`, `contact_name`, `unread_count`, `last_message_preview` y `assignee_name`. Con `include_resolved=False` se mantiene el comportamiento actual; las resueltas cuentan como `BOT` y las pospuestas nunca se listan |
| `get_conversation(id)` | Mismo resumen para una conversación; `ResourceNotFoundError` si no existe |
| `list_messages(id, *, before_id, limit)` | Sustituye `before: datetime` por un cursor por id (D16); `ConversationMessage` suma remitente (`CONTACT`/`USER`/`AGENT_BOT`/`None`), nombre, `status` (crudo: `sent`, `delivered`, `read`, `failed`), `external_error` (texto crudo, nunca sale del backend), `content_type` y adjuntos (`id`, `file_type`, `content_type`, extensión, tamaño, nombre). Incluye los avisos de actividad (`MessageDirection.ACTIVITY`, sin remitente); las notas privadas no |
| `mark_conversation_read(id)` | `update_last_seen` con el token de agente (D13) |
| `get_attachment(id, attachment_id)` | `AttachmentContent` (bytes, tipo y nombre); `ResourceNotFoundError` si el adjunto no está en la conversación o el destino no es seguro; ver D17 |

> **Decisión de diseño D16.** El cursor de mensajes es por id. *Por qué:* Chatwoot ya pagina por id; el cursor por fecha del puerto obligaba a recorrer hasta 25 páginas y a fabricar microsegundos (`chatwoot_payloads.py:147-166`). El API devuelve del más reciente al más antiguo, como 2.14; el puerto sigue entregando orden cronológico y el caso de uso lo invierte.

Puerto de lectura nuevo `IInboxLookupPort` con tres consultas por lote: `client_names(client_ids)`, `user_names(user_ids)` y `quote_statuses(quote_ids)`. *Por qué* un puerto aparte: evita tocar `IQuoteRepositoryPort` y `IClientRepositoryPort`, que otros responsables modifican en paralelo (spec 08, §3.3 y §5).

> **Decisión de diseño D12.** La bandeja se arma en memoria: se leen las conversaciones de Chatwoot (tope de 500, 20 páginas de 25, el mismo del adaptador, `chatwoot_messaging_adapter.py:32-34`), se unen con `conversation_links` y las consultas por lote, y se filtran, ordenan y paginan en el caso de uso. *Por qué:* es lo más simple para el volumen de este proyecto (un número de prueba); la salida si crece es guardar `last_message_at` y `unread_count` en el vínculo y paginar en SQL.

---

## 6. Flujos

### 6.1 Evento entrante en el *worker*

1. El parser clasifica `message_created` (entrante o saliente, no privado) como evento de mensaje con la instantánea de la conversación incluida en el *payload* (`status`, `unread_count`, `meta.sender`, `can_reply`).
2. `ensure` del vínculo; si el teléfono corresponde a un cliente, se fija `client_id`.
3. Si es entrante, `record_client_message(at)` actualiza `last_client_message_at` y, si el `lead_status` era `EVENT_DONE`, reinicia el ciclo comercial (D25).
4. Si es saliente y no hay fila de *outbox* para su id, el resultado es `UNKNOWN_MESSAGE` (reintento acotado, sección 4.3).
5. Se publican `message.created` y `conversation.updated` (sección 8). El fallo de publicación se registra y no falla el trabajo.
6. Si es entrante y la conversación está en `pending`, se entrega al bot (`HandleIncomingMessage`), como hoy.
7. Un aviso de entrega aplicado (`RecordDeliveryStatus`) publica `message.updated` con el estado y el motivo ya traducido (sección 9).

> **Decisión de diseño D22.** La suscripción del webhook no cambia (`message_created` y `message_updated`). *Por qué:* esos eventos traen el estado, el asignado y los no leídos de la conversación; los cambios de asignación nacen en EventPro, que publica por su cuenta.

### 6.2 Derivación del bot

> **Decisión de diseño D2.** La derivación persiste en el vínculo y emite `handoff.requested`; los motivos internos del bot se traducen a `HandoffReason`: `requested`, `chosen`, `client_request` → `CLIENT_REQUEST`; `not_understood`, `bot_not_understood` → `BOT_NOT_UNDERSTOOD`; `error`, `no_catalog` → `BOT_ERROR`. *Por qué:* RF-30 y US-27 exigen motivo y resumen persistentes; `no_catalog` es una falla del sistema, no un pedido del cliente.

1. El bot encola el aviso al cliente (como hoy).
2. Arma el resumen **antes** de `sessions.clear`, desde los campos estructurados de la sesión (`BotSession` o `AgentSession`) y la cotización vigente.
3. Limpia la sesión y pasa Chatwoot a `open` (como hoy, `handle_incoming_message.py:279-283`).
4. Solo si el paso 3 funcionó: `ensure` y `register_handoff(reason, summary, now)` en una transacción corta (asignado nulo, `handed_off_at` = ahora).
5. Publica `handoff.requested` y `conversation.updated`.

* **Vínculo con la cotización:** al crear una cotización, ambos motores llaman `link_quote(conversation_id, quote_id, client_id)` dentro de la transacción de `CreateQuote`, de modo que se confirman juntos (`BotTransaction` suma el repositorio de vínculos, `bot_unit_of_work_port.py:19-26`).
* **Limitación conocida:** si Chatwoot no acepta el paso 3, el cliente ya recibió «Te comunico con un encargado» y la conversación sigue en `pending`. No se registra la derivación ni se emite el evento; lo cubre el *job* de reconciliación pendiente (spec 05, §4).

### 6.3 Tomar (`POST /conversations/{id}/takeover`)

> **Decisión de diseño D11.** La concurrencia se resuelve con *compare-and-set* en base de datos y compensación, sin transacciones abiertas durante la llamada HTTP a Chatwoot y sin *lock* de Redis. *Por qué:* es el mismo criterio del despachador (`dispatch_due_messages.py`, llamadas fuera de toda transacción) y evita bloqueos por una llamada lenta.

> **Decisión de diseño D23.** Tomar una conversación en modo `BOT` limpia la sesión del bot. *Por qué:* al devolverla, el bot debe retomar desde el saludo (6.5) y no a mitad de un flujo que el encargado ya atendió.

> **Decisión de diseño D8.** Tomar una conversación `resolved` la reabre: pasa a `open` y se asigna, con `handoff_reason = MANUAL_TAKEOVER`. *Por qué:* el encargado quiere escribirle al cliente y `resolved` no admite envío; reabrir es lo que haría `toggle_status`.

1. `get_conversation` en Chatwoot (`404` → `not-found`; caída → `503`). `ensure` del vínculo si falta.
2. Si ya está `open` y asignada al mismo usuario, responde `200` sin cambios.
3. Si está asignada a otro: `ENCARGADO` recibe `409 conversation-taken-by-other`; `SUPERADMIN` sigue como reasignación (6.6).
4. `claim(conversation, user, expected_assignee)`. Si pierde, `409 conversation-taken-by-other`.
5. Si el estado no es `open`: `set_conversation_status(HUMAN)`. Si falla, **compensa** (`release` con el asignado esperado = el usuario) y responde `503`.
6. Si estaba en modo `BOT` (`pending` o `resolved`): `handoff_reason = MANUAL_TAKEOVER` y `handed_off_at`. Si ya era una derivación sin asignar, conserva el motivo original.
7. Si estaba en modo `BOT`, limpia la sesión del bot en Redis (D23), de mejor esfuerzo: una falla se registra y no revierte la toma.
8. Publica `conversation.updated` y responde `200` con la fila actualizada.

### 6.4 Enviar (`POST /conversations/{id}/messages`)

1. Valida `open` y `assigned_user_id = usuario` (`409 conversation-not-taken` o `conversation-taken-by-other`). Responder **no** modifica la asignación.
2. Con ventana cerrada (`can_reply = false`) y texto o adjunto: `422 service-window-closed` con `service_window_expires_at`. En esta versión el encargado no envía plantillas (D20); el tipo `template` del cuerpo responde `422 validation-error`.
3. En una sola transacción: `EnqueueMessage(author_user_id = usuario)` (TEXT o DOCUMENT) y auditoría `SEND_CONVERSATION_MESSAGE` (`entity_name = "outbox_message"`, `entity_id` = id de la fila, `new_values` con id de conversación y tipo; **sin contenido**).
4. Responde `202 {outbox_id, chatwoot_conversation_id, delivery_status: "QUEUED"}`.
5. El despachador envía por teléfono (`dispatch_due_messages.py:194-207`), y el eco y los avisos de entrega llegan por 6.1.

> **Decisión de diseño D19.** Los adjuntos que sube un encargado se guardan con el almacenamiento de evidencias existente (`IPaymentEvidenceStoragePort`: 5 MB, validación por contenido, JPEG, PNG, WebP y PDF) y viajan como `DOCUMENT`. *Por qué:* es lo que ya lee `StorageDocumentSource`; renombrar el puerto es un seguimiento.

### 6.5 Devolver (`POST /conversations/{id}/release`)

> **Decisión de diseño D18.** Un `ENCARGADO` que intenta devolver una conversación `open` sin asignar recibe `409 conversation-not-taken`. *Por qué:* la regla es que solo la devuelve el asignado o un `SUPERADMIN`; sin asignado, el encargado debe tomarla primero.

1. Si ya está en `pending` (o `resolved` sin asignado), responde `200` sin cambios.
2. Autoriza: el asignado o `SUPERADMIN`; otro `ENCARGADO`, `409 conversation-taken-by-other`.
3. `release` con el asignado esperado y luego `set_conversation_status(BOT)`; si Chatwoot falla, restituye la asignación y responde `503`.
4. `handoff_reason` y `handed_off_at` se conservan como historial.
5. Si un `SUPERADMIN` devolvió una conversación asignada a otro, audita `OVERRIDE_CONVERSATION_ASSIGNMENT` (D9).
6. Publica `conversation.updated`. El bot retoma **desde el saludo**, porque su sesión se limpió al derivar.

### 6.6 Reasignar (solo `SUPERADMIN`)

Es el flujo 6.3 con asignado distinto. Tras el éxito de Chatwoot (si hacía falta) y del `claim`, se audita `OVERRIDE_CONVERSATION_ASSIGNMENT` con `entity_name = "conversation_link"`, `entity_id` = id del vínculo, `old_values = {assigned_user_id: anterior}` y `new_values = {assigned_user_id: nuevo}`.

> **Decisión de diseño D9.** No se agregan acciones de auditoría. Tomar y devolver comunes no se auditan (el vínculo ya guarda al asignado); toda intervención de un `SUPERADMIN` sobre la asignación de otro, sea tomar o devolver, usa `OVERRIDE_CONVERSATION_ASSIGNMENT`. *Por qué:* las dos acciones del módulo ya existen en el vocabulario y en el `CHECK`; evita una migración de `audit_logs`. Si la auditoría falla después de actualizar Chatwoot, la petición responde `500` y la asignación queda hecha (limitación conocida, se registra el error).

### 6.7 Reintentar

> **Decisión de diseño D6.** «Reintentar» reencola **la misma fila** del *outbox* con un endpoint nuevo, `POST /conversations/{id}/messages/{outbox_id}/retry`, que usa `RetryMessage`. *Por qué:* un `POST` nuevo exigiría reenviar el contenido (que la interfaz no tiene de un mensaje rechazado por Meta) y crearía filas duplicadas. RF-31 (paso 6) describía el reintento como un envío nuevo; esta especificación lo refina.

1. Precondiciones de 6.4 (tomada por el usuario).
2. Solo reintentable si la fila tiene `status = FAILED` (envío agotado) o `delivery_status = FAILED` (rechazo de WhatsApp) y conserva su *payload* (`outbox_message.py:231-247`). Si no, `409 invalid-outbox-state`.
3. Si la ventana está cerrada: `422 service-window-closed`.
4. `RetryMessage` reinicia intentos, copia el id externo actual a la columna nueva `outbox_messages.retried_external_message_id` y luego lo limpia; el despachador crea un mensaje nuevo en Chatwoot. El mensaje fallido original queda en el hilo, sin botón, y conserva su autor porque la búsqueda de autoría (D3) compara contra ambas columnas (D24).
5. Audita `SEND_CONVERSATION_MESSAGE` con `new_values.retry_of = outbox_id`. Responde `202`.

> **Decisión de diseño D24.** El reintento conserva el id externo anterior en `retried_external_message_id` (texto, nulo, se suma a la migración de 5.1). *Por qué:* sin él, el mensaje fallido de un encargado se mostraría como «Bot» tras reintentar.

* **Mensajes que nunca llegaron a Chatwoot:** un envío agotado queda `FAILED` en el *outbox* y no existe en el hilo. Por eso `GET /messages` devuelve, solo en la primera página, la lista `unsent` con las filas del destinatario en `PENDING` (estado `QUEUED`) o `FAILED`.

### 6.8 Marcar como leída (`POST /conversations/{id}/read`)

La interfaz lo llama al abrir un hilo `HUMAN` y al recibir mensajes de la conversación abierta. Llama `mark_conversation_read`, publica `conversation.updated` con `unread_count = 0` y responde `204`.

---

## 7. Contrato de API

### 7.1 Resumen

Todos exigen `ENCARGADO` o `SUPERADMIN`; `OPERADOR` recibe `403 forbidden`. Detalle en el módulo 2.14; aquí solo el resumen y los deltas.

| Método y ruta | Roles | Éxito | Estado |
| :--- | :--- | :---: | :--- |
| `GET /conversations` | ENCARGADO, SUPERADMIN | `200` | Extendido (7.2) |
| `GET /conversations/{id}` | ENCARGADO, SUPERADMIN | `200` | **Nuevo** (7.4) |
| `GET /conversations/{id}/messages` | ENCARGADO, SUPERADMIN | `200` | Extendido (7.3) |
| `GET /conversations/{id}/attachments/{attachment_id}` | ENCARGADO, SUPERADMIN | `200` | Sin cambios |
| `POST /conversations/{id}/messages` | ENCARGADO, SUPERADMIN | `202` | Sin cambios |
| `POST /conversations/{id}/messages/{outbox_id}/retry` | ENCARGADO, SUPERADMIN | `202` | **Nuevo** (7.4) |
| `POST /conversations/{id}/takeover` | ENCARGADO, SUPERADMIN | `200` | Sin cambios |
| `POST /conversations/{id}/release` | ENCARGADO, SUPERADMIN | `200` | Sin cambios |
| `POST /conversations/{id}/read` | ENCARGADO, SUPERADMIN | `204` | **Nuevo** (7.4) |
| `GET /conversations/stream` | ENCARGADO, SUPERADMIN | `200` SSE | Sin cambios (sección 8) |

El router declara `/conversations/stream` **antes** que `/conversations/{id}`, para que `stream` no se interprete como identificador.

> **Decisión de diseño D21.** Se agrega `GET /conversations/{id}`, que devuelve el mismo formato que un ítem. *Por qué:* la cabecera del hilo debe poder abrirse por enlace directo o con una conversación fuera de la página cargada (por ejemplo, `resolved`).

### 7.2 Extensión del ítem de `GET /conversations` (y de `conversation.updated`, `takeover` y `release`)

Query nuevos: `q` (texto, mínimo 2 caracteres) y `assigned_user_id` (UUID; un `ENCARGADO` que lo envía recibe `403 forbidden`). Campos nuevos del ítem:

| Campo | Tipo | Nota |
| :--- | :--- | :--- |
| `client.id` | UUID o `null` | Pasa a nulo cuando no hay cliente registrado (D1) |
| `client.name` | texto | Nombre según 4.4 |
| `assigned_user_name` | texto o `null` | Para el *chip* del encargado |
| `unread_count` | entero | Ver D13 |
| `quote_status` | `QuoteStatus` o `null` | Estado de la cotización vinculada |
| `lead_status` | `QUOTING`, `QUOTE_SENT`, `PAYMENT_STARTED`, `CONVERTED`, `QUOTE_CLOSED` | Sección 4.2; nunca nulo |

```json
{
  "chatwoot_conversation_id": 57,
  "client": {"id": "c3d1a7f2-...", "name": "Carlos Ramírez", "phone": "+51999888777"},
  "quote_id": "q9c8a1b2-...",
  "quote_status": "SENT",
  "lead_status": "QUOTE_SENT",
  "status": "open",
  "mode": "HUMAN",
  "assigned_user_id": "b1eebc99-...",
  "assigned_user_name": "María Torres",
  "unread_count": 2,
  "handoff_reason": "CLIENT_REQUEST",
  "handed_off_at": "2026-10-03T16:40:12Z",
  "last_message_preview": "Quisiera cambiar la hora del show",
  "last_message_at": "2026-10-03T16:52:30Z",
  "service_window_open": true,
  "service_window_expires_at": "2026-10-04T16:52:30Z"
}
```

### 7.3 Extensión de `GET /conversations/{id}/messages`

Campos nuevos por mensaje: `author_name` (texto o `null`, solo `AGENT`), `failure_code` (entero o `null`), `outbox_id` (UUID o `null`) y `retryable` (booleano, verdadero si hay fila reintentable, 6.7). `failure_reason` sigue siendo el texto de la sección 9. Con `before` ausente, la respuesta suma `unsent`:

```json
{
  "items": ["..."],
  "has_more": true,
  "unsent": [
    {
      "outbox_id": "ob-91c2...",
      "author_type": "AGENT",
      "author_name": "María Torres",
      "message_type": "TEXT",
      "content": "Claro, con gusto lo reprogramamos.",
      "delivery_status": "FAILED",
      "failure_reason": "La mensajería no estuvo disponible. Reintenta el envío.",
      "retryable": true,
      "created_at": "2026-10-03T16:50:00Z"
    }
  ]
}
```

`delivery_status` de `unsent` es `QUEUED` o `FAILED`. El estado de los mensajes del hilo sale del `status` del mensaje en Chatwoot (`sent`, `delivered`, `read`, `failed` → `SENT`, `DELIVERED`, `READ`, `FAILED`); el *outbox* solo aporta autoría y reintento.

### 7.4 Endpoints nuevos

* **`GET /conversations/{id}`:** `200` con un ítem (7.2). Errores `404 not-found`, `503 messaging-gateway-unavailable`.
* **`POST /conversations/{id}/messages/{outbox_id}/retry`:** cuerpo vacío; `202` con la forma del envío (`QUEUED`). Errores `404 not-found`, `409 conversation-not-taken`, `409 conversation-taken-by-other`, `409 invalid-outbox-state`, `422 service-window-closed`.
* **`POST /conversations/{id}/read`:** cuerpo vacío; `204`. Errores `404 not-found`, `503 messaging-gateway-unavailable`.
* **`POST /conversations/{id}/lead/event-done`:** cuerpo vacío; roles `ENCARGADO` y `SUPERADMIN`; no exige haber tomado la conversación. `200` con el ítem actualizado (7.2) y publica `conversation.updated`. Idempotente si ya está en `EVENT_DONE`. Errores `404 not-found` y `409 invalid-lead-transition` si el `lead_status` no es `CONVERTED` (D25).

La sección 2.14 de la especificación REST y su catálogo de errores se actualizan con estos deltas (sección 18).

---

## 8. Tiempo real (SSE)

> **Decisión de diseño D4.** El puente entre *worker* y API es un canal Redis *pub/sub* único, `eventpro:conversations:events`, con un sobre JSON versionado; cada conexión SSE abre una suscripción. *Por qué:* el *worker* y la API son procesos distintos y Redis ya está desplegado; *pub/sub* no persiste ni reenvía, que es justo la garantía documentada (sin búfer).

* **Puerto `IConversationEventPublisherPort`** con `publish(event)`; adaptador `RedisConversationEventPublisher` y un *fake* en memoria para pruebas. Lo usan el *worker* (sección 6.1), el bot (6.2) y los comandos de la API (6.3 a 6.8). La publicación es de mejor esfuerzo: una falla de Redis se registra y nunca falla el comando ni el trabajo (el estado ya cambió; la interfaz se recupera con el refetch).
* **Sobre:** `{"v": 1, "event": "<nombre>", "data": {...}}`. `event` es uno de `conversation.updated`, `message.created`, `message.updated`, `handoff.requested`; `data` tiene la forma definida en 2.14 (ítem de la bandeja, `{chatwoot_conversation_id, message}` o la carga de derivación), con los campos de 7.2 y 7.3.
* **Endpoint:** `GET /conversations/stream` devuelve `StreamingResponse` con `Content-Type: text/event-stream`, `Cache-Control: no-cache` y `X-Accel-Buffering: no`. Primero emite `retry: 3000`; después, por cada mensaje del canal, `event: <nombre>` y `data: <json>`, y `: keepalive` cada 25 s si no hubo tráfico (`app/infrastructure/adapters/primary/web/sse.py`). El router depende del puerto `IConversationEventSubscriberPort`, cuya suscripción expone `next_event(timeout)` y `close()`.
* **Autenticación:** dependencia nueva que lee `access_token` de la consulta, valida firma y vigencia con `decode_access_token` (`security.py:38`), recarga usuario y rol desde la base como `get_auth_context` (`deps.py:61-84`) y exige `ENCARGADO` o `SUPERADMIN` **antes** de abrir el stream (`401 invalid-credentials`, `403 forbidden`). Es la única ruta que acepta el token fuera de `Authorization`.
* **Cierre:** el generador termina cuando vence el `exp` del token, cuando la petición se desconecta (`request.is_disconnected()`) o cuando Redis falla; el cliente renueva y reconecta (12.4). La desactivación de un usuario surte efecto, como máximo, al vencer su token (60 min).
* **Filtrado por rol:** no hay filtrado por usuario. Ambos roles ven todas las conversaciones (RBAC 2.10, `GET /conversations` sin alcance por asignación), y `handoff.requested` se difunde a todos los conectados. El único filtro es la verificación de rol al conectar.
* **Registro:** la consulta nunca se registra. Uvicorn escribe la línea de petición completa en su registro de acceso (`Dockerfile:59` no lo desactiva), por lo que se arranca con `--no-access-log` (`Dockerfile` y `docker-compose.override.yml`, B4); la aplicación no tiene *middleware* que registre URL ni consulta. El proxy reemplaza `access_token` en su registro y usa `flush_interval -1` (`deploy/Caddyfile`).

---

## 9. Catálogo de motivos de falla

> **Decisión de diseño D5.** Se extrae el código de Meta del texto `external_error` (`(#131030) ...`, `chatwoot_payloads.py:487-492`) con una expresión regular y se traduce con un catálogo fijo en la capa de aplicación; el texto original **nunca** llega al navegador y el código se expone aparte como `failure_code`. *Por qué:* la interfaz no puede mencionar al gateway (US-30) y el texto de Meta cambia sin aviso.
>
> **Ajuste del 2026-10-20 (B2).** El fallo por ventana de 24 h lo produce Chatwoot antes de llegar a Meta: el mensaje queda en `failed` con un `external_error` en español (la ventana de atención al cliente de WhatsApp de 24 horas está cerrada) y **sin** código numérico. Por eso ese caso se identifica por la ausencia de código más ese texto, no por `131047`, que se conserva como respaldo si Meta llegara a rechazarlo.

| Código | Origen | `failure_reason` (español) |
| :--- | :--- | :--- |
| sin código y texto de ventana cerrada (Chatwoot) | Chatwoot rechaza el envío porque la ventana de 24 h está cerrada; es el caso real observado | Han pasado más de 24 horas; el cliente debe escribir primero. |
| `131047` | Respaldo: Meta rechaza un mensaje fuera de la ventana de re-interacción (24 h) | Han pasado más de 24 horas; el cliente debe escribir primero. |
| `131026` | Mensaje no entregable | El cliente no puede recibir el mensaje. Comprueba que su número tenga WhatsApp activo. |
| `131030` | Destinatario fuera de la lista permitida | El número no está entre los destinatarios de prueba. |
| `131031` | Cuenta de WhatsApp Business bloqueada | La cuenta de WhatsApp Business está bloqueada. Contacta al administrador del sistema. |
| `131056` | Límite de envíos al mismo cliente | Se enviaron demasiados mensajes a este cliente. Espera unos minutos. |
| `131049` | Mensaje limitado por WhatsApp | WhatsApp limitó este mensaje. Intenta más tarde. |
| otro, o sin código y sin el texto de ventana | Cualquier fallo | No se pudo entregar el mensaje. |

Para filas del *outbox* que no salieron (`last_error`, sin código de Meta) se traduce por el tipo de excepción que ya guarda el despachador: `ServiceWindowClosedError` → «Han pasado más de 24 horas; el cliente debe escribir primero.»; `MessagingUnavailableError` → «La mensajería no estuvo disponible. Reintenta el envío.»; cualquier otro → «No se pudo enviar el mensaje.» Los códigos y su significado provienen de la referencia de errores de WhatsApp Cloud API; solo `131030` y el caso de la ventana de 24 h sin código están respaldados por capturas propias (spec 05, §4; B2, 2026-10-20). `131026` no se pudo provocar con un número ficticio (falla antes por la ventana) y su fixture está construida y marcada como «no capturada»; el resto de los códigos sigue sin captura.

**Reintentar:** ver 6.7. El botón aparece si `retryable` es verdadero; si la causa es la ventana de 24 h (sin código o `131047`), el API lo rechaza con `service-window-closed` mientras la ventana siga cerrada.

---

## 10. Errores (RFC 7807)

Se reutilizan los tipos del catálogo de la sección 3 de la especificación REST; solo `invalid-outbox-state` e `invalid-lead-transition` son nuevos en el catálogo.

| `type` (sufijo) | Estado | Dónde |
| :--- | :---: | :--- |
| `not-found` | `404` | Conversación, adjunto o fila del *outbox* inexistente o ajena |
| `conversation-not-taken` | `409` | Enviar o reintentar sin conversación tomada; devolver una `open` sin asignar siendo `ENCARGADO` |
| `conversation-taken-by-other` | `409` | Tomar, devolver, enviar o reintentar en una conversación de otro (incluye `assigned_user_id`) |
| `invalid-outbox-state` | `409` | Reintentar una fila que no está fallida o cuyo contenido se anuló |
| `invalid-lead-transition` | `409` | Marcar «Evento realizado» cuando el estado comercial no es `CONVERTED` (D25) |
| `service-window-closed` | `422` | Texto o adjunto con ventana cerrada (incluye `service_window_expires_at`) |
| `validation-error` | `422` | Cuerpo vacío, `q` de menos de 2 caracteres, archivo inválido |
| `forbidden` | `403` | `OPERADOR`, o `assigned_user_id` enviado por un `ENCARGADO` |
| `messaging-gateway-unavailable` | `503` | Chatwoot no responde en una operación síncrona |
| `event-queue-unavailable` | `503` | Redis no disponible al abrir el stream |

> **Decisión de diseño D10.** `MessagingUnavailableError` (código interno `messaging-unavailable`, `messaging_exceptions.py:12`) se traduce a `503 messaging-gateway-unavailable` en el router de conversaciones, con un detalle fijo («La mensajería no está disponible temporalmente.»), y `ResourceNotFoundError` de Chatwoot a `404 not-found`. *Por qué:* el nombre público del tipo difiere del interno, y un manejador global alteraría a otros módulos; ni el detalle ni los registros devueltos al navegador mencionan a Chatwoot.

---

## 11. Seguridad y RBAC

* Todos los endpoints exigen `ENCARGADO` o `SUPERADMIN` con `require_role` (`deps.py:26-50`); el rol se lee de la base en cada petición.
* El navegador nunca recibe URL, tokens ni textos de error de Chatwoot (RN de aislamiento de binarios, RBAC regla 5).
* **Proxy de adjuntos (D17):** Chatwoot no ofrece lectura de un adjunto por id; el caso de uso recorre los mensajes de la conversación (con el mismo tope de páginas) para hallar el adjunto y su `data_url`, y valida que pertenezca a esa conversación. La URL se reescribe al host interno de Chatwoot y solo se descarga si coincide con `CHATWOOT_BASE_URL`; cualquier otra se rechaza (anti-SSRF). Verificado el 2026-10-20 (B2): `data_url` usa el anfitrión público y redirige (302) al archivo con un identificador firmado sin vencimiento; desde el contenedor del API se descarga con el anfitrión interno más los encabezados `Host` y `X-Forwarded-Proto` originales, siguiendo redirecciones. El adaptador lo implementa así: solo sigue redirecciones relativas o hacia el anfitrión interno o el público (reescrito al interno), con un máximo de 3, sin enviar el token, y rechaza cualquier otro destino con `ResourceNotFoundError`.
* `handoff_summary` y la auditoría no contienen texto libre del cliente ni de los mensajes.
* El `access_token` en la consulta del stream no se registra (sección 8) y se reutiliza el mismo token de 60 minutos.
* La publicación Redis viaja por la red interna de Docker; el contenido de los mensajes no se persiste en Redis.

---

## 12. Frontend (slice 2)

Repositorio hermano `../frontend` (Next.js 16, React 19, Tailwind 4, FSD). `AGENTS.md` exige leer la guía de `node_modules/next/dist/docs/` antes de escribir código: Next 16 tiene cambios incompatibles con versiones previas. La captura visual de referencia (tema oscuro tipo WhatsApp Web) es solo una guía.

### 12.1 *Slices* (alineados con la sección 4.3 de la spec 03)

| Slice | Capa | Contenido nuevo respecto de la spec 03 |
| :--- | :--- | :--- |
| `entities/conversation` | entities | Tipos del ítem (7.2), consultas, `ConversationRow`, badges de modo, motivo, **estado comercial**, **no leídos** y *chip* del encargado, indicador de ventana |
| `entities/message` | entities | Tipos (7.3), consulta por cursor, burbuja por autor (etiqueta «Bot» en las del bot, nombre en las de encargado), marcas de entrega, motivo de falla, carga de adjuntos como `blob:` |
| `features/conversation-takeover` | features | «Tomar», «Devolver al bot» y confirmación de reasignación (`SUPERADMIN`) |
| `features/send-message` | features | Compositor, `QUEUED`, «Reintentar» (`POST .../retry`, no un envío nuevo) |
| `features/conversation-stream` | features | `EventSource`, aplicación de eventos al caché, renovación y reconexión |
| `widgets/conversation-inbox` | widgets | Lista con búsqueda, filtros y aviso de derivaciones |
| `widgets/conversation-thread` | widgets | Cabecera, hilo, `unsent`, compositor |
| `pages/conversations` | pages | Orquesta ambos widgets y el stream; guardia de rol |

Se mantienen las reglas de importación de la spec 03: las *features* no se importan entre sí y los widgets las componen.

### 12.2 Disposición (escritorio primero)

* **Panel izquierdo** (lista): campo de búsqueda; filtros «Todas», «Sin asignar», «Mías», «Bot» y, solo para `SUPERADMIN`, un selector de encargado; interruptor «Incluir resueltas». Cada fila: avatar con iniciales, nombre, hora relativa del último mensaje, vista previa de una línea, *chip* del responsable («Bot», «Sin asignar» o el nombre del encargado), insignia de no leídos y badge del estado comercial.
* **Panel derecho** (hilo): cabecera con nombre, teléfono, badge del estado comercial, modo y estado de la ventana de 24 h, y los botones «Tomar», «Devolver al bot» o «Reasignarme» según rol y estado. Cuerpo con separadores por día y burbujas: cliente a la izquierda; bot y encargado a la derecha, el bot con etiqueta «Bot» y el encargado con su nombre. Las burbujas salientes llevan marcas de entrega (una `SENT`, dos `DELIVERED`, dos resaltadas `READ`, aviso rojo `FAILED`). Abajo, el compositor.
* **Colores de los badges del estado comercial:** a criterio de quien implemente, con contraste suficiente y sin depender solo del color (la etiqueta siempre está en texto).
* **Pantallas angostas:** un solo panel con navegación de regreso (la spec 03 pide diseño responsivo).
* **Accesibilidad:** `Enter` envía y `Shift+Enter` agrega salto; los avisos de derivación usan una región `aria-live`.

### 12.3 Estados

| Estado | Comportamiento |
| :--- | :--- |
| Cargando | Esqueletos en lista e hilo; el compositor deshabilitado |
| Vacío | «No hay conversaciones» sin filtros; «Sin resultados para los filtros» con filtros, con acción «Limpiar» |
| Error genérico | Mensaje con «Reintentar» que repite la consulta |
| Chatwoot caído (`503 messaging-gateway-unavailable`) | Aviso «La mensajería no está disponible temporalmente», sin mencionar al gateway; la lista conserva lo último cargado y el compositor se deshabilita |
| Sin tomar | El compositor muestra «Toma la conversación para responder» y el botón «Tomar» (`conversation-not-taken`); asignada a otro, el nombre del responsable |
| Ventana cerrada | Compositor deshabilitado con el aviso «Han pasado más de 24 h; el cliente debe escribir primero» |
| Stream caído | Indicador discreto «Reconectando...»; al volver, refetch |

### 12.4 Reconexión y sesión

1. `EventSource` se abre con `?access_token=` solo si el token vigente tiene más de 2 minutos de vida; si no, primero renueva con `POST /auth/refresh`.
2. Se programa una reconexión proactiva 60 segundos antes del `exp` del token.
3. `EventSource` no expone el código HTTP: ante `error` con `readyState = CLOSED` se cierra la conexión, se renueva la sesión y se reabre con espera creciente (1 a 30 s, con variación aleatoria).
4. Al `open` posterior a una caída se invalida la consulta de la bandeja y la primera página del hilo abierto (no hay búfer).
5. Hoy el frontend no guarda el *refresh token* ni renueva (`auth-storage.ts`, `client.ts`): es un requisito previo del slice (tarea F0).

> **Decisión de diseño D20 (acordada con el responsable del producto, 2026-10-20).** Sin plantillas en esta versión: con la ventana de 24 h cerrada el compositor queda deshabilitado con el aviso «Han pasado más de 24 h; el cliente debe escribir primero». *Por qué:* no hay plantillas propias aprobadas por Meta (la verificación sigue pendiente y el número de prueba solo trae `hello_world`, en inglés). Las plantillas se suman cuando Meta apruebe alguna.

---

## 13. Plan de entrega

Todo el trabajo va en `feat/e1-conversation-inbox`, con commits por unidad de trabajo, pruebas y documentación junto al comportamiento. **Comprobaciones del backend** (como en `.github/workflows/ci.yml:43-52`): `ruff check .`, `ruff format --check .`, `mypy app`, `pytest -q --cov=app --cov-fail-under=75`; las pruebas de integración (`-m integration`) requieren Docker.

### 13.1 Slice 1: backend

| ID | Entrega | Criterios de aceptación |
| :--- | :--- | :--- |
| B1 | Migración (`client_id` nulo, `last_client_message_at`, `author_user_id`); entidad, modelo, mapper y repositorio de `conversation_links`; autor en `OutboxMessage`, `EnqueueMessage` y repositorio | `ensure` es idempotente bajo concurrencia; `claim` gana una sola vez; `author_user_id` viaja ida y vuelta; un solo `head` de Alembic. Pruebas de dominio y de integración |
| B2 | `IMessagingPort` ampliado (5.4), adaptador, `FakeMessagingAdapter` y suite de contrato; **capturas reales** nuevas | La misma suite pasa contra *fake* y adaptador; fixtures nuevas saneadas con: remitente del Agent Bot, conversación con mensajes (vista previa), adjunto, fallos `131047`/`131026`, `update_last_seen`, reapertura de una `resolved`; `test_chatwoot_fixtures.py` en verde |
| B3 | Eventos del gateway: parser de mensajes, vínculo, `UNKNOWN_MESSAGE` para ecos sin fila, `message.updated` tras la entrega; catálogo de fallas (sección 9) | Un entrante en `open` publica eventos y no responde el bot; un eco saliente con fila publica `author_type` correcto; el catálogo cubre cada código y el respaldo |
| B4 | Publicador Redis, endpoint `stream`, autenticación por consulta, `--no-access-log` | Rechaza `401`/`403` antes de abrir; latido a los 25 s; cierra al vencer el token; la consulta no aparece en los registros; la publicación fallida no rompe el trabajo |
| B5 | Casos de uso de lectura (`ListConversations`, `GetConversation`, `ListMessages` con `unsent`, `MarkRead`), `IInboxLookupPort`, estado comercial, router y mapeo `503`/`404` | Filtros `mode`, `assigned`, `assigned_user_id`, `q`, `include_resolved`; `OPERADOR` recibe `403`; `lead_status` según la tabla 4.2; Chatwoot caído responde `503` con el tipo correcto |
| B5b | Etapa `EVENT_DONE` (D25): cálculo desde el evento `SETTLED`, endpoint manual `lead/event-done` y reinicio del ciclo en el *worker* | Marca manual solo desde `CONVERTED` (`409 invalid-lead-transition` en otro caso) e idempotente; evento `SETTLED` da `EVENT_DONE` sin marca; un mensaje entrante en `EVENT_DONE` deja `QUOTING` y desvincula la cotización sin borrarla |
| B6 | `Takeover` y `Release` con `claim`/compensación, reapertura de `resolved`, auditoría de intervención | Dos `takeover` simultáneos: solo uno gana; fallo de Chatwoot restituye la asignación; `SUPERADMIN` audita `OVERRIDE_CONVERSATION_ASSIGNMENT` con el anterior; idempotencia de ambos |
| B7 | `SendMessage` (texto y documento, sin plantillas) y endpoint de reintento | `202 QUEUED`; `409`/`422` según 6.4 y 6.7; fila con `author_user_id`; auditoría sin contenido; el reintento reutiliza la fila |
| B8 | Derivación del bot persistente y vínculo de cotización en ambos motores | Los tres disparadores y `BOT_ERROR` dejan motivo, resumen estructurado e instante; `handoff.requested` se emite; el vínculo con la cotización se confirma con ella; falla de Chatwoot no registra derivación |
| B9 | Proxy de adjuntos y envío multipart (D17, D19) | Valida pertenencia y anfitrión; `invalid-file` para tipo o tamaño inválidos; se descarga un adjunto real de prueba |
| B10 | Sincronización de documentos (sección 18) y verificación manual (sección 14) | REST y datos actualizados; checklist ejecutado con el número de prueba |

Orden sugerido: B1, B2, luego B3 y B5 en paralelo lógico, B4, B6, B7, B8, B9, B10. El slice 1 se cierra con el contrato de API y la suite de contrato del puerto en verde.

### 13.2 Slice 2: frontend

**Comprobaciones:** `npm run lint` y `npm run build` (el proyecto no tiene *runner* de pruebas; agregar uno queda fuera de este slice) más la verificación manual de la sección 14.

| ID | Entrega | Criterios de aceptación |
| :--- | :--- | :--- |
| F0 | Previos: leer la guía de Next 16; agregar TanStack Query (spec 03); guardar *refresh token* y exponer `refreshSession` en `shared/api` | Sesión renovable sin cerrar sesión; `lint` y `build` en verde |
| F1 | `entities/conversation` y `entities/message` | Tipos iguales a 7.2 y 7.3; consulta por cursor; adjuntos como `blob:` por el cliente con JWT |
| F2 | `features/conversation-stream` | Aplica los cuatro eventos al caché; reconecta y refresca según 12.4 |
| F3 | `widgets/conversation-inbox` | Búsqueda, filtros, selector de encargado solo `SUPERADMIN`, filas con no leídos, *chip* y estado comercial, aviso de derivación |
| F4 | `widgets/conversation-thread`, `features/conversation-takeover`, `features/send-message` | Autoría visible; marcas de entrega; `unsent` y «Reintentar»; compositor según ventana y asignación; marca de leída al abrir |
| F5 | `pages/conversations` con guardia de rol y los estados de 12.3 | `OPERADOR` no ve la página; cada estado reproducible; Chatwoot caído muestra el aviso sin detalles |
| F6 | Verificación manual de extremo a extremo | Checklist de la sección 14 completa |

---

## 14. Verificación manual (número de prueba de Meta)

Con Chatwoot, API, *worker* y el frontend levantados, un encargado y un `SUPERADMIN` con sesión, y el teléfono de prueba:

1. El cliente escribe: aparece la conversación (modo `BOT`), con vista previa y no leídos; el estado comercial es «Cotizando».
2. El cliente completa una cotización con el bot: el estado pasa a «Cotización enviada»; pulsa «Pagar adelanto»: «Pago iniciado».
3. El cliente pide un encargado: llega el aviso de derivación en tiempo real, con motivo; la fila queda «Sin asignar».
4. El encargado abre el hilo: el contador se reinicia y se distinguen las burbujas del cliente, el bot («Bot») y la propia.
5. Intenta escribir sin tomar: la interfaz ofrece «Tomar». Toma y responde: llega a WhatsApp con las marcas `SENT`, `DELIVERED` y `READ`.
6. Un segundo usuario `ENCARGADO` intenta tomarla: recibe el conflicto. El `SUPERADMIN` la reasigna y queda el registro `OVERRIDE_CONVERSATION_ASSIGNMENT`.
7. Envía una imagen y un PDF; el cliente envía una imagen: se ve por el proxy, sin URL de Chatwoot en la red del navegador.
8. Se espera a que la ventana cierre (o se simula): el compositor se deshabilita con el aviso de las 24 h.
9. Se escribe a un número no verificado: el mensaje queda `FAILED` con motivo en español y `failure_code`; «Reintentar» reutiliza la fila.
10. Con Chatwoot detenido: la bandeja muestra el aviso de mensajería no disponible; un envío en curso queda en `unsent` y se entrega al volver.
11. Se corta la conexión del stream (reiniciar la API): el indicador aparece y, al volver, la lista se refresca; con el token por vencer se renueva solo.
12. Devolver al bot: el bot responde desde el saludo y la fila vuelve a `BOT`.
13. Un `OPERADOR` recibe `403` en la API y no ve la página.
14. En los registros de la API no aparece `access_token=`.

---

## 15. Verificaciones (resultados de las capturas de B2)

Las capturas se tomaron el 2026-10-20 con el responsable del producto, a través de SSH a la VM de Oracle, contra la API interna de Chatwoot v4.18.0 (cuenta 2). Las fixtures saneadas están en `tests/fixtures/chatwoot/` y su procedencia, en el `README.md` de ese directorio.

| # | Verificación | Resultado |
| :--- | :--- | :--- |
| 1 | `sender.type` del Agent Bot (D3) | **Verificado en la API.** Agent Bot: `message_type: 1` y `sender.type: "agent_bot"`; cliente: `message_type: 0` y `sender.type: "contact"`; actividad: `message_type: 2` y sin `sender`. El *payload* de webhook del Agent Bot **no** se capturó |
| 2 | `update_last_seen` (D13) | **Verificado.** `POST /conversations/{id}/update_last_seen` con el token de agente: `unread_count` pasa de 10 a 0. No hace falta la contingencia |
| 3 | Adjuntos y alcance de `data_url` (D17) | **Verificado.** `attachments[]` trae `file_type`, `extension`, `content_type`, `file_size`, `width`, `height`, `data_url` y `thumb_url`; `data_url` redirige (302) y se descarga desde el contenedor del API con el anfitrión interno más `Host` y `X-Forwarded-Proto`: 200 `image/jpeg`. La URL pública funciona sin autenticación (identificador firmado sin vencimiento) |
| 4 | `last_non_activity_message` poblado | **Verificado** en conversaciones reales |
| 5 | Reapertura de una `resolved` | **Verificado.** Al escribir el cliente, la conversación pasa a `pending` y responde el bot (premisa de D8) |
| 6 | Formato de `external_error` para códigos distintos de `131030` | **Cambió.** El fallo por la ventana de 24 h lo produce Chatwoot antes de Meta: `status: "failed"` y `external_error` en español **sin** código numérico. `131026` no se pudo provocar (un número ficticio falla antes por la ventana): su fixture está construida desde el formato de `131030` y marcada como «no capturada». El catálogo de la sección 9 se ajustó |
| 7 | Reglas de resolución automática | **Verificado.** No hay reglas de automatización y `auto_resolve_after` es nulo |
| 8 | `flush_interval -1` en Caddy para el stream y claim `exp` en el JWT (`security.py:26-38`) | **Resuelto en B4.** `deploy/Caddyfile` aplica `flush_interval -1` al proxy de la API y reemplaza `access_token` en su registro; el JWT siempre lleva `exp` (60 min) y el stream rechaza con `401` un token sin él. Queda por confirmar en la VM, con el stream real, que el proxy entrega cada evento sin retraso (sección 14) |
| 9 | `can_reply` equivale a la ventana de 24 h del último mensaje entrante | Pendiente: ya presente en las fixtures; falta confirmar el borde |

**Fuera de alcance de las capturas:** el *payload* de webhook del Agent Bot y el borde de `can_reply` quedan sin verificar; `131047` exige esperar más de 24 h y se cubre con el caso real sin código.

**Contingencias previstas (descartadas por las verificaciones 2 y 3, que salieron bien):**
* **Punto 2 (`update_last_seen`)** — si no reinicia `unread_count`, el contador se calcula en EventPro: columna `conversation_links.last_read_at` y conteo de mensajes entrantes posteriores en la primera página de mensajes. Cambia la migración, el caso de uso 6.8 y el ítem de la bandeja; el contrato de API no cambia.
* **Punto 3 (`data_url`)** — si no es alcanzable desde la red interna aun reescribiendo el host, se descarga con el token de agente en la cabecera `api_access_token`; si tampoco funciona, el hilo muestra «Adjunto no disponible» con nombre y tipo, y la vista de adjuntos entrantes pasa a seguimiento.

**Límites conocidos:** el evento `conversation.updated` de la marca manual «Evento realizado» se publica antes de confirmar la transacción (si la confirmación falla, la interfaz se corrige en la siguiente consulta); tope de 500 conversaciones leídas; contador de no leídos compartido; sin reenvío de eventos perdidos; si Chatwoot falla durante la derivación, la reconciliación pendiente es quien corrige; la auditoría de una intervención puede fallar tras el cambio de Chatwoot.

---

## 16. Preguntas abiertas

1. ~~**Plantillas aprobadas.**~~ Resuelta el 2026-10-20: sin plantillas en esta versión (D20).
2. ~~**Contador compartido de no leídos.**~~ Resuelta el 2026-10-20: el contador compartido es aceptable por ahora (D13); un contador por encargado queda como seguimiento.
3. ~~**Cierre de conversaciones.**~~ Resuelta el 2026-10-20: no hay cierre ni archivo; basta el filtro y la búsqueda, y el ciclo comercial se reinicia al volver el cliente (D25).

---

## 17. Decisiones de diseño (índice)

D1 vínculo por *upsert* sin crear clientes; D2 derivación persistente y mapa de motivos; D3 autoría por *outbox*; D4 puente Redis *pub/sub*; D5 catálogo de fallas; D6 reintento sobre la misma fila; D7 estados del API; D8 tomar reabre `resolved`; D9 auditoría sin acciones nuevas; D10 `503` acotado al router; D11 CAS y compensación; D12 bandeja en memoria; D13 no leídos de Chatwoot; D14 estado comercial derivado; D15 `last_client_message_at`; D16 cursor por id; D17 proxy de adjuntos; D18 devolver sin asignado; D19 adjuntos con almacenamiento de evidencias; D20 sin plantillas; D21 `GET /conversations/{id}`; D22 suscripción de webhook sin cambios; D23 tomar limpia la sesión del bot; D24 autoría conservada tras reintentar; D25 etapa `EVENT_DONE` (calculada y manual) y reinicio del ciclo al volver el cliente.

---

## 18. Impacto en la documentación

| Documento | Cambio |
| :--- | :--- |
| `04-api/01-especificacion-endpoints-rest.md` | Módulo 2.14: parámetros `q` y `assigned_user_id`; campos de 7.2 y 7.3; endpoints `GET /conversations/{id}`, `.../retry`, `.../read` y `.../lead/event-done`; filas `invalid-outbox-state` e `invalid-lead-transition` en el catálogo (se hace en este cambio) |
| `02-arquitectura/05-spec-chatwoot-gateway.md` | Estado de bot y bandeja, eventos procesados y autoría de los mensajes (se hace en este cambio); enlace a esta especificación |
| `03-datos/02-diccionario-de-datos.md` | `conversation_links.client_id` nulo y `last_client_message_at`; `outbox_messages.author_user_id` |
| `01-requisitos/04-reglas-de-negocio-y-control.md` | Tabla 3.5: bloque «Estado comercial de la conversación» con los cinco valores de 4.2 |
| `01-requisitos/02-requerimientos-funcionales.md` | RF-31 paso 6: el reintento reencola la fila (no un `POST` nuevo); RF-31: búsqueda, no leídos y estado comercial |
| `01-requisitos/05-historias-de-usuario.md` | US-30: búsqueda, no leídos, filtro por encargado y estado comercial |
| `02-arquitectura/03-frontend-arquitectura-fsd.md` | Slices de 12.1 y reintento por `retry` |
| `Docs/README.md` | Índice con esta especificación |
