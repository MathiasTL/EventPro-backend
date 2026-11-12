# Especificación 10 — E1: link de pago del adelanto con Mercado Pago

> **Estado:** diseño acordado el 2026-11-10, pendiente de revisión; revisado contra el código el 2026-11-11; decisiones D3/D4 actualizadas. **Responsable:** Mathias (E1). **Coordinación:** Christian (E5, pagos), Diego (E2, contrato) y el dueño del módulo de eventos.

## 1. Intención

Hoy el adelanto se paga por Yape, Plin o transferencia y el cliente envía una captura que un encargado valida a mano. Una captura se puede falsificar y la validación depende de que alguien revise su Yape o su banco.

Con este cambio, apenas se crea la cotización el bot envía un **link de pago de Mercado Pago (Checkout Pro)** por el monto exacto del adelanto. Mercado Pago avisa al backend cuando el pago se aprueba (o el backend lo detecta por consulta periódica), el backend lo confirma consultando el pago y el flujo continúa solo hasta el contrato. El cliente no envía nada. Yape y transferencia siguen disponibles como alternativa con validación humana.

El equipo aceptó el cambio de alcance. Se trata de un proyecto académico: todo funciona en **modo de prueba**, sin dinero real.

## 2. Objetivos, no objetivos y antiobjetivos

**Objetivos**

- El link se envía automáticamente junto con el resumen de la cotización (US-07), sin que el cliente lo pida.
- Un pago aprobado por Mercado Pago se reconoce sin intervención humana cuando hay cupo.
- El cliente nunca queda sin respuesta: si el aviso de Mercado Pago no llega, el bot puede comprobar el pago cuando el cliente escribe "ya pagué".
- La empresa no cobra un horario que no puede cumplir: la disponibilidad se protege **antes** del pago.
- La demo funciona de punta a punta con credenciales y tarjetas de prueba.

**No objetivos**

- Link de pago para el saldo. El saldo sigue cobrándose en el lugar el día del evento (RN-03, concepto `BALANCE`). Puede agregarse después con el mismo diseño.
- Comprobantes electrónicos SUNAT.
- Otras pasarelas (Culqi, Niubiz, Izipay). Se evaluaron y se descartaron (sección 11).
- Aceptar pagos sobre cotizaciones vencidas (D4).

**Antiobjetivos** (sería un fracaso aunque funcione técnicamente)

- Que un cliente pague y la empresa le devuelva el dinero por falta de cupo como camino normal. La política del negocio es cumplir con quien pagó.
- Que el encargado tenga que escribir datos técnicos (por ejemplo, un UUID de evento) para aprobar un pago.
- Que un pago se marque como aprobado solo por el contenido del aviso, sin consultarlo en Mercado Pago.
- Que el cliente quede esperando sin saber qué pasa con su pago.

## 3. Decisiones acordadas

| # | Decisión |
| :--- | :--- |
| D1 | Pasarela: **Mercado Pago Checkout Pro**, un link (preferencia) por cotización, por el monto del adelanto (10 % de los servicios, RN-02; la movilidad no se incluye). |
| D2 | El link se envía automáticamente en el mismo turno en que se crea la cotización. El mensaje indica que el link paga el adelanto y que con él se agenda el evento. |
| D3 | **Vigencia del link** (actualizada el 2026-11-11): vence en lo que ocurra primero entre el vencimiento de la cotización (`expires_at`) y 24 horas antes del inicio del evento. La cotización conserva su vigencia de 24 horas (RN-09.1), por lo que el link dura como máximo 24 horas. Si la vigencia calculada deja menos de 1 hora, no se crea link (sección 9.1). Las horas se calculan en America/Lima y `expiration_date_to` se envía en ISO 8601 con desfase horario. |
| D4 | **Cotización vencida, link vencido** (actualizada el 2026-11-11): si la cotización venció, el link también. No hay aceptación de pagos tardíos ni transición `EXPIRED` → `CONVERTED`. Si el cliente vuelve después del vencimiento y quiere pagar, el bot crea una cotización nueva (sección 4.7). Protección contra el cron: sección 4.8. |
| D5 | **Competencia por el horario (opción B):** cuando un pago confirma un horario, el sistema vence los links de otras cotizaciones que pasarían a `CONFLICT` y el bot avisa a esos clientes con alternativas. No se reserva cupo antes del pago (RN-09.2 se mantiene). |
| D6 | Los links de cotizaciones que pasarían a **sobrecupo** (`REQUIRES_MANUAL_APPROVAL`, cuarto show simultáneo) quedan abiertos. Si se pagan, el encargado aprueba el sobrecupo. Es un **punto de control con intervención humana** (sección 7). |
| D7 | Yape, Plin y transferencia siguen disponibles a pedido del cliente. Ese camino requiere que un encargado confirme el pago en el panel. |
| D8 | Cuando el cliente dice que pagó o envía una captura, el encargado recibe un aviso inmediato para validarlo lo antes posible. |
| D9 | Aprobar un pago (automático o manual) crea el evento a partir de la cotización. El encargado solo aprueba o rechaza; no ingresa `event_id`. |
| D10 | Tras la aprobación, el bot dice "Pago aprobado. En breve te enviaremos tu contrato." y continúa el flujo de contrato existente (E2). |

## 4. Flujos

### 4.1 Pago con link (camino principal)

1. El agente crea la cotización (`CreateQuote`, que ya valida disponibilidad).
2. En la misma operación, el backend crea la preferencia en Mercado Pago con: monto del adelanto en PEN, descripción, `external_reference` = id de la cotización, `notification_url` pública, `expires = true` y `expiration_date_to` según D3. Guarda el id de la preferencia, la URL y la fecha de vencimiento del link asociados a la cotización. Al enviar el link, la cotización pasa a `PAYMENT_STARTED` directamente (sección 9.1).
3. El bot envía el resumen US-07 (texto determinista existente) y, a continuación, el mensaje con el link (sección 5). Los dos caminos de creación de cotización del bot generan el link (sección 9).
4. El cliente paga en la página de Mercado Pago.
5. El backend se entera del pago por una de tres entradas: notificación de Mercado Pago, consulta periódica (4.2) o comprobación "ya pagué" (4.2). Las tres invocan el **mismo caso de uso** `ProcessMercadoPagoPayment(mp_payment_id)` (sección 4.9). Este consulta `GET /v1/payments/{id}` y valida: estado `approved`, `transaction_amount` igual al monto del adelanto de la cotización, `currency_id` = `PEN`, `external_reference` igual al id de la cotización y `date_approved` dentro de la vigencia del link (sección 4.8). Ante cualquier discrepancia, el pago pasa a aprobación manual, no se crea evento y se avisa al encargado.
6. Bajo el bloqueo de disponibilidad (RN-09.6), revalida el cupo:
   - `AVAILABLE`: el pago queda `VERIFIED` (verificado por el sistema), se crea el evento, la cotización pasa a `CONVERTED` y se ejecuta la sección 4.6.
   - `REQUIRES_MANUAL_APPROVAL`: el pago queda en aprobación manual, se avisa al encargado y el bot envía el mensaje de "confirmando tu fecha" (sección 5).
   - `CONFLICT`: igual que el caso anterior, pero el aviso al encargado indica conflicto (sección 7).

### 4.2 Detección del pago: consulta periódica y "ya pagué"

1. El cliente escribe que pagó y el sistema aún no tiene el pago registrado.
2. El bot busca en Mercado Pago pagos con `external_reference` = id de la cotización.
3. Si hay un pago aprobado, se procesa con `ProcessMercadoPagoPayment` igual que en 4.1 paso 5.
4. Si no hay pago, el bot responde que todavía no se refleja y que lo intente de nuevo en unos minutos, o que envíe la captura si pagó por Yape o transferencia. Si el cliente insiste, se deriva a un encargado (US-27).

Además, una tarea periódica consulta los pagos de las cotizaciones con link vigente, por si se pierde una notificación. Es imprescindible en modo de prueba, donde Mercado Pago no envía notificaciones (sección 8). Se sugiere un intervalo de 1 minuto (ajustable por el constructor, sección 10).

### 4.3 Pago por Yape, Plin o transferencia (camino manual)

1. El mensaje del link incluye una línea: si prefiere Yape o transferencia, que lo indique.
2. El bot envía los datos de pago existentes (`PaymentInstructionsDTO`).
3. Cuando el cliente envía la captura, el bot registra el pago del adelanto con la imagen como evidencia (`RegisterAdvancePayment`), en `PENDING_VERIFICATION` (o `REQUIRES_MANUAL_APPROVAL` si la revalidación temprana de RN-09.5 detecta falta de cupo). El bot responde que el comprobante se recibió y que un encargado lo validará. Hoy el bot no invoca `RegisterAdvancePayment` y las imágenes llegan como `ATTACHMENT_PLACEHOLDER` (`agent_engine.py`): el manejo de la captura es trabajo nuevo (sección 9).
4. Si el cliente escribe "ya pagué" sin captura, primero se aplica 4.2. Si no hay pago en Mercado Pago, el bot le pide la captura.
5. El encargado recibe el aviso (sección 4.5), revisa la captura contra su Yape o banco y pulsa **Aprobar** o **Rechazar** (con motivo).
6. Aprobar ejecuta el mismo cierre que 4.1 paso 6. Rechazar hace que el bot informe el motivo y vuelva a ofrecer el link si sigue vigente. Un rechazo manual no reabre una cotización vencida.

### 4.4 Competencia por el horario (D5 y D6)

Cuando un pago queda `VERIFIED` y se crea el evento:

1. Se buscan cotizaciones con link vigente cuyo intervalo se superpone con el del nuevo evento.
2. Para cada una se evalúa la disponibilidad con el evento ya contado:
   - `CONFLICT`: se vence el link en Mercado Pago (actualizar la preferencia con `expiration_date_to` = ahora), se marca como anulado y el bot avisa al cliente que el horario ya no está disponible y le ofrece otra fecha o un encargado.
   - `REQUIRES_MANUAL_APPROVAL`: el link queda abierto (D6).
   - `AVAILABLE`: no se hace nada.

Vencer la preferencia es una llamada externa posterior a la confirmación de la base de datos y es de mejor esfuerzo. Entre el commit y la actualización en Mercado Pago, otro cliente puede pagar: ese pago cae en 4.1 paso 6 con `CONFLICT` y lo resuelve el encargado (sección 7). El camino `CONFLICT` cubre ese margen, que puede ser de segundos o más si Mercado Pago falla.

### 4.5 Avisos al encargado

Se avisa en tiempo real en el panel y con un indicador persistente, para que no se pierda si nadie estaba conectado. El canal SSE actual solo transporta eventos de conversación: `ConversationEventType` es un enum cerrado (`conversation_event_dto.py`). Hace falta un tipo de evento nuevo para pagos y un suscriptor en el frontend (sección 9). El indicador persistente necesita una consulta de pagos pendientes de validar, porque `panel-sobrecupo` hoy solo lista `REQUIRES_MANUAL_APPROVAL`. Casos:

- El cliente envió una captura o dijo que pagó y no hay pago de Mercado Pago.
- Un pago quedó en aprobación manual por sobrecupo.
- Un pago quedó en aprobación manual por conflicto.
- Un pago quedó en aprobación manual por discrepancia de monto, moneda o referencia (4.1 paso 5).
- Un pago duplicado quedó en `REFUND_PENDING` (sección 9.1).
- Falló la generación o el envío del contrato tras un pago aprobado.
- No se pudo crear el link de pago (sección 9.1) o la vigencia dejó menos de 1 hora.

### 4.6 Cierre tras la aprobación

1. El bot envía "Pago aprobado. En breve te enviaremos tu contrato."
2. Se emite el contrato con el flujo existente (`issue_for_event`, E2), que envía el enlace de firma y luego el PDF firmado. La emisión la dispara el caso de uso nuevo de creación de evento desde la cotización (sección 9.1), no `ConfirmManualBookingUseCase`.
3. No hay espera fija: el contrato se envía apenas está listo. Si falla, se avisa al encargado (4.5).

### 4.7 El cliente vuelve después del vencimiento

No se genera un link nuevo sobre la cotización vencida. Si el cliente quiere pagar, el bot crea una **cotización nueva**: revalida disponibilidad y precio, y esa cotización lleva su propio link (4.1). La cotización vencida queda `EXPIRED` sin cambios.

### 4.8 Protección contra el vencimiento de la cotización

Un pago aprobado por Mercado Pago dentro de la vigencia del link debe aceptarse aunque se detecte después del vencimiento de la cotización. En modo de prueba no hay notificaciones: la detección es por consulta periódica o por "ya pagué".

- La tarea `expire_due_quotes` no vence una cotización con link activo hasta `expires_at` + margen. El margen es de al menos el intervalo de consulta; se sugiere consulta cada 1 minuto y margen de 5 minutos (ajustables, sección 10).
- La validez del pago se decide con `date_approved` de Mercado Pago: debe ser menor o igual al vencimiento del link.
- Un pago con `date_approved` posterior al vencimiento del link va a aprobación manual. No debería ocurrir, porque Mercado Pago rechaza pagos sobre preferencias vencidas (`expiration_date_to`); se mantiene como regla defensiva.
- Una cotización que ya pasó a `EXPIRED` no vuelve a `CONVERTED` (D4).

### 4.9 Procesamiento único e idempotente

La notificación, la consulta periódica y "ya pagué" pueden procesar el mismo pago a la vez. Los tres llaman a `ProcessMercadoPagoPayment(mp_payment_id)`, que en una sola transacción:

1. Inserta el pago con `mp_payment_id` único usando insert-on-conflict-do-nothing. Si ya existía, termina sin efectos.
2. Bloquea la cotización con `SELECT ... FOR UPDATE`.
3. Aplica las validaciones de 4.1 paso 5 y el cierre de 4.1 paso 6.

## 5. Mensajes del bot

Texto en español neutro (tú). Redacción final a cargo del constructor, respetando el contenido.

| Momento | Contenido |
| :--- | :--- |
| Link (tras el resumen) | Monto del adelanto, que con él se agenda el evento, el link, la fecha y hora de vencimiento del link (hora de Lima) y la alternativa de Yape o transferencia. |
| Pago recibido, confirmando fecha | "Recibimos tu pago. Estamos confirmando tu fecha; te escribimos en unos minutos." |
| Pago aprobado | "Pago aprobado. En breve te enviaremos tu contrato." |
| "Ya pagué" sin pago encontrado | Que aún no se refleja, que lo intente en unos minutos o envíe la captura si usó Yape o transferencia. |
| Link anulado por conflicto | Que el horario ya no está disponible, con alternativas o la opción de hablar con un encargado. |
| Pago manual rechazado | El motivo y, si el link sigue vigente, el link. |
| Cliente vuelve tras el vencimiento | Que la cotización venció y que se prepara una nueva con disponibilidad y precio actualizados (4.7). |

## 6. Reglas y documentos que cambian

Los cambios en `01-requisitos/01-vision-alcance-y-actores.md` (línea 50 aún lista Mercado Pago fuera del alcance) y en los demás documentos van en el **mismo PR** que esta especificación.

| Documento | Cambio |
| :--- | :--- |
| `01-requisitos/01-vision-alcance-y-actores.md` §3.2 | Quitar Mercado Pago de "Fuera del alcance" y describir el cobro del adelanto por link en §3.1. |
| `01-requisitos/04-reglas-de-negocio-y-control.md` RN-09.3 y RN-09.4 | El mensaje de cotización ahora incluye el link; la revalidación previa a mostrar datos de pago aplica al camino manual. Agregar la vigencia del link (D3), que un pago no se acepta sobre una cotización vencida (D4), la protección del cron (4.8) y la anulación de links en conflicto (D5). |
| Mismo documento, RN-04 y RN-10 | Registrar el sobrecupo pagado con link como punto de control humano (sección 7). |
| `02-arquitectura/08-spec-e1-contrato-cotizacion.md` §6, pregunta 1 | Resuelta en sentido contrario al planteado antes: una cotización `EXPIRED` no se convierte (D4); el cliente recibe una cotización nueva (4.7). |
| `04-api/01-especificacion-endpoints-rest.md` | Nuevo endpoint de notificaciones de Mercado Pago; contratos de verificar y aprobar pago sin `event_id`. |
| `04-api/02-matriz-rbac-y-seguridad.md` | Matriz RBAC si se agregan endpoints (por ejemplo, la consulta de pagos pendientes) y reglas de seguridad del endpoint público de notificaciones. |
| `03-datos/02-diccionario-de-datos.md` | Columnas nuevas de pagos y de cotización (sección 9.1). |

## 7. Puntos de control con intervención humana

| Punto | Quién | Por qué |
| :--- | :--- | :--- |
| Aprobar un pago en sobrecupo | Encargado | Comprometerse a un cuarto show simultáneo exige elenco y logística adicionales (RN-04.5). Con la política de no devolver, la expectativa es aprobarlo y organizar los recursos. |
| Resolver un pago en conflicto | Encargado | Solo ocurre en la carrera de 4.4. El encargado busca una solución con el cliente; la devolución es una excepción. |
| Resolver un pago con discrepancia | Encargado | Monto, moneda, referencia o fecha de aprobación no coinciden con la cotización (4.1 paso 5, 4.8). |
| Validar un pago por Yape, Plin o transferencia | Encargado | La captura no es una prueba confiable; hay que verificar el ingreso en la cuenta. |
| Devolver un pago duplicado | Encargado | Se devuelve a mano desde el panel de Mercado Pago o la cuenta de origen (sección 9.1). |

## 8. Modo de prueba

- Credenciales de prueba de la aplicación de Mercado Pago, por variables de entorno (token de acceso y clave secreta de notificaciones). Sin credenciales, o con la función desactivada por configuración, el link no se crea, el bot ofrece solo el camino manual y se registra una advertencia.
- Tarjeta de prueba Visa 4009 1753 3280 6176, CVV 123, vencimiento 11/30. Titular `APRO` aprueba, `OTHE` rechaza.
- **Los pagos con credenciales de prueba no envían notificaciones.** En la demo el pago se detecta por la tarea periódica o por 4.2. La firma de las notificaciones se prueba con la función "Simular" del panel de Mercado Pago.
- La `notification_url` debe ser HTTPS pública. El proxy (`deploy/Caddyfile`) solo bloquea hacia internet el webhook de Chatwoot (`/api/v1/webhooks/chatwoot`); una ruta nueva en `api` queda pública sin cambiar el proxy. Por eso el endpoint debe validar la cabecera `x-signature` (HMAC sobre `data.id`, `x-request-id` y `ts`) y rechazar notificaciones fuera de una ventana de repetición (por ejemplo, 5 minutos).

## 9. Cambios en piezas existentes

- **Bot (E1):** el bot tiene dos caminos de creación de cotización: la herramienta `create_quote` en `agent_engine.py` (solo encola el resumen) y el camino determinista `_create_quote` en `handle_incoming_message.py`. Ambos deben generar y enviar el link. La acción `pay_advance` del agente pasa a ser el camino manual (entregar datos de Yape o transferencia). Ante una imagen o archivo después del pago, registrar el pago con `RegisterAdvancePayment` en lugar de solo responder "recibido"; hoy las imágenes llegan como `ATTACHMENT_PLACEHOLDER`, así que el manejo de la captura es trabajo nuevo.
- **Pagos (E5):** nuevo medio `MERCADO_PAGO`. Aprobar (verificación y sobrecupo) deja de exigir `event_id`: el evento se crea a partir de la cotización. `verify_payment.py` y `approve_overbooked_payment.py` (en `app/application/use_cases/payment/`) hoy exigen `event_id` y deben cambiar. Hoy ningún caso de uso crea el evento para cotizaciones de WhatsApp; solo lo hace el flujo manual. Detalle de dominio y migración en 9.1.
- **Panel:**
  - Quitar el campo "ID del evento" en `frontend/src/pages/panel-sobrecupo/payments.tsx` y en `frontend/src/features/verify-payment/VerifyPaymentModal.tsx` (ambos exigen `event_id`), y mostrar la captura y los datos del pago para decidir.
  - Agregar `MERCADO_PAGO` a `PaymentMethod`, `PAYMENT_METHODS` y `PAYMENT_METHOD_LABELS` en `frontend/src/entities/payment/types.ts`.
  - `frontend/src/entities/payment/ui/PaymentEvidenceViewer.tsx` y `frontend/src/widgets/payment-detail/PaymentDetailModal.tsx` muestran los datos de Mercado Pago (id de pago, estado, `date_approved`) cuando no hay imagen.
  - Nuevo consumidor del evento SSE de pagos y un filtro o insignia "pendiente de validar" (4.5).
- **Cotización:** sin transiciones nuevas desde `EXPIRED`. `EXPIRED` sigue siendo terminal (D4). `PAYMENT_STARTED` se establece al enviar el link (9.1).
- **Tarea `expire_due_quotes`** (`app/infrastructure/adapters/primary/jobs/worker.py`): no vence cotizaciones con link activo hasta `expires_at` + margen (4.8).

## 9.1 Decisiones del diseñador (revisables)

- **Dominio del pago automático (bloqueante):** hoy `Payment` rechaza un pago verificado por el sistema. `payment.py` exige `verified_by_user_id` para `VERIFIED` y `REFUNDED` (líneas 84-89), exige `evidence_path` no vacío (línea 68), el enum `PaymentMethod` no incluye `MERCADO_PAGO` (líneas 20-22) y la migración `0001_initial_schema.py` declara `evidence_path` `NOT NULL` y limita `payment_method` a `YAPE`, `PLIN`, `BANK_TRANSFER`, `CASH` (`ck_payments_payment_method`). Cambios requeridos:
  - Migración nueva: ampliar el CHECK de `payment_method` con `MERCADO_PAGO`, permitir `evidence_path` nulo cuando el medio es `MERCADO_PAGO`, y agregar `mp_payment_id` con índice único.
  - Dominio: un método de verificación por el sistema (por ejemplo, `verify_by_system()`), o permitir `verified_by_user_id` nulo solo cuando el medio es `MERCADO_PAGO`, y relajar la validación de `evidence_path` para ese medio.
  - Enum, DTO y esquema de la API actualizados; el frontend en la sección 9.
  - `issue_for_event` acepta `user_id` nulo (`app/application/ports/output/contract_port.py`), pero eso **no** es precedente para `Payment`, que hoy no lo admite.
- **Actor de la aprobación automática:** `verified_by_user_id` nulo con medio `MERCADO_PAGO`, según el cambio de dominio anterior. La auditoría registra la acción como realizada por el sistema.
- **Creación del evento:** no se reutiliza `IManualBookingPort.finalize` tal cual. Ese puerto está atado a reservas manuales: `manual_booking_repository.py` crea con `source='MANUAL'`, contrato en modo manual y auditoría `MANUAL_CONTRACT`, con un índice único acotado a MANUAL (`0003_manual_booking_documents.py`). Además `ConfirmManualBookingUseCase` (`app/application/use_cases/quote/confirm_manual_booking.py`) exige `PAYMENT_STARTED`, una cotización no vencida y compara el monto pagado. Se define un **caso de uso y método de puerto nuevos** que crean el evento desde la cotización con origen WHATSAPP, en `AWAITING_SIGNATURE`. El contrato lo emite luego `issue_for_event`, invocado por ese caso de uso nuevo (4.6). Coordinar con el dueño del módulo de eventos.
- **Estados de la cotización:** al enviar el link, la cotización pasa a `PAYMENT_STARTED` directamente, sin pasar por `PayAdvanceUseCase`: la disponibilidad se acaba de validar en `create_quote`. `PayAdvanceUseCase` (`pay_advance.py`) rechaza `now >= expires_at` y revalida disponibilidad; ese chequeo se conserva para el camino manual. Un rechazo manual deja la cotización en `PAYMENT_STARTED` mientras el link siga vigente; si no, sigue su vencimiento normal y no se reabre (D4). No existe la transición `EXPIRED` → `CONVERTED`.
- **Registro del pago de Mercado Pago:** un `Payment` de concepto `ADVANCE` con medio `MERCADO_PAGO`, sin imagen de evidencia, y el id de pago de Mercado Pago en la columna única `mp_payment_id` (idempotencia, 4.9). La pantalla de evidencia muestra los datos del pago en lugar de una imagen.
- **Rechazo de un pago ya cobrado por Mercado Pago (sobrecupo o conflicto):** no se llama a la API de devoluciones. La devolución, si ocurre, es excepcional y se registra con el flujo `refund_payment` existente, hecha a mano desde el panel de Mercado Pago.
- **Pago duplicado (decisión del negocio, 2026-11-10):** si llega un segundo pago del adelanto para una cotización ya pagada o convertida (por ejemplo, link y Yape), el segundo pago se devuelve. No reabre ni modifica el evento: queda en `REFUND_PENDING` con aviso al encargado, que lo devuelve a mano y lo marca como `REFUNDED`. Es un caso poco probable. Hoy no es posible, por dos motivos, y ambos requieren cambio:
  - `mark_refund_pending` solo acepta pagos en `REQUIRES_MANUAL_APPROVAL` (`payment.py`, línea 172 en adelante). Se agrega la transición nueva: pago duplicado de Mercado Pago → `REFUND_PENDING` sin evento.
  - `RegisterAdvancePayment` usa `find_active_advance` y lanza `ResourceInUseError` si ya hay un adelanto en `PENDING_VERIFICATION`, `REQUIRES_MANUAL_APPROVAL` o `REFUND_PENDING` (`register_advance_payment.py`, líneas 17-19). Un Yape tardío tras un pago con link fallaría. El duplicado de Mercado Pago no pasa por ese caso de uso: lo registra `ProcessMercadoPagoPayment` directamente, sin la guarda de adelanto activo, y la restricción única por `mp_payment_id` evita doble registro. Qué hacer con un Yape posterior queda a criterio del constructor, con aviso al encargado.
- **Evento muy cercano o vigencia corta:** si la vigencia calculada (D3) deja menos de 1 hora, no se crea link; el bot ofrece el camino manual y avisa al encargado.
- **Mercado Pago caído:** si falla la creación de la preferencia, el resumen de la cotización se envía igual, el bot ofrece el camino manual, se registra el error y (opcional) se reintenta una vez. El manejador de notificaciones responde 5xx ante fallas transitorias para que Mercado Pago reintente; la tarea periódica es el respaldo. El tiempo máximo de espera HTTP es ajustable por el constructor.
- **Tarea periódica:** cron de arq en el worker existente (como `expire_due_quotes`). La respuesta al cliente usa la conversación vinculada a la cotización (`conversation_links.quote_id`).
- **Indicador persistente (4.5):** sin tabla nueva. Se usa una consulta de pagos pendientes de validar (no la lista actual de sobrecupo) más el aviso SSE.

## 10. Decisiones que quedan al constructor

- Nombres de puertos, adaptador y tablas o columnas para guardar la preferencia (siguiendo la arquitectura hexagonal del backend).
- Ruta exacta del endpoint de notificaciones. El proxy no requiere registro (sección 8), pero el endpoint debe validar firma y ventana de repetición.
- Intervalo de la tarea periódica de consulta de pagos (sugerido: 1 minuto) y margen de `expire_due_quotes` (sugerido: 5 minutos, nunca menor que el intervalo).
- Tiempo máximo de espera HTTP hacia Mercado Pago y si se reintenta una vez.
- Redacción final de los mensajes de la sección 5.
- Si el link se crea dentro de la unidad de trabajo de `CreateQuote` o justo después, siempre que una falla de Mercado Pago no impida enviar el resumen (en ese caso, se ofrece el camino manual y se registra el error).

## 11. Pendientes y datos no verificados

- **Ventana de 24 horas de WhatsApp:** como el link dura como máximo 24 horas desde la cotización, el aviso de pago casi siempre cae dentro de la ventana de servicio y el cliente suele escribir después de pagar. Las plantillas quedan como respaldo para el aviso de pago y siguen siendo necesarias para E2 (enlace de firma, OTP). El 2026-11-11 se envió a revisión, en la cuenta de prueba de WhatsApp Business de Meta, una plantilla personalizada de categoría UTILITY llamada `pago_aprobado` (idioma `es`, solo cuerpo, variables posicionales {{1}} nombre, {{2}} monto, {{3}} fecha del evento). Se permite crear plantillas personalizadas en la cuenta de prueba. La aprobación y la entrega siguen pendientes de confirmar. El adaptador solo admite parámetros de cuerpo (`build_template_params` en `chatwoot_payloads.py`), por lo que las plantillas no deben usar botones ni encabezados con medios. Idea abierta a decidir con Diego (E2): unir el aviso de pago con el enlace de firma como {{4}}.
- **Pagos sobre un link vencido:** Mercado Pago debería rechazarlos por `expiration_date_to`. Confirmar que también aplica a pagos con tarjeta en modo de prueba, y los campos exactos de la preferencia para Perú (`external_reference`, `expiration_date_to`).
- Si Yape aparece y puede probarse dentro de Checkout Pro en modo de prueba. La demo se planifica con tarjeta.
- Comisiones y requisitos para pasar a producción con DNI: fuera del alcance académico.
- Alternativas descartadas: Culqi (los links solo se crean desde su app y piden RUC), Stripe (no opera en Perú), Niubiz e Izipay (credenciales tras contrato o ejecutivo comercial).

## Fuentes

- [Mercado Pago: crear preferencia](https://www.mercadopago.com.pe/developers/en/docs/checkout-pro/create-payment-preference)
- [Mercado Pago: notificaciones de pago](https://www.mercadopago.com.pe/developers/en/docs/checkout-pro/payment-notifications)
- [Mercado Pago: medios de pago de Checkout Pro en Perú](https://www.mercadopago.com.pe/developers/en/docs/checkout-pro-orders/overview)
- [Mercado Pago: pruebas de integración](https://www.mercadopago.com.pe/developers/en/docs/checkout-pro/integration-test)
- [Mercado Pago: compras de prueba](https://www.mercadopago.com.pe/developers/en/docs/checkout-pro/integration-test/test-purchases)
- [Mercado Pago: vigencia de la preferencia](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/additional-settings/preferences/term-of-preference)
- [Manual CulqiLink](https://culqi.com/static/files/manuals/manual-culqiLink.pdf)
- [Stripe: países soportados](https://stripe.com/global)
