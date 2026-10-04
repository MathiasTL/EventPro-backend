# 02. Especificación de Requerimientos Funcionales (RF)

---

## 1. Módulo M01: Canal WhatsApp y Captura de Pedidos

### RF-01: Atención Automatizada y Saludo Inicial
* **Descripción:** El sistema debe procesar los mensajes entrantes de clientes a través del gateway de mensajería (Chatwoot, ADR-10), que recibe los mensajes del canal de WhatsApp y los reenvía al backend por el webhook `POST /webhooks/chatwoot`, y responder de manera automatizada con un mensaje de bienvenida y el catálogo estructurado de servicios.
* **Entradas:** Evento `message_created` entrante recibido del gateway de mensajería por el webhook de Chatwoot (identificador de la conversación, número de teléfono del remitente, identificador de mensaje, texto o payload de botón). El canal del cliente sigue siendo WhatsApp.
* **Procesamiento:** 
  1. Verificar si el número de teléfono corresponde a un cliente con una cotización o conversación activa.
  2. Si no existe conversación activa, inicializar una nueva sesión de atención.
  3. Despachar mensaje de saludo inicial junto con el menú principal de opciones interactivas.
* **Salidas:** Mensaje interactivo de WhatsApp despachado al cliente a través del gateway de mensajería (HTTP 200 al webhook en menos de 1.5 s, RNF-01.2). El bot solo responde mientras la conversación está en modo `BOT` (`pending`); en modo `HUMAN` (`open`) no responde (RF-30).
* **Reglas Asociadas:** PC-10, RN-10.
* **Prioridad:** Alta.

---

### RF-02: Captura Estructurada de Datos del Evento
* **Descripción:** El sistema debe guiar al cliente a través del chatbot para capturar y validar los parámetros obligatorios del evento requerido.
* **Entradas:** 
  * Nombre y apellido del cliente.
  * Número de teléfono de contacto.
  * Fecha solicitada para el evento.
  * Hora estimada de inicio y duración prevista.
  * Ubicación geográfica (dirección completa, distrito, referencia o enlace de ubicación GPS).
* **Procesamiento:**
  1. Validar que la fecha sea igual o posterior a la fecha actual.
  2. Validar que la dirección contenga datos suficientes para su resolución en el servicio de mapas.
  3. Almacenar los datos de la sesión vinculados al identificador de solicitud.
* **Salidas:** Registro preliminar de la solicitud en la sesión de conversación (aún no existe cotización; la cotización nace al enviarse, ver RF-08).
* **Prioridad:** Alta.

---

## 2. Módulo M02: Catálogo de Servicios, Temáticas y Extras

### RF-03: Gestión de Paquetes y Temáticas
* **Descripción:** El sistema debe mantener y exponer un catálogo parametrizable de paquetes base (ej. Hora Loca Básica, Medium, Premium, Show Infantil, Baby Shower, Paquete DJ, Toldos + Decoración) vinculados a sus temáticas compatibles (ej. Selva, Neón, Años 80, Superhéroes).
* **Entradas:** Solicitud de consulta del catálogo o selección del cliente.
* **Procesamiento:** Consultar en base de datos la lista de paquetes activos, temáticas habilitadas y sus descripciones operativas.
* **Salidas:** Catálogo estructurado en formato JSON / Mensajes de lista interactiva para WhatsApp.
* **Prioridad:** Alta.

---

### RF-04: Selección y Adición de Extras
* **Descripción:** El sistema debe permitir la selección de uno o múltiples servicios y personajes complementarios (extras) para añadirlos a la cotización (ej. Muñeco Gorila Gigante, Robot LED, bailarines adicionales, cañón de confeti/espuma, horas adicionales de DJ).
* **Entradas:** Identificador del paquete base seleccionado e identificadores de los extras elegidos.
* **Procesamiento:** 
  1. Verificar la compatibilidad del extra con el paquete seleccionado.
  2. Incorporar los extras seleccionados al detalle de la cotización preliminar.
* **Salidas:** Lista de extras vinculada a la cotización en curso.
* **Prioridad:** Alta.

---

## 3. Módulo M03: Motor de Cotización y Movilidad

### RF-05: Cálculo Automatizado del Costo de Movilidad
* **Descripción:** El sistema debe calcular automáticamente el costo del traslado de ida y vuelta del personal y equipos mediante la API de Google Maps, determinando la distancia y tiempo de ruta y aplicando un margen comercial del 15%.
* **Entradas:** 
  * Coordenadas o dirección de la base de operaciones de la promotora.
  * Coordenadas o dirección del lugar del evento.
* **Procesamiento:**
  1. Consultar la API de Google Maps (Distance Matrix / Directions) para obtener distancia en kilómetros ($D$) y tiempo estimado de tránsito en minutos ($T$) para el trayecto de ida y vuelta.
  2. Aplicar la tarifa base operativa por kilómetro y minuto.
  3. Aplicar el recargo de seguridad y contingencia del 15%:
     $$\text{Costo Movilidad} = \text{Tarifa Base}(D, T) \times 1.15$$
* **Salidas:** Monto decimal del costo de movilidad sugerido.
* **Reglas Asociadas:** RN-03, PC-04.
* **Prioridad:** Alta.

---

### RF-06: Exención de Movilidad por Transporte Propio
* **Descripción:** El sistema debe permitir registrar la exoneración del cobro de movilidad si el cliente especifica que proveerá transporte de ida y vuelta para el elenco y materiales.
* **Entradas:** Bandera booleana de transporte provisto por el cliente (`movilidad_propia_cliente: boolean`).
* **Procesamiento:** Si `movilidad_propia_cliente == true`, fijar el costo de movilidad en `0.00`.
* **Salidas:** Costo de movilidad registrado en S/. 0.00 con anotación en la cotización.
* **Reglas Asociadas:** RN-03.
* **Prioridad:** Media.

---

### RF-07: Liquidación Económica de Cotización (Total, Adelanto y Saldo)
* **Descripción:** El sistema debe realizar el cálculo determinístico de la estructura financiera del pedido aplicando estrictamente las reglas de negocio de la promotora:
  1. **Subtotal de Servicios:** Suma del precio del paquete base más la suma de los precios de todos los extras seleccionados.
  2. **Total General de la Cotización:** Suma del subtotal de servicios más el costo de movilidad calculado o ajustado.
  3. **Monto de Adelanto Obligatorio (10%):** Equivalente estrictamente al 10% del subtotal de servicios. **La movilidad no forma parte de la base de cálculo del adelanto**.
  4. **Saldo Pendiente de Pago:** Diferencia entre el total general y el adelanto cancelado.
  5. **Desglose Operativo para Liquidación:** El sistema debe discriminar internamente y en los documentos el saldo de servicios (90% restante) y el monto total de movilidad, ya que ambos conceptos se cobran el día del evento antes de iniciar el show.
* **Entradas:**
  * `precio_paquete`: Decimal $> 0$.
  * `precios_extras`: Lista de decimales $\ge 0$.
  * `costo_movilidad`: Decimal $\ge 0$.
* **Procesamiento / Fórmulas:**
  $$\text{Subtotal Servicios} = \text{precio\_paquete} + \sum_{i=1}^n \text{precio\_extra}_i$$
  $$\text{Total Cotización} = \text{Subtotal Servicios} + \text{costo\_movilidad}$$
  $$\text{Adelanto (10%)} = 0.10 \times \text{Subtotal Servicios}$$
  $$\text{Saldo Pendiente Total} = \text{Total Cotización} - \text{Adelanto (10\%)}$$
  $$\text{Saldo Pendiente Total} = (0.90 \times \text{Subtotal Servicios}) + \text{costo\_movilidad}$$
* **Salidas:** Estructura de liquidación con:
  * `subtotal_servicios`: Decimal.
  * `costo_movilidad`: Decimal.
  * `monto_total`: Decimal.
  * `monto_adelanto`: Decimal.
  * `saldo_pendiente_total`: Decimal.
  * `desglose_saldo_servicios`: Decimal (90% de servicios).
  * `desglose_saldo_movilidad`: Decimal (100% de movilidad).
* **Reglas Asociadas:** RN-01, RN-02, RN-03, PC-07.
* **Prioridad:** Alta (Crítica).

---

### RF-08: Despacho Automático de Resumen de Cotización
* **Descripción:** El sistema debe componer un mensaje estructurado y legible con el desglose comercial de la cotización y transmitirlo automáticamente al cliente a través del chat de WhatsApp (por el gateway de mensajería).
* **Entradas:** Identificador de la cotización calculada y número de WhatsApp del cliente.
* **Procesamiento:**
  1. Generar plantilla de texto con detalle de paquete, temática, extras, movilidad, monto total y monto de adelanto requerido (10%).
  2. El mensaje **no incluye datos de pago** (Yape, Plin ni cuentas bancarias). Incluye únicamente un botón interactivo «Pagar adelanto».
  3. El mensaje advierte de forma explícita que **la fecha y el horario solo quedan asegurados cuando el adelanto es validado**, e informa el plazo máximo para pagarlo (`ADVANCE_DEADLINE_HOURS`, por defecto 24 horas desde el envío).
  4. Registrar la hora de envío como inicio del plazo de vigencia de la cotización.
* **Salidas:** Mensaje enviado por WhatsApp mediante el gateway de mensajería (a través de `outbox_messages`) con cambio de estado de la cotización a `SENT` (ver ciclo de vida de cotización en RN, sección 3).
* **Reglas Asociadas:** RN-09.
* **Prioridad:** Alta.

---

## 4. Módulo M04: Verificación de Disponibilidad y Capacidad

### RF-09: Verificación de Disponibilidad de Recursos e Inventario
* **Descripción:** Antes de enviar la cotización, y nuevamente en los puntos de revalidación definidos en RN-09, el sistema debe comprobar la factibilidad operativa del evento contrastando los recursos solicitados contra la programación existente. La disponibilidad **no reserva** el cupo: este solo queda asegurado cuando el adelanto es validado.
* **Entradas:** Fecha, intervalo horario [inicio, fin), tipo de paquete, extras solicitados y requerimientos de infraestructura (toldos/decoración).
* **Procesamiento:**
  1. Para shows y animación: Comprobar disponibilidad de artistas freelance registrados en la categoría requerida.
  2. Para toldos y decoración: Comprobar que el stock de `inventory_items` (estructuras y telas) no se encuentre comprometido por `inventory_reservations` activas de otros eventos en la misma ventana de tiempo: `total_stock` menos las unidades reservadas solapadas debe cubrir las unidades que consume el paquete de cada ítem. La comprobación abarca TODOS los ítems que el paquete consume (filas de `package_inventory_items`); si algún ítem no tiene stock suficiente, el resultado es `CONFLICT`.
  3. Al validar el adelanto y crear el evento, registrar las reservas de inventario del evento (`inventory_reservations`, una por cada fila de `package_inventory_items` del paquete, con la cantidad copiada y ventana `starts_at`–`ends_at`); se liberan (`RELEASED`) si el evento se cancela.
* **Salidas:** Resultado de disponibilidad (`AVAILABLE`, `CONFLICT`, `THRESHOLD_EXCEEDED`). Este resultado no es un estado de ciclo de vida; `THRESHOLD_EXCEEDED` indica que se superó `SIMULTANEOUS_SHOWS_THRESHOLD` (ver RN-04).
* **Reglas Asociadas:** RN-04, PC-01.
* **Prioridad:** Alta.

---

### RF-10: Cálculo de Intervalo de Traslado entre Shows Sucesivos
* **Descripción:** El sistema debe verificar que exista una ventana de tiempo suficiente entre eventos asignados al mismo elenco o grupo de trabajo en una misma fecha.
* **Entradas:** Coordenadas del Evento A, horario de término del Evento A, coordenadas del Evento B y horario de inicio del Evento B.
* **Procesamiento:**
  1. Calcular tiempo de tránsito entre Evento A y Evento B mediante Google Maps.
  2. Sumar 30 minutos mínimos por concepto de desmontaje, descanso y preparación.
  3. Validar si el margen disponible es mayor o igual al intervalo mínimo requerido.
* **Salidas:** Intervalo sugerido (en minutos) y alerta en caso de solapamiento de horario.
* **Reglas Asociadas:** RN-05, PC-02.
* **Prioridad:** Alta.

---

## 5. Módulo M05: Gestión de Pagos, Comprobantes y Validación

### RF-11: Recepción de Comprobantes de Pago del Adelanto
* **Descripción:** El sistema debe recibir y almacenar la imagen de la captura de pantalla o comprobante digital del depósito o transferencia del adelanto del 10% (Yape o transferencia bancaria).
* **Entradas:** Archivo de imagen (JPEG, PNG, WebP) o documento PDF enviado por el cliente vía WhatsApp, asociado a la cotización vigente.
* **Procesamiento:**
  1. Almacenar el archivo en el repositorio de archivos con un identificador UUID no predecible.
  2. Vincular el registro de pago a la cotización (el vínculo con el evento es opcional, porque el evento solo se crea al validar el adelanto).
  3. **Revalidación temprana de disponibilidad (RN-09):** verificar si el cupo sigue disponible. Si hay cupo, el pago ingresa en estado `PENDING_VERIFICATION`. Si el cupo está lleno o se supera `SIMULTANEOUS_SHOWS_THRESHOLD`, el pago ingresa en estado `REQUIRES_MANUAL_APPROVAL` (alerta temprana al encargado; no es la verificación autoritativa).
  4. Si la cotización ya está `EXPIRED`, el comprobante se almacena igualmente, pero el pago ingresa en `REQUIRES_MANUAL_APPROVAL` para decisión del encargado (el cliente pudo haber pagado dentro del plazo).
  5. La cotización pasa a `PAYMENT_STARTED` si aún estaba en `SENT`.
* **Salidas:** Comprobante almacenado y pago en cola de verificación (`PENDING_VERIFICATION` o `REQUIRES_MANUAL_APPROVAL`).
* **Reglas Asociadas:** RN-04, RN-09, PC-03, PC-11.
* **Prioridad:** Alta.

---

### RF-12: Validación de Pago y Flujo de Reintento
* **Descripción:** El sistema debe permitir validar el comprobante de pago. En caso de inconsistencia o ilegibilidad, debe emitir una notificación automática al cliente solicitando un nuevo comprobante.
* **Entradas:** Dictamen de validación (Aprobado / Rechazado con motivo).
* **Procesamiento:**
  * Si es aprobado:
    1. **Revalidación autoritativa y atómica de disponibilidad** bajo bloqueo distribuido (Redis lock, ADR-06) sobre la fecha y el intervalo solicitados, antes de confirmar.
    2. Si hay cupo: cambiar el pago a `VERIFIED`, la cotización a `CONVERTED`, crear el evento en estado `AWAITING_SIGNATURE` y disparar la generación del contrato.
    3. Si el cupo está lleno al validar: el encargado decide entre **aprobar el sobrecupo** (se continúa como en el paso anterior) o **rechazar con devolución** (el pago pasa a `REFUND_PENDING`, no se crea evento y se notifica al cliente con opción de otra fecha u horario).
  * Si es rechazado por comprobante inválido o ilegible (el pago puede estar en `PENDING_VERIFICATION` o en `REQUIRES_MANUAL_APPROVAL`): cambiar el pago a `REJECTED` y enviar mensaje vía WhatsApp con el motivo del rechazo y botón/instrucción de reintento (el reintento crea un nuevo registro de pago).
  * Una vez efectuada la devolución, el pago pasa a `REFUNDED`.
* **Salidas:** Estado actualizado y notificación de WhatsApp emitida.
* **Reglas Asociadas:** RN-04, RN-09, PC-03, PC-06, PC-11.
* **Prioridad:** Alta.

---

## 6. Módulo M06: Generación de Contratos y Firma Electrónica

### RF-13: Generación Automatizada del Contrato en PDF
* **Descripción:** Una vez validado el adelanto, el sistema debe compilar automáticamente el contrato de prestación de servicios en formato PDF estándar.
* **Entradas:** Datos del cliente, datos del evento, paquete, temática, extras, cuadro de liquidación económica (total, adelanto cobrado, saldo pendiente desglosado con movilidad) y cláusulas de servicio.
* **Procesamiento:** Renderizar plantilla HTML/CSS a PDF mediante motor de compilación de documentos, estampando correlativo único del contrato.
* **Salidas:** Archivo PDF generado y almacenado, disponible para visualización y descarga.
* **Reglas Asociadas:** RN-02, RN-06.
* **Prioridad:** Alta.

---

### RF-14: Registro de Observaciones Especiales del Cliente
* **Descripción:** El sistema debe permitir incluir notas y directrices específicas en formato de texto libre (ej. temas musicales no permitidos, momento exacto de ingreso del gorila gigante, restricciones de espacio o iluminación).
* **Entradas:** Texto de observaciones ingresado por el cliente en el chat o por el encargado en el panel.
* **Procesamiento:** Almacenar el texto de forma estructurada en la entidad del evento y mapearlo obligatoriamente en una sección visible del contrato PDF y del cronograma.
* **Salidas:** Campo de observaciones reflejado en el contrato y en la vista de monitoreo operativo.
* **Reglas Asociadas:** PC-10.
* **Prioridad:** Media.

---

### RF-15: Registro de Firma Electrónica del Contrato
* **Descripción:** El sistema debe proveer una interfaz web responsiva y segura para que el cliente revise el contrato y lo firme electrónicamente, y sellar el PDF resultante con un mecanismo propio (ADR-07, puerto `SignaturePort`). Flujo:
  1. El cliente recibe por WhatsApp un enlace de un solo uso con expiración (`signature_token_expires_at`).
  2. Revisa el PDF del contrato en el enlace.
  3. El sistema envía por WhatsApp un código OTP de 6 dígitos (con expiración y límite de intentos fallidos); el cliente lo ingresa para continuar.
  4. El cliente traza su firma manuscrita y acepta los términos.
  5. El backend estampa la firma y sella el PDF con **PAdES** usando **pyHanko** y un certificado **PKCS#12** (`.p12`), con marca de tiempo **RFC 3161** opcional.
  6. Se calcula el **SHA-256** del PDF sellado y se registra, junto con los metadatos de la firma, en la bitácora de auditoría.
* **Entradas:** Token del enlace, código OTP, trazado de firma manuscrita (PNG), aceptación de términos, dirección IP y agente de usuario del cliente.
* **Procesamiento:**
  1. Validar token (hash, expiración, un solo uso) y OTP (hash, expiración, `otp_attempts`).
  2. Estampar la imagen de la firma en la sección de firmas del contrato PDF y sellarlo con PAdES.
  3. Registrar `signed_at`, `signer_ip`, `signer_user_agent`, `sealed_pdf_sha256` y la ruta del PDF sellado; cambiar el contrato a `SIGNED` y el evento a `SCHEDULED`; registrar la acción `CONTRACT_SIGNED` en `audit_logs`.
  4. Despachar copia del contrato firmado al WhatsApp del cliente (vía `outbox_messages`).
* **Salidas:** Contrato PDF sellado y copia enviada al cliente.
* **Reglas Asociadas:** PC-05 (modo manual), RN-06.
* **Prioridad:** Alta.
> **Nota terminológica:** se usa «firma electrónica» y no «firma digital» porque, según la Ley 27269 (Perú), la firma digital exige un certificado emitido por una entidad acreditada ante INDECOPI. El certificado `.p12` de desarrollo es autofirmado; incorporar uno acreditado por INDECOPI más adelante no requiere cambios en el dominio, solo reemplazar el certificado del adaptador de `SignaturePort`.

---

## 7. Módulo M07: Cronograma Operativo y Ejecución en Vivo

### RF-16: Tablero de Cronograma y Filtros de Búsqueda
* **Descripción:** El sistema debe suministrar una vista calendarizada y listado cronológico de eventos confirmados con capacidades de filtrado dinámico.
* **Entradas:** Parámetros de consulta: rango de fechas, distrito, temática, estado del evento o grupo de elenco asignado.
* **Procesamiento:** Ejecutar consulta indexada sobre la base de datos y retornar la colección de eventos que coincidan con los criterios.
* **Salidas:** Vista tipo calendario y grilla de datos con información operativa.
* **Prioridad:** Alta.

---

### RF-17: Visualización Rápida de Observaciones en Cronograma
* **Descripción:** En la vista principal del cronograma, cada tarjeta de evento debe desplegar de forma prominente un indicador o extracto de las observaciones especiales para lectura inmediata del equipo operativo.
* **Entradas:** Solicitud de vista de cronograma.
* **Procesamiento:** Extraer el campo de observaciones y renderizarlo resaltado en la tarjeta de resumen sin requerir la apertura del PDF.
* **Salidas:** Indicador visual desplegable con las directrices críticas del evento.
* **Reglas Asociadas:** PC-10.
* **Prioridad:** Media.

---

### RF-18: Protocolo de Cobro Pre-Show y Bloqueo de Inicio
* **Descripción:** El sistema debe registrar la confirmación del cobro del saldo pendiente total (saldo de servicios + movilidad) al llegar a la locación. El sistema debe bloquear el pase a estado «En Ejecución» si no se confirma la recepción de este saldo.
* **Entradas:** Registro de cobro presencial (medio de pago: Yape, Plin, transferencia o efectivo; monto recibido; **evidencia obligatoria**: fotografía de la pantalla de Yape/Plin o del efectivo recibido, tomada con la cámara del teléfono; identificador del usuario que confirma).
* **Procesamiento:**
  1. Validar que el monto cobrado complete el 100% del saldo pendiente y que se adjunte la evidencia.
  2. Registrar el cobro como un pago de concepto `BALANCE` directamente en `VERIFIED` (sin esperar a un encargado), con `audit_status = UNREVIEWED`.
  3. Actualizar estado del evento a `IN_PROGRESS` (desde `AWAITING_BALANCE`).
  4. El encargado audita el cobro después (`REVIEWED` o `FLAGGED`).
* **Salidas:** Evento habilitado operativamente y registro contable de ingreso in-situ con su evidencia.
* **Reglas Asociadas:** RN-06, PC-07, PC-12.
* **Prioridad:** Alta (Crítica).

---

### RF-19: Registro de Extensiones en Vivo y Liquidación Post-Evento
* **Descripción:** El sistema debe permitir registrar cargos adicionales solicitados por el cliente durante el evento (horas extra de show, tiempo extra de espera o servicios adicionales en caliente) y consolidar el cierre definitivo del evento.
* **Entradas:** Minutos/horas de extensión, tarifa pactada, medio de pago del extra y evidencia obligatoria (fotografía de la pantalla de Yape/Plin o del efectivo).
* **Procesamiento:**
  1. Sumar el recargo extraordinario al total facturado del evento.
  2. Registrar el cobro como un pago de concepto `EXTENSION` directamente en `VERIFIED` con `audit_status = UNREVIEWED`, y la extensión en `event_extensions` vinculada a ese pago.
  3. Transicionar el estado del evento a `EXTENDED` (si hubo extensión) y luego a `SETTLED`.
  4. El encargado audita el cobro después (`REVIEWED` o `FLAGGED`).
* **Salidas:** Estado de evento `SETTLED` y cierre de caja del servicio.
* **Reglas Asociadas:** RN-07, PC-08, PC-12.
* **Prioridad:** Alta.

---

## 8. Módulo M08: Procesos de Control y Sobrescritura (Overrides) Manuales

### RF-20: Aprobación Manual por Umbral de Eventos Simultáneos
* **Descripción:** Dos shows son simultáneos cuando sus intervalos reales $[\text{inicio}, \text{fin})$ se solapan, con $\text{fin} = \text{inicio} + \text{duración del paquete}$. Si al incorporar el show solicitado la cantidad de shows simultáneos supera el umbral configurable `SIMULTANEOUS_SHOWS_THRESHOLD` (por defecto 3), el sistema debe detener la confirmación automática y exigir la autorización expresa de un encargado. La aprobación manual es un **estado del pago** (`REQUIRES_MANUAL_APPROVAL`), no una bandera del evento.
* **Entradas:** Pago con comprobante recibido (RF-11) o validación en curso (RF-12); intervalo $[\text{inicio}, \text{fin})$ del show solicitado; umbral de concurrencia configurado ($N = 3$ por defecto).
* **Procesamiento:**
  1. Contar los eventos cuyo intervalo se solapa con el solicitado y que cumplan **ambas** condiciones: tienen adelanto validado y no están en estado `CANCELLED`. Las cotizaciones sin adelanto validado no cuentan.
  2. Si $\text{eventos solapados} + 1 > N$, llevar el pago a `REQUIRES_MANUAL_APPROVAL` y notificar al encargado.
* **Salidas:** Notificación de alerta en panel administrativo con acciones de Aprobar (sobrecupo) / Rechazar (el pago pasa a `REFUND_PENDING`) / Reagendar.
* **Reglas Asociadas:** RN-04, RN-09, PC-03.
* **Prioridad:** Alta.

---

### RF-21: Sobrescritura (*Override*) Manual de Movilidad
* **Descripción:** El sistema debe permitir a los encargados modificar manualmente el monto de movilidad calculado por el motor de mapas antes de emitir la cotización o el contrato.
* **Entradas:** Nuevo monto de movilidad ajustado y justificación de la modificación.
* **Procesamiento:**
  1. Reemplazar el valor calculado por el valor manual.
  2. Recalcular el Total General y el Saldo Pendiente (el adelanto del 10% no se altera).
  3. Registrar en bitácora de auditoría el identificador del usuario y motivo del ajuste.
* **Salidas:** Cotización actualizada con bandera `movilidad_ajustada_manualmente: true`.
* **Reglas Asociadas:** RN-03, PC-04.
* **Prioridad:** Alta.

---

### RF-22: Ajuste Manual del Intervalo entre Shows
* **Descripción:** El sistema debe otorgar a los encargados la capacidad de alterar la ventana de traslado estimada entre shows asignados a un mismo elenco.
* **Entradas:** Nuevo tiempo de intervalo en minutos y justificación del ajuste.
* **Procesamiento:** Actualizar la validación de solapamiento para la asignación de ese elenco específico y registrar en log de auditoría.
* **Salidas:** Intervalo modificado y asignación de elenco confirmada.
* **Reglas Asociadas:** RN-05, PC-02.
* **Prioridad:** Media.

---

### RF-23: Modo Manual de Creación de Contratos
* **Descripción:** El sistema debe ofrecer un módulo administrativo para crear y emitir contratos directamente desde un formulario web sin requerir la interacción previa del cliente por el bot de WhatsApp.
* **Entradas:** Formulario administrativo con datos del cliente, paquete, temática, extras, fecha, horario, dirección, montos acordados y observaciones.
* **Procesamiento:** Registrar al cliente (`clients`, por teléfono) y crear una cotización con `source = MANUAL` que captura los montos acordados; el evento (`events.quote_id` sigue siendo obligatorio) y el contrato se crean cuando el adelanto es registrado y validado, que el encargado puede hacer en el mismo formulario. Generar el contrato en estado `DRAFT` o `ISSUED` (`is_manual_mode = true`), calculando liquidación económica y permitiendo su descarga o envío por enlace de firma. Registrar la acción `MANUAL_CONTRACT` en `audit_logs`.
* **Salidas:** Contrato generado mediante flujo manual de respaldo.
* **Reglas Asociadas:** PC-05.
* **Prioridad:** Alta.

---

## 9. Módulo M09: Analítica Financiera y Dashboards

### RF-24: Consolidación Automática de Ingresos y Costos Fijos
* **Descripción:** El sistema debe procesar periódicamente (semanal y mensualmente) las métricas financieras del negocio contrastando ingresos totales contra costos fijos directos tabulados.
* **Entradas:** Base de datos de eventos en estado `SETTLED` y tabla maestra de costos fijos de paquetes y extras.
* **Procesamiento:**
  1. $\text{Ingresos Brutos} = \sum \text{Total Cobrado por Eventos Liquidados}$
  2. $\text{Costos Directos} = \sum (\text{Costo Fijo Paquete} + \sum \text{Costo Fijo Extras} + \text{Costo Real Movilidad})$
  3. $\text{Utilidad Neta} = \text{Ingresos Brutos} - \text{Costos Directos}$
* **Salidas:** Tablas de consolidación contable por período (semana / mes).
* **Reglas Asociadas:** RN-08, PC-09.
* **Prioridad:** Alta.

---

### RF-25: Dashboard Ejecutivo de Desempeño
* **Descripción:** El sistema debe mostrar en el panel administrativo tableros gráficos interactivos con indicadores clave de rendimiento (KPIs).
* **Entradas:** Datos consolidados del módulo financiero y del cronograma.
* **Procesamiento:** Generar agregaciones y series de tiempo para:
  * Utilidad neta mensual comparada con meses anteriores.
  * Volumen de eventos por paquete y temática más vendida.
  * Ranking de extras más contratados (ej. índice de contratación del Gorila Gigante).
  * Distribución de eventos por distritos de Lima.
* **Salidas:** Dashboard interactivo con gráficos de barras, líneas y torta.
* **Prioridad:** Media.

---

## 10. Módulo M10: Administración de la Plataforma

### RF-26: Gestión de Usuarios del Panel y Roles
* **Descripción:** El sistema debe permitir al `SUPERADMIN` administrar las cuentas del panel (encargados y operadores): crear, consultar, editar, cambiar rol y activar o desactivar usuarios. El primer `SUPERADMIN` se crea con el comando de arranque desde variables de entorno.
* **Entradas:** Nombre, correo, teléfono, contraseña inicial, rol (`SUPERADMIN`, `ENCARGADO`, `OPERADOR`) y estado activo; filtros de búsqueda por rol, estado o texto.
* **Procesamiento:**
  1. Almacenar la contraseña únicamente como hash Argon2id (RNF-02.2); nunca se devuelve en la API.
  2. Rechazar correos o teléfonos duplicados.
  3. Al desactivar un usuario o cambiar su contraseña, revocar todos sus refresh tokens.
  4. Impedir que un `SUPERADMIN` se desactive a sí mismo o se quite su propio rol.
* **Salidas:** Usuario creado o actualizado (sin datos sensibles) y listado paginado.
* **Reglas Asociadas:** RNF-02.1, RNF-02.2.
* **Prioridad:** Alta.

---

### RF-27: Consulta de la Bitácora de Auditoría
* **Descripción:** El sistema debe exponer en modo de solo lectura la bitácora de decisiones críticas (`audit_logs`): *overrides*, aprobaciones de sobrecupo, auditoría de cobros, contratos manuales y firmas. La bitácora no se edita ni se elimina desde la API.
* **Entradas:** Filtros por acción, entidad, identificador de entidad, usuario y rango de fechas; paginación.
* **Procesamiento:** Consultar `audit_logs` con los filtros indicados, ordenados del más reciente al más antiguo.
* **Salidas:** Listado paginado de registros con usuario, acción, entidad, valores previos/posteriores y marca de tiempo.
* **Reglas Asociadas:** PC-04, PC-12.
* **Prioridad:** Media.

---

### RF-28: Consulta de Clientes
* **Descripción:** El sistema debe permitir al encargado consultar el registro de clientes. Los clientes se crean o actualizan automáticamente al generar una cotización (por bot o por contrato manual, RF-23), usando el teléfono de WhatsApp como clave natural; no existe una creación independiente.
* **Entradas:** Búsqueda por nombre o teléfono; identificador de cliente; paginación.
* **Procesamiento:** Consultar `clients` con acceso restringido a los roles `ENCARGADO` y `SUPERADMIN`, por tratarse de datos personales (teléfono, DNI, RUC).
* **Salidas:** Listado paginado y ficha del cliente con sus datos de contacto e identificación.
* **Prioridad:** Media.

---

### RF-29: Gestión de Elencos y Vinculación con Operadores
* **Descripción:** El sistema debe permitir al encargado registrar y mantener los elencos y proveedores freelance asignables a eventos, y vincular cada elenco con un usuario `OPERADOR` para que este solo vea y opere sus propios eventos.
* **Entradas:** Nombre del líder, teléfono, categoría de servicio (la misma que usan los paquetes), usuario `OPERADOR` opcional (`user_id`) y estado activo.
* **Procesamiento:**
  1. Validar que `user_id` corresponda a un usuario con rol `OPERADOR` y que no esté vinculado a otro elenco.
  2. Permitir filtrar el listado por categoría de servicio y estado.
  3. Exponer los elencos activos al motor de disponibilidad (RF-09) y a la validación de traslados (RF-10).
* **Salidas:** Elenco creado o actualizado; listado filtrable.
* **Reglas Asociadas:** RN-04, RN-05.
* **Prioridad:** Alta.

---

## 11. Módulo M11: Atención Humana y Bandeja de Conversaciones

Este módulo se apoya en Chatwoot como gateway de mensajería oculto (ADR-10): los encargados nunca usan la interfaz de Chatwoot, sino la bandeja de EventPro. Los endpoints se definen en el módulo 2.14 de la [especificación de endpoints REST](../04-api/01-especificacion-endpoints-rest.md) y el diseño en la [especificación del gateway](../02-arquitectura/05-spec-chatwoot-gateway.md).

### RF-30: Traspaso de la Conversación del Bot a un Encargado y Retorno al Bot
* **Descripción:** El sistema debe permitir que una conversación de WhatsApp pase de la atención del bot a la de un encargado (modo `HUMAN`) y regrese al bot cuando el encargado la devuelve. Mientras la conversación está atendida por un encargado, el bot no responde. Cada traspaso registra su motivo (`handoff_reason`) y un resumen del contexto (`handoff_summary`: datos capturados y cotización vigente).
* **Entradas:**
  * Disparadores del traspaso: (1) el cliente solicita hablar con un encargado (opción «Hablar con un encargado» o texto equivalente); (2) el bot no entiende al cliente dos veces consecutivas; (3) un encargado ejecuta la toma manual de la conversación (`POST /conversations/{id}/takeover`).
  * Excepción no controlada del bot durante el procesamiento de un mensaje.
  * Devolución de la conversación al bot por el encargado asignado o por un `SUPERADMIN` (`POST /conversations/{id}/release`).
* **Procesamiento:**
  1. En los disparadores (1) y (2), el bot avisa al cliente («Te comunico con un encargado»), registra `handoff_reason` (`CLIENT_REQUEST` o `BOT_NOT_UNDERSTOOD`) y `handoff_summary`, y la conversación pasa a `open` sin asignar; se emite en tiempo real el evento `handoff.requested` hacia la bandeja (RF-32).
  2. Ante una excepción no controlada, el bot responde «Tuvimos un problema, te comunico con un encargado» y deriva automáticamente con `handoff_reason = BOT_ERROR`.
  3. En la toma manual, la conversación pasa a `open`, se asigna al encargado autenticado (`assigned_user_id`) y, si estaba en modo `BOT`, se registra `handoff_reason = MANUAL_TAKEOVER`. Si ya había sido derivada y estaba sin asignar, conserva su motivo original. La operación es idempotente para el mismo usuario.
  4. Una conversación asignada a otro encargado no puede ser tomada por un `ENCARGADO` (error `conversation-taken-by-other`). Un `SUPERADMIN` puede reasignarla a sí mismo; la acción se registra en `audit_logs` como `OVERRIDE_CONVERSATION_ASSIGNMENT` con el usuario anterior.
  5. Al devolver la conversación, pasa a `pending`, se limpia `assigned_user_id` y el bot retoma las respuestas. `handoff_reason` y `handed_off_at` se conservan como historial de la última derivación.
  6. Las decisiones de negocio (aprobación del adelanto, sobrecupo, rechazo de comprobante) se mantienen en el panel de EventPro y no se toman desde la conversación.
* **Salidas:** Conversación con `mode`, `status`, `assigned_user_id`, `handoff_reason` y `handoff_summary` actualizados en `conversation_links` y en Chatwoot; aviso al cliente cuando deriva el bot. Si Chatwoot no responde, la toma y la devolución fallan con `503` (`messaging-gateway-unavailable`).
* **Reglas Asociadas:** RN-10, PC-13.
* **Endpoints:** `POST /conversations/{id}/takeover`, `POST /conversations/{id}/release`, `POST /webhooks/chatwoot` (módulos 2.14 y 2.8).
* **Prioridad:** Alta.

---

### RF-31: Bandeja de Conversaciones en EventPro
* **Descripción:** El sistema debe ofrecer a los encargados una bandeja dentro de EventPro para listar las conversaciones de WhatsApp, leer sus mensajes y responder a los clientes, sin exponer Chatwoot al usuario. Chatwoot es la fuente de verdad de mensajes, medios y estados de entrega; EventPro no duplica mensajes y solo almacena el vínculo de negocio (`conversation_links`).
* **Entradas:** Filtros de la bandeja (`mode`: `BOT` o `HUMAN`; `assigned`: `me` o `unassigned`; `include_resolved`; paginación); identificador de conversación; mensaje a enviar (texto, adjunto o plantilla aprobada); identificador de adjunto.
* **Procesamiento:**
  1. **Listado:** devolver las conversaciones ordenadas por último mensaje, con cliente, cotización vinculada, `status`, `mode`, encargado asignado, motivo del traspaso, vista previa del último mensaje y estado de la ventana de servicio de 24 h. Por defecto se excluyen las conversaciones `resolved`.
  2. **Lectura:** obtener los mensajes de la conversación desde Chatwoot con paginación por cursor, indicando dirección, autor (`CLIENT`, `BOT` o `AGENT`) y estado de entrega.
  3. **Respuesta:** solo puede enviar mensajes el encargado que tomó la conversación (`status = open` y `assigned_user_id` igual al usuario autenticado); en otro caso se rechaza con `conversation-not-taken` o `conversation-taken-by-other`. El mensaje se encola en `outbox_messages` y la respuesta es `202` con estado `QUEUED`; el autor real se registra en `audit_logs` (`SEND_CONVERSATION_MESSAGE`).
  4. **Ventana de servicio de 24 h:** `service_window_open` es verdadero mientras no hayan transcurrido 24 horas desde el último mensaje entrante del cliente. Con la ventana cerrada solo se admiten plantillas aprobadas; un texto libre se rechaza con `service-window-closed`.
  5. **Medios:** los adjuntos (imágenes, comprobantes, documentos) se sirven únicamente mediante el proxy autenticado `GET /conversations/{id}/attachments/{attachment_id}`; las URL de Chatwoot nunca llegan al navegador. La lectura de medios no exige haber tomado la conversación.
  6. **Fallas de entrega:** un mensaje con estado `FAILED` muestra un motivo legible (por ejemplo, ventana de 24 h cerrada o número fuera de los destinatarios de prueba). Si el envío agotó sus reintentos, la bandeja ofrece «Reintentar», que vuelve a enviar el mensaje (nuevo `POST /conversations/{id}/messages`).
  7. Acceso restringido a los roles `ENCARGADO` y `SUPERADMIN`.
* **Salidas:** Bandeja filtrable, hilo de mensajes con estados de entrega y adjuntos visibles, mensaje aceptado para envío (`QUEUED`) o error de negocio identificado por su código.
* **Reglas Asociadas:** RN-10, RN-11, RNF-03.2.
* **Endpoints:** `GET /conversations`, `GET /conversations/{id}/messages`, `POST /conversations/{id}/messages`, `GET /conversations/{id}/attachments/{attachment_id}` (módulo 2.14).
* **Prioridad:** Alta.

---

### RF-32: Actualización en Tiempo Real de la Bandeja
* **Descripción:** El sistema debe mantener actualizada la bandeja de los encargados sin recargar la página: mensajes nuevos, cambios de estado o asignación, cambios en el estado de entrega y avisos de nuevas derivaciones del bot.
* **Entradas:** Eventos recibidos por el worker desde Chatwoot (`POST /webhooks/chatwoot`) y cambios hechos desde EventPro; conexión SSE del encargado con su access token (`access_token`).
* **Procesamiento:**
  1. Publicar por Server-Sent Events los eventos `conversation.updated`, `message.created`, `message.updated` y `handoff.requested`.
  2. Autenticar el stream con el access token en el parámetro de consulta `access_token` (`EventSource` no admite cabeceras personalizadas); el servidor cierra el stream al vencer el token y el cliente renueva la sesión y se reconecta.
  3. No existe búfer de reenvío: tras una desconexión, el cliente se reconecta automáticamente y vuelve a solicitar la bandeja completa para recuperar el estado.
* **Salidas:** Flujo de eventos en tiempo real (`text/event-stream`) con latido periódico para mantener la conexión.
* **Reglas Asociadas:** RN-10.
* **Endpoints:** `GET /conversations/stream` (módulo 2.14).
* **Prioridad:** Media.
