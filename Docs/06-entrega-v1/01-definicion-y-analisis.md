# EventPro — Definición y Análisis de Requerimientos

**Sistema:** EventPro — Automatización de cotizaciones por WhatsApp y control operativo para una promotora de eventos.
**Etapa:** 1 · Versión 1
**Documento:** Definición y análisis (problema, proceso AS-IS, objetivos, alcance, actores, entradas/salidas, RF/RNF e identificación inicial de eventos, reglas, decisiones y acciones).

---

## 1. Planteamiento del problema

### 1.1 Contexto

La promotora objeto de estudio es una empresa de eventos sociales y corporativos constituida ante SUNAT con RUC personal, ubicada en Lima Metropolitana y Callao. Su portafolio comprende servicios de **hora loca**, **shows infantiles**, **baby showers**, **servicio de DJ**, **maestría de ceremonia**, **ambientación y arriendo de toldos**, así como personajes y extras de alto impacto comercial (por ejemplo, el muñeco gorila gigante).

El modelo operativo se sustenta en una **red de proveedores freelance** —artistas, animadores, decoradores, DJs y personal de montaje— que no integran planilla: se contratan por servicio y se pagan por prestación. La gestión comercial y operativa recae en **dos personas (los encargados)**, quienes atienden al cliente, cotizan, verifican disponibilidad, elaboran contratos, controlan pagos y coordinan la logística de los eventos.

### 1.2 Descripción del problema

El proceso de negocio se ejecuta de forma **predominantemente manual y desarticulada**, sobre canales de comunicación informal (WhatsApp, llamadas telefónicas, documentos de texto) y sin un sistema de información que integre las etapas de venta, verificación de recursos, formalización contractual, cobranza y control operativo.

Esta condición genera una cadena de ineficiencias que impacta tanto en la experiencia del cliente como en la rentabilidad del negocio: los tiempos de respuesta son elevados, la cotización depende del criterio y disponibilidad de un encargado, la elaboración de contratos se resuelve copiando y editando documentos antiguos, y la verificación de disponibilidad carece de un control formal de personal e inventario, lo que incrementa el riesgo de sobreventa y de incumplimiento de servicios comprometidos.

### 1.3 Síntomas y consecuencias

| Síntoma observado | Consecuencia en el negocio |
| :--- | :--- |
| Armado de contratos lento y repetitivo (copiar y editar documentos antiguos) | Alto consumo de horas hombre; demora en la formalización; imagen poco profesional ante el cliente. |
| Cotización y movilidad calculadas manualmente (consulta a terceros o aplicación InDrive) | Errores de cálculo, tarifas inconsistentes entre clientes y pérdida de margen comercial. |
| Sin control formal de disponibilidad de personal ni de inventario | Riesgo de sobreventa (*overbooking*), choques de elencos y compromisos incumplibles. |
| Observaciones del cliente transmitidas de forma verbal o por mensaje | Pérdida de información crítica el día del evento (música prohibida, iluminación, protocolos de ingreso). |
| Registro informal de eventos, sin cronograma centralizado | Falta de visibilidad operativa; conflictos de agenda no detectados hasta el día del evento. |
| Sin visibilidad de ganancias reales (ingresos vs. costos del elenco) | Decisiones comerciales basadas en estimaciones; rentabilidad desconocida por servicio y período. |
| Ausencia de reportes y dashboards | Imposibilidad de gestión basada en indicadores. |

### 1.4 Formulación del problema

¿Cómo automatizar el proceso de cotización de eventos por WhatsApp y el control operativo de la promotora —disponibilidad de recursos, contratación, cobranza y reportes— de modo que se reduzcan los tiempos de atención, se eliminen los errores de cálculo y de registro manual, se prevenga la sobreventa de recursos y se obtenga visibilidad financiera del negocio?

---

## 2. Proceso AS-IS (proceso de negocio actual)

### 2.1 Descripción general

El proceso actual es un **flujo secuencial de gestión manual** entre el cliente, los encargados y los proveedores freelance, sin soporte de un sistema de información integrado. Cada oportunidad de venta se atiende de forma individual y artesanal.

### 2.2 Fases del proceso actual

| # | Fase | Descripción | Medio utilizado |
| :--: | :--- | :--- | :--- |
| 1 | Contacto inicial | El cliente se comunica por WhatsApp manifestando su interés en celebrar un evento (por ejemplo, sus 30 o 40 años) y describe lo que desea: una decoración, el show de hora loca con DJ, o solo la hora loca, entre otras opciones. | WhatsApp |
| 2 | Recojo de datos y oferta | El encargado le solicita sus datos personales y le ofrece los paquetes disponibles junto con las temáticas que maneja. | WhatsApp / llamada |
| 3 | Elección del cliente | El cliente elige un paquete y una temática; frecuentemente solicita combinaciones personalizadas (por ejemplo, paquete *Medium* con temática de personajes de la selva, más el extra «gorila gigante»). | WhatsApp |
| 4 | Cotización manual | El encargado arma la cotización a mano según lo elegido. La movilidad se calcula también manualmente: se consulta a personas que conocen la zona o se revisa lo que marca la aplicación InDrive y se estima el costo de ida y vuelta. | Hoja de cálculo / cálculo mental |
| 5 | Evaluación de disponibilidad | La disponibilidad no depende de una agenda formal, sino del criterio del proveedor en ese momento: cuántas personas puede llamar, cuántos grupos puede formar y las distancias entre eventos del mismo día. Varios eventos pueden coincidir en fecha y horario si se cuenta con personal suficiente. | Llamadas / criterio personal |
| 6 | Elaboración manual del contrato | El encargado vuelve a sus archivos, busca un contrato antiguo, lo copia y lo modifica según las necesidades del nuevo cliente. El procedimiento se repite con cada cliente y resulta tedioso. | Procesador de texto |
| 7 | Cobro del adelanto | Para que el contrato proceda, el cliente debe realizar un adelanto del **10 % del total (sobre paquete + extras)** mediante Yape o transferencia bancaria, y envía la captura de pantalla como comprobante. En el contrato se deja constancia del adelanto y del saldo pendiente. | Yape / transferencia + captura |
| 8 | Registro informal del evento | El evento queda anotado de manera informal, sin cronograma centralizado con filtros ni control de horarios. Las observaciones del cliente (bailes no permitidos, formas de iluminación) se comunican verbalmente o por mensaje, con riesgo de extravío. | Cuaderno / chat |
| 9 | Ejecución el día del evento | El personal llega al lugar y cobra el **saldo pendiente (más la movilidad) antes de iniciar** el show o de armar la decoración y los toldos. El pago puede ser por Yape, transferencia o efectivo y no se emite boleta. Si el cliente solicita tiempo adicional (media hora más de espera o de show), el ajuste se negocia en el momento con el encargado. | Efectivo / Yape / transferencia |
| 10 | Cierre sin reportes formales | No existe un cálculo sistemático de ganancias y costos por semana ni a fin de mes, ni dashboards automáticos que muestren los resultados del negocio. | No aplica |

### 2.3 Diagnóstico de ineficiencias

Del análisis del proceso se identifican seis **cuellos de botella críticos**:

1. **Formalización contractual manual**: el ciclo «buscar contrato antiguo → copiar → editar» es la etapa más repetitiva y propensa a errores.
2. **Cálculo artesanal de la movilidad**: la estimación depende de terceros o de aplicativos de transporte, sin margen comercial estandarizado ni trazabilidad.
3. **Gestión de disponibilidad por criterio personal**: no existe control formal de capacidad de elencos ni de inventario físico (toldos, decoración), lo que expone a la promotora a sobreventa.
4. **Pérdida de observaciones del cliente**: al no persistirse en un campo estructurado, se pierden o malinterpretan.
5. **Control de cobranza fragmentado**: el adelanto se valida manualmente y el cobro del saldo el día del evento carece de un protocolo con evidencia.
6. **Ausencia de analítica financiera**: sin consolidación de ingresos contra costos fijos, no hay visibilidad de rentabilidad ni soporte para la toma de decisiones.

---

## 3. Objetivos

### 3.1 Objetivo general

Automatizar el proceso de cotización de eventos por WhatsApp y el control operativo de la promotora, integrando disponibilidad de recursos, generación de contratos con firma electrónica, gestión de cobros y analítica financiera en un único sistema de información.

### 3.2 Objetivos específicos

1. **Automatizar la atención y cotización por WhatsApp**, de modo que el cliente reciba una propuesta completa (paquete, temática, extras, movilidad, adelanto y saldo) sin intervención manual del encargado.
2. **Institucionalizar la verificación de disponibilidad**, mediante el control de capacidad de elencos, stock de inventario físico e intervalos de traslado entre shows, con umbral de concurrencia configurable.
3. **Eliminar la elaboración manual de contratos**, generando automáticamente documentos en PDF con los datos del cliente y permitiendo su firma electrónica, con un modo manual de respaldo.
4. **Estandarizar el control de cobros**, desde la recepción del comprobante del adelanto hasta el cobro del saldo y las extensiones en vivo, con evidencia obligatoria y trazabilidad.
5. **Proporcionar visibilidad financiera del negocio**, consolidando ingresos y costos fijos de forma automática y presentando dashboards ejecutivos para la toma de decisiones.
6. **Garantizar trazabilidad y seguridad**, mediante auditoría de acciones críticas, control de acceso por roles y cumplimiento de prácticas de seguridad OWASP.

---

## 4. Alcance

### 4.1 Alcance funcional (versión MVP)

El sistema EventPro abarca el ciclo completo de gestión comercial y operativa de un evento:

| Dominio | Alcance incluido |
| :--- | :--- |
| Atención automatizada | Bot de WhatsApp: saludo, catálogo, selección de paquete/temática/extras, captura de datos, envío del resumen. |
| Disponibilidad de recursos | Control de inventario físico (toldos, decoración), capacidad de elencos, intervalos de traslado entre shows y umbral de shows simultáneos. |
| Cotización | Cálculo automático de movilidad (Google Maps, ida y vuelta con margen comercial), liquidación determinística (total, adelanto 10 %, saldo) y exención de movilidad por transporte del cliente. |
| Pagos | Recepción de comprobantes, verificación, flujo de reintento, aprobación de sobrecupo y cobro con evidencia del saldo y extensiones. |
| Contratos | Generación automática de PDF con observaciones, modo manual de respaldo, firma electrónica con OTP y sellado PAdES. |
| Operación del evento | Cronograma con filtros y observaciones, protocolo de cobro pre-show, bloqueo de inicio sin saldo, extensiones en vivo y liquidación final. |
| Controles manuales (*overrides*) | Ajuste del monto de movilidad y de los intervalos de traslado, con trazabilidad de auditoría. |
| Administración | Gestión de usuarios y roles, bitácora de auditoría, consulta de clientes y gestión de elencos con vinculación a operadores. |
| Atención humana | Traspaso de la conversación del bot a un encargado, bandeja de conversaciones y actualización en tiempo real. |
| Analítica | Consolidación semanal y mensual de ingresos vs. costos fijos y dashboards ejecutivos. |

### 4.2 Fuera de alcance

- Emisión de boletas o facturación electrónica (SUNAT).
- Pasarela de pagos en línea (Yape/Plin operan manualmente con comprobante).
- Aplicación móvil nativa (la interfaz operativa es web, *mobile-first*).
- Gestión de personal en planilla, remuneraciones o control de asistencia.
- Reservas de línea de tiempo para clientes vía web pública (la venta ocurre por WhatsApp).

### 4.3 Premisas y restricciones

- El cliente interactúa exclusivamente a través de **WhatsApp**; no se requiere registro de usuario en el sistema.
- Los proveedores freelance se contratan por servicio; el sistema registra **elencos**, nóminas de personal.
- Los datos de pago (Yape, Plin, transferencia) se configuran como parámetros del sistema; el bot los revela únicamente tras verificar disponibilidad.
- El número de WhatsApp operativo es el de pruebas de Meta (limitado a 5 destinatarios registrados) por razones de costos; la funcionalidad no cambia.
- La infraestructura de despliegue es de costo cero (capa *Always Free* de nube pública).

---

## 5. Actores

### 5.1 Actores humanos

| Actor | Denominación en el sistema | Descripción y responsabilidades |
| :--- | :--- | :--- |
| **Cliente** | `CLIENTE` (acceso por token) | Persona que contrata el evento. Interactúa por WhatsApp para cotizar, pagar el adelanto y firmar el contrato mediante enlace público (sin credenciales de acceso al panel). |
| **Encargado del negocio** | `ENCARGADO` | Responsable de la operación comercial: administra el catálogo, gestiona cotizaciones y contratos, aplica *overrides*, aprueba sobrecupos, verifica pagos, audita cobros in situ y consulta reportes. |
| **Operador de elenco / campo** | `OPERADOR` | Personal que ejecuta el servicio en el lugar del evento. Acceso restringido a sus eventos asignados: registra la llegada, el cobro del saldo con evidencia y las extensiones de show. |
| **Superadministrador** | `SUPERADMIN` | Máximo nivel de privilegio: configuración global, gestión de usuarios y roles, auditoría general y reasignación de conversaciones. |
| **Proveedor freelance / líder de elenco** | *(actor externo al sistema)* | Líder de grupo de artistas o proveedor de servicios (toldos, decoración). Recibe la asignación del evento; su vinculación con un usuario `OPERADOR` habilita la visión de agenda. |

### 5.2 Actores no humanos (sistemas y procesos)

| Actor | Tipo | Función |
| :--- | :--- | :--- |
| **Bot de WhatsApp** | Aplicación | Atiende la conversación en modo automático a través del gateway de mensajería; ejecuta los casos de uso de cotización. |
| **Tareas programadas (worker)** | Proceso | Ejecuta la expiración de cotizaciones, el despacho y reintento de la cola de mensajes, la reconciliación con el gateway y la generación de reportes periódicos. |
| **Gateway de mensajería (Chatwoot)** | Sistema externo | Centraliza la mensajería de WhatsApp: recibe los mensajes entrantes (webhook) y envía los salientes (bot y encargados). |
| **Google Maps Platform** | Sistema externo | Provee distancias y tiempos de recorrido para el cálculo de movilidad y de los intervalos de traslado entre shows. |
| **Autoridad de sellado de tiempo (TSA)** | Sistema externo | *(Opcional)* Marca de tiempo RFC 3161 sobre los documentos firmados con PAdES. |

---

## 6. Entradas y salidas del sistema

### 6.1 Entradas

| Categoría | Entrada | Descripción |
| :--- | :--- | :--- |
| Mensajería | Mensaje de WhatsApp (texto, imagen, documento) | Dispara la conversación con el bot o el encargado; incluye las capturas de comprobante de pago. |
| Datos del cliente | Nombre, teléfono (E.164), DNI/RUC opcional | Registro del cliente; el teléfono es la clave natural de identificación. |
| Datos del evento | Fecha, hora estimada, dirección y distrito de la locación, coordenadas opcionales | Base para la verificación de disponibilidad y el cálculo de movilidad. |
| Observaciones | Texto libre del cliente o del encargado | Instrucciones especiales del evento (música permitida, protocolos de ingreso, iluminación). |
| Catálogo | Paquetes, temáticas, extras, inventario físico, elencos | Catálogo parametrizable administrado por el encargado. |
| Parámetros configurables | Umbral de simultaneidad (3), plazo del adelanto (24 h), margen de movilidad (15 %), porcentaje de adelanto (10 %), margen de desarme (30 min), revalidación de disponibilidad (60 min) | Reglas de negocio ajustables sin modificar el código. |
| Comprobantes de pago | Imagen o PDF del comprobante de Yape/Plin/transferencia | Validación de identidad real de tipo MIME (no solo extensión). |
| Firma del cliente | Código OTP de 6 dígitos + firma manuscrita digital | Formalización electrónica del contrato. |
| Datos externos | Distancias y tiempos (Google Maps); estado de conversaciones (Chatwoot) | Alimentan el cálculo logístico y la bandeja de atención. |

### 6.2 Salidas

| Categoría | Salida | Descripción |
| :--- | :--- | :--- |
| Cotización | Resumen de cotización por WhatsApp | Desglose de ítems y totales, adelanto requerido, saldo pendiente, plazo de vigencia y botón «Pagar adelanto». |
| Instrucciones de pago | Datos de Yape/Plin/transferencia | Se muestran únicamente tras verificar disponibilidad (revalidación). |
| Contrato | Documento PDF (contrato formal) | Incluye datos del cliente, paquete, temática, extras, montos, adelanto, saldo, movilidad y observaciones. |
| Contrato firmado | PDF sellado con PAdES + registro de auditoría | Copia final con firma electrónica, hash SHA-256, IP, agente de usuario y marcas de tiempo. |
| Control operativo | Cronograma de eventos | Vista filtrable por fecha con observaciones destacadas en la tarjeta de cada evento. |
| Control de cobros | Comprobantes y evidencias asociadas a pagos | Registro de adelantos, saldos y extensiones con medio de pago y fotografía. |
| Notificaciones | Mensajes automáticos de estado | Confirmaciones, recordatorios de vencimiento, avisos de rechazo con motivo y reenvío de contratos. |
| Analítica | Reportes semanales/mensuales y dashboards | Ingresos liquidados, costos fijos (paquetes y extras), costos operativos de movilidad y utilidad neta. |
| Trazabilidad | Bitácora de auditoría (solo lectura) | Registro de acciones críticas: *overrides*, aprobaciones de sobrecupo, auditoría de cobros, contratos manuales y firmas. |

---

## 7. Requerimientos

### 7.1 Requerimientos funcionales

Se presentan los 32 requerimientos funcionales (RF-01 a RF-32) organizados por dominio, con su prioridad asociada (Alta = *Must have*, Media = *Should have*).

**Dominio: Atención y cotización automatizada**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-01 | Atención automatizada y saludo inicial | El sistema debe recibir los mensajes entrantes de WhatsApp y responder automáticamente con un saludo y la presentación del catálogo de servicios, con una latencia inferior a 1.5 segundos. | Alta |
| RF-02 | Captura estructurada de datos del evento | El sistema debe recopilar nombre, teléfono, fecha, hora, dirección (con distrito o coordenadas válidas de Lima/Callao) y observaciones opcionales del cliente. | Alta |
| RF-03 | Gestión de paquetes y temáticas | El sistema debe mantener y exponer un catálogo parametrizable de paquetes base vinculados a sus temáticas compatibles. | Alta |
| RF-04 | Selección y adición de extras | El sistema debe permitir seleccionar uno o más extras del catálogo sobre un paquete, sin límite de combinación. | Alta |
| RF-05 | Cálculo automatizado del costo de movilidad | El sistema debe computar distancia y tiempo de ida y vuelta mediante Google Maps y aplicar un recargo comercial del 15 %. | Alta |
| RF-06 | Exención de movilidad por transporte propio | El sistema debe fijar el costo de movilidad en S/ 0.00 cuando el cliente indica que provee el transporte. | Media |
| RF-07 | Liquidación económica | El sistema debe calcular el total (paquete + extras + movilidad), el adelanto del 10 % sobre servicios (sin movilidad) y el saldo pendiente de forma determinística. | Alta |
| RF-08 | Despacho automático del resumen de cotización | El sistema debe enviar el desglose completo por WhatsApp, sin datos de pago, advirtiendo el plazo del adelanto y la no reserva de fecha. | Alta |

**Dominio: Verificación de disponibilidad y procesos de control**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-09 | Verificación de disponibilidad de recursos | El sistema debe verificar la capacidad de elencos y el stock de inventario físico (toldos, decoración) contra las reservas activas de la ventana de tiempo solicitada, respondiendo `CONFLICT` cuando las unidades no cubren el requerimiento. | Alta |
| RF-10 | Cálculo del intervalo de traslado entre shows | El sistema debe calcular el tiempo mínimo de traslado entre eventos sucesivos de un mismo elenco, sumando el tiempo de tránsito y un margen de desarme y descanso. | Alta |
| RF-20 | Aprobación manual por umbral de shows simultáneos | El sistema debe bloquear la confirmación automática y exigir aprobación manual del encargado cuando se superen más de 3 shows simultáneos por solape real de intervalos. | Alta |

**Dominio: Pagos y validación**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-11 | Recepción de comprobantes de adelanto | El sistema debe recibir la captura del comprobante, asociarla unívocamente a la cotización y registrar el pago con su estado inicial. | Alta |
| RF-12 | Validación de pago y flujo de reintento | El sistema debe permitir verificar o rechazar el comprobante (con motivo), habilitar el reintento sin cancelar la cotización y ejecutar una revalidación atómica de disponibilidad antes de confirmar. | Alta |

**Dominio: Contratos y firma electrónica**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-13 | Generación automatizada del contrato en PDF | El sistema debe compilar el contrato con número correlativo, desglose de pagos y observaciones, regenerándose ante modificaciones previas a la firma. | Alta |
| RF-14 | Registro de observaciones especiales | El sistema debe persistir el texto de observaciones en un campo específico, visible en el PDF y en el cronograma. | Media |
| RF-15 | Registro de la firma electrónica | El sistema debe verificar un OTP, capturar la firma manuscrita, sellar el PDF con PAdES y registrar hash, IP, agente de usuario y marcas de tiempo. | Alta |
| RF-23 | Modo manual de creación de contratos | El sistema debe permitir al encargado armar un contrato a mano con los ítems pactados fuera del bot, como respaldo del flujo automatizado. | Alta |

**Dominio: Operación del evento**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-16 | Tablero de cronograma y filtros | El sistema debe presentar la agenda de eventos con filtros por fecha. | Alta |
| RF-17 | Visualización rápida de observaciones | El sistema debe mostrar las observaciones en la tarjeta del evento sin abrir el documento completo. | Media |
| RF-18 | Protocolo de cobro pre-show y bloqueo de inicio | El sistema debe impedir el inicio del show sin el cobro del 100 % del saldo y registrar el cobro in situ con evidencia obligatoria. | Alta |
| RF-19 | Registro de extensiones en caliente y cierre | El sistema debe registrar tiempos adicionales pactados como cobro de extensión y liquidar el evento al cierre. | Alta |

**Dominio: Procesos de control manual (*overrides*)**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-21 | Sobrescritura manual de movilidad | El sistema debe permitir editar el monto de movilidad calculado, con justificación obligatoria y recálculo de totales sin alterar el adelanto. | Alta |
| RF-22 | Ajuste manual del intervalo entre shows | El sistema debe permitir acortar o extender la ventana de traslado sugerida, validando la excepción y registrándola en auditoría. | Media |

**Dominio: Administración**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-26 | Gestión de usuarios y roles | El sistema debe crear, editar, activar y desactivar cuentas del panel con roles `ENCARGADO` y `OPERADOR`, revocando sesiones ante cambios sensibles. | Alta |
| RF-27 | Consulta de la bitácora de auditoría | El sistema debe permitir consultar quién hizo qué en las decisiones críticas, con filtros y solo lectura. | Media |
| RF-28 | Consulta de clientes | El sistema debe permitir buscar clientes por nombre o teléfono y reutilizar el registro existente ante nuevas cotizaciones. | Media |
| RF-29 | Gestión de elencos y vinculación con operadores | El sistema debe registrar elencos freelance con categoría de servicio y vincularlos a usuarios `OPERADOR` exclusivamente. | Alta |

**Dominio: Atención humana**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-30 | Traspaso de la conversación del bot a un encargado y retorno | El sistema debe derivar la conversación a un humano según reglas definidas, con motivo y resumen, y permitir su devolución al bot. | Alta |
| RF-31 | Bandeja de conversaciones en EventPro | El sistema debe presentar la bandeja con filtros por modo, asignación y estado, incluyendo motivos de falla de envío y reintentos. | Alta |
| RF-32 | Actualización en tiempo real de la bandeja | El sistema debe refrescar la bandeja y los estados de mensaje sin recarga, con reconexión automática. | Media |

**Dominio: Analítica financiera**

| RF | Denominación | Descripción | Prioridad |
| :--: | :--- | :--- | :---: |
| RF-24 | Consolidación automática de ingresos y costos | El sistema debe totalizar semanal y mensualmente los cobros recibidos, descontar los costos fijos de paquetes y extras y reportar la utilidad neta. | Alta |
| RF-25 | Dashboard ejecutivo de desempeño | El sistema debe presentar indicadores comparativos: rentabilidad por período, volumen de eventos por temática, ranking de extras y distribución por distrito. | Media |

### 7.2 Requerimientos no funcionales

| RNF | Categoría | Descripción |
| :--: | :--- | :--- |
| RNF-01 | **Rendimiento** | El bot debe responder en menos de 1.5 segundos (saludo y catálogo). La generación de PDF y la firma PAdES se ejecutan fuera del *event loop* (worker o *threadpool*). |
| RNF-02 | **Seguridad** | Autenticación JWT con refresh rotativo, hash de contraseñas Argon2id, límite de peticiones por IP, validación de tipo MIME real para subidas, y cumplimiento de la Top 10 OWASP. Control de acceso por roles (RBAC). |
| RNF-03 | **Disponibilidad e integridad concurrente** | Verificación y reserva de disponibilidad bajo bloqueo distribuido (Redis) para evitar la doble reserva ante accesos simultáneos. Arquitectura desacoplada (API + worker + cola de mensajes con reintentos). |
| RNF-04 | **Calidad del software** | Análisis estático estricto (`mypy` sin advertencias), formateo y lint (`ruff`), cobertura de pruebas mínima del 75 % global y del 100 % en servicios de dominio y cálculos financieros. Pruebas de integración contra bases de datos reales (Testcontainers). |
| RNF-05 | **Integración y usabilidad** | Especificación OpenAPI 3 con esquemas y ejemplos para todos los endpoints. Interfaz *mobile-first* operable desde 360 px de ancho (vista del operador en celular). |
| RNF-06 | **Trazabilidad** | Logs estructurados en JSON con identificador de trazado (*trace id*) para las operaciones críticas. Bitácora de auditoría inmutable (solo lectura). |
| RNF-07 | **Configurabilidad** | Parámetros de negocio (umbral de simultaneidad, plazos, porcentajes, márgenes) definidos en variables de entorno, sin cambios de código. |

---

## 8. Identificación inicial de eventos, reglas, decisiones y acciones

### 8.1 Eventos iniciales del sistema

| Tipo | Evento | Origen / Disparador | Efecto principal |
| :--- | :--- | :--- | :--- |
| **Entrante** | Mensaje de WhatsApp entrante (texto o comprobante) | Cliente → webhook del gateway de mensajería | Inicia o continúa la conversación (bot o encargado). |
| **Entrante** | Solicitud de hablar con un encargado | Cliente (texto libre o opción del menú) | Derivación de la conversación a modo humano. |
| **Temporal** | Vencimiento del plazo del adelanto (24 h) | Tarea programada | La cotización sin comprobante pasa a estado `EXPIRED`. |
| **Temporal** | Umbral de revalidación de disponibilidad (60 min) | Al pulsar «Pagar adelanto» | Revalidación de cupo antes de revelar los datos de pago. |
| **Temporal** | Cierre semanal y mensual | Tarea programada | Consolidación financiera y generación de dashboards. |
| **Temporal** | Vencimiento del enlace de firma (7 días) y del OTP (10 min) | Reloj del sistema | Invalidación del enlace o del código; permite reemisión. |
| **Interno** | Comprobante de pago recibido | Sistema (asociación al pago) | Registro del pago en estado inicial de verificación. |
| **Interno** | Validación del adelanto | Encargado | Creación del evento, del contrato y transición de la cotización. |
| **Interno** | Aprobación o rechazo de sobrecupo | Encargado | Transición del pago entre `VERIFIED` y `REFUND_PENDING`. |
| **Interno** | Emisión, firma o anulación del contrato | Sistema / Cliente | Transición del contrato (`DRAFT`, `ISSUED`, `SIGNED`, `VOIDED`). |
| **Interno** | Llegada del personal a la locación | Operador | Transición del evento a `AWAITING_BALANCE`. |
| **Interno** | Cobro del saldo con evidencia | Operador | Habilita el inicio del show (`IN_PROGRESS`). |
| **Interno** | Solicitud y cobro de extensión en vivo | Operador | Registro de cobro adicional y transición a `EXTENDED`. |
| **Interno** | Toma y devolución de conversación | Encargado / Superadministrador | Cambio del responsable de atención. |
| **Externo** | Respuesta de Google Maps (distancia y tiempo) | Google Maps API | Alimenta el cálculo de movilidad y de traslado. |
| **Externo** | Cambio de estado de conversación (`pending`/`open`) | Gateway de mensajería | Cambio del modo de atención (bot ↔ humano). |

### 8.2 Reglas de negocio

| ID | Regla |
| :--: | :--- |
| **RN-01** | **Estructura de la cotización.** Total cotizado = precio del paquete base + suma de precios de extras + costo de movilidad. Los precios provienen del catálogo; la movilidad se calcula por separado. |
| **RN-02** | **Adelanto y saldo.** Adelanto = 10 % de (paquete + extras). Saldo = Total − Adelanto. **La movilidad no integra la base del adelanto**: se liquida íntegramente el día del evento. |
| **RN-03** | **Movilidad con margen comercial.** Costo de movilidad = f(distancia y tiempo de ida y vuelta, Google Maps) × 1.15. Si el cliente provee su propia movilidad, el costo se fija en S/ 0.00. |
| **RN-04** | **Disponibilidad y aprobación por umbral.** La disponibilidad depende de la conformación de elencos y del stock de inventario. Dos shows son simultáneos cuando sus intervalos `[inicio, fin)` se solapan (fin = inicio + duración del paquete). Solo cuentan eventos con adelanto validado y no cancelados. Si al incorporar el show solicitado la cantidad de simultáneos es ≤ 3, la asignación es automática; si supera 3, se exige aprobación manual expresa del encargado, gestionada como estado del pago (`REQUIRES_MANUAL_APPROVAL`). |
| **RN-05** | **Intervalo obligatorio de tránsito.** Para un mismo elenco con varios shows el mismo día: intervalo mínimo = tiempo de tránsito (Google Maps) + margen de desarme y descanso (30 min). Si la holgura real es inferior, se rechaza la asignación automática y deriva a revisión del encargado. |
| **RN-06** | **Condición de inicio del show.** Ningún show, armado de toldo ni ambientación puede iniciar sin haber cobrado el 100 % del saldo pendiente (servicios + movilidad). El cobro se registra in situ con evidencia obligatoria (medio de pago y fotografía) para no bloquear la operación. |
| **RN-07** | **Extensiones y liquidación post-evento.** El tiempo adicional pactado se registra como «Extensión en vivo» con tarifa acordada y se suma a la liquidación final antes de marcar el evento como liquidado. |
| **RN-08** | **Utilidad neta y costos fijos.** Utilidad neta = ingresos totales liquidados − (suma de costos fijos de paquetes + suma de costos fijos de extras + costos operativos de movilidad). |
| **RN-09** | **Vigencia de la cotización y revalidación de disponibilidad.** La cotización tiene vigencia de 24 h desde su envío; al vencer sin comprobante pasa a `EXPIRED`. Una cotización sin adelanto validado **no reserva cupo**. Al pulsar «Pagar adelanto» (tras 60 min del envío) se revalida la disponibilidad antes de revelar los datos de pago; al subir el comprobante se realiza una revalidación temprana; y al validar el pago una revalidación **atómica bajo bloqueo distribuido**, que deriva en aprobación o rechazo del sobrecupo según el cupo disponible. |
| **RN-10** | **Atención de la conversación.** Toda conversación tiene un solo responsable a la vez: modo `BOT` (estado `pending`) u `HUMANO` (estado `open`). La derivación registra motivo y resumen; las decisiones de negocio (pagos, sobrecupo) solo se toman en el panel, nunca en la conversación. |
| **RN-11** | **Ventana de servicio de 24 horas.** Con la ventana abierta (24 h desde el último mensaje entrante del cliente) se envía texto libre; cerrada, solo plantillas aprobadas. La bandeja indica el estado de la ventana en todo momento. |

### 8.3 Procesos de control

| # | Proceso | Tipo | Mecanismo de control |
| :--: | :--- | :---: | :--- |
| PC-01 | Verificación de recursos | Automático | Cruce de disponibilidad contra agenda de elencos e inventario físico. |
| PC-02 | Ajuste de intervalos de traslado | Híbrido | Sugerencia automática con Google Maps; facultad del encargado de editar el intervalo. |
| PC-03 | Umbral de shows simultáneos | Manual | Más de 3 eventos simultáneos → pago en `REQUIRES_MANUAL_APPROVAL` y notificación al encargado. |
| PC-04 | *Override* de movilidad | Manual | Edición del monto sugerido con justificación previa a la emisión. |
| PC-05 | Modo manual de contrato | Manual | Formulario administrativo que omite el bot. |
| PC-06 | Validación de pagos con reintento | Híbrido | Comprobante inválido → recordatorio y reintento sin cancelar la cotización. |
| PC-07 | Control de inicio del show | Operativo | Bloqueo del inicio hasta registrar el cobro del saldo con evidencia. |
| PC-08 | Liquidación de horas extra | Operativo | Registro formal de montos por tiempo adicional, con evidencia, previo al cierre. |
| PC-09 | Trazabilidad contable fija | Automático | Uso de costos fijos precargados para reportes auditables. |
| PC-10 | Persistencia de observaciones | Estructural | Campo específico visible en PDF y cronograma. |
| PC-11 | Revalidación de disponibilidad y vencimiento del adelanto | Automático | Revalidación con bloqueo distribuido; vencimiento automático a las 24 h. |
| PC-12 | Auditoría posterior de cobros in situ | Manual | El cobro nace verificado y se audita después (`REVIEWED` / `FLAGGED`). |
| PC-13 | Traspaso de conversación a encargado | Híbrido | Derivación a modo humano con motivo; retorno al bot mediante *release*. |

### 8.4 Decisiones y acciones — Reglas ECA (Evento · Condición · Acción)

| # | Evento | Condición | Acción |
| :--: | :--- | :--- | :--- |
| ECA-01 | Mensaje de WhatsApp entrante | La conversación no está en curso | El bot envía el saludo de bienvenida con las categorías de servicio y el catálogo. |
| ECA-02 | El cliente selecciona paquete, temática y extras | La selección es válida y los elementos están activos en el catálogo | El bot acepta la combinación y solicita los datos del evento. |
| ECA-03 | Datos del evento capturados | La fecha es futura y la dirección incluye distrito o coordenadas válidas de Lima/Callao | Se verifica la disponibilidad de recursos y se calcula la movilidad con Google Maps (ida y vuelta + 15 %). |
| ECA-04 | Verificación de disponibilidad | Hay cupo (inventario y elencos disponibles) | Se calcula total, adelanto (10 % de servicios) y saldo; se envía la cotización y la misma pasa a estado `SENT`. |
| ECA-05 | Verificación de disponibilidad | No hay cupo | Se recomienda otro horario o se deriva la conversación al encargado; **no se revelan datos de pago**. |
| ECA-06 | El cliente pulsa «Pagar adelanto» | Han transcurrido más de 60 minutos desde el envío de la cotización | Se revalida la disponibilidad antes de mostrar los medios de pago. |
| ECA-07 | Revalidación de disponibilidad | Hay cupo / no hay cupo | Se muestran los datos de pago y la cotización pasa a `PAYMENT_STARTED` / se ofrece alternativa o derivación. |
| ECA-08 | Comprobante de pago recibido | El cupo está disponible / el cupo está lleno o se supera el umbral | El pago se registra en `PENDING_VERIFICATION` / en `REQUIRES_MANUAL_APPROVAL` (alerta temprana). |
| ECA-09 | El encargado aprueba el pago | La revalidación atómica bajo bloqueo distribuido confirma el cupo | El pago pasa a `VERIFIED`, la cotización a `CONVERTED`, se crea el evento en `AWAITING_SIGNATURE` y el contrato en `DRAFT`. |
| ECA-10 | El comprobante es inválido o ilegible | El encargado lo rechaza indicando el motivo | El pago pasa a `REJECTED` y se habilita el reintento con un nuevo comprobante, sin cancelar la cotización. |
| ECA-11 | Adelanto validado | — | Se genera el contrato en PDF (`DRAFT → ISSUED`) con los datos, montos y observaciones, y se envía el enlace de firma por WhatsApp. |
| ECA-12 | El cliente completa la firma | El enlace es vigente y el OTP de 6 dígitos es correcto | Se sella el PDF con PAdES, el contrato pasa a `SIGNED`, el evento a `SCHEDULED` y se registra la auditoría (hash SHA-256, IP, agente de usuario, marcas de tiempo). |
| ECA-13 | Vencen las 24 h sin comprobante | El plazo de la cotización expira | La cotización pasa a `EXPIRED` y deja de retener cupo. |
| ECA-14 | El personal llega a la locación | El evento está en `SCHEDULED` | El evento pasa a `AWAITING_BALANCE`. |
| ECA-15 | El operador registra el cobro del saldo con evidencia | El saldo se ha cobrado al 100 % | El pago `BALANCE` se registra en `VERIFIED` (con auditoría posterior) y el evento pasa a `IN_PROGRESS`; en caso contrario, el inicio del show permanece **bloqueado**. |
| ECA-16 | El cliente solicita tiempo adicional durante el evento | La extensión es pactada | Se registra el cobro `EXTENSION` en `VERIFIED` con evidencia y el evento pasa a `EXTENDED`. |
| ECA-17 | El show culmina | Los cobros han sido liquidados | El evento pasa a `SETTLED`. |
| ECA-18 | Se incorpora un show con más de 3 simultáneos | El solape de intervalos reales supera el umbral con eventos de adelanto validado | El pago pasa a `REQUIRES_MANUAL_APPROVAL`; el encargado aprueba (`VERIFIED`) o rechaza (`REFUND_PENDING → REFUNDED`). |
| ECA-19 | El cliente declara proveer su movilidad | — | El costo de movilidad se fija en S/ 0.00 y queda asentado en el resumen. |
| ECA-20 | Se cumple el cierre semanal o mensual | — | Se consolida la utilidad neta (ingresos − costos fijos − movilidad) y se actualizan los dashboards. |
| ECA-21 | El cliente pide hablar con un encargado, o el bot falla | La conversación está en modo automático (dos incomprensiones consecutivas, error no controlado o solicitud explícita) | La conversación deriva a modo humano con motivo y resumen; el bot deja de responder y se notifica en la bandeja en tiempo real. |
| ECA-22 | Un encargado o superadministrador devuelve la conversación al bot | La conversación está asignada y abierta | La conversación vuelve al modo automático conservando el historial de la derivación. |

### 8.5 Resumen de ciclos de vida involucrados

| Ciclo | Estados iniciales identificados | Observación |
| :--- | :--- | :--- |
| **Cotización** | `SENT`, `PAYMENT_STARTED`, `CONVERTED`, `EXPIRED`, `CANCELLED` | La cotización sin adelanto validado no reserva cupo. |
| **Pago** | `PENDING_VERIFICATION`, `REQUIRES_MANUAL_APPROVAL`, `VERIFIED`, `REJECTED`, `REFUND_PENDING`, `REFUNDED` | El `REJECTED` habilita reintento con un pago nuevo. |
| **Evento** | `AWAITING_SIGNATURE`, `SCHEDULED`, `AWAITING_BALANCE`, `IN_PROGRESS`, `EXTENDED`, `SETTLED`, `CANCELLED` | El inicio del show exige saldo cobrado al 100 %. |
| **Contrato** | `DRAFT`, `ISSUED`, `SIGNED`, `VOIDED` | Solo un contrato vigente por evento; tras anular puede emitirse uno nuevo. |
| **Conversación (modo)** | `BOT`, `HUMAN` | Un solo responsable a la vez; decisión de negocio solo en el panel. |

---

## Referencias internas del proyecto

- Requerimientos funcionales completos (RF-01 a RF-32): `Docs/01-requisitos/02-requerimientos-funcionales.md`.
- Requerimientos no funcionales: `Docs/01-requisitos/03-requerimientos-no-funcionales.md`.
- Reglas de negocio, procesos de control y máquinas de estado: `Docs/01-requisitos/04-reglas-de-negocio-y-control.md`.
- Historias de usuario con criterios de aceptación (US-01 a US-32): `Docs/01-requisitos/05-historias-de-usuario.md`.
