# 05. Historias de Usuario (User Stories) — EventPro

---

## 1. Introducción y Estándar Ágil

Las presentes **Historias de Usuario (US)** complementan la especificación de requerimientos de software de EventPro. Están estructuradas bajo el estándar de Scrum/Ágil:

* **Estructura de la Narrativa:**
  $$\text{Como } [\text{Rol}] \quad \text{quiero } [\text{Acción / Capacidad}] \quad \text{para } [\text{Beneficio de Negocio}]$$
* **Criterios de Aceptación:** Formulados bajo la sintaxis **Given-When-Then (Dado / Cuando / Entonces)**.
* **Priorización MoSCoW:** `Must have` (Crítico para MVP), `Should have` (Importante), `Could have` (Deseable).
* **Estimación:** Puntos de Historia (*Story Points* - SP) basados en la serie de Fibonacci (1, 2, 3, 5, 8).

---

## 2. Épica 1: Atención y Cotización Automatizada por WhatsApp

### US-01: Saludo Inicial y Presentación de Catálogo
* **Mapeo:** RF-01, RF-03
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** cliente interesado en celebrar un evento,
  * **Quiero** escribir a la línea de WhatsApp de la promotora y recibir un saludo inmediato con el menú de paquetes y temáticas,
  * **Para** conocer las opciones y precios disponibles sin esperar a que un encargado responda manualmente.
* **Criterios de Aceptación:**
  * **Dado que** un cliente envía un mensaje a la línea de WhatsApp fuera de una conversación en curso,
  * **Cuando** el sistema recibe el mensaje a través del gateway de mensajería (webhook de Chatwoot) y acusa recibo en menos de 1.5 segundos,
  * **Entonces** envía un saludo de bienvenida con botones/lista interactiva mostrando las categorías de servicio (Hora Loca, Shows Infantiles, Baby Showers, DJ, Toldos).

---

### US-02: Selección de Paquete, Temática y Extras Personalizados
* **Mapeo:** RF-03, RF-04
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** cliente,
  * **Quiero** seleccionar un paquete base (ej. Hora Loca Medium), asociarle una temática (ej. Selva) y agregar extras llamativos (ej. Gorila Gigante),
  * **Para** armar una propuesta a la medida de mi fiesta.
* **Criterios de Aceptación:**
  * **Dado que** el cliente eligió un paquete base,
  * **Cuando** el chatbot le consulta si desea personalizar su show,
  * **Entonces** le permite seleccionar una temática compatible y marcar uno o más extras del catálogo sin límite de combinación.

---

### US-03: Captura de Datos y Ubicación del Evento
* **Mapeo:** RF-02, RF-14
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** chatbot del sistema,
  * **Quiero** recopilar el nombre del cliente, teléfono, fecha, hora estimada y dirección exacta de la locación,
  * **Para** contar con los parámetros necesarios para verificar disponibilidad y calcular la movilidad.
* **Criterios de Aceptación:**
  * **Dado que** el cliente configuró su paquete y extras,
  * **Cuando** el bot solicita la fecha y ubicación,
  * **Entonces** valida que la fecha sea futura y que la dirección incluya distrito o coordenadas válidas de Lima/Callao.
  * **Dado que** el bot ya capturó los datos obligatorios del evento,
  * **Cuando** pregunta si el cliente tiene observaciones especiales (música no permitida, momento de ingreso del gorila gigante, restricciones de espacio o iluminación) y este responde con texto libre,
  * **Entonces** almacena el texto como observaciones de la cotización, que pasan al evento y al contrato; si el cliente no tiene observaciones, la pregunta es opcional y el flujo continúa.

---

### US-04: Cálculo Automatizado de Costo de Movilidad
* **Mapeo:** RF-05, RN-03
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** encargado del negocio,
  * **Quiero** que el sistema calcule automáticamente el costo de ida y vuelta del personal y equipos mediante Google Maps con un 15% de margen,
  * **Para** no perder tiempo cotizando a mano en apps como inDrive ni cobrar de menos por distancias largas.
* **Criterios de Aceptación:**
  * **Dado que** se conoce la dirección del evento y la base de la promotora,
  * **Cuando** el motor de cotización consulta la API de Google Maps,
  * **Entonces** computa la distancia y tiempo de ida y vuelta, aplica la tarifa base por km/tiempo y le añade exactamente el 15% comercial.

---

### US-05: Exención de Movilidad por Transporte Propio
* **Mapeo:** RF-06, RN-03
* **Prioridad:** Should have | **Estimación:** 1 SP
* **Narrativa:**
  * **Como** cliente que dispone de movilidad particular para recoger y retornar al elenco,
  * **Quiero** indicar que brindaré el transporte,
  * **Para** que no se me cobre recargo de movilidad en la cotización.
* **Criterios de Aceptación:**
  * **Dado que** el cliente selecciona la opción "Yo proveo la movilidad",
  * **Cuando** se liquida la cotización,
  * **Entonces** el costo de movilidad se fija en S/. 0.00 y se deja constancia en el resumen.

---

### US-06: Liquidación Económica Determinística (Total, Adelanto 10% y Saldo)
* **Mapeo:** RF-07, RN-01, RN-02
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado y como cliente,
  * **Quiero** que el total sume servicios y movilidad, pero que el adelanto del 10% se calcule únicamente sobre los servicios (sin incluir movilidad),
  * **Para** mantener una política comercial justa donde la movilidad se pague completa el día del evento junto con el saldo.
* **Criterios de Aceptación:**
  * **Dado que** un paquete cuesta S/. 1,000, los extras S/. 200 y la movilidad S/. 100,
  * **Cuando** el motor financiero procesa los montos,
  * **Entonces** el Total es S/. 1,300.00, el Adelanto requerido es S/. 120.00 (10% de S/. 1,200), y el Saldo pendiente es S/. 1,180.00 (S/. 1,080 de servicios + S/. 100 de movilidad).

---

### US-07: Envío del Resumen de Cotización al WhatsApp del Cliente
* **Mapeo:** RF-08, RN-09
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** cliente,
  * **Quiero** recibir en el chat un mensaje claro con el detalle de lo cotizado, el adelanto requerido y un botón para pagar,
  * **Para** tomar una decisión informada y proceder con el pago cuando esté listo.
* **Criterios de Aceptación:**
  * **Dado que** el sistema finalizó el cálculo,
  * **Cuando** se despacha la cotización,
  * **Entonces** el cliente recibe en WhatsApp el desglose detallado de ítems y totales, el plazo para pagar el adelanto (`ADVANCE_DEADLINE_HOURS`, por defecto 24 horas), una advertencia de que la fecha y el horario solo quedan asegurados cuando el adelanto es validado, y un botón «Pagar adelanto». El mensaje **no incluye** datos de Yape, Plin ni cuentas bancarias, y la cotización queda en estado `SENT`.
  * **Dado que** el cliente pulsa «Pagar adelanto» y han transcurrido más de `AVAILABILITY_RECHECK_MINUTES` minutos (por defecto 60) desde el envío,
  * **Cuando** el bot revalida la disponibilidad,
  * **Entonces** si hay cupo muestra los datos de Yape, Plin o cuenta bancaria y la cotización pasa a `PAYMENT_STARTED`; si no hay cupo ofrece otra fecha u horario o derivar a un encargado, sin revelar datos de pago.
  * **Dado que** transcurre `ADVANCE_DEADLINE_HOURS` sin que se reciba un comprobante,
  * **Cuando** vence el plazo,
  * **Entonces** la cotización pasa a `EXPIRED` y no retiene cupo.

---

## 3. Épica 2: Verificación de Disponibilidad y Procesos de Control

### US-08: Validación de Capacidad de Elencos e Inventario
* **Mapeo:** RF-09, PC-01
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** que el sistema impida confirmar un show si no hay personal freelance disponible o si los toldos ya están comprometidos en ese horario,
  * **Para** evitar la sobreventa (*overbooking*) y no quedar mal con los clientes.
* **Criterios de Aceptación:**
  * **Dado que** un cliente solicita una fecha y un horario,
  * **Cuando** el sistema consulta la base de recursos,
  * **Entonces** si la capacidad está colmada, alerta al cliente ofreciendo otros horarios o derivando el caso al encargado.
  * **Dado que** la fecha solicitada requiere toldos o decoración,
  * **Cuando** el sistema consulta el stock de `inventory_items` contra las `inventory_reservations` activas en esa ventana,
  * **Entonces** informa `CONFLICT` si las unidades restantes no cubren el paquete, y al validar el adelanto registra la reserva de inventario del evento.

---

### US-09: Control de Tiempos de Traslado entre Shows Sucesivos
* **Mapeo:** RF-10, PC-02
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** que el sistema verifique que un mismo elenco tenga tiempo suficiente para trasladarse de un evento a otro considerando el tráfico y 30 min de descanso/desarme,
  * **Para** que los artistas no lleguen tarde a sus presentaciones.
* **Criterios de Aceptación:**
  * **Dado que** un elenco tiene un show de 18:00 a 19:00 en San Borja y se solicita otro a las 20:00 en Los Olivos,
  * **Cuando** el sistema calcula que el traslado requiere 75 minutos,
  * **Entonces** emite una alerta de solapamiento y rechaza la asignación automática por no cumplir con la ventana de seguridad.

---

### US-10: Aprobación Manual por Umbral de Más de 3 Shows Simultáneos
* **Mapeo:** RF-20, RN-04, PC-03
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** que cuando se solapen más de 3 shows (intervalos reales de inicio y fin) el sistema me pida autorización expresa antes de confirmar,
  * **Para** evaluar personalmente si cuento con suficientes grupos freelance de respaldo para asumir la demanda.
* **Criterios de Aceptación:**
  * **Dado que** ya existen 3 eventos con adelanto validado y no cancelados cuyos intervalos $[\text{inicio}, \text{fin})$ se solapan con el del nuevo pedido,
  * **Cuando** entra un 4.º pedido con comprobante de adelanto,
  * **Entonces** el sistema lleva el pago a `REQUIRES_MANUAL_APPROVAL` (no marca el evento) y envía una notificación al panel del encargado para Aprobar o Rechazar.
  * **Dado que** existen 3 eventos cuyos intervalos son contiguos pero no se solapan con el del nuevo pedido (por ejemplo, uno termina exactamente cuando el otro empieza),
  * **Cuando** entra el nuevo pedido,
  * **Entonces** no se exige aprobación manual.
  * **Dado que** existen cotizaciones sin adelanto validado o eventos `CANCELLED` en el mismo intervalo,
  * **Cuando** se cuenta el umbral (`SIMULTANEOUS_SHOWS_THRESHOLD`, por defecto 3),
  * **Entonces** esos registros no se consideran.

---

## 4. Épica 3: Gestión de Pagos, Comprobantes y Validación

### US-11: Recepción de Captura del Adelanto por Yape / Transferencia
* **Mapeo:** RF-11, RN-09
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** cliente que depositó el 10% de adelanto,
  * **Quiero** subir la captura de pantalla de mi comprobante por WhatsApp,
  * **Para** acreditar mi pago sin trámites presenciales.
* **Criterios de Aceptación:**
  * **Dado que** el cliente tiene una cotización vigente,
  * **Cuando** adjunta una imagen o PDF del comprobante en el chat de WhatsApp,
  * **Entonces** el sistema la asocia unívocamente a su cotización y registra el pago en estado `PENDING_VERIFICATION`.
  * **Dado que** al recibir el comprobante el cupo ya no está disponible o se supera el umbral de shows simultáneos,
  * **Cuando** el sistema ejecuta la revalidación temprana,
  * **Entonces** el pago ingresa en estado `REQUIRES_MANUAL_APPROVAL` en lugar de `PENDING_VERIFICATION`.

---

### US-12: Verificación de Pago y Flujo de Reintento
* **Mapeo:** RF-12, RN-09, PC-06
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** validar el comprobante recibido y, si no es legible o el monto está incompleto, rechazarlo indicando el motivo para que el bot pida reintentar,
  * **Para** no emitir contratos sin tener el dinero acreditado en cuenta.
* **Criterios de Aceptación:**
  * **Dado que** un comprobante es rechazado por el encargado con el motivo "Monto incompleto",
  * **Cuando** el sistema procesa el rechazo,
  * **Entonces** el pago pasa a `REJECTED` y se despacha un mensaje por WhatsApp al cliente informando el motivo y habilitando un botón para subir un nuevo comprobante.
  * **Dado que** un pago en `REQUIRES_MANUAL_APPROVAL` tiene un comprobante inválido o ilegible,
  * **Cuando** el encargado lo rechaza,
  * **Entonces** el pago pasa a `REJECTED` y se habilita el reintento, igual que desde `PENDING_VERIFICATION`.
  * **Dado que** el encargado aprueba un comprobante,
  * **Cuando** el sistema ejecuta la revalidación autoritativa y atómica (bloqueo Redis) y hay cupo,
  * **Entonces** el pago pasa a `VERIFIED`, la cotización a `CONVERTED` y se crea el evento en `AWAITING_SIGNATURE`.
  * **Dado que** al validar el pago el cupo ya está lleno,
  * **Cuando** el encargado decide,
  * **Entonces** puede aprobar el sobrecupo (el pago pasa a `VERIFIED`) o rechazarlo (el pago pasa a `REFUND_PENDING` y, tras la devolución, a `REFUNDED`).

---

## 5. Épica 4: Contratos Inteligentes y Firma Electrónica

### US-13: Compilación Automatizada del Contrato en PDF
* **Mapeo:** RF-13, RF-14
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** que el contrato se genere automáticamente en PDF con todos los datos del cliente, paquete, temática, extras, desglose de saldo y observaciones,
  * **Para** eliminar el proceso tedioso de copiar y modificar documentos Word antiguos.
* **Criterios de Aceptación:**
  * **Dado que** el adelanto ha sido verificado,
  * **Cuando** se dispara la emisión del contrato,
  * **Entonces** se compila un PDF formal con número correlativo (`CTR-2026-XXXX`), desglose claro de pagos y las notas especiales del cliente.
  * **Dado que** el evento tiene observaciones especiales registradas por el cliente en el chat o por el encargado en el panel,
  * **Cuando** se genera el contrato,
  * **Entonces** el PDF muestra las observaciones literales en una sección propia y visible, y el mismo texto queda disponible en el cronograma (US-16).
  * **Dado que** el encargado edita las observaciones de un evento antes de que el contrato sea firmado,
  * **Cuando** guarda el cambio,
  * **Entonces** el contrato en borrador se regenera con el texto actualizado y el cambio se registra en `audit_logs`.

---

### US-14: Emisión de Contratos en Modo Manual de Respaldo
* **Mapeo:** RF-23, PC-05
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** disponer de un formulario administrativo para armar un contrato a mano seleccionando los ítems pactados por llamada o chat tradicional,
  * **Para** atender clientes que no completaron el flujo del bot o ante fallas en WhatsApp.
* **Criterios de Aceptación:**
  * **Dado que** el encargado ingresa a la opción "Nuevo Contrato Manual",
  * **Cuando** completa los datos y montos pactados y presiona "Emitir",
  * **Entonces** el sistema registra al cliente, crea una cotización con `source = MANUAL`, genera el contrato PDF con bandera `is_manual_mode: true` y lo agenda en el cronograma una vez registrado y validado el adelanto.
  * **Dado que** el encargado completa el campo de observaciones especiales del formulario,
  * **Cuando** emite el contrato manual,
  * **Entonces** las observaciones se guardan en el evento y aparecen en el PDF y en el cronograma.

---

### US-15: Firma Electrónica del Contrato por el Cliente
* **Mapeo:** RF-15
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** cliente,
  * **Quiero** recibir un enlace por WhatsApp, revisar el contrato, confirmar mi identidad con un código y trazar mi firma con el dedo,
  * **Para** formalizar el acuerdo de inmediato sin imprimir papel.
* **Criterios de Aceptación:**
  * **Dado que** el cliente abre el enlace de firma recibido por WhatsApp y revisa el PDF,
  * **Cuando** ingresa el código OTP de 6 dígitos que recibe por WhatsApp, dibuja su firma manuscrita y acepta los términos,
  * **Entonces** el sistema sella el PDF con PAdES (pyHanko + PKCS#12, con marca de tiempo RFC 3161 opcional), registra el SHA-256 del PDF sellado, la IP, el agente de usuario y las marcas de tiempo en la bitácora de auditoría, y envía la copia final firmada a su chat.
  * **Dado que** el OTP expiró o se superó el máximo de intentos fallidos,
  * **Cuando** el cliente intenta continuar,
  * **Entonces** el sistema rechaza la firma y permite solicitar un nuevo OTP sin invalidar el enlace.
  * **Dado que** el enlace de firma expiró,
  * **Cuando** el cliente lo abre,
  * **Entonces** el sistema informa la expiración y el encargado puede reemitir el contrato.

---

## 6. Épica 5: Cronograma y Operación el Día del Evento

### US-16: Cronograma con Filtros y Visualización Rápida de Observaciones
* **Mapeo:** RF-16, RF-17, PC-10
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado y personal de elenco,
  * **Quiero** consultar la agenda con filtros por fecha y ver de inmediato las observaciones del cliente (bailes prohibidos, momento del gorila) en la tarjeta del evento,
  * **Para** no olvidar ningún detalle acordado antes de salir al show.
* **Criterios de Aceptación:**
  * **Dado que** el usuario visualiza el cronograma semanal,
  * **Cuando** revisa las tarjetas de los eventos,
  * **Entonces** visualiza un recuadro destacado con las observaciones especiales sin tener que abrir el documento PDF completo.

---

### US-17: Protocolo de Cobro Pre-Show y Bloqueo de Inicio
* **Mapeo:** RF-18, RN-06, PC-07
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado de la promotora,
  * **Quiero** que el sistema impida marcar un evento en ejecución si el personal en sitio no ha confirmado el cobro del 100% del saldo restante (servicios + movilidad),
  * **Para** garantizar que ningún show inicie sin haber liquidado el pago pendiente.
* **Criterios de Aceptación:**
  * **Dado que** el elenco llega a la locación y el evento está en `SCHEDULED` o `AWAITING_BALANCE`,
  * **Cuando** el operador intenta cambiar el estado a `IN_PROGRESS` sin registrar el cobro del saldo,
  * **Entonces** el sistema bloquea la acción con un mensaje de error exigiendo confirmar el medio, el monto y la evidencia (fotografía) del cobro in-situ.
  * **Dado que** el operador registra el cobro con medio de pago y fotografía de la pantalla de Yape/Plin o del efectivo,
  * **Cuando** confirma el cobro,
  * **Entonces** el pago `BALANCE` se registra directamente en `VERIFIED` con `audit_status = UNREVIEWED`, el evento pasa a `IN_PROGRESS` sin esperar al encargado, y este puede auditarlo después como `REVIEWED` o `FLAGGED`.

---

### US-18: Registro de Extensiones en Caliente y Cierre de Evento
* **Mapeo:** RF-19, RN-07, PC-08
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** operador del show,
  * **Quiero** registrar si el cliente solicitó 30 o 60 minutos adicionales de show o espera durante la fiesta,
  * **Para** sumar la tarifa extraordinaria pactada a la liquidación final antes de marcar el evento como liquidado.
* **Criterios de Aceptación:**
  * **Dado que** un show culminó pero el cliente pagó por media hora más,
  * **Cuando** se ingresa el cargo por tiempo extra,
  * **Entonces** se actualiza el ingreso total del evento y se transiciona su estado a `EXTENDED` y, al registrar el cobro, a `SETTLED`.
  * **Dado que** el operador registra el cobro de la extensión con medio de pago y fotografía como evidencia,
  * **Cuando** confirma el registro,
  * **Entonces** el pago `EXTENSION` queda en `VERIFIED` con `audit_status = UNREVIEWED` y el encargado lo audita después (`REVIEWED` o `FLAGGED`).

---

## 7. Épica 6: Procesos de Control y Sobrescrituras Manuales

### US-19: Sobrescritura (*Override*) Manual de Movilidad
* **Mapeo:** RF-21, PC-04
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** editar el monto de movilidad sugerido por Google Maps si conozco que la ruta tiene peajes atípicos o zonas de acceso complejo,
  * **Para** asegurar que la cotización refleje el gasto real de traslado.
* **Criterios de Aceptación:**
  * **Dado que** la cotización calculó S/. 60 de movilidad,
  * **Cuando** el encargado ingresa un ajuste manual a S/. 80 con su justificación,
  * **Entonces** el sistema recalcula el total y el saldo restante, conservando inalterado el adelanto del 10% de los servicios.

---

### US-20: Ajuste Manual de Intervalos de Traslado
* **Mapeo:** RF-22, PC-02
* **Prioridad:** Should have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** acortar o extender la ventana de tiempo sugerida entre dos shows de un mismo elenco,
  * **Para** adaptar la asignación cuando los eventos están muy cerca o se dispone de vehículo propio de alta velocidad.
* **Criterios de Aceptación:**
  * **Dado que** el sistema calculó 45 minutos de intervalo mínimo,
  * **Cuando** el encargado ingresa 35 minutos y confirma la asignación,
  * **Entonces** el sistema valida la excepción y registra la modificación en el log de auditoría.

---

## 8. Épica 7: Analítica Financiera y Dashboards

### US-21: Consolidación Automática de Ingresos vs. Costos Fijos
* **Mapeo:** RF-24, RN-08, PC-09
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** dueño/encargado de la promotora,
  * **Quiero** que el sistema calcule automáticamente cada semana y mes el balance de ingresos totales, costos fijos directos de elencos/extras y la ganancia neta real,
  * **Para** conocer la rentabilidad de mi negocio sin llevar cálculos manuales en cuadernos.
* **Criterios de Aceptación:**
  * **Dado que** finaliza una semana con 10 eventos liquidados,
  * **Cuando** se ejecuta la consolidación contable,
  * **Entonces** el sistema totaliza los cobros recibidos, descuenta los costos fijos tabulados de cada paquete y extra, y reporta la utilidad neta exacta.

---

### US-22: Dashboard Ejecutivo de Indicadores de Negocio
* **Mapeo:** RF-25
* **Prioridad:** Should have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** ver gráficos de barras y torta en el panel con el volumen de eventos por temática, los distritos más rentables y la demanda del Gorila Gigante,
  * **Para** tomar decisiones comerciales sobre qué servicios promocionar más en redes sociales.
* **Criterios de Aceptación:**
  * **Dado que** el encargado ingresa a la sección de reportes,
  * **Cuando** selecciona el mes actual,
  * **Entonces** el panel carga gráficos interactivos mostrando la comparación de rentabilidad vs. mes anterior y el ranking de extras contratados.

---

## 9. Épica 8: Administración de la Plataforma

### US-23: Gestión de Usuarios del Panel y Roles
* **Mapeo:** RF-26
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** superadministrador,
  * **Quiero** crear, editar, activar y desactivar las cuentas del panel y asignar su rol (`ENCARGADO`, `OPERADOR`),
  * **Para** controlar quién accede al sistema y con qué permisos, sin tocar la base de datos.
* **Criterios de Aceptación:**
  * **Dado que** el superadministrador completa nombre, correo, teléfono, contraseña inicial y rol,
  * **Cuando** crea el usuario,
  * **Entonces** la cuenta queda activa, la contraseña se guarda solo como hash Argon2id y no se devuelve en ninguna respuesta.
  * **Dado que** el correo o el teléfono ya pertenecen a otro usuario,
  * **Cuando** intenta crearlo,
  * **Entonces** el sistema rechaza la operación con un error de recurso duplicado.
  * **Dado que** el superadministrador desactiva un usuario o cambia su contraseña,
  * **Cuando** guarda el cambio,
  * **Entonces** todos los refresh tokens del usuario quedan revocados y no puede renovar su sesión.
  * **Dado que** el superadministrador intenta desactivarse a sí mismo o quitarse su propio rol,
  * **Cuando** envía el cambio,
  * **Entonces** el sistema lo rechaza.
  * **Dado que** un usuario con rol `ENCARGADO` u `OPERADOR` intenta acceder a la gestión de usuarios,
  * **Cuando** invoca el endpoint,
  * **Entonces** recibe un error de permiso denegado.

---

### US-24: Consulta de la Bitácora de Auditoría
* **Mapeo:** RF-27
* **Prioridad:** Should have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** encargado o superadministrador,
  * **Quiero** consultar quién hizo qué en las decisiones críticas (*overrides*, aprobaciones de sobrecupo, auditoría de cobros, contratos manuales y firmas),
  * **Para** tener trazabilidad ante disputas con clientes o errores de operación.
* **Criterios de Aceptación:**
  * **Dado que** existen registros de auditoría,
  * **Cuando** el encargado filtra por acción, entidad, usuario o rango de fechas,
  * **Entonces** el sistema devuelve una lista paginada, del más reciente al más antiguo, con usuario, acción, valores previos y posteriores, y marca de tiempo.
  * **Dado que** un usuario intenta modificar o eliminar un registro de la bitácora,
  * **Cuando** consulta los endpoints disponibles,
  * **Entonces** no existe ninguna operación de escritura: la bitácora es de solo lectura.
  * **Dado que** un usuario con rol `OPERADOR` intenta consultar la bitácora,
  * **Cuando** invoca el endpoint,
  * **Entonces** recibe un error de permiso denegado.

---

### US-25: Consulta de Clientes
* **Mapeo:** RF-28
* **Prioridad:** Should have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** buscar clientes por nombre o teléfono y ver su ficha,
  * **Para** atender recontrataciones y consultas sin revisar chats de WhatsApp uno por uno.
* **Criterios de Aceptación:**
  * **Dado que** un cliente generó una cotización por el bot o por un contrato manual,
  * **Cuando** el encargado lo busca por nombre o teléfono,
  * **Entonces** el sistema muestra su ficha con teléfono, nombre y DNI o RUC si fueron registrados, sin que exista un alta manual independiente.
  * **Dado que** un cliente vuelve a cotizar con el mismo número de WhatsApp,
  * **Cuando** se genera la nueva cotización,
  * **Entonces** el sistema reutiliza el cliente existente en lugar de duplicarlo.
  * **Dado que** un usuario con rol `OPERADOR` intenta listar clientes,
  * **Cuando** invoca el endpoint,
  * **Entonces** recibe un error de permiso denegado, porque son datos personales.

---

### US-26: Gestión de Elencos y Vinculación con Operadores
* **Mapeo:** RF-29
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** registrar los elencos freelance con su categoría de servicio y vincularlos a un usuario operador,
  * **Para** asignarlos a eventos y que cada operador vea únicamente sus propios eventos en su teléfono.
* **Criterios de Aceptación:**
  * **Dado que** el encargado registra un elenco con líder, teléfono y categoría de servicio,
  * **Cuando** lo guarda,
  * **Entonces** el elenco queda activo y disponible para el motor de disponibilidad y la asignación a eventos.
  * **Dado que** el encargado vincula el elenco con un usuario,
  * **Cuando** el usuario no tiene rol `OPERADOR` o ya está vinculado a otro elenco,
  * **Entonces** el sistema rechaza el vínculo.
  * **Dado que** un operador vinculado a un elenco inicia sesión,
  * **Cuando** consulta su agenda,
  * **Entonces** solo ve los eventos asignados a su elenco.
  * **Dado que** el encargado desactiva un elenco,
  * **Cuando** el sistema busca elencos para nuevas asignaciones,
  * **Entonces** el elenco desactivado no se ofrece.

---

## 10. Épica 9: Atención Humana y Bandeja de Conversaciones

### US-27: Solicitar Hablar con un Encargado
* **Mapeo:** RF-30, RN-10, PC-13
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** cliente que conversa con el bot por WhatsApp,
  * **Quiero** poder pedir que me atienda una persona, o ser derivado si el bot no logra entenderme,
  * **Para** resolver mi consulta sin quedarme atascado en el flujo automático.
* **Criterios de Aceptación:**
  * **Dado que** el cliente elige la opción «Hablar con un encargado» o lo escribe con texto equivalente,
  * **Cuando** el bot procesa el mensaje,
  * **Entonces** responde «Te comunico con un encargado», la conversación pasa a `open` sin asignar con `handoff_reason = CLIENT_REQUEST` y un `handoff_summary` (datos capturados y cotización vigente), y el bot deja de responder.
  * **Dado que** el bot no entiende dos mensajes consecutivos del cliente,
  * **Cuando** procesa el segundo mensaje,
  * **Entonces** deriva la conversación con `handoff_reason = BOT_NOT_UNDERSTOOD`.
  * **Dado que** el bot sufre una excepción no controlada al procesar un mensaje,
  * **Cuando** captura el error,
  * **Entonces** responde «Tuvimos un problema, te comunico con un encargado» y deriva con `handoff_reason = BOT_ERROR`.
  * **Dado que** la conversación está `open` (modo `HUMAN`),
  * **Cuando** el cliente envía nuevos mensajes,
  * **Entonces** el bot no responde y los mensajes quedan disponibles para el encargado.

---

### US-28: Tomar una Conversación y Responder desde EventPro
* **Mapeo:** RF-30, RF-31, RN-10, RN-11
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** tomar una conversación derivada y responder al cliente desde la plataforma EventPro,
  * **Para** atender el caso sin abrir otra herramienta y sin que el bot interfiera.
* **Criterios de Aceptación:**
  * **Dado que** existe una conversación derivada sin asignar,
  * **Cuando** el encargado ejecuta «Tomar conversación»,
  * **Entonces** la conversación queda `open` y asignada a él, y se conserva el motivo original de la derivación.
  * **Dado que** el encargado no ha tomado la conversación (modo `BOT` o asignada a otro encargado),
  * **Cuando** intenta enviar un mensaje,
  * **Entonces** el sistema lo rechaza con `conversation-not-taken` o `conversation-taken-by-other`, y la interfaz le ofrece tomar la conversación cuando corresponde.
  * **Dado que** el encargado tomó la conversación y la ventana de 24 h está abierta,
  * **Cuando** envía un texto o un adjunto,
  * **Entonces** el mensaje se acepta con estado `QUEUED`, se entrega al cliente por WhatsApp y el autor real queda registrado en `audit_logs`.
  * **Dado que** la ventana de 24 h está cerrada,
  * **Cuando** el encargado intenta enviar texto libre,
  * **Entonces** el sistema lo rechaza con `service-window-closed` y la interfaz solo permite elegir una plantilla aprobada.
  * **Dado que** el cliente envió una imagen o un comprobante en el chat,
  * **Cuando** el encargado abre la conversación,
  * **Entonces** visualiza el adjunto mediante el proxy autenticado de EventPro, sin que el navegador acceda a Chatwoot.

---

### US-29: Devolver la Conversación al Bot
* **Mapeo:** RF-30, RN-10
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** encargado que terminó de atender a un cliente,
  * **Quiero** devolver la conversación al bot,
  * **Para** que el flujo automático continúe con el cliente sin que yo deba seguir pendiente del chat.
* **Criterios de Aceptación:**
  * **Dado que** el encargado tiene asignada una conversación `open`,
  * **Cuando** ejecuta «Devolver al bot»,
  * **Entonces** la conversación pasa a `pending`, se limpia el encargado asignado, el bot retoma las respuestas y el motivo de la última derivación se conserva como historial.
  * **Dado que** la conversación está asignada a otro encargado,
  * **Cuando** un `ENCARGADO` intenta devolverla,
  * **Entonces** el sistema responde `conversation-taken-by-other`; solo la puede devolver el encargado asignado o un `SUPERADMIN`.
  * **Dado que** la conversación ya está en `pending`,
  * **Cuando** se ejecuta la devolución,
  * **Entonces** la operación no produce cambios y responde correctamente.

---

### US-30: Bandeja de Conversaciones y Motivos de Falla de Envío
* **Mapeo:** RF-31, RN-10, RN-11
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** ver una bandeja con las conversaciones de WhatsApp, filtrarlas y entender por qué falló un mensaje,
  * **Para** priorizar a quién atender y reenviar los mensajes que no llegaron.
* **Criterios de Aceptación:**
  * **Dado que** existen conversaciones atendidas por el bot, por encargados y derivaciones sin asignar,
  * **Cuando** el encargado filtra por modo (`BOT` o `HUMAN`) o por «asignadas a mí» o «sin asignar»,
  * **Entonces** la bandeja muestra el cliente, el modo, el motivo de traspaso con su etiqueta en español, la vista previa del último mensaje y si la ventana de 24 h sigue abierta.
  * **Dado que** un mensaje saliente tiene estado de entrega `FAILED`,
  * **Cuando** el encargado abre el hilo,
  * **Entonces** ve un motivo legible en español (por ejemplo, «La ventana de 24 horas está cerrada» o «El número no está entre los destinatarios de prueba») y, si se agotaron los reintentos del envío, un botón «Reintentar» que vuelve a enviar el mensaje.
  * **Dado que** Chatwoot no está disponible,
  * **Cuando** el encargado abre la bandeja o un hilo,
  * **Entonces** la interfaz informa que la mensajería no está disponible temporalmente, sin exponer detalles del gateway.
  * **Dado que** un usuario con rol `OPERADOR` intenta acceder a las conversaciones,
  * **Cuando** invoca el endpoint,
  * **Entonces** recibe un error de permiso denegado.

---

### US-31: Bandeja en Tiempo Real y Aviso de Nuevas Derivaciones
* **Mapeo:** RF-32, RF-30
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado con la bandeja abierta,
  * **Quiero** que los mensajes nuevos y las derivaciones del bot aparezcan sin recargar la página,
  * **Para** responder rápido a los clientes que necesitan ayuda.
* **Criterios de Aceptación:**
  * **Dado que** el encargado tiene la bandeja abierta,
  * **Cuando** el bot deriva una conversación o el cliente envía un mensaje nuevo,
  * **Entonces** la bandeja se actualiza en tiempo real y muestra un aviso de la nueva derivación con su motivo.
  * **Dado que** cambia el estado de entrega de un mensaje (`SENT`, `DELIVERED`, `READ` o `FAILED`),
  * **Cuando** el sistema recibe la actualización,
  * **Entonces** el hilo abierto refleja el nuevo estado sin recargar.
  * **Dado que** se interrumpe la conexión de eventos,
  * **Cuando** la interfaz se reconecta automáticamente,
  * **Entonces** vuelve a solicitar la bandeja completa para recuperar los eventos perdidos.
  * **Dado que** el token de acceso del encargado vence,
  * **Cuando** el servidor cierra el stream,
  * **Entonces** la interfaz renueva la sesión y se reconecta sin intervención del usuario.

---

### US-32: Reasignación de una Conversación por el Superadministrador
* **Mapeo:** RF-30
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** superadministrador,
  * **Quiero** tomar una conversación que está asignada a otro encargado,
  * **Para** que ningún cliente quede sin atención si ese encargado no está disponible.
* **Criterios de Aceptación:**
  * **Dado que** una conversación está asignada a otro encargado,
  * **Cuando** el `SUPERADMIN` ejecuta «Tomar conversación»,
  * **Entonces** la conversación queda asignada al `SUPERADMIN` y la acción se registra en `audit_logs` como `OVERRIDE_CONVERSATION_ASSIGNMENT` con el usuario anterior.
  * **Dado que** un `ENCARGADO` intenta tomar una conversación asignada a otro encargado,
  * **Cuando** ejecuta la acción,
  * **Entonces** el sistema responde `conversation-taken-by-other` y no cambia la asignación.

---

## 11. Matriz de Trazabilidad: Requerimientos Funcionales (RF) vs. Historias de Usuario (US)

| RF | Requerimiento Funcional Técnico | Historia de Usuario Vinculada | Épica | Prioridad |
| :---: | :--- | :---: | :--- | :---: |
| **RF-01** | Atención Automatizada y Saludo Inicial | **US-01** | Épica 1: Atención y Cotización | Must have |
| **RF-02** | Captura Estructurada de Datos del Evento | **US-03** | Épica 1: Atención y Cotización | Must have |
| **RF-03** | Gestión de Paquetes y Temáticas | **US-01, US-02** | Épica 1: Atención y Cotización | Must have |
| **RF-04** | Selección y Adición de Extras | **US-02** | Épica 1: Atención y Cotización | Must have |
| **RF-05** | Cálculo Automatizado de Costo de Movilidad | **US-04** | Épica 1: Atención y Cotización | Must have |
| **RF-06** | Exención de Movilidad por Transporte Propio | **US-05** | Épica 1: Atención y Cotización | Should have |
| **RF-07** | Liquidación Económica (Total, Adelanto 10%, Saldo) | **US-06** | Épica 1: Atención y Cotización | Must have |
| **RF-08** | Despacho Automático de Resumen de Cotización | **US-07** | Épica 1: Atención y Cotización | Must have |
| **RF-09** | Verificación de Disponibilidad de Recursos | **US-08** | Épica 2: Disponibilidad y Control | Must have |
| **RF-10** | Cálculo de Intervalo de Traslado entre Shows | **US-09** | Épica 2: Disponibilidad y Control | Must have |
| **RF-11** | Recepción de Comprobantes de Adelanto | **US-11** | Épica 3: Pagos y Validación | Must have |
| **RF-12** | Validación de Pago y Flujo de Reintento | **US-12** | Épica 3: Pagos y Validación | Must have |
| **RF-13** | Generación Automatizada del Contrato en PDF | **US-13** | Épica 4: Contratos y Firma | Must have |
| **RF-14** | Registro de Observaciones Especiales del Cliente | **US-03, US-13, US-14, US-16** | Épica 1 / Épica 4 / Épica 5 | Should have |
| **RF-15** | Registro de Firma Electrónica del Contrato | **US-15** | Épica 4: Contratos y Firma | Must have |
| **RF-16** | Tablero de Cronograma y Filtros de Búsqueda | **US-16** | Épica 5: Cronograma y Operación | Must have |
| **RF-17** | Visualización Rápida de Observaciones | **US-16** | Épica 5: Cronograma y Operación | Should have |
| **RF-18** | Protocolo de Cobro Pre-Show y Bloqueo de Inicio | **US-17** | Épica 5: Cronograma y Operación | Must have |
| **RF-19** | Registro de Extensiones en Caliente y Cierre | **US-18** | Épica 5: Cronograma y Operación | Must have |
| **RF-20** | Aprobación Manual por Umbral de Shows Simultáneos | **US-10** | Épica 2: Disponibilidad y Control | Must have |
| **RF-21** | Sobrescritura (*Override*) Manual de Movilidad | **US-19** | Épica 6: Overrides Manuales | Must have |
| **RF-22** | Ajuste Manual del Intervalo entre Shows | **US-20** | Épica 6: Overrides Manuales | Should have |
| **RF-23** | Modo Manual de Creación de Contratos | **US-14** | Épica 4: Contratos y Firma | Must have |
| **RF-24** | Consolidación Automática de Ingresos y Costos | **US-21** | Épica 7: Analítica Financiera | Must have |
| **RF-25** | Dashboard Ejecutivo de Desempeño | **US-22** | Épica 7: Analítica Financiera | Should have |
| **RF-26** | Gestión de Usuarios del Panel y Roles | **US-23** | Épica 8: Administración de la Plataforma | Must have |
| **RF-27** | Consulta de la Bitácora de Auditoría | **US-24** | Épica 8: Administración de la Plataforma | Should have |
| **RF-28** | Consulta de Clientes | **US-25** | Épica 8: Administración de la Plataforma | Should have |
| **RF-29** | Gestión de Elencos y Vinculación con Operadores | **US-26** | Épica 8: Administración de la Plataforma | Must have |
| **RF-30** | Traspaso de la Conversación del Bot a un Encargado y Retorno al Bot | **US-27, US-28, US-29, US-31, US-32** | Épica 9: Atención Humana y Bandeja | Must have |
| **RF-31** | Bandeja de Conversaciones en EventPro | **US-28, US-30** | Épica 9: Atención Humana y Bandeja | Must have |
| **RF-32** | Actualización en Tiempo Real de la Bandeja | **US-31** | Épica 9: Atención Humana y Bandeja | Should have |

> **Criterio de prioridad:** el catálogo de RF es la fuente de verdad (Alta = *Must have*, Media = *Should have*, Baja = *Could have*). La prioridad de cada fila de la matriz es la del RF; la prioridad de una historia es la mayor de los RF que cubre. Cobertura: 32 RF y 32 historias; cada RF tiene al menos una historia.
