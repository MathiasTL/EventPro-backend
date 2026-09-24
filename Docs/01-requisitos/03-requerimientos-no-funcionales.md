# 03. Especificación de Requerimientos No Funcionales (RNF)

---

## 1. RNF-01: Rendimiento y Eficiencia

* **RNF-01.1 (Tiempo de respuesta de API):** Los endpoints transaccionales (catálogo, cotizaciones, consulta de agenda) deben responder con un tiempo de latencia $P_{95} \le 300\text{ ms}$ bajo condiciones normales de carga.
* **RNF-01.2 (Respuesta a Webhooks):** El endpoint receptor del Webhook de WhatsApp debe procesar y acusar recibo (HTTP 200) en menos de **1.5 segundos** para prevenir timeouts y reintentos automáticos del servidor de WhatsApp.
* **RNF-01.3 (Generación de Documentos PDF):** La renderización y compilación del contrato en formato PDF no debe exceder los **3 segundos** desde que se valida el pago.
* **RNF-01.4 (Concurrencia de Cotizaciones):** El motor de cotización debe soportar al menos 50 solicitudes concurrentes sin degradación del servicio ni inconsistencias en el cálculo.

---

## 2. RNF-02: Seguridad y Protección de Datos

* **RNF-02.1 (Autenticación y Autorización):** Los endpoints administrativos deben estar protegidos mediante autenticación basada en tokens JWT (*JSON Web Tokens*) firmados con algoritmo asimétrico o HMAC-SHA256 y tiempo de expiración corto (máximo 60 minutos para Access Token, con Refresh Token rotativo).
* **RNF-02.2 (Almacenamiento de Credenciales):** Las contraseñas de los administradores y operadores deben almacenarse utilizando funciones de derivación de claves seguras: **Argon2id** o **Bcrypt** con factor de trabajo adecuado ($cost \ge 12$).
* **RNF-02.3 (Cifrado de Comunicaciones):** Toda la comunicación en tránsito debe ejecutarse obligatoriamente bajo el protocolo criptográfico **TLS 1.3** (HTTPS y WSS).
* **RNF-02.4 (Validación y Sanitización de Entradas):** Todas las entradas recibidas a través de la API y el Webhook deben someterse a esquemas estrictos de validación con tipado fuerte (Pydantic v2), previniendo inyecciones SQL (mitigadas por el uso del ORM SQLAlchemy) y ataques Cross-Site Scripting (XSS).
* **RNF-02.5 (Gestión de Comprobantes de Pago e Imágenes):** Los archivos subidos (capturas de Yape/transferencia y firmas digitales) deben validarse por tipo MIME real y tamaño (máximo 5 MB por archivo), almacenándose de forma segura con identificadores UUID aleatorios sin exponer rutas directas del servidor.

---

## 3. RNF-03: Disponibilidad y Resiliencia

* **RNF-03.1 (Tasa de Disponibilidad):** La API backend de EventPro debe ofrecer una disponibilidad mínima del **99.5%** en horario operativo comercial (08:00 a 23:00 hrs GMT-5).
* **RNF-03.2 (Manejo de Caídas de Servicios Externos):** 
  * En caso de indisponibilidad temporal de la API de Google Maps, el sistema no debe abortar la cotización; debe aplicar una tarifa plana de contingencia o habilitar el modo de cotización manual con notificación al encargado.
  * Si el servicio de WhatsApp experimenta interrupciones, los mensajes pendientes deben encolarse para su reprocesamiento automático una vez restablecida la conexión.
* **RNF-03.3 (Backups de Base de Datos):** La base de datos relacional debe contar con copias de seguridad automáticas diarias e instantáneas (*snapshots*) previas a cualquier migración de esquema.

---

## 4. RNF-04: Mantenibilidad y Calidad de Código

* **RNF-04.1 (Arquitectura Limpia y Modular):** El backend debe estructurarse separando responsabilidades en capas independientes:
  * **Capa de Transporte / Controladores (API Routers):** Gestión de peticiones HTTP y serialización.
  * **Capa de Lógica de Negocio (Services / Use Cases):** Reglas de cotización, validación y contratos.
  * **Capa de Persistencia (Repositories / Models):** Acceso a base de datos mediante SQLAlchemy.
  * **Capa de Integración Externa:** Clientes HTTP desacoplados para WhatsApp y Google Maps.
* **RNF-04.2 (Tipado y Cobertura de Pruebas):** El código fuente en Python 3.12+ debe aplicar tipado estático (*Type Hints*) en el 100% de funciones de servicio y alcanzar una cobertura mínima de pruebas automatizadas (*Unit Tests* con `pytest`) del **75%** en los módulos críticos de cotización, pagos y contratos.
* **RNF-04.3 (Registro de Actividad / Logging):** Se debe implementar *Structured Logging* en formato JSON con niveles estándar (`INFO`, `WARNING`, `ERROR`), capturando identificadores de traza (*Trace ID*) para auditar cada interacción del cliente desde WhatsApp hasta la liquidación final.

---

## 5. RNF-05: Integración e Interoperabilidad

* **RNF-05.1 (Compatibilidad OpenAPI / Swagger):** El backend debe generar y exponer automáticamente la especificación OpenAPI v3 con esquemas completos y ejemplos para todos los endpoints expuestos.
* **RNF-05.2 (Consumo de Google Maps Platform):** Las llamadas a la API de Google Maps deben implementar mecanismos de almacenamiento en caché (Redis o caché en memoria) para rutas idénticas en un lapso de 24 horas, optimizando costos de cuota de API.
