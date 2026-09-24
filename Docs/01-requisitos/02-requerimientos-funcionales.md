# 02. Especificación de Requerimientos Funcionales (RF)

---

## 1. Módulo M01: Canal WhatsApp y Captura de Pedidos

### RF-01: Atención Automatizada y Saludo Inicial
* **Descripción:** El sistema debe procesar los mensajes entrantes de clientes mediante un Webhook conectado a la API de WhatsApp Business y responder de manera automatizada con un mensaje de bienvenida y el catálogo estructurado de servicios.
* **Entradas:** Mensaje entrante vía webhook de WhatsApp (número de teléfono del remitente, identificador de mensaje, texto o payload de botón).
* **Procesamiento:** 
  1. Verificar si el número de teléfono corresponde a un cliente con una cotización o conversación activa.
  2. Si no existe conversación activa, inicializar una nueva sesión de atención.
  3. Despachar mensaje de saludo inicial junto con el menú principal de opciones interactivas.
* **Salidas:** Mensaje interactivo de WhatsApp despachado al cliente (HTTP 200 al Webhook).
* **Reglas Asociadas:** PC-10.
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
* **Salidas:** Registro preliminar de la solicitud de evento en estado `BORRADOR`.
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
* **Descripción:** El sistema debe componer un mensaje estructurado y legible con el desglose comercial de la cotización y transmitirlo automáticamente al cliente a través del chat de WhatsApp.
* **Entradas:** Identificador de la cotización calculada y número de WhatsApp del cliente.
* **Procesamiento:** Generar plantilla de texto con detalle de paquete, temática, extras, movilidad, monto total, monto de adelanto requerido (10%) y canales de pago disponibles (número de Yape / cuentas bancarias).
* **Salidas:** Mensaje enviado por la API de WhatsApp con cambio de estado de la cotización a `COTIZADO`.
* **Prioridad:** Alta.

---

## 4. Módulo M04: Verificación de Disponibilidad y Capacidad

### RF-09: Verificación de Disponibilidad de Recursos e Inventario
* **Descripción:** Antes de habilitar la aceptación de una cotización, el sistema debe comprobar la factibilidad operativa del evento contrastando los recursos solicitados contra la programación existente.
* **Entradas:** Fecha, bloque horario, tipo de paquete, extras solicitados y requerimientos de infraestructura (toldos/decoración).
* **Procesamiento:**
  1. Para shows y animación: Comprobar disponibilidad de artistas freelance registrados en la categoría requerida.
  2. Para toldos y decoración: Comprobar que el inventario físico de estructuras y telas no se encuentre asignado a otro evento en la misma ventana de tiempo.
* **Salidas:** Estado de disponibilidad (`DISPONIBLE`, `CON_CONFLICTO`, `REQUIERE_APROBACION`).
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
  2. Vincular el registro de pago a la cotización en estado `PAGO_EN_REVISION`.
* **Salidas:** Comprobante almacenado y cotización en cola de verificación.
* **Prioridad:** Alta.

---

### RF-12: Validación de Pago y Flujo de Reintento
* **Descripción:** El sistema debe permitir validar el comprobante de pago. En caso de inconsistencia o ilegibilidad, debe emitir una notificación automática al cliente solicitando un nuevo comprobante.
* **Entradas:** Dictamen de validación (Aprobado / Rechazado con motivo).
* **Procesamiento:**
  * Si es aprobado: Cambiar estado del evento a `ADELANTO_CONFIRMADO` y disparar generación de contrato.
  * Si es rechazado: Cambiar estado a `PAGO_RECHAZADO` y enviar mensaje vía WhatsApp con el motivo del rechazo y botón/instrucción de reintento.
* **Salidas:** Estado actualizado y notificación de WhatsApp emitida.
* **Reglas Asociadas:** PC-06.
* **Prioridad:** Alta.

---

## 6. Módulo M06: Generación de Contratos y Firma Digital

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

### RF-15: Registro de Firma Digital / Electrónica
* **Descripción:** El sistema debe proveer una interfaz web responsiva y segura para que el cliente visualice el contrato generado y plasme su firma electrónica manuscrita.
* **Entradas:** Trazado de firma manuscrita en formato vectorial/PNG, dirección IP y metadatos de confirmación del cliente.
* **Procesamiento:**
  1. Estampar la imagen de la firma en la sección de firmas del contrato PDF.
  2. Registrar marca temporal (*timestamp*), dirección IP y cambiar estado a `CONTRATO_FIRMADO`.
  3. Despachar copia del contrato firmado al WhatsApp del cliente.
* **Salidas:** Contrato PDF final firmado y copia enviada al cliente.
* **Prioridad:** Alta.

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
* **Entradas:** Registro de cobro presencial (medio de pago: Yape, transferencia o efectivo; monto recibido; identificador de usuario que confirma).
* **Procesamiento:**
  1. Validar que el monto cobrado complete el 100% del saldo pendiente.
  2. Actualizar estado del evento a `EN_EJECUCION`.
* **Salidas:** Evento habilitado operativamente y registro contable de ingreso in-situ.
* **Reglas Asociadas:** RN-06, PC-07.
* **Prioridad:** Alta (Crítica).

---

### RF-19: Registro de Extensiones en Vivo y Liquidación Post-Evento
* **Descripción:** El sistema debe permitir registrar cargos adicionales solicitados por el cliente durante el evento (horas extra de show, tiempo extra de espera o servicios adicionales en caliente) y consolidar el cierre definitivo del evento.
* **Entradas:** Minutos/horas de extensión, tarifa pactada, medio de pago del extra.
* **Procesamiento:**
  1. Sumar el recargo extraordinario al total facturado del evento.
  2. Registrar el cobro y transicionar el estado del evento a `LIQUIDADO`.
* **Salidas:** Estado de evento `LIQUIDADO` y cierre de caja del servicio.
* **Reglas Asociadas:** RN-07, PC-08.
* **Prioridad:** Alta.

---

## 8. Módulo M08: Procesos de Control y Sobrescritura (Overrides) Manuales

### RF-20: Aprobación Manual por Umbral de Eventos Simultáneos
* **Descripción:** Si en una misma fecha y bloque horario se reciben solicitudes que superen el umbral configurable (por defecto: más de 3 shows simultáneos), el sistema debe detener la confirmación automática y exigir la autorización expresa de un encargado.
* **Entradas:** Solicitud de cotización entrante; umbral de concurrencia configurado en el sistema ($N = 3$).
* **Procesamiento:**
  1. Contar eventos activos en el intervalo temporal solicitado.
  2. Si $\text{eventos} > N$, marcar la solicitud como `REQUIERE_APROBACION_MANUAL` y notificar al encargado.
* **Salidas:** Notificación de alerta en panel administrativo con acciones de Aprobar / Rechazar / Reagendar.
* **Reglas Asociadas:** RN-04, PC-03.
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
* **Procesamiento:** Generar directamente el contrato en estado `BORRADOR` o `EMITIDO`, calculando liquidación económica y permitiendo su descarga o envío por enlace.
* **Salidas:** Contrato generado mediante flujo manual de respaldo.
* **Reglas Asociadas:** PC-05.
* **Prioridad:** Alta.

---

## 9. Módulo M09: Analítica Financiera y Dashboards

### RF-24: Consolidación Automática de Ingresos y Costos Fijos
* **Descripción:** El sistema debe procesar periódicamente (semanal y mensualmente) las métricas financieras del negocio contrastando ingresos totales contra costos fijos directos tabulados.
* **Entradas:** Base de datos de eventos en estado `LIQUIDADO` y tabla maestra de costos fijos de paquetes y extras.
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
