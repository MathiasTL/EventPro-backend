# 01. Visión, Alcance y Actores del Sistema (EventPro)

---

## 1. Contexto del Negocio y Problemática

### 1.1 Contexto Organizacional
**EventPro** es una solución integral diseñada para una promotora de eventos con sede en Lima, Perú, registrada en la SUNAT bajo persona natural con negocio (RUC personal). La gestión administrativa, operativa y comercial está a cargo de **dos encargados (administradores)**.

La promotora comercializa servicios de entretenimiento para eventos sociales y corporativos (cumpleaños, shows de 30/40/50 años, baby showers, eventos infantiles, etc.). Su oferta comprende:
* **Paquetes principales:** Shows de Hora Loca, servicios de DJ, Maestros de Ceremonia (MC), shows infantiles, baby showers.
* **Infraestructura y ambientación:** Decoraciones temáticas, estructuras de toldos, iluminación y sonido.
* **Extras llamativos:** Personajes temáticos especiales, muñecos gigantes (ej. gorila gigante), bailarines adicionales, efectos especiales.

El modelo operativo se fundamenta en la contratación de **artistas, elencos y proveedores freelance** (bailarines, animadores, decoradores, técnicos de toldos, DJs), quienes no forman parte de una planilla fija, sino que son convocados y remunerados por evento/servicio prestado.

### 1.2 Diagnóstico del Estado Actual (As-Is)
Antes de la implementación de EventPro, la operación sufría de cuellos de botella críticos:
1. **Atención y cotización manual por WhatsApp:** Respuestas lentas y no estandarizadas a los clientes; cálculo artesanal de tarifas y costos de transporte (consultas subjetivas o sondeos en apps de movilidad tipo inDrive).
2. **Generación lenta y propensa a errores de contratos:** El encargado clonaba y editaba archivos Word/PDF antiguos, aumentando el riesgo de inconsistencias legales o datos errados.
3. **Falta de visibilidad de agenda y recursos:** La asignación de personal y reservas dependía exclusivamente de la memoria y el criterio de los administradores, sin alertas de sobreventa ni verificación formal de inventario de toldos/decoración.
4. **Pérdida de observaciones del cliente:** Preferencias de música, bailes prohibidos o directrices específicas quedaban aisladas en chats de WhatsApp y no llegaban al elenco.
5. **Opacidad financiera:** Ausencia de consolidación automática de ingresos, costos de elencos/materiales y utilidad neta semanal o mensual.

---

## 2. Visión del Producto (To-Be)

**EventPro** automatiza el ciclo de vida comercial y operacional de la promotora: desde el primer contacto en WhatsApp vía chatbot, el cálculo determinístico de cotizaciones y movilidad, la validación de anticipos y generación de contratos digitales en PDF con firma electrónica, hasta la visualización en cronograma y tableros financieros. 

Al mismo tiempo, incorpora **mecanismos de control y aprobación humana** en puntos neurálgicos, garantizando que el negocio preserve su flexibilidad y toma de decisiones ante eventualidades o alta concurrencia.

---

## 3. Alcance del Sistema (Scope)

### 3.1 Dentro del Alcance (In Scope - MVP / Fase 1)
* **Canal Conversacional (WhatsApp Business API & Webhook):** Saludo automático, presentación de catálogo estructurado de paquetes, temáticas y extras, captura de datos del cliente, fecha, hora y ubicación del evento.
* **Motor de Cotización y Cálculo de Movilidad:** Integración con Google Maps Platform (Distance Matrix / Directions) para el cálculo de distancia y tiempo (ida y vuelta) con recargo comercial (+15%) y posibilidad de exención si el cliente provee movilidad.
* **Control de Disponibilidad y Reglas de Despacho:** Validación de elencos freelance e inventario de mobiliario; cálculo de tiempos de traslado entre eventos y bloqueo/aprobación manual cuando se superen 3 eventos simultáneos.
* **Gestión de Pagos y Comprobantes:** Registro de anticipos (10% sobre servicios base) mediante billeteras digitales (Yape / Plin) o transferencias bancarias; subida de capturas y flujo de verificación con reintentos.
* **Contratos Inteligentes en PDF y Firma Digital:** Emisión automatizada del contrato PDF con desglose estricto de conceptos y soporte para modo manual de respaldo; integración de firma digital.
* **Cronograma Operativo Centralizado:** Tablero calendarizado con filtros temporales y visualización prominente de observaciones del cliente por evento.
* **Protocolo de Ejecución y Liquidación en Vivo:** Regla estricta de cobro del saldo pendiente antes de iniciar el show, registro de extensiones de tiempo post-evento y cierre contable de servicio.
* **Módulo Financiero y Dashboard Analítico:** Consolidación semanal y mensual de ingresos, costos fijos directos y margen de utilidad neta.

### 3.2 Fuera del Alcance (Out of Scope - Fases Posteriores)
* Emisión automática de comprobantes electrónicos SUNAT (Boletas / Facturas electrónicas vía PSE/OSE). En esta fase los cobros quedan registrados como transacciones internas.
* Cobros con tarjeta de crédito mediante pasarelas internacionales (Stripe, Mercado Pago Web Checkout); el canal principal es transferencias y billeteras locales peruanas (Yape).
* Aplicación móvil nativa para el elenco (iOS / Android); el personal se coordina mediante reportes consolidados y resúmenes compartidos.

---

## 4. Perfiles y Actores del Sistema

| Actor | Tipo | Descripción y Responsabilidades |
| :--- | :--- | :--- |
| **Cliente** | Externo (Humano) | Usuario interesado en contratar servicios. Interactúa mediante WhatsApp para consultar catálogo, cotizar, subir comprobantes de pago y firmar digitalmente el contrato. |
| **Chatbot / WhatsApp Service** | Automatizado (Sistema) | Servicio conversacional que procesa webhooks de WhatsApp, guía al cliente a través del flujo guiado y recopila parámetros del evento. |
| **Encargado / Administrador** | Interno (Humano) | Uno de los 2 responsables del negocio. Cuenta con privilegios completos para aprobar shows simultáneos, aplicar *overrides* de movilidad o tiempo de traslado, emitir contratos en modo manual y auditar métricas financieras. |
| **Personal de Elenco / Operador** | Interno / Freelance | Artistas, animadores, DJs y armadores de toldos. Ejecutan el servicio en campo, reportan cobro del saldo in-situ e informan extensiones de tiempo de show. |
| **Google Maps API** | Externo (Servicio) | Servicio externo consumido para geolocalización, cálculo de distancias y tiempos de tránsito en Lima Metropolitana y Callao. |
