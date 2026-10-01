# 04. Matriz de Reglas de Negocio y Procesos de Control

---

## 1. Reglas de Negocio del Sistema (RN)

### RN-01: Estructura de la Cotización Económica
El precio final a cobrar al cliente se determina de acuerdo con la fórmula:
$$\text{Total Cotizado} = \text{Precio Paquete Base} + \sum_{i=1}^{n} \text{Precio Extra}_i + \text{Costo Movilidad}$$
* Los precios de los paquetes y de los extras se encuentran tabulados en el catálogo del sistema.
* La movilidad se calcula de forma independiente y se suma al consolidado final.

---

### RN-02: Determinación del Adelanto y Saldo Pendiente
Para mitigar el riesgo de cancelación sin sobrecargar financieramente al cliente al momento de reservar:
$$\text{Monto Adelanto (10%)} = 0.10 \times \left( \text{Precio Paquete Base} + \sum_{i=1}^{n} \text{Precio Extra}_i \right)$$
$$\text{Saldo Pendiente} = \text{Total Cotizado} - \text{Monto Adelanto}$$
> **Importante:** La movilidad no se incluye dentro de la base de cálculo del 10% del adelanto. El costo íntegro de la movilidad se liquida el día del evento como parte del saldo pendiente.

---

### RN-03: Cálculo de Movilidad con Margen Comercial
1. La movilidad cubre el desplazamiento de **ida y vuelta** del personal y equipos desde la base de operaciones hasta el lugar del evento.
2. La distancia ($D$) en kilómetros y la duración ($T$) en minutos son calculadas mediante la API de Google Maps.
3. Se aplica un recargo comercial de seguridad del **15%**:
$$\text{Movilidad Base} = f(D_{\text{ida+vuelta}}, T_{\text{ida+vuelta}})$$
$$\text{Costo Movilidad} = \text{Movilidad Base} \times 1.15$$
4. **Excepción de Transporte del Cliente:** Si el cliente opta por brindar movilidad propia de ida y vuelta para el elenco, el costo de movilidad se fija en **S/. 0.00**.

---

### RN-04: Disponibilidad de Recursos y Aprobación por Umbral
1. La disponibilidad de un show u hora loca depende de la conformación de grupos con el personal freelance registrado y activo.
2. La disponibilidad de servicios de decoración y toldos depende estrictamente del stock de inventario disponible en esa fecha y horario.
3. **Simultaneidad por solapamiento real de intervalos:** dos shows son simultáneos cuando sus intervalos $[\text{inicio}, \text{fin})$ se solapan, con $\text{fin} = \text{inicio} + \text{duración del paquete}$. No se utilizan bloques horarios fijos.
4. **Eventos que cuentan para el umbral:** solo los eventos con adelanto validado y que no estén en estado `CANCELLED`. Las cotizaciones sin adelanto validado no reservan cupo y no cuentan.
5. **Umbral de Concurrencia** (`SIMULTANEOUS_SHOWS_THRESHOLD`, por defecto `3`):
   * Si, al incorporar el show solicitado, la cantidad de shows simultáneos es **$\le 3$**, la asignación es automática.
   * Si la cantidad **supera 3** (el show solicitado sería el cuarto simultáneo), el sistema bloquea la confirmación automática y exige la **aprobación manual expresa** de un encargado.
6. **La aprobación manual es un estado del pago** (`REQUIRES_MANUAL_APPROVAL`), no una bandera del evento. El encargado puede aprobar el sobrecupo (el pago pasa a `VERIFIED`) o rechazarlo (el pago pasa a `REFUND_PENDING`).

---

### RN-05: Intervalo Obligatorio de Tránsito entre Shows Sucesivos
Para un mismo grupo de artistas asignado a múltiples presentaciones en el mismo día:
$$\text{Intervalo Mínimo} = \text{Tiempo de Tránsito (Google Maps)} + \text{Margen de Desarme y Descanso (30 min)}$$
* Si el intervalo entre el fin del Evento $A$ y el inicio del Evento $B$ es menor al intervalo mínimo, el sistema alerta sobre solapamiento y rechaza la asignación automática, derivando el caso a revisión del encargado.

---

### RN-06: Condición Sine Qua Non de Inicio del Show
* **Ningún show, armado de toldo ni ambientación puede dar inicio sin que se haya cobrado el 100% del saldo pendiente (saldo de servicios + movilidad).**
* El personal del elenco o encargado en sitio debe registrar el cobro (vía Yape, transferencia o efectivo) para habilitar el cambio de estado del evento a `IN_PROGRESS` («En ejecución»).

---

### RN-07: Extensiones de Show y Liquidación Post-Evento
* Si el cliente solicita prolongar la duración del show o mantener tiempo de espera durante el evento, la tarifa adicional por hora o fracción debe registrarse como «Extensión en Vivo».
* Este concepto se añade a la liquidación final antes de marcar el evento como `SETTLED` («Liquidado»).

---

### RN-08: Cálculo de Utilidad Neta y Costos Fijos
La rentabilidad del negocio se audita comparando los ingresos reales contra los costos directos fijos:
$$\text{Utilidad Neta} = \text{Ingresos Totales Liquidados} - \left( \sum \text{Costo Fijo Paquetes} + \sum \text{Costo Fijo Extras} + \text{Costos Operativos de Movilidad} \right)$$
* Los costos asignados a cada paquete y extra representan las tarifas fijas acordadas con el elenco freelance, DJ y armadores.

---

### RN-09: Plazo del Adelanto, Vigencia de la Cotización y Revalidación de Disponibilidad
1. **Plazo del adelanto:** la cotización tiene una vigencia de `ADVANCE_DEADLINE_HOURS` horas (por defecto `24`) contadas desde su envío al cliente. Si vence el plazo sin que se reciba un comprobante, la cotización pasa a `EXPIRED`. Una cotización con comprobante ya recibido no vence mientras el pago esté en verificación.
2. **Sin reserva previa:** una cotización sin adelanto validado **no reserva cupo**. El cupo solo queda asegurado cuando el adelanto es validado y se crea el evento.
3. **Mensaje de cotización:** no contiene datos de pago. Advierte que la fecha y el horario solo quedan asegurados tras la validación del adelanto, informa el plazo y ofrece el botón «Pagar adelanto».
4. **Revalidación al pulsar «Pagar adelanto»:** si han transcurrido más de `AVAILABILITY_RECHECK_MINUTES` minutos (por defecto `60`) desde el envío de la cotización, el bot revalida la disponibilidad antes de mostrar los datos de Yape, Plin o cuenta bancaria. Si hay cupo, muestra los datos de pago y la cotización pasa a `PAYMENT_STARTED`. Si no hay cupo, ofrece otra fecha u horario o derivar la conversación a un encargado, y no revela datos de pago.
5. **Revalidación temprana al subir el comprobante:** si el cupo ya no está disponible, el pago ingresa en `REQUIRES_MANUAL_APPROVAL` en lugar de `PENDING_VERIFICATION` (alerta temprana, no autoritativa).
6. **Revalidación autoritativa al validar el pago:** se ejecuta de forma atómica bajo bloqueo distribuido (Redis lock, ADR-06) antes de confirmar. Si el cupo está lleno, el encargado decide: aprobar el sobrecupo (el pago pasa a `VERIFIED`) o rechazar (el pago pasa a `REFUND_PENDING` y luego a `REFUNDED` al efectuarse la devolución).

---

## 2. Matriz de Procesos de Control y Sobrescritura (*Overrides*)

| # | Proceso de Control | Tipo | Condición de Activación | Mecanismo de Control |
| :-: | :--- | :--- | :--- | :--- |
| **PC-01** | **Verificación de Recursos** | Automático | Al cotizar fecha y hora | Cruce contra agenda de personal e inventario físico de toldos/decoración. |
| **PC-02** | **Ajuste de Intervalos** | Híbrido | Tránsito entre shows del mismo elenco | El sistema sugiere tiempo de tránsito por Google Maps; el encargado tiene facultad de editar el intervalo. |
| **PC-03** | **Umbral de Shows Simultáneos** | Manual | Solapamiento real de intervalos $[\text{inicio}, \text{fin})$ con más de `SIMULTANEOUS_SHOWS_THRESHOLD` (3) eventos con adelanto validado y no cancelados | El pago pasa a `REQUIRES_MANUAL_APPROVAL`; notificación al encargado con panel de aprobación o rechazo manual. |
| **PC-04** | **Override de Movilidad** | Manual | Previa emisión de cotización/contrato | El encargado puede modificar a criterio el monto sugerido de movilidad. |
| **PC-05** | **Modo Manual de Contrato** | Manual | A requerimiento del administrador | Formulario administrativo para armar contratos omitiendo el bot de WhatsApp. |
| **PC-06** | **Validación de Pagos con Reintento** | Híbrido | Al subir captura de comprobante | Si el comprobante es inválido, el sistema envía recordatorio y habilita reintento sin cancelar la cotización. |
| **PC-07** | **Control de Inicio de Show** | Operativo | Llegada del personal a locación | Bloqueo del inicio del servicio hasta validar cobro del saldo restante. |
| **PC-08** | **Liquidación de Horas Extra** | Operativo | Al finalizar el show | Registro formal de montos por tiempo adicional previo al cierre del evento. |
| **PC-09** | **Trazabilidad Contable Fija** | Automático | Cierre semanal y mensual | Uso de costos fijos precargados para asegurar reportes contables auditables. |
| **PC-10** | **Persistencia de Observaciones** | Estructural | Registro de cotización y contrato | Almacenamiento en campo específico visible en PDF y cronograma para evitar extravíos. |
| **PC-11** | **Revalidación de Disponibilidad y Vencimiento de Adelanto** | Automático | Al pulsar «Pagar adelanto» (más de `AVAILABILITY_RECHECK_MINUTES`), al subir comprobante y al validar el pago; y al vencer `ADVANCE_DEADLINE_HOURS` | Revalidación con bloqueo distribuido (Redis lock) en la validación; la cotización pasa a `EXPIRED` al vencer el plazo; si no hay cupo se ofrece otro horario o derivación al encargado. |

---

## 3. Máquinas de Estados

El sistema maneja **cuatro ciclos de vida independientes**: cotización, pago, evento y contrato. Los códigos de estado son identificadores en inglés (`UPPER_SNAKE_CASE`) y se usan tal cual en el código, en las restricciones `CHECK` de la base de datos y en los *payloads* de la API. La etiqueta en español es solo para la interfaz de usuario. **Esta sección es la fuente única de verdad**: los demás documentos deben referenciarla en lugar de duplicarla.

### 3.1 Ciclo de Vida de la Cotización
```mermaid
stateDiagram-v2
    [*] --> SENT: Cotización enviada por WhatsApp
    SENT --> PAYMENT_STARTED: Cliente pulsa «Pagar adelanto»
    SENT --> EXPIRED: Vence ADVANCE_DEADLINE_HOURS sin comprobante
    PAYMENT_STARTED --> CONVERTED: Adelanto validado y evento creado
    PAYMENT_STARTED --> EXPIRED: Vence ADVANCE_DEADLINE_HOURS sin comprobante
    SENT --> CANCELLED: Cliente o encargado cancela
    PAYMENT_STARTED --> CANCELLED: Cliente o encargado cancela
    CONVERTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
```

### 3.2 Ciclo de Vida del Pago
```mermaid
stateDiagram-v2
    [*] --> PENDING_VERIFICATION: Comprobante recibido con cupo disponible
    [*] --> REQUIRES_MANUAL_APPROVAL: Comprobante recibido sin cupo o sobre el umbral
    PENDING_VERIFICATION --> VERIFIED: Encargado aprueba y la revalidación atómica confirma cupo
    PENDING_VERIFICATION --> REJECTED: Comprobante inválido o ilegible
    PENDING_VERIFICATION --> REQUIRES_MANUAL_APPROVAL: Revalidación atómica detecta cupo lleno
    REQUIRES_MANUAL_APPROVAL --> VERIFIED: Encargado aprueba el sobrecupo
    REQUIRES_MANUAL_APPROVAL --> REFUND_PENDING: Encargado rechaza el sobrecupo
    REFUND_PENDING --> REFUNDED: Devolución efectuada
    VERIFIED --> [*]
    REJECTED --> [*]
    REFUNDED --> [*]
```
> Un pago `REJECTED` permite reintento: el cliente envía un nuevo comprobante y se crea un nuevo registro de pago, sin cancelar la cotización.

### 3.3 Ciclo de Vida del Evento
El evento se crea únicamente cuando el adelanto es validado.
```mermaid
stateDiagram-v2
    [*] --> AWAITING_SIGNATURE: Adelanto validado, evento creado
    AWAITING_SIGNATURE --> SCHEDULED: Cliente firma el contrato
    SCHEDULED --> AWAITING_BALANCE: Personal llega al lugar del evento
    AWAITING_BALANCE --> IN_PROGRESS: Saldo y movilidad cobrados
    IN_PROGRESS --> EXTENDED: Cliente solicita tiempo adicional
    EXTENDED --> SETTLED: Cobro de extensión registrado
    IN_PROGRESS --> SETTLED: Show culminado sin extensiones
    AWAITING_SIGNATURE --> CANCELLED: Cancelación antes de la ejecución
    SCHEDULED --> CANCELLED: Cancelación antes de la ejecución
    AWAITING_BALANCE --> CANCELLED: Cancelación antes de la ejecución
    SETTLED --> [*]
    CANCELLED --> [*]
```

### 3.4 Ciclo de Vida del Contrato
```mermaid
stateDiagram-v2
    [*] --> DRAFT: Contrato creado (automático o modo manual)
    DRAFT --> ISSUED: PDF compilado y enviado con enlace de firma
    ISSUED --> SIGNED: Cliente firma digitalmente
    DRAFT --> VOIDED: Anulación
    ISSUED --> VOIDED: Anulación
    SIGNED --> VOIDED: Cancelación del evento antes de su ejecución
    SIGNED --> [*]
    VOIDED --> [*]
```

### 3.5 Tabla de Mapeo: Código, Etiqueta de Interfaz y Significado

| Ciclo | Código | Etiqueta en la interfaz (español) | Significado |
| :--- | :--- | :--- | :--- |
| Cotización | `SENT` | Cotizado | Cotización enviada al cliente; dentro del plazo de vigencia y sin comprobante. No reserva cupo. |
| Cotización | `PAYMENT_STARTED` | Pago iniciado | El cliente pulsó «Pagar adelanto» y se le mostraron los datos de pago. |
| Cotización | `CONVERTED` | Convertida | El adelanto fue validado y se creó el evento. |
| Cotización | `EXPIRED` | Vencida | Venció `ADVANCE_DEADLINE_HOURS` sin comprobante recibido. |
| Cotización | `CANCELLED` | Cancelada | Cancelada por el cliente o por el encargado antes de convertirse. |
| Pago | `PENDING_VERIFICATION` | Pendiente de verificación | Comprobante recibido y en cola de revisión del encargado. |
| Pago | `REQUIRES_MANUAL_APPROVAL` | Requiere aprobación manual | Cupo lleno o umbral de shows simultáneos superado; el encargado debe decidir. |
| Pago | `VERIFIED` | Verificado | Adelanto validado; habilita la creación del evento. |
| Pago | `REJECTED` | Rechazado | Comprobante inválido o ilegible; se permite reintento con un nuevo pago. |
| Pago | `REFUND_PENDING` | Devolución pendiente | Sobrecupo rechazado; el adelanto debe devolverse al cliente. |
| Pago | `REFUNDED` | Devuelto | Devolución del adelanto efectuada. |
| Evento | `AWAITING_SIGNATURE` | Pendiente de firma | Evento creado con adelanto validado; el contrato espera la firma del cliente. |
| Evento | `SCHEDULED` | Agendado | Contrato firmado; evento registrado en el cronograma. |
| Evento | `AWAITING_BALANCE` | En espera de cobro | El personal llegó al lugar; falta cobrar el saldo y la movilidad. |
| Evento | `IN_PROGRESS` | En ejecución | Saldo cobrado al 100%; el show está en curso. |
| Evento | `EXTENDED` | Con extensión | El cliente solicitó tiempo adicional durante el show. |
| Evento | `SETTLED` | Liquidado | Evento cerrado con todos los cobros registrados. |
| Evento | `CANCELLED` | Cancelado | Cancelado desde cualquier estado previo a `IN_PROGRESS`; deja de contar para el umbral de simultaneidad. |
| Contrato | `DRAFT` | Borrador | Creado automáticamente al validar el adelanto o generado en modo manual. |
| Contrato | `ISSUED` | Emitido, pendiente de firma | PDF compilado y enviado con enlace de firma digital. |
| Contrato | `SIGNED` | Firmado | Sellado digitalmente con la firma del cliente y metadatos de validación. |
| Contrato | `VOIDED` | Anulado | Anulado por cancelación del evento antes de su ejecución u otra causa administrativa. |
