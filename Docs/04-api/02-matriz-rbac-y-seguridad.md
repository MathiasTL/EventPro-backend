# 02. Matriz de Control de Acceso (RBAC) y Seguridad

---

## 1. Perfiles y Roles del Sistema

| Rol | Código | Descripción y Nivel de Acceso |
| :--- | :--- | :--- |
| **Super Administrador** | `SUPERADMIN` | Acceso irrestricto. Configuración de parámetros globales, gestión de usuarios, auditoría de logs y anulaciones especiales. |
| **Encargado del Negocio** | `ENCARGADO` | Acceso operativo y gerencial. Gestión de catálogo, emisión de cotizaciones y contratos, aplicación de *overrides*, aprobación de shows simultáneos, auditoría de cobros in situ y consulta de dashboards financieros. |
| **Operador de Elenco / Campo** | `OPERADOR` | Acceso móvil restringido a **sus propios eventos asignados** (los de su elenco, `crews.user_id`). Visualización de notas/observaciones, registro de llegada, cobro de saldo in situ con evidencia y extensiones de show. |
| **Cliente / Invitado** | `CLIENTE` | No tiene cuenta ni JWT. Acceso público acotado por un token temporal criptográfico de un solo uso, entregado por WhatsApp, que solo da acceso a **su propio contrato** (visualización, OTP y firma electrónica). Sus cotizaciones y comprobantes los gestiona a través del chat de WhatsApp (bot). |

> **Actores no humanos:** el **bot de WhatsApp** (que opera a través de Chatwoot) y las **tareas programadas** (vencimiento de cotizaciones, despacho de la cola `outbox_messages`) ejecutan casos de uso internos sin pasar por HTTP ni por esta matriz. Los endpoints HTTP equivalentes a las acciones del bot (`POST /quotes`, `POST /quotes/{id}/pay-advance`, `POST /quotes/{id}/cancel`, `POST /payments/advance`) están reservados a `ENCARGADO` y `SUPERADMIN`, para actuar en nombre del cliente.

---

## 2. Matriz de Permisos por Endpoint

Esta matriz y la [Especificación de Endpoints REST](01-especificacion-endpoints-rest.md) describen **exactamente el mismo inventario** de endpoints (método y ruta). Todas las rutas son relativas a `/api/v1`, con la excepción de `GET /health`, que se expone en la raíz del servicio (`/health`) para las sondas de infraestructura. Cualquier endpoint nuevo debe agregarse en ambos documentos.

**Leyenda:**

| Símbolo | Significado |
| :---: | :--- |
| `Sí` | Permitido. |
| `-` | Denegado (`403`, o `404` cuando el recurso está fuera de alcance del rol). |
| `Propios` | Permitido solo sobre eventos asignados al elenco del operador (`crews.user_id` = usuario autenticado, mediante `crew_assignments`); los demás eventos responden `404`. |
| `Token` | Permitido con el token de un solo uso del enlace de firma, solo para el contrato al que pertenece el token. |
| `Público` | Sin autenticación (acceso acotado por límites de peticiones). |
| `Firma` | Sin JWT; autenticado por la firma HMAC del webhook de Chatwoot (acceso interno, no es un acceso de usuario). |

### 2.0 Salud del Servicio

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /health` | Público | Público | Público | Público | Sin autenticación; se sirve en `/health` (fuera de `/api/v1`). No expone datos sensibles: solo el estado de PostgreSQL y Redis. |

### 2.1 Autenticación y Cuentas

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `POST /auth/login` | Público | Público | Público | - | Límite de 5 intentos por minuto por IP. |
| `POST /auth/refresh` | Público | Público | Público | - | Requiere refresh token vigente; rota el token. |
| `POST /auth/logout` | Sí | Sí | Sí | - | Revoca el refresh token indicado. |

### 2.2 Usuarios y Bitácora de Auditoría

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /users` | Sí | - | - | - | |
| `POST /users` | Sí | - | - | - | |
| `GET /users/{id}` | Sí | - | - | - | |
| `PATCH /users/{id}` | Sí | - | - | - | Desactivar o cambiar contraseña revoca los refresh tokens. |
| `GET /audit-logs` | Sí | Sí | - | - | Solo lectura. |

### 2.3 Catálogo Comercial y Elencos

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /catalog/packages` | Sí | Sí | Sí | Público | `direct_cost` e `inventory_items` solo para `SUPERADMIN` y `ENCARGADO`. |
| `GET /catalog/packages/{id}` | Sí | Sí | Sí | Público | Ídem. |
| `POST /catalog/packages` | Sí | Sí | - | - | |
| `PATCH /catalog/packages/{id}` | Sí | Sí | - | - | |
| `DELETE /catalog/packages/{id}` | Sí | Sí | - | - | Baja lógica. |
| `PUT /catalog/packages/{id}/inventory-items` | Sí | Sí | - | - | Gestiona `package_inventory_items`. |
| `PUT /catalog/packages/{id}/themes` | Sí | Sí | - | - | Gestiona `package_themes`. |
| `GET /catalog/themes` | Sí | Sí | Sí | Público | |
| `POST /catalog/themes` | Sí | Sí | - | - | |
| `PATCH /catalog/themes/{id}` | Sí | Sí | - | - | |
| `DELETE /catalog/themes/{id}` | Sí | Sí | - | - | Baja lógica. |
| `GET /catalog/extras` | Sí | Sí | Sí | Público | `direct_cost` solo para `SUPERADMIN` y `ENCARGADO`. |
| `POST /catalog/extras` | Sí | Sí | - | - | |
| `PATCH /catalog/extras/{id}` | Sí | Sí | - | - | |
| `DELETE /catalog/extras/{id}` | Sí | Sí | - | - | Baja lógica. |
| `GET /catalog/inventory-items` | Sí | Sí | - | - | |
| `POST /catalog/inventory-items` | Sí | Sí | - | - | |
| `PATCH /catalog/inventory-items/{id}` | Sí | Sí | - | - | |
| `DELETE /catalog/inventory-items/{id}` | Sí | Sí | - | - | Baja lógica. |
| `GET /crews` | Sí | Sí | - | - | |
| `POST /crews` | Sí | Sí | - | - | Vincula el elenco con un usuario `OPERADOR` (`user_id`). |
| `PATCH /crews/{id}` | Sí | Sí | - | - | |

### 2.4 Clientes y Cotizaciones

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /clients` | Sí | Sí | - | - | Datos personales (teléfono, DNI, RUC): acceso restringido a la gestión. |
| `GET /clients/{id}` | Sí | Sí | - | - | |
| `POST /quotes` | Sí | Sí | - | - | El bot ejecuta el caso de uso internamente. Límite de 30 solicitudes por minuto por IP. |
| `GET /quotes` | Sí | Sí | - | - | |
| `GET /quotes/{id}` | Sí | Sí | - | - | |
| `POST /quotes/{id}/pay-advance` | Sí | Sí | - | - | Revalidación de disponibilidad (D3). El bot lo ejecuta al pulsar «Pagar adelanto». |
| `POST /quotes/{id}/cancel` | Sí | Sí | - | - | |
| `PATCH /overrides/quotes/{id}/mobility` | Sí | Sí | - | - | Audita `OVERRIDE_MOBILITY`. |

### 2.5 Webhook de Chatwoot

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `POST /webhooks/chatwoot` | Firma | Firma | Firma | Firma | Valida `X-Chatwoot-Signature` (HMAC-SHA256 de `"{X-Chatwoot-Timestamp}.{cuerpo crudo}"`) y rechaza marcas de tiempo con más de 5 minutos. No usa JWT. Solo interno: bloqueado en el proxy. |

### 2.6 Pagos y Comprobantes

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `POST /payments/advance` | Sí | Sí | - | - | El bot ejecuta el caso de uso al recibir la imagen del cliente. |
| `GET /payments` | Sí | Sí | - | - | |
| `GET /payments/{id}` | Sí | Sí | - | - | |
| `GET /payments/{id}/evidence` | Sí | Sí | - | - | Archivo servido con control de acceso. |
| `PATCH /payments/{id}/verify` | Sí | Sí | - | - | Aprueba o rechaza un `ADVANCE` (rechazo permitido también desde `REQUIRES_MANUAL_APPROVAL`). |
| `PATCH /payments/{id}/audit` | Sí | Sí | - | - | Marca `REVIEWED` o `FLAGGED` un cobro `BALANCE` o `EXTENSION`. |
| `PATCH /payments/{id}/refund` | Sí | Sí | - | - | `REFUND_PENDING` → `REFUNDED`. |
| `POST /overrides/payments/{id}/approve-simultaneous` | Sí | Sí | - | - | Audita `APPROVE_OVERBOOKED_PAYMENT` o `REJECT_OVERBOOKED_PAYMENT`. |

### 2.7 Contratos y Firma Electrónica

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /contracts` | Sí | Sí | - | - | |
| `GET /contracts/{id}` | Sí | Sí | - | - | |
| `GET /contracts/{id}/pdf` | Sí | Sí | - | - | PDF sellado si el contrato está `SIGNED`. |
| `POST /contracts/manual` | Sí | Sí | - | - | Crea cotización `MANUAL`, evento y contrato; audita `MANUAL_CONTRACT`. |
| `POST /contracts/{id}/resend-link` | Sí | Sí | - | - | Invalida el enlace anterior. |
| `POST /contracts/{id}/void` | Sí | Sí | - | - | |
| `GET /contracts/sign/{token}` | - | - | - | Token | Vista del contrato; solo el contrato del token. |
| `GET /contracts/sign/{token}/pdf` | - | - | - | Token | |
| `POST /contracts/sign/{token}/otp` | - | - | - | Token | Envía OTP de 6 dígitos por WhatsApp; con límite de solicitudes. |
| `POST /contracts/sign/{token}/otp/verify` | - | - | - | Token | Máximo 5 intentos por OTP. Devuelve `otp_proof`. |
| `POST /contracts/sign/{token}` | - | - | - | Token | Firma manuscrita + prueba de OTP; sello PAdES; consume el token. Audita `CONTRACT_SIGNED`. |

### 2.8 Cronograma y Operación en Evento

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /events/schedule` | Sí | Sí | Propios | - | Filtros: rango de fechas, distrito, temática, estado, elenco. |
| `GET /events/{id}` | Sí | Sí | Propios | - | El operador no ve el teléfono del cliente ni los pagos. |
| `POST /events/{id}/crew-assignments` | Sí | Sí | - | - | Con override del intervalo (RF-22) audita `OVERRIDE_TRANSIT_INTERVAL`. |
| `DELETE /events/{id}/crew-assignments/{assignment_id}` | Sí | Sí | - | - | Solo antes de `IN_PROGRESS`. |
| `POST /events/{id}/arrive` | Sí | Sí | Propios | - | `SCHEDULED` → `AWAITING_BALANCE`. |
| `POST /events/{id}/check-in-and-collect` | Sí | Sí | Propios | - | Crea un pago `BALANCE` `VERIFIED` con evidencia obligatoria. |
| `POST /events/{id}/extensions` | Sí | Sí | Propios | - | Crea un pago `EXTENSION` `VERIFIED` con evidencia obligatoria. |
| `POST /events/{id}/settle` | Sí | Sí | Propios | - | `IN_PROGRESS` o `EXTENDED` → `SETTLED`. |
| `POST /events/{id}/cancel` | Sí | Sí | - | - | Libera inventario y anula el contrato. |
| `PATCH /overrides/crew-assignments/{id}/transit-interval` | Sí | Sí | - | - | Audita `OVERRIDE_TRANSIT_INTERVAL`. |

### 2.9 Analítica Financiera y BI

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /reports/dashboard` | Sí | Sí | - | - | KPIs de RF-25. |
| `GET /reports/financial/pnl` | Sí | Sí | - | - | Utilidad neta (RF-24). |

### 2.10 Conversaciones (Bandeja de WhatsApp)

| Endpoint | SUPERADMIN | ENCARGADO | OPERADOR | CLIENTE (Token) | Notas |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /conversations` | Sí | Sí | - | - | Contiene teléfonos de clientes: acceso restringido a la gestión. |
| `GET /conversations/{id}/messages` | Sí | Sí | - | - | Consultado a Chatwoot; `503` si no responde. |
| `GET /conversations/{id}/attachments/{attachment_id}` | Sí | Sí | - | - | Proxy autenticado de los medios del chat; no exige que la conversación esté tomada. |
| `POST /conversations/{id}/messages` | Sí | Sí | - | - | Solo en conversaciones tomadas por el propio usuario. Envía como el agente de servicio y audita al autor real (`SEND_CONVERSATION_MESSAGE`). |
| `POST /conversations/{id}/takeover` | Sí | Sí | - | - | Un `ENCARGADO` no puede tomar una conversación asignada a otro usuario (`409`); un `SUPERADMIN` sí y audita `OVERRIDE_CONVERSATION_ASSIGNMENT`. |
| `POST /conversations/{id}/release` | Sí | Sí | - | - | Solo el usuario asignado o un `SUPERADMIN`. |
| `GET /conversations/stream` | Sí | Sí | - | - | SSE. El access token JWT viaja en el parámetro `access_token` (ver sección 4). |

---

---

## 3. Mecanismo de Seguridad y Autenticación JWT

### 3.1 Ciclo de Vida de Tokens
1. **Access Token:**
   * Algoritmo: HMAC-SHA256 (`HS256`) o Asimétrico (`RS256`). Biblioteca: **PyJWT** (ADR-09).
   * Tiempo de vida: **60 minutos**.
   * Payload: `sub` (User UUID), `role` (`ENCARGADO`), `exp`, `iat`.
2. **Refresh Token:**
   * UUID aleatorio criptográfico opaco; solo se almacena su hash en la tabla `refresh_tokens`.
   * Tiempo de vida: **7 días**.
   * **Rotación Obligatoria:** Cada uso genera un nuevo refresh token e invalida el anterior, mitigando ataques de secuestro de sesión. Presentar un token ya revocado devuelve `401`.
   * **Cierre de sesión:** `POST /auth/logout` revoca el refresh token indicado. Desactivar un usuario o cambiar su contraseña revoca todos sus refresh tokens.
3. **Token del enlace de firma (CLIENTE):**
   * Valor criptográfico aleatorio de un solo uso, entregado por WhatsApp; solo se almacena su hash SHA-256 (`signature_token_hash`) con expiración (`signature_token_expires_at`).
   * No es un JWT y no otorga ningún rol del panel: solo permite operar el contrato al que pertenece.
   * Se consume al firmar; `POST /contracts/{id}/resend-link` lo reemplaza e invalida el anterior.
4. **Prueba de OTP (`otp_proof`):** credencial de corta duración (15 minutos), ligada a un contrato, emitida al verificar el OTP y exigida en `POST /contracts/sign/{token}`.

### 3.2 Alcance por Rol
* **Control por endpoint:** cada ruta valida el rol del JWT contra la matriz de la sección 2 mediante una dependencia de autorización; un rol no permitido recibe `403`.
* **Alcance del `OPERADOR`:** además del rol, las rutas marcadas `Propios` verifican que el evento tenga una asignación (`crew_assignments`) de un elenco cuyo `crews.user_id` sea el usuario autenticado. Si no, responden `404` para no revelar la existencia del evento.
* **Alcance del `CLIENTE`:** el token del enlace identifica un único contrato; no puede listar ni consultar otros recursos.
* **Datos sensibles:** los costos directos (`direct_cost`) y los datos personales de clientes (teléfono, DNI, RUC) no se exponen a `OPERADOR` ni a consultas públicas.

---

## 4. Políticas de Seguridad de la API (OWASP Top 10)

1. **CORS (Cross-Origin Resource Sharing):** Restringido explícitamente a los dominios del frontend de la promotora (`https://app.eventpro.pe`) y `localhost` en desarrollo.
2. **Rate Limiting:** Implementado con `slowapi` sobre Redis (ADR-09). Un exceso responde `429` con el tipo de error `rate-limit-exceeded` y la cabecera `Retry-After`:

   | Endpoint | Límite |
   | :--- | :--- |
   | `POST /auth/login` | Máximo 5 intentos por minuto por IP. |
   | `POST /quotes` | Máximo 30 solicitudes por minuto por IP. |
   | `POST /contracts/sign/{token}/otp` | Máximo 3 solicitudes por contrato cada 10 minutos y 10 por IP por hora; reenvío no antes de 60 segundos. |
   | `POST /contracts/sign/{token}/otp/verify` | Máximo 5 intentos fallidos por OTP (`otp_attempts`); al superarlos se invalida el OTP. Adicionalmente, 20 intentos por IP por hora. |
   | `GET /contracts/sign/{token}` y `GET /contracts/sign/{token}/pdf` | Máximo 30 solicitudes por minuto por IP, para dificultar la enumeración de tokens. |

3. **Firma del Webhook de Chatwoot:** `POST /webhooks/chatwoot` exige las cabeceras `X-Chatwoot-Timestamp` (marca de tiempo Unix en segundos) y `X-Chatwoot-Signature: sha256=<hex>`, el HMAC-SHA256 de `"{X-Chatwoot-Timestamp}.{cuerpo crudo}"` calculado con `CHATWOOT_WEBHOOK_SECRET`. Se recalcula y se compara en tiempo constante antes de procesar el evento, y se rechazan las marcas de tiempo con más de 5 minutos de antigüedad (mitiga la repetición de peticiones capturadas). Sin firma válida responde `401` (`invalid-webhook-signature`), no se encola nada y se registra el intento. El endpoint es **solo interno**: el proxy inverso lo bloquea hacia internet y únicamente es accesible desde la red interna de Docker. El procesamiento es idempotente por el identificador de mensaje o evento de Chatwoot (deduplicación en Redis, TTL de 7 días). La firma `X-Hub-Signature-256` de Meta y el reto de verificación de suscripción los valida ahora el propio Chatwoot en su webhook público, no EventPro; EventPro ya no expone ningún endpoint hacia Meta.
4. **Seguridad del OTP:** código de 6 dígitos generado con un generador criptográfico, almacenado solo con hash (`otp_hash`), con vigencia de 10 minutos, intentos limitados y entrega por WhatsApp a través de `outbox_messages` (el contenido del OTP se elimina del `payload` tras el envío).
5. **Aislamiento de Archivos Binarios:** los medios del chat (adjuntos de Chatwoot) se sirven únicamente a través del proxy autenticado `GET /conversations/{id}/attachments/{attachment_id}`; las URL de Chatwoot no se exponen al navegador. Los comprobantes y evidencias subidos no se ejecutan ni se sirven directamente desde rutas del sistema operativo; se almacenan con extensión neutral y nombre UUID, y se descargan únicamente a través de la API con control de acceso (`GET /payments/{id}/evidence`).
6. **Validación de Subidas:** máximo 5 MB por archivo; el tipo se valida por contenido (*magic bytes*, biblioteca `filetype`) y no solo por extensión ni por `Content-Type`. Las evidencias de cobro in situ admiten solo imágenes (JPEG, PNG, WebP); los comprobantes de adelanto, además, PDF.
7. **Headers de Seguridad HTTP:** Inclusión obligatoria de `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
8. **Auditoría:** las acciones críticas (overrides, aprobación de sobrecupo, auditoría de cobros, contratos manuales y firmas) se registran en `audit_logs`, que es de solo lectura vía API (`GET /audit-logs`).
9. **Autenticación del stream SSE:** `GET /conversations/stream` usa el mismo access token JWT (rol `ENCARGADO` o `SUPERADMIN`) enviado en el parámetro de consulta `access_token`, porque `EventSource` no permite cabeceras personalizadas y la API no usa cookies. Es el único endpoint que acepta el token fuera de `Authorization`. Como la cadena de consulta puede quedar en registros, el proxy y la aplicación no deben registrar la consulta de esta ruta; el servidor cierra el stream al vencer el token y el cliente renueva con `POST /auth/refresh` y se reconecta. El stream es de solo lectura y no sustituye la validación de rol de los demás endpoints del módulo.
