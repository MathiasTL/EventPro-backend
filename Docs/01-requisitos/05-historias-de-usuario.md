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
  * **Cuando** el sistema procesa el webhook en menos de 1.5 segundos,
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
* **Mapeo:** RF-02
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** chatbot del sistema,
  * **Quiero** recopilar el nombre del cliente, teléfono, fecha, hora estimada y dirección exacta de la locación,
  * **Para** contar con los parámetros necesarios para verificar disponibilidad y calcular la movilidad.
* **Criterios de Aceptación:**
  * **Dado que** el cliente configuró su paquete y extras,
  * **Cuando** el bot solicita la fecha y ubicación,
  * **Entonces** valida que la fecha sea futura y que la dirección incluya distrito o coordenadas válidas de Lima/Callao.

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
* **Mapeo:** RF-08
* **Prioridad:** Must have | **Estimación:** 2 SP
* **Narrativa:**
  * **Como** cliente,
  * **Quiero** recibir en el chat un mensaje claro con el detalle de lo cotizado, el adelanto requerido y los números de cuenta para depositar,
  * **Para** tomar una decisión inmediata y proceder con el pago.
* **Criterios de Aceptación:**
  * **Dado que** el sistema finalizó el cálculo,
  * **Cuando** se despacha la cotización,
  * **Entonces** el cliente recibe en WhatsApp el desglose detallado de ítems, totales, número de Yape/BCP y la fecha límite de reserva.

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
  * **Dado que** un cliente solicita una fecha y bloque horario,
  * **Cuando** el sistema consulta la base de recursos,
  * **Entonces** si la capacidad está colmada, alerta al cliente ofreciendo otros horarios o derivando el caso al encargado.

---

### US-09: Control de Tiempos de Traslado entre Shows Sucesivos
* **Mapeo:** RF-10, PC-02
* **Prioridad:** Should have | **Estimación:** 3 SP
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
* **Mapeo:** RF-20, PC-03
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** que cuando coincidan más de 3 shows en el mismo horario el sistema me pida autorización expresa antes de confirmar,
  * **Para** evaluar personalmente si cuento con suficientes grupos freelance de respaldo para asumir la demanda.
* **Criterios de Aceptación:**
  * **Dado que** ya existen 3 shows agendados en una misma franja horaria,
  * **Cuando** entra un 4to pedido,
  * **Entonces** el sistema marca el evento como `REQUIERE_APROBACION_MANUAL` y envía una notificación al panel del encargado para Aprobar o Rechazar.

---

## 4. Épica 3: Gestión de Pagos, Comprobantes y Validación

### US-11: Recepción de Captura del Adelanto por Yape / Transferencia
* **Mapeo:** RF-11
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** cliente que depositó el 10% de adelanto,
  * **Quiero** subir la captura de pantalla de mi comprobante por WhatsApp,
  * **Para** acreditar mi pago sin trámites presenciales.
* **Criterios de Aceptación:**
  * **Dado que** el cliente tiene una cotización vigente,
  * **Cuando** adjunta una imagen o PDF del comprobante en el chat de WhatsApp,
  * **Entonces** el sistema la asocia unívocamente a su cotización y la coloca en estado `PENDIENTE_VERIFICACION`.

---

### US-12: Verificación de Pago y Flujo de Reintento
* **Mapeo:** RF-12, PC-06
* **Prioridad:** Must have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** encargado,
  * **Quiero** validar el comprobante recibido y, si no es legible o el monto está incompleto, rechazarlo indicando el motivo para que el bot pida reintentar,
  * **Para** no emitir contratos sin tener el dinero acreditado en cuenta.
* **Criterios de Aceptación:**
  * **Dado que** un comprobante es rechazado por el encargado con el motivo "Monto incompleto",
  * **Cuando** el sistema procesa el rechazo,
  * **Entonces** despacha un mensaje por WhatsApp al cliente informando el motivo y habilitando un botón para subir un nuevo comprobante.

---

## 5. Épica 4: Contratos Inteligentes y Firma Digital

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
  * **Entonces** el sistema genera el contrato PDF con bandera `is_manual_mode: true` y lo agenda en el cronograma.

---

### US-15: Firma Electrónica del Contrato por el Cliente
* **Mapeo:** RF-15
* **Prioridad:** Must have | **Estimación:** 5 SP
* **Narrativa:**
  * **Como** cliente,
  * **Quiero** abrir un enlace seguro en mi teléfono, revisar el contrato y trazar mi firma con el dedo,
  * **Para** formalizar el acuerdo de inmediato sin imprimir papel.
* **Criterios de Aceptación:**
  * **Dado que** el cliente abre el enlace de firma,
  * **Cuando** visualiza el PDF, dibuja su firma manuscrita y acepta los términos,
  * **Entonces** el sistema sella el PDF con la firma, registra la IP y fecha/hora, y envía la copia final firmada a su chat.

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
  * **Dado que** el elenco llega a la locación y el evento está en `AGENDADO`,
  * **Cuando** el operador intenta cambiar el estado a `EN_EJECUCION` sin registrar el cobro del saldo,
  * **Entonces** el sistema bloquea la acción con un mensaje de error exigiendo confirmar el medio y monto del cobro in-situ.

---

### US-18: Registro de Extensiones en Caliente y Cierre de Evento
* **Mapeo:** RF-19, RN-07, PC-08
* **Prioridad:** Should have | **Estimación:** 3 SP
* **Narrativa:**
  * **Como** operador del show,
  * **Quiero** registrar si el cliente solicitó 30 o 60 minutos adicionales de show o espera durante la fiesta,
  * **Para** sumar la tarifa extraordinaria pactada a la liquidación final antes de marcar el evento como liquidado.
* **Criterios de Aceptación:**
  * **Dado que** un show culminó pero el cliente pagó por media hora más,
  * **Cuando** se ingresa el cargo por tiempo extra,
  * **Entonces** se actualiza el ingreso total del evento y se transiciona su estado a `LIQUIDADO`.

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
* **Prioridad:** Could have | **Estimación:** 2 SP
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

## 9. Matriz de Trazabilidad: Requerimientos Funcionales (RF) vs. Historias de Usuario (US)

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
| **RF-10** | Cálculo de Intervalo de Traslado entre Shows | **US-09** | Épica 2: Disponibilidad y Control | Should have |
| **RF-11** | Recepción de Comprobantes de Adelanto | **US-11** | Épica 3: Pagos y Validación | Must have |
| **RF-12** | Validación de Pago y Flujo de Reintento | **US-12** | Épica 3: Pagos y Validación | Must have |
| **RF-13** | Generación Automatizada del Contrato en PDF | **US-13** | Épica 4: Contratos y Firma | Must have |
| **RF-14** | Registro de Observaciones Especiales del Cliente | **US-13, US-16** | Épica 4 / Épica 5 | Must have |
| **RF-15** | Registro de Firma Digital / Electrónica | **US-15** | Épica 4: Contratos y Firma | Must have |
| **RF-16** | Tablero de Cronograma y Filtros de Búsqueda | **US-16** | Épica 5: Cronograma y Operación | Must have |
| **RF-17** | Visualización Rápida de Observaciones | **US-16** | Épica 5: Cronograma y Operación | Must have |
| **RF-18** | Protocolo de Cobro Pre-Show y Bloqueo de Inicio | **US-17** | Épica 5: Cronograma y Operación | Must have |
| **RF-19** | Registro de Extensiones en Caliente y Cierre | **US-18** | Épica 5: Cronograma y Operación | Should have |
| **RF-20** | Aprobación Manual por Umbral de Shows Simultáneos | **US-10** | Épica 2: Disponibilidad y Control | Must have |
| **RF-21** | Sobrescritura (*Override*) Manual de Movilidad | **US-19** | Épica 6: Overrides Manuales | Must have |
| **RF-22** | Ajuste Manual del Intervalo entre Shows | **US-20** | Épica 6: Overrides Manuales | Could have |
| **RF-23** | Modo Manual de Creación de Contratos | **US-14** | Épica 4: Contratos y Firma | Must have |
| **RF-24** | Consolidación Automática de Ingresos y Costos | **US-21** | Épica 7: Analítica Financiera | Must have |
| **RF-25** | Dashboard Ejecutivo de Desempeño | **US-22** | Épica 7: Analítica Financiera | Should have |
