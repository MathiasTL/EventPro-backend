# 01. Especificación de Endpoints RESTful (API v1)

---

## 1. Convenciones Globales de la API

* **URL Base:** `https://api.eventpro.pe/api/v1` (o `http://localhost:8000/api/v1` en local). Todas las rutas de este documento son relativas a la URL base, con la excepción de `GET /health`, que se expone en la raíz del servicio (`/health`) para las sondas de infraestructura.
* **Formato de Intercambio:** `application/json` (UTF-8). Excepciones: `multipart/form-data` para subida de comprobantes, evidencias y adjuntos de conversación, y `text/event-stream` (Server-Sent Events) en `GET /conversations/stream`.
* **Autenticación:** Cabecera HTTP `Authorization: Bearer <jwt_access_token>`. Las excepciones (endpoints públicos, de token de cliente, del webhook de Chatwoot y del stream SSE) se indican en cada endpoint y se resumen en la [Matriz RBAC](02-matriz-rbac-y-seguridad.md), que es el complemento obligatorio de este documento: ambos describen exactamente el mismo inventario de endpoints (método y ruta).
* **Códigos de estado:** `200 OK` (lecturas y actualizaciones), `201 Created` (creaciones de recursos), `202 Accepted` (acción aceptada y procesada de forma asíncrona), `204 No Content` (acciones sin cuerpo de respuesta), `400`/`422` (validación), `401`/`403` (autenticación y autorización), `404` (recurso inexistente o fuera de alcance del rol), `409 Conflict` (conflicto de dominio), `410 Gone` (recurso vencido), `429` (límite de peticiones), `503` (dependencia no disponible).
* **Identificadores de estado y enumeraciones:** todos los valores de enumeración de los *payloads* son códigos en inglés `UPPER_SNAKE_CASE` (ver [RN, sección 3.5](../01-requisitos/04-reglas-de-negocio-y-control.md#35-tabla-de-mapeo-código-etiqueta-de-interfaz-y-significado)). Las etiquetas en español pertenecen solo a la interfaz. Enumeraciones usadas en esta API:
  * `payment_method`: `YAPE`, `PLIN`, `BANK_TRANSFER`, `CASH`.
  * `concept` (pago): `ADVANCE`, `BALANCE`, `EXTENSION`.
  * `service_category`: `SHOW`, `DJ`, `DECORATION`, `TENTS`.
  * Estados de cotización, pago, evento, contrato y `audit_status`: los de las máquinas de estados de la sección 3 del documento de RN.
* **Listados paginados:** los listados marcados como *paginado* aceptan `page` (por defecto `1`) y `page_size` (por defecto `20`, máximo `100`) y responden `{"items": [...], "page": 1, "page_size": 20, "total": 135}`.
* **Montos:** números decimales en Soles (PEN) con dos decimales.
* **Subida de archivos:** máximo **5 MB** por archivo. El tipo se valida por contenido (*magic bytes*), no solo por la extensión ni por la cabecera `Content-Type`. Comprobantes de adelanto: JPEG, PNG, WebP o PDF. Evidencias de cobro in situ: solo imagen (JPEG, PNG o WebP). Un archivo inválido responde `422` con el tipo de error `invalid-file`.
* **Respuestas de Error:** Estandarizadas bajo la norma **RFC 7807 (Problem Details)**, con `Content-Type: application/problem+json`:
  ```json
  {
    "type": "https://errors.eventpro.pe/invalid-advance-amount",
    "title": "Monto de adelanto inválido",
    "status": 400,
    "detail": "El adelanto debe ser exactamente el 10% de los servicios contratados (S/. 120.00).",
    "instance": "/api/v1/payments/advance"
  }
  ```
  El catálogo de tipos de error de dominio se encuentra en la [sección 3](#3-catálogo-de-errores-de-dominio-rfc-7807).

---

## 2. Catálogo de Endpoints

### 2.0 Módulo: Salud del Servicio (`/health`)

#### `GET /health`
* **Descripción:** Sonda de salud (*liveness* y *readiness*) usada por el `HEALTHCHECK` del contenedor, por Docker Compose y por el balanceador. Verifica la conectividad con PostgreSQL (consulta trivial) y con Redis (`PING`), cada una con un tiempo límite corto (2 s).
* **Seguridad:** Público, sin autenticación. Se sirve en la raíz del servicio (`/health`), no bajo `/api/v1`. No incluye versiones, credenciales ni datos de negocio.
* **Response `200 OK`:** `{"status": "ok", "checks": {"database": "ok", "redis": "ok"}}`
* **Response `503 Service Unavailable`:** `{"status": "degraded", "checks": {"database": "ok", "redis": "error"}}` cuando alguna dependencia no responde.

### 2.1 Módulo: Autenticación y Cuentas (`/auth`)

#### `POST /auth/login`
* **Descripción:** Autentica a un usuario del panel (superadministrador, encargado u operador) y emite tokens JWT.
* **Seguridad:** Público. Límite de 5 intentos por minuto por IP.
* **Request Body:**
  ```json
  {
    "email": "encargado@eventpro.pe",
    "password": "PasswordSeguro123!"
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "refresh_token": "d8f9a2b1-5c3e-4f8a-9b1d...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "id": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
      "full_name": "Juan Pérez",
      "role": "ENCARGADO"
    }
  }
  ```
* **Errores:** `401` (`invalid-credentials`), `403` (`user-inactive`), `429` (`rate-limit-exceeded`).

#### `POST /auth/refresh`
* **Descripción:** Rota el Refresh Token y entrega un nuevo Access Token. El refresh token usado queda revocado; presentar un token ya revocado devuelve `401`.
* **Seguridad:** Público (requiere un refresh token vigente).
* **Request Body:** `{"refresh_token": "d8f9a2b1-5c3e-4f8a-9b1d..."}`
* **Response `200 OK`:** `{"access_token": "...", "refresh_token": "...", "expires_in": 3600}`

#### `POST /auth/logout`
* **Descripción:** Cierra la sesión revocando el refresh token indicado (`refresh_tokens.is_revoked = true`). El access token expira por su propio tiempo de vida (60 minutos). La operación es idempotente.
* **Seguridad:** Autenticado (cualquier rol del panel).
* **Request Body:** `{"refresh_token": "d8f9a2b1-5c3e-4f8a-9b1d..."}`
* **Response `204 No Content`.**

---

### 2.2 Módulo: Usuarios (`/users`)

#### `GET /users`
* **Descripción:** Lista paginada de usuarios del panel (gestión de cuentas del superadministrador).
* **Seguridad:** Rol `SUPERADMIN`.
* **Query Params:** `role=OPERADOR`, `is_active=true`, `q=juan` (búsqueda por nombre, correo o teléfono), `page`, `page_size`.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "id": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
        "full_name": "Juan Pérez",
        "email": "encargado@eventpro.pe",
        "phone": "+51987654321",
        "role": "ENCARGADO",
        "is_active": true,
        "created_at": "2026-09-01T15:00:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```

#### `POST /users`
* **Descripción:** Crea un usuario del panel con su rol. La contraseña se almacena con hash (Argon2id/Bcrypt); nunca se devuelve.
* **Seguridad:** Rol `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "full_name": "María Gómez",
    "email": "operador1@eventpro.pe",
    "phone": "+51911222333",
    "role": "OPERADOR",
    "password": "PasswordTemporal123!"
  }
  ```
* **Response `201 Created`:** el usuario creado (mismo formato que un ítem de `GET /users`).
* **Errores:** `409` (`duplicate-resource`, correo o teléfono ya registrado), `422` (`validation-error`).

#### `GET /users/{id}`
* **Descripción:** Detalle de un usuario.
* **Seguridad:** Rol `SUPERADMIN`.
* **Response `200 OK`:** el usuario (mismo formato que un ítem de `GET /users`).

#### `PATCH /users/{id}`
* **Descripción:** Actualiza datos, rol, estado o contraseña de un usuario en una única transacción atómica (fila bloqueada con `SELECT … FOR UPDATE` y bloqueo de sesión): desactivar un usuario (`is_active = false`) o cambiar su contraseña revoca todos sus refresh tokens **en esa misma transacción** — si la revocación falla, el cambio se deshace por completo. Un `SUPERADMIN` no puede desactivarse a sí mismo ni quitarse su propio rol, y la operación conserva siempre al menos un `SUPERADMIN` activo. El efecto sobre los access tokens vigentes es inmediato: la autorización se resuelve con la cuenta en cada petición, así que una cuenta desactivada responde `401` y un rol degradado pierde sus permisos sin esperar a la expiración del JWT.
* **Seguridad:** Rol `SUPERADMIN`.
* **Request Body (todos los campos son opcionales):**
  ```json
  {
    "full_name": "María Gómez Salas",
    "phone": "+51911222444",
    "role": "ENCARGADO",
    "is_active": true,
    "password": "NuevaPassword456!"
  }
  ```
* **Response `200 OK`:** el usuario actualizado.
* **Errores:** `403` (modificación de sí mismo), `404` (`not-found`), `409` (`duplicate-resource`, correo o teléfono ya registrado), `422` (`validation-error`; por ejemplo, «Debe permanecer al menos un SUPERADMIN activo»).

---

### 2.3 Módulo: Bitácora de Auditoría (`/audit-logs`)

#### `GET /audit-logs`
* **Descripción:** Consulta paginada de la bitácora de decisiones críticas (`audit_logs`): overrides, aprobaciones de sobrecupo, auditoría de cobros, contratos manuales y firmas. Solo lectura; la bitácora no se edita ni se elimina.
* **Seguridad:** Roles `SUPERADMIN` o `ENCARGADO`.
* **Query Params:** `action=OVERRIDE_MOBILITY`, `entity_name=quotes`, `entity_id=<uuid>`, `user_id=<uuid>`, `from_date=2026-10-01`, `to_date=2026-10-31`, `page`, `page_size`.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "id": "al-3f21...",
        "user_id": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
        "action": "OVERRIDE_MOBILITY",
        "entity_name": "quotes",
        "entity_id": "q9c8a1b2-...",
        "old_values": {"final_mobility_amount": 80.50},
        "new_values": {"final_mobility_amount": 95.00, "reason": "Zona de alto tráfico con peajes no computados."},
        "created_at": "2026-09-23T18:02:11Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```

---

### 2.4 Módulo: Catálogo Comercial (`/catalog`)

Los endpoints de lectura de paquetes, temáticas y extras son públicos (los consume también el bot de WhatsApp) y **no exponen** costos directos (`direct_cost`). Cuando los consulta un `ENCARGADO` o `SUPERADMIN` autenticado, la respuesta incluye además `direct_cost` y los registros inactivos (con `include_inactive=true`). Los endpoints de escritura exigen rol `ENCARGADO` o `SUPERADMIN`. Eliminar un recurso del catálogo es una baja lógica (`is_active = false`); los registros ya referenciados por cotizaciones o eventos nunca se borran físicamente.

#### `GET /catalog/packages`
* **Descripción:** Lista los paquetes disponibles para venta con sus temáticas compatibles (RF-03).
* **Seguridad:** Público. Con rol `ENCARGADO` o `SUPERADMIN` se incluye `direct_cost` y `inventory_items`.
* **Query Params:** `service_category=SHOW`, `include_inactive=false`.
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "e4b2d5a1-...",
      "name": "Hora Loca Medium",
      "service_category": "SHOW",
      "description": "Show completo con 4 bailarines, animador, DJ y cotillón.",
      "base_price": 750.00,
      "duration_minutes": 60,
      "is_active": true,
      "compatible_themes": [
        {"id": "t1-...", "name": "Selva"},
        {"id": "t2-...", "name": "Neón Glow"}
      ]
    }
  ]
  ```

#### `GET /catalog/packages/{id}`
* **Descripción:** Detalle de un paquete, incluidos los ítems de inventario que consume (`package_inventory_items`).
* **Seguridad:** Público. Los campos `direct_cost` e `inventory_items` solo se devuelven a `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:**
  ```json
  {
    "id": "e4b2d5a1-...",
    "name": "Toldos + Decoración Premium",
    "service_category": "TENTS",
    "description": "Toldo 3x3 m con decoración temática.",
    "base_price": 1200.00,
    "direct_cost": 650.00,
    "duration_minutes": 480,
    "is_active": true,
    "compatible_themes": [{"id": "t1-...", "name": "Selva"}],
    "inventory_items": [
      {"inventory_item_id": "inv-01...", "name": "Toldo 3x3 m", "quantity": 1},
      {"inventory_item_id": "inv-07...", "name": "Kit decoración Selva", "quantity": 1}
    ]
  }
  ```

#### `POST /catalog/packages`
* **Descripción:** Crea un paquete. Opcionalmente asocia temáticas compatibles (`package_themes`) e ítems de inventario consumidos (`package_inventory_items`) en la misma operación.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "name": "Toldos + Decoración Premium",
    "service_category": "TENTS",
    "description": "Toldo 3x3 m con decoración temática.",
    "base_price": 1200.00,
    "direct_cost": 650.00,
    "duration_minutes": 480,
    "theme_ids": ["t1-..."],
    "inventory_items": [
      {"inventory_item_id": "inv-01...", "quantity": 1},
      {"inventory_item_id": "inv-07...", "quantity": 1}
    ]
  }
  ```
* **Response `201 Created`:** el paquete creado (formato de `GET /catalog/packages/{id}`).
* **Errores:** `422` (`validation-error`, por ejemplo `base_price <= 0`, o ítems de inventario en un paquete que no es `DECORATION` ni `TENTS`).

#### `PATCH /catalog/packages/{id}`
* **Descripción:** Actualiza los campos propios del paquete (nombre, categoría, descripción, precios, duración, `is_active`). Las temáticas y los ítems de inventario se gestionan con los endpoints `PUT` siguientes. Los cambios de precio no afectan cotizaciones ya emitidas (los precios se congelan al cotizar).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"base_price": 1300.00, "is_active": true}` (campos opcionales).
* **Response `200 OK`:** el paquete actualizado.

#### `DELETE /catalog/packages/{id}`
* **Descripción:** Baja lógica del paquete (`is_active = false`); deja de ofrecerse en el catálogo y en el bot.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `204 No Content`.**

#### `PUT /catalog/packages/{id}/inventory-items`
* **Descripción:** Reemplaza el conjunto completo de ítems de inventario que consume el paquete (`package_inventory_items`). Una lista vacía indica que el paquete no consume inventario (`SHOW`, `DJ`). Los eventos ya creados conservan sus reservas.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "items": [
      {"inventory_item_id": "inv-01...", "quantity": 1},
      {"inventory_item_id": "inv-07...", "quantity": 2}
    ]
  }
  ```
* **Response `200 OK`:** `{"package_id": "e4b2d5a1-...", "items": [{"inventory_item_id": "inv-01...", "name": "Toldo 3x3 m", "quantity": 1}, {"inventory_item_id": "inv-07...", "name": "Kit decoración Selva", "quantity": 2}]}`
* **Errores:** `422` (ítem repetido, cantidad `<= 0` o ítem inexistente).

#### `PUT /catalog/packages/{id}/themes`
* **Descripción:** Reemplaza el conjunto de temáticas compatibles del paquete (`package_themes`).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"theme_ids": ["t1-...", "t2-..."]}`
* **Response `200 OK`:** `{"package_id": "e4b2d5a1-...", "compatible_themes": [{"id": "t1-...", "name": "Selva"}, {"id": "t2-...", "name": "Neón Glow"}]}`

#### `GET /catalog/themes`
* **Descripción:** Lista las temáticas habilitadas para cotización.
* **Seguridad:** Público.
* **Response `200 OK`:** `[{"id": "t1-...", "name": "Selva", "description": "Ambientación de selva tropical.", "is_active": true}]`

#### `POST /catalog/themes`
* **Descripción:** Crea una temática.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"name": "Retro 80s", "description": "Colores neón y música de los años 80."}`
* **Response `201 Created`:** la temática creada. **Errores:** `409` (`duplicate-resource`, el nombre es único).

#### `PATCH /catalog/themes/{id}`
* **Descripción:** Actualiza nombre, descripción o `is_active` de una temática.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"description": "Nueva descripción", "is_active": true}` (campos opcionales).
* **Response `200 OK`:** la temática actualizada.

#### `DELETE /catalog/themes/{id}`
* **Descripción:** Baja lógica de la temática (`is_active = false`).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `204 No Content`.**

#### `GET /catalog/extras`
* **Descripción:** Lista los extras y muñecos disponibles con su precio de venta (RF-04).
* **Seguridad:** Público. Con rol `ENCARGADO` o `SUPERADMIN` se incluye `direct_cost`.
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "x1-...",
      "name": "Muñeco Gorila Gigante",
      "sale_price": 250.00,
      "description": "Personaje estrella gigante para ingreso sorpresa.",
      "is_active": true
    }
  ]
  ```

#### `POST /catalog/extras`
* **Descripción:** Crea un extra.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"name": "Robot LED", "description": "Robot luminoso para pista.", "sale_price": 180.00, "direct_cost": 90.00}`
* **Response `201 Created`:** el extra creado.

#### `PATCH /catalog/extras/{id}`
* **Descripción:** Actualiza un extra (precio, costo, descripción o `is_active`).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"sale_price": 200.00}` (campos opcionales).
* **Response `200 OK`:** el extra actualizado.

#### `DELETE /catalog/extras/{id}`
* **Descripción:** Baja lógica del extra (`is_active = false`).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `204 No Content`.**

#### `GET /catalog/inventory-items`
* **Descripción:** Lista el inventario físico (toldos y decoración) con su stock total (RF-09).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "inv-01...",
      "name": "Toldo 3x3 m",
      "service_category": "TENTS",
      "total_stock": 6,
      "description": "Estructura metálica con cubierta blanca.",
      "is_active": true
    }
  ]
  ```

#### `POST /catalog/inventory-items`
* **Descripción:** Crea un ítem de inventario. `service_category` solo admite `DECORATION` o `TENTS`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"name": "Toldo 4x4 m", "service_category": "TENTS", "total_stock": 3, "description": "Toldo grande."}`
* **Response `201 Created`:** el ítem creado. **Errores:** `409` (`duplicate-resource`, el nombre es único), `422` (`validation-error`).

#### `PATCH /catalog/inventory-items/{id}`
* **Descripción:** Actualiza nombre, descripción, stock total o `is_active`. Reducir `total_stock` por debajo de las unidades ya reservadas en fechas futuras responde `409` (`inventory-in-use`).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"total_stock": 8}` (campos opcionales).
* **Response `200 OK`:** el ítem actualizado.

#### `DELETE /catalog/inventory-items/{id}`
* **Descripción:** Baja lógica del ítem (`is_active = false`). Responde `409` (`inventory-in-use`) si algún paquete activo lo consume o tiene reservas `ACTIVE` futuras.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `204 No Content`.**

---

### 2.5 Módulo: Elencos (`/crews`)

#### `GET /crews`
* **Descripción:** Lista los elencos y proveedores freelance asignables a eventos (RF-09, RF-10).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `service_category=SHOW`, `is_active=true`.
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "crew-01...",
      "leader_name": "Luis Torres",
      "phone": "+51955666777",
      "service_category": "SHOW",
      "user_id": "u-op-01...",
      "is_active": true
    }
  ]
  ```

#### `POST /crews`
* **Descripción:** Registra un elenco. `user_id` (opcional, único) vincula al elenco con un usuario `OPERADOR`; ese vínculo define los eventos propios que el operador puede ver y operar.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"leader_name": "Luis Torres", "phone": "+51955666777", "service_category": "SHOW", "user_id": "u-op-01..."}`
* **Response `201 Created`:** el elenco creado. **Errores:** `422` si `user_id` no corresponde a un usuario con rol `OPERADOR`; `409` si el usuario ya está vinculado a otro elenco.

#### `PATCH /crews/{id}`
* **Descripción:** Actualiza datos, vínculo con el usuario o `is_active` de un elenco.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"phone": "+51955666888", "is_active": false}` (campos opcionales).
* **Response `200 OK`:** el elenco actualizado.

---

### 2.6 Módulo: Clientes (`/clients`)

Los clientes se crean o actualizan automáticamente al generar una cotización (ver `POST /quotes`); no existe un endpoint de creación independiente.

#### `GET /clients`
* **Descripción:** Lista paginada de clientes, con búsqueda por teléfono o nombre.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `q=carlos` o `phone=+51999888777`, `page`, `page_size`.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "id": "c1-...",
        "phone": "+51999888777",
        "full_name": "Carlos Rodríguez",
        "dni": "45678912",
        "ruc": null,
        "created_at": "2026-09-20T14:10:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```

#### `GET /clients/{id}`
* **Descripción:** Detalle del cliente con el resumen de sus cotizaciones.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:**
  ```json
  {
    "id": "c1-...",
    "phone": "+51999888777",
    "full_name": "Carlos Rodríguez",
    "dni": "45678912",
    "ruc": null,
    "created_at": "2026-09-20T14:10:00Z",
    "quotes": [
      {"quote_id": "q9c8a1b2-...", "event_date": "2026-10-15", "total_amount": 1080.50, "status": "CONVERTED"}
    ]
  }
  ```

---

### 2.7 Módulo: Cotizador y Motor de Movilidad (`/quotes`)

#### `POST /quotes`
* **Descripción:** Calcula y crea una cotización aplicando las reglas financieras (RF-05, RF-07) tras verificar la disponibilidad (RF-09). El cliente se indica con `client_id` (cliente existente) **o** con el objeto `client`, que crea o actualiza el registro de `clients` usando el teléfono de WhatsApp (E.164) como clave natural. El nombre y el teléfono del cliente no se almacenan en la cotización: viven únicamente en `clients`. Se debe enviar exactamente uno de los dos (`client_id` o `client`); de lo contrario, `422`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`. El bot de WhatsApp la ejecuta como caso de uso interno al completar la captura de datos del chat (RF-02), sin pasar por HTTP.
* **Request Body:**
  ```json
  {
    "client": {
      "phone": "+51999888777",
      "full_name": "Carlos Rodríguez",
      "dni": null,
      "ruc": null
    },
    "event_date": "2026-10-15",
    "event_time": "21:30:00",
    "location_address": "Av. Benavides 2150",
    "location_district": "Miraflores",
    "package_id": "e4b2d5a1-...",
    "theme_id": "t1-...",
    "extras": [{"extra_id": "x1-...", "quantity": 1}],
    "client_provides_mobility": false
  }
  ```
  Alternativa con cliente existente: reemplazar `client` por `"client_id": "c1-..."`.
* **Response `201 Created`:**
  ```json
  {
    "quote_id": "q9c8a1b2-...",
    "client_id": "c1-...",
    "source": "WHATSAPP",
    "availability": "AVAILABLE",
    "services_subtotal": 1000.00,
    "calculated_distance_km": 18.40,
    "calculated_transit_minutes": 55,
    "final_mobility_amount": 80.50,
    "total_amount": 1080.50,
    "advance_amount": 100.00,
    "pending_balance": 980.50,
    "breakdown": {
      "services_balance_due": 900.00,
      "mobility_due": 80.50
    },
    "status": "SENT",
    "sent_at": "2026-09-23T20:15:00Z",
    "expires_at": "2026-09-24T20:15:00Z"
  }
  ```
  `source` es `WHATSAPP` cuando la cotización nace del bot y también cuando la crea un encargado con este endpoint; `MANUAL` solo lo asigna `POST /contracts/manual`.
* **Errores:** `409` (`availability-conflict` o `simultaneous-threshold-exceeded` si no hay disponibilidad; el detalle ofrece fechas u horarios alternativos), `422` (`validation-error`: fecha pasada, paquete o temática incompatible, teléfono no E.164).

#### `GET /quotes`
* **Descripción:** Lista paginada de cotizaciones con filtros.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `status=SENT`, `client_id=<uuid>`, `from_date=2026-10-01`, `to_date=2026-10-31`, `page`, `page_size`.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "quote_id": "q9c8a1b2-...",
        "client": {"id": "c1-...", "full_name": "Carlos Rodríguez", "phone": "+51999888777"},
        "event_date": "2026-10-15",
        "package_name": "Hora Loca Medium",
        "total_amount": 1080.50,
        "status": "SENT",
        "expires_at": "2026-09-24T20:15:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```

#### `GET /quotes/{id}`
* **Descripción:** Detalle de la cotización con su desglose financiero, extras congelados, estado y pagos asociados.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:**
  ```json
  {
    "quote_id": "q9c8a1b2-...",
    "client": {"id": "c1-...", "full_name": "Carlos Rodríguez", "phone": "+51999888777"},
    "source": "WHATSAPP",
    "event_date": "2026-10-15",
    "event_time": "21:30:00",
    "location_address": "Av. Benavides 2150",
    "location_district": "Miraflores",
    "package": {"id": "e4b2d5a1-...", "name": "Hora Loca Medium", "base_price": 750.00},
    "theme": {"id": "t1-...", "name": "Selva"},
    "extras": [{"extra_id": "x1-...", "name": "Muñeco Gorila Gigante", "quantity": 1, "unit_price": 250.00, "subtotal": 250.00}],
    "services_subtotal": 1000.00,
    "final_mobility_amount": 80.50,
    "mobility_overridden": false,
    "total_amount": 1080.50,
    "advance_amount": 100.00,
    "pending_balance": 980.50,
    "status": "PAYMENT_STARTED",
    "sent_at": "2026-09-23T20:15:00Z",
    "expires_at": "2026-09-24T20:15:00Z",
    "payments": [{"payment_id": "pay-11a2...", "concept": "ADVANCE", "validation_status": "PENDING_VERIFICATION"}],
    "event_id": null
  }
  ```

#### `POST /quotes/{id}/pay-advance`
* **Descripción:** Acción «Pagar adelanto» (RN-09, PC-11). Si han transcurrido más de `AVAILABILITY_RECHECK_MINUTES` (por defecto 60) desde `sent_at`, se revalida la disponibilidad antes de revelar los datos de pago (sin bloqueo distribuido: es una consulta informativa; la verificación autoritativa ocurre al validar el pago). Si hay disponibilidad, la cotización pasa de `SENT` a `PAYMENT_STARTED` (si ya estaba en `PAYMENT_STARTED`, la operación es idempotente) y se devuelven las instrucciones de pago (Yape, Plin y cuenta bancaria). Si no la hay, **no se revelan datos de pago**: responde `409` con alternativas y la opción de derivar a un encargado. La cotización conserva su estado y su vencimiento.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`. El bot de WhatsApp la ejecuta como caso de uso interno cuando el cliente pulsa el botón «Pagar adelanto».
* **Request Body:** vacío.
* **Response `200 OK`:**
  ```json
  {
    "quote_id": "q9c8a1b2-...",
    "status": "PAYMENT_STARTED",
    "availability": "AVAILABLE",
    "rechecked": true,
    "advance_amount": 100.00,
    "payment_deadline": "2026-09-24T20:15:00Z",
    "payment_instructions": {
      "yape": {"phone": "+51900111222", "holder": "EventPro SAC"},
      "plin": {"phone": "+51900111222", "holder": "EventPro SAC"},
      "bank_transfer": {"bank": "BCP", "account": "194-1234567-0-12", "cci": "00219400123456701234", "holder": "EventPro SAC"}
    }
  }
  ```
* **Response `409 Conflict`** (sin cupo):
  ```json
  {
    "type": "https://errors.eventpro.pe/availability-conflict",
    "title": "Sin disponibilidad para la fecha y el horario",
    "status": 409,
    "detail": "El cupo ya no está disponible. Puede elegir otra fecha u horario o solicitar la ayuda de un encargado.",
    "instance": "/api/v1/quotes/q9c8a1b2-.../pay-advance",
    "alternatives": [{"event_date": "2026-10-15", "event_time": "18:00:00"}],
    "handoff_available": true
  }
  ```
  Cuando el motivo es la superación de `SIMULTANEOUS_SHOWS_THRESHOLD`, el tipo de error es `simultaneous-threshold-exceeded`.
* **Otros errores:** `410` (`quote-expired`, la cotización está `EXPIRED`), `409` (`invalid-quote-state`, la cotización está `CONVERTED` o `CANCELLED`).

#### `POST /quotes/{id}/cancel`
* **Descripción:** Cancela la cotización (`SENT` o `PAYMENT_STARTED` → `CANCELLED`). Si existe un pago `PENDING_VERIFICATION` o `REQUIRES_MANUAL_APPROVAL`, la cancelación se rechaza (`409`, `invalid-quote-state`): primero debe resolverse el pago.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`. El bot la ejecuta cuando el cliente cancela desde el chat.
* **Request Body:** `{"reason": "El cliente cambió la fecha."}` (opcional).
* **Response `200 OK`:** `{"quote_id": "q9c8a1b2-...", "status": "CANCELLED"}`

#### Vencimiento de cotizaciones (tarea programada)
No existe un endpoint público para el vencimiento. Una **tarea programada** (ejecutada cada minuto) busca las cotizaciones en `SENT` o `PAYMENT_STARTED` con `expires_at` vencido y sin pagos en verificación (ninguno en `PENDING_VERIFICATION` ni `REQUIRES_MANUAL_APPROVAL`) y las pasa a `EXPIRED` (RN-09). El plazo es `ADVANCE_DEADLINE_HOURS` (por defecto 24) desde `sent_at`. Un comprobante que llega después del vencimiento se acepta igualmente y el pago ingresa en `REQUIRES_MANUAL_APPROVAL` (RF-11).

---

### 2.8 Módulo: Webhook de Chatwoot (`/webhooks/chatwoot`)

El canal de WhatsApp se opera a través de Chatwoot, un gateway de mensajería autoalojado e invisible para los usuarios (ADR-10). Meta entrega sus webhooks a Chatwoot, no a EventPro, y Chatwoot reenvía cada evento a este endpoint como webhook de cuenta.

#### `POST /webhooks/chatwoot`
* **Descripción:** Receptor de los eventos de cuenta de Chatwoot: mensajes entrantes del cliente (texto, clics de botones e imágenes de comprobantes de pago), mensajes nuevos, cambios de estado de la conversación y actualizaciones de entrega.
* **Seguridad:** Sin JWT; autenticado por firma. Cada petición debe incluir las cabeceras `X-Chatwoot-Timestamp` (marca de tiempo Unix, en segundos) y `X-Chatwoot-Signature: sha256=<hex>`, donde `<hex>` es el HMAC-SHA256 de la cadena `"{X-Chatwoot-Timestamp}.{cuerpo crudo}"` (bytes exactos, sin reserializar) calculado con el secreto `CHATWOOT_WEBHOOK_SECRET`. El backend recalcula el HMAC y lo compara en tiempo constante antes de procesar nada, y rechaza las peticiones cuya marca de tiempo tenga más de 5 minutos de antigüedad. Si alguna cabecera falta, la firma no coincide o la marca de tiempo está vencida, responde `401` (`invalid-webhook-signature`), no encola el evento y registra el intento.
* **Exposición:** solo interna. El proxy inverso bloquea esta ruta hacia internet y únicamente es accesible desde la red interna de Docker (`http://api:8000/api/v1/webhooks/chatwoot`).
* **Request Body:** Payload estándar del webhook de cuenta de Chatwoot. Ejemplo recortado para `message_created`:
  ```json
  {
    "event": "message_created",
    "id": 4821,
    "message_type": "incoming",
    "content": "Hola, quiero cotizar una hora loca para el 15 de octubre",
    "conversation": {"id": 57, "status": "pending"},
    "sender": {"phone_number": "+51999888777"},
    "attachments": []
  }
  ```
* **Response `200 OK`:** `{"status": "EVENT_RECEIVED"}` (procesamiento asíncrono en menos de 1.5 s; el evento se encola en arq).
* **Idempotencia:** el evento se procesa una sola vez por identificador de mensaje o evento de Chatwoot (deduplicación en Redis, TTL de 7 días); un reenvío responde `200` sin reprocesar.
* **Enrutamiento del worker:** un mensaje entrante (`message_created`, `incoming`) en una conversación `pending` lo procesa el bot; cualquier otro evento (mensajes nuevos, cambios de estado, actualizaciones de entrega) se publica a la web de EventPro por el stream SSE (`GET /conversations/stream`).
* **Errores:** `401` (`invalid-webhook-signature`).

---

### 2.9 Módulo: Gestión de Pagos y Comprobantes (`/payments`)

#### `POST /payments/advance`
* **Descripción:** Recibe la captura del comprobante de adelanto del 10% asociado a una cotización (RF-11). Es la ruta HTTP equivalente a la recepción de la imagen por WhatsApp.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN` (registro en nombre del cliente). El bot de WhatsApp ejecuta el mismo caso de uso al recibir la imagen del cliente.
* **Content-Type:** `multipart/form-data`
* **Form Data:**
  * `quote_id`: UUID de la cotización.
  * `payment_method`: `YAPE`, `PLIN` o `BANK_TRANSFER`.
  * `amount`: `100.00` (debe ser exactamente `advance_amount` de la cotización).
  * `transaction_reference`: número de operación (opcional).
  * `receipt_file`: Archivo binario (JPEG, PNG, WebP o PDF; máximo 5 MB).
* **Descripción adicional:** Al recibir el comprobante se ejecuta la revalidación temprana de disponibilidad (RN-09). Si no hay cupo o se supera el umbral de shows simultáneos, `validation_status` es `REQUIRES_MANUAL_APPROVAL` en lugar de `PENDING_VERIFICATION`. Lo mismo ocurre si la cotización ya está `EXPIRED`. Si la cotización estaba en `SENT`, pasa a `PAYMENT_STARTED`.
* **Response `201 Created`:**
  ```json
  {
    "payment_id": "pay-11a2...",
    "quote_id": "q9c8a1b2-...",
    "concept": "ADVANCE",
    "validation_status": "PENDING_VERIFICATION",
    "message": "Comprobante recibido con éxito. En cola de validación."
  }
  ```
  Cuando no hay cupo, `validation_status` es `REQUIRES_MANUAL_APPROVAL` y el mensaje indica que el encargado revisará el caso.
* **Errores:** `400` (`invalid-advance-amount`), `409` (`invalid-quote-state`, la cotización está `CONVERTED` o `CANCELLED`), `422` (`invalid-file`).

#### `GET /payments`
* **Descripción:** Lista paginada de pagos, incluida la cola de verificación del encargado y la cola de auditoría de cobros in situ.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `validation_status=PENDING_VERIFICATION`, `concept=BALANCE`, `audit_status=UNREVIEWED`, `quote_id=<uuid>`, `event_id=<uuid>`, `from_date`, `to_date`, `page`, `page_size`.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "payment_id": "pay-11a2...",
        "quote_id": "q9c8a1b2-...",
        "event_id": null,
        "concept": "ADVANCE",
        "payment_method": "YAPE",
        "amount": 100.00,
        "validation_status": "PENDING_VERIFICATION",
        "audit_status": null,
        "created_at": "2026-09-23T20:40:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```

#### `GET /payments/{id}`
* **Descripción:** Detalle del pago, con quién lo verificó, registró o auditó, motivo de rechazo y observaciones de auditoría.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:**
  ```json
  {
    "payment_id": "pay-22b3...",
    "quote_id": "q9c8a1b2-...",
    "event_id": "evt-77a8...",
    "concept": "BALANCE",
    "payment_method": "YAPE",
    "amount": 980.50,
    "transaction_reference": "00912345",
    "validation_status": "VERIFIED",
    "rejection_reason": null,
    "verified_by_user_id": null,
    "registered_by_user_id": "u-op-01...",
    "audit_status": "UNREVIEWED",
    "audited_by_user_id": null,
    "audited_at": null,
    "audit_notes": null,
    "created_at": "2026-10-15T21:33:00Z"
  }
  ```

#### `GET /payments/{id}/evidence`
* **Descripción:** Descarga la evidencia del pago (comprobante o fotografía del cobro). El archivo se sirve a través de la API con control de acceso y cabecera `Content-Disposition`; nunca se expone una ruta del sistema de archivos.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:** Archivo binario (`image/jpeg`, `image/png`, `image/webp` o `application/pdf`).

#### `PATCH /payments/{id}/verify`
* **Descripción:** El encargado aprueba o rechaza el comprobante de un adelanto (RF-12, PC-06). Al aprobar se ejecuta la revalidación autoritativa y atómica de disponibilidad con bloqueo Redis (RN-09); si el cupo está lleno o se supera el umbral, el pago pasa a `REQUIRES_MANUAL_APPROVAL` y se resuelve con `POST /overrides/payments/{id}/approve-simultaneous`. El rechazo por comprobante inválido o ilegible se permite desde `PENDING_VERIFICATION` y también desde `REQUIRES_MANUAL_APPROVAL`; el reintento del cliente crea un nuevo pago.
* **Valores de `status` aceptados:** `VERIFIED` o `REJECTED`. Solo aplica a pagos `ADVANCE` en `PENDING_VERIFICATION` (ambos valores) o `REQUIRES_MANUAL_APPROVAL` (solo `REJECTED`; la aprobación de un pago en este estado es la acción `APPROVE` del endpoint de overrides).
* **Seguridad:** Requiere rol `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "status": "VERIFIED",
    "rejection_reason": null
  }
  ```
  Para rechazar: `{"status": "REJECTED", "rejection_reason": "La captura está cortada y no se ve el monto."}` (`rejection_reason` obligatorio).
* **Response `200 OK`:**
  ```json
  {
    "payment_id": "pay-11a2...",
    "validation_status": "VERIFIED",
    "event_created_id": "evt-77a8...",
    "contract_status": "ISSUED"
  }
  ```
  Si la revalidación autoritativa detecta cupo lleno, `validation_status` es `REQUIRES_MANUAL_APPROVAL`, `event_created_id` y `contract_status` son `null` y se incluye `"reason": "CONFLICT"` o `"reason": "THRESHOLD_EXCEEDED"`. Con `REJECTED`, `validation_status` es `REJECTED` y se notifica al cliente por WhatsApp con el motivo y la instrucción de reintento.
* **Errores:** `409` (`invalid-payment-state`, el pago ya no está en un estado que admita la acción), `422` (`validation-error`).

#### `PATCH /payments/{id}/audit`
* **Descripción:** Auditoría posterior del encargado de un cobro in situ (`BALANCE` o `EXTENSION`), RN-07, PC-12. Marca el cobro como `REVIEWED` o `FLAGGED`; no revierte el pago ni bloquea el evento. Transiciones permitidas: `UNREVIEWED` → `REVIEWED`, `UNREVIEWED` → `FLAGGED`, `FLAGGED` → `REVIEWED`. Registra la acción `AUDIT_PAYMENT` en `audit_logs`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "audit_status": "FLAGGED",
    "audit_notes": "El monto de la captura (S/. 950.00) no coincide con el monto registrado."
  }
  ```
  `audit_notes` es obligatorio cuando `audit_status` es `FLAGGED`.
* **Response `200 OK`:** `{"payment_id": "pay-22b3...", "audit_status": "FLAGGED", "audited_by_user_id": "b1eebc99-...", "audited_at": "2026-10-16T09:12:00Z"}`
* **Errores:** `409` (`invalid-payment-state`, el pago es un `ADVANCE` o la transición no está permitida), `422` (`validation-error`, falta `audit_notes`).

#### `PATCH /payments/{id}/refund`
* **Descripción:** Confirma que la devolución del adelanto fue efectuada (`REFUND_PENDING` → `REFUNDED`, RF-12). El encargado indica cómo y cuándo se devolvió; la constancia se guarda como observación del pago.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "refund_method": "YAPE",
    "transaction_reference": "00987654",
    "notes": "Devuelto al mismo número de Yape del cliente."
  }
  ```
* **Response `200 OK`:** `{"payment_id": "pay-11a2...", "validation_status": "REFUNDED"}`
* **Errores:** `409` (`invalid-payment-state`, el pago no está en `REFUND_PENDING`).

---

### 2.10 Módulo: Contratos y Firma Electrónica (`/contracts`)

El contrato se crea automáticamente al validar el adelanto (RF-13): se compila el PDF, el contrato pasa a `ISSUED` y se envía por WhatsApp un enlace de firma de un solo uso (`/contracts/sign/{token}`). El `{token}` es un valor criptográfico aleatorio con expiración (`signature_token_expires_at`); solo se almacena su hash. Un token solo da acceso al contrato al que pertenece. La firma electrónica es un flujo propio (ADR-07): visualización, OTP por WhatsApp, firma manuscrita y sello PAdES.

#### `GET /contracts`
* **Descripción:** Lista paginada de contratos.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `status=ISSUED`, `event_id=<uuid>`, `is_manual_mode=true`, `page`, `page_size`.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "contract_id": "ctr-5d10...",
        "contract_number": "CTR-2026-0042",
        "event_id": "evt-77a8...",
        "status": "ISSUED",
        "is_manual_mode": false,
        "signed_at": null,
        "created_at": "2026-09-23T20:50:00Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```

#### `GET /contracts/{id}`
* **Descripción:** Detalle del contrato: estado, vigencia del enlace de firma y metadatos de la firma (si está firmado).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`. Los usuarios `OPERADOR` no tienen acceso a contratos.
* **Response `200 OK`:**
  ```json
  {
    "contract_id": "ctr-5d10...",
    "contract_number": "CTR-2026-0042",
    "event_id": "evt-77a8...",
    "status": "SIGNED",
    "is_manual_mode": false,
    "custom_clauses": null,
    "signature_token_expires_at": "2026-09-30T20:50:00Z",
    "signed_at": "2026-09-23T21:05:00Z",
    "signer_ip": "190.234.10.20",
    "sealed_pdf_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "is_timestamped": false,
    "created_at": "2026-09-23T20:50:00Z"
  }
  ```

#### `GET /contracts/{id}/pdf`
* **Descripción:** Descarga el archivo PDF compilado del contrato (RF-13). Si el contrato está `SIGNED`, devuelve el PDF sellado con PAdES.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:** Archivo binario `application/pdf`. **Errores:** `404` si el contrato está en `DRAFT` (aún no hay PDF).

#### `POST /contracts/manual`
* **Descripción:** Creación de un contrato en modo manual de contingencia, sin pasar por el bot de WhatsApp (RF-23, PC-05). En una sola operación atómica: crea o actualiza el cliente por teléfono, crea una cotización con `source = MANUAL` con los montos acordados, registra el adelanto como pago `ADVANCE` ya `VERIFIED` por el encargado (verificación autoritativa de disponibilidad con bloqueo Redis incluida), convierte la cotización a `CONVERTED`, crea el evento (`AWAITING_SIGNATURE`) con sus reservas de inventario y genera el contrato con `is_manual_mode = true`. Registra la acción `MANUAL_CONTRACT` en `audit_logs`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Content-Type:** `multipart/form-data` con dos partes:
  * `payload` (`application/json`): descrito a continuación.
  * `advance_evidence_file`: evidencia del adelanto recibido (imagen o PDF, máximo 5 MB).
* **Request `payload`:**
  ```json
  {
    "client": {
      "phone": "+51999888777",
      "full_name": "Carlos Rodríguez",
      "dni": "45678912",
      "ruc": null
    },
    "event_date": "2026-10-15",
    "event_time": "21:30:00",
    "location_address": "Av. Benavides 2150",
    "location_district": "Miraflores",
    "package_id": "e4b2d5a1-...",
    "theme_id": "t1-...",
    "extras": [{"extra_id": "x1-...", "quantity": 1}],
    "client_provides_mobility": false,
    "agreed_services_subtotal": 950.00,
    "agreed_services_reason": "Descuento acordado por cliente frecuente.",
    "agreed_mobility_amount": 70.00,
    "mobility_override_reason": "Tarifa pactada con el cliente.",
    "advance": {
      "payment_method": "CASH",
      "amount": 95.00,
      "transaction_reference": null
    },
    "client_observations": "MÚSICA PROHIBIDA: Reggaetón. Salida sorpresa del gorila al min 45.",
    "custom_clauses": "El cliente proveerá un punto de energía eléctrica a menos de 10 metros.",
    "issue_contract": true
  }
  ```
  * `agreed_services_subtotal` y `agreed_mobility_amount` son opcionales: si se omiten, se calculan con el catálogo y el motor de movilidad. Si se envían, `agreed_services_reason` y `mobility_override_reason` son obligatorios respectivamente, y el adelanto se calcula como el 10% del subtotal de servicios acordado.
  * `advance.amount` debe ser exactamente el 10% del subtotal de servicios (`400` `invalid-advance-amount` en caso contrario). `advance.payment_method` admite `YAPE`, `PLIN`, `BANK_TRANSFER` o `CASH`.
  * `issue_contract`: si es `true` (por defecto), el contrato se compila y pasa a `ISSUED` con envío del enlace de firma por WhatsApp; si es `false`, queda en `DRAFT`.
* **Response `201 Created`:**
  ```json
  {
    "quote_id": "q-manual-01...",
    "client_id": "c1-...",
    "payment_id": "pay-33c4...",
    "event_id": "evt-88b9...",
    "event_code": "EVT-2026-0043",
    "contract_id": "ctr-6e21...",
    "contract_number": "CTR-2026-0043",
    "contract_status": "ISSUED",
    "quote_status": "CONVERTED",
    "services_subtotal": 950.00,
    "total_amount": 1020.00,
    "advance_amount": 95.00,
    "pending_balance": 925.00
  }
  ```
* **Errores:** `400` (`invalid-advance-amount`), `409` (`availability-conflict` o `simultaneous-threshold-exceeded`: la operación se revierte por completo y no se persiste nada; para estos casos, el encargado puede crear la cotización con `POST /quotes` y seguir el flujo normal de aprobación de sobrecupo), `422` (`validation-error`, `invalid-file`).

#### `POST /contracts/{id}/resend-link`
* **Descripción:** Genera un nuevo enlace de firma (invalida el anterior y reinicia el OTP) y lo reenvía por WhatsApp al cliente. Solo aplica a contratos `ISSUED`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `200 OK`:** `{"contract_id": "ctr-5d10...", "status": "ISSUED", "signature_token_expires_at": "2026-10-07T20:50:00Z"}`
* **Errores:** `409` (`invalid-contract-state`).

#### `POST /contracts/{id}/void`
* **Descripción:** Anula el contrato (`DRAFT`, `ISSUED` o `SIGNED` → `VOIDED`). Tras la anulación se puede emitir un nuevo contrato para el mismo evento. La anulación de un contrato `SIGNED` solo procede por cancelación del evento antes de su ejecución.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"reason": "El cliente solicitó cambios en las cláusulas."}`
* **Response `200 OK`:** `{"contract_id": "ctr-5d10...", "status": "VOIDED"}`
* **Errores:** `409` (`invalid-contract-state`).

#### `GET /contracts/sign/{token}`
* **Descripción:** Vista del contrato para el cliente a través del enlace de firma (RF-15, paso 2). Devuelve el resumen del contrato y del evento y la URL del PDF. No requiere sesión: el token es la credencial y solo da acceso a ese contrato.
* **Seguridad:** Cliente con token de un solo uso. Límite por IP (ver Matriz RBAC, sección 4).
* **Response `200 OK`:**
  ```json
  {
    "contract_number": "CTR-2026-0042",
    "status": "ISSUED",
    "client_full_name": "Carlos Rodríguez",
    "event": {
      "event_date": "2026-10-15",
      "start_time": "21:30",
      "end_time": "22:30",
      "address": "Av. Benavides 2150",
      "district": "Miraflores",
      "package_name": "Hora Loca Medium",
      "theme_name": "Selva",
      "client_observations": "MÚSICA PROHIBIDA: Reggaetón. Salida sorpresa del gorila al min 45."
    },
    "total_amount": 1080.50,
    "advance_paid": 100.00,
    "pending_balance": 980.50,
    "pdf_url": "/api/v1/contracts/sign/{token}/pdf",
    "token_expires_at": "2026-09-30T20:50:00Z"
  }
  ```
* **Errores:** `404` (`invalid-signature-token`, el token no existe), `410` (`signature-token-expired`, el enlace venció), `409` (`invalid-contract-state`, el contrato ya está `SIGNED` o `VOIDED`).

#### `GET /contracts/sign/{token}/pdf`
* **Descripción:** Descarga el PDF del contrato para su revisión por el cliente.
* **Seguridad:** Cliente con token de un solo uso.
* **Response `200 OK`:** Archivo binario `application/pdf`. Errores: los mismos que `GET /contracts/sign/{token}`.

#### `POST /contracts/sign/{token}/otp`
* **Descripción:** Solicita el envío por WhatsApp de un código OTP de 6 dígitos al teléfono del cliente (RF-15, paso 3). El código se almacena con hash (`otp_hash`), vence en 10 minutos y se encola en `outbox_messages`. Cada solicitud nueva reemplaza el OTP vigente y reinicia `otp_attempts`.
* **Seguridad:** Cliente con token. Límite: 3 solicitudes por contrato cada 10 minutos y 10 por IP por hora (`429`, `rate-limit-exceeded`).
* **Request Body:** vacío.
* **Response `200 OK`:** `{"otp_sent": true, "expires_in": 600, "resend_available_in": 60, "phone_hint": "+51 *** *** 777"}`
* **Errores:** `410` (`signature-token-expired`), `409` (`invalid-contract-state`), `429` (`rate-limit-exceeded`).

#### `POST /contracts/sign/{token}/otp/verify`
* **Descripción:** Verifica el código OTP ingresado por el cliente. Si es correcto, devuelve una prueba de OTP (`otp_proof`) de corta duración (15 minutos), ligada al contrato, que debe presentarse al firmar. Tras el máximo de intentos fallidos (5), el OTP se invalida y debe solicitarse uno nuevo.
* **Seguridad:** Cliente con token.
* **Request Body:** `{"otp_code": "482913"}`
* **Response `200 OK`:** `{"otp_verified": true, "otp_proof": "eyJhbGciOiJIUzI1NiIsIn...", "expires_in": 900}`
* **Errores:** `422` (`invalid-otp`, con `attempts_remaining` en el detalle), `410` (`otp-expired`), `429` (`otp-attempts-exceeded`).

#### `POST /contracts/sign/{token}`
* **Descripción:** El cliente estampa su firma manuscrita electrónica en el contrato (RF-15, pasos 4 a 6). El backend valida token y prueba de OTP, estampa la imagen de la firma, sella el PDF con **PAdES** (pyHanko + PKCS#12, marca de tiempo RFC 3161 opcional), calcula el SHA-256 del PDF sellado, registra IP y agente de usuario, cambia el contrato a `SIGNED` y el evento a `SCHEDULED`, registra `CONTRACT_SIGNED` en `audit_logs` y envía una copia al WhatsApp del cliente.
* **Seguridad:** Cliente con token de un solo uso; el token queda consumido al firmar.
* **Request Body:**
  ```json
  {
    "otp_proof": "eyJhbGciOiJIUzI1NiIsIn...",
    "signature_base64": "data:image/png;base64,iVBORw0KGgoAAA...",
    "signer_full_name": "Carlos Rodríguez",
    "accept_terms": true
  }
  ```
  `signature_base64` debe ser una imagen PNG de hasta 1 MB; `accept_terms` debe ser `true`.
* **Response `200 OK`:**
  ```json
  {
    "contract_number": "CTR-2026-0042",
    "status": "SIGNED",
    "signed_at": "2026-09-23T21:05:00Z",
    "sealed_pdf_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "message": "Contrato firmado satisfactoriamente. Se ha enviado una copia a su WhatsApp."
  }
  ```
* **Errores:** `401` (`invalid-otp`, prueba de OTP ausente, inválida o vencida), `404` (`invalid-signature-token`), `410` (`signature-token-expired`), `409` (`invalid-contract-state`, ya firmado o anulado), `422` (`validation-error`, imagen inválida o términos no aceptados).

---

### 2.11 Módulo: Cronograma y Operación en Evento (`/events`)

Los usuarios `OPERADOR` solo ven y operan los eventos que tienen asignado su elenco (`crews.user_id` = su usuario, mediante `crew_assignments`); acceder a otro evento responde `404`. Los roles `ENCARGADO` y `SUPERADMIN` acceden a todos los eventos.

#### `GET /events/schedule`
* **Descripción:** Consulta el calendario operativo con filtros avanzados (RF-16, RF-17).
* **Seguridad:** Autenticado. `OPERADOR` ve únicamente sus eventos asignados; el filtro `crew_id` se ignora para él.
* **Query Params (todos opcionales y combinables):** `from_date=2026-10-01`, `to_date=2026-10-31` (rango de fechas), `district=Miraflores`, `theme_id=t1-...`, `status=SCHEDULED`, `crew_id=crew-01...`.
* **Response `200 OK`:**
  ```json
  [
    {
      "event_id": "evt-77a8...",
      "event_code": "EVT-2026-0042",
      "event_date": "2026-10-15",
      "start_time": "21:30",
      "end_time": "22:30",
      "end_date": "2026-10-15",
      "district": "Miraflores",
      "client_name": "Carlos Rodríguez",
      "package_name": "Hora Loca Medium",
      "theme_name": "Selva",
      "crews": [{"crew_id": "crew-01...", "leader_name": "Luis Torres"}],
      "client_observations": "MÚSICA PROHIBIDA: Reggaetón. Salida sorpresa del gorila al min 45.",
      "status": "SCHEDULED",
      "pending_balance_to_collect": 980.50
    }
  ]
  ```
  `client_name` se obtiene de `clients` a través de la cotización del evento.

> **Implementación provisional — US-16, Slice 1:** la ruta publicada es
> `GET /api/v1/events/schedule`. Se implementan `from_date`, `to_date` y `status`
> (opcionales, combinables, límites inclusivos). `district`, `theme_id` y `crew_id`
> responden `422` hasta la entrega de esos filtros. Un rango invertido también
> responde `422`; sin coincidencias se devuelve `[]`. El orden es fecha, hora e ID.
>
> Los eventos se consultan en PostgreSQL. Mientras E1/E3 integran sus tablas, los
> puertos de enriquecimiento se conectan a fakes reemplazables en DI: sin datos
> asociados devuelven `Cliente pendiente de integración`, `Paquete pendiente de
> integración`, `Temática pendiente de integración` y `crews: []`. No se insertan
> datos simulados en la base. `ENCARGADO` y `SUPERADMIN` pueden consultar todos los
> eventos; `OPERADOR` solo los IDs asignados por el fake y, sin asignaciones,
> recibe `403` indicando que requiere asignación activa. Esta excepción temporal
> se sustituirá por la lectura de `crews.user_id` y `crew_assignments`.
> `client_observations` conserva el texto literal y puede ser `null`; las horas
> se serializan como `HH:MM` y el saldo como número JSON en PEN, calculado con
> decimales: `max(final_total_amount - advance_paid - pre_show_balance_paid - extra_hours_amount, 0)`.

> **US-18:** `end_time` y `end_date` describen el fin operativo con los minutos
> adicionales, incluso al cruzar medianoche o extenderse varios días. El horario
> contratado en PostgreSQL se conserva. La comprobación de disponibilidad usa
> asignaciones y reservas reales; el enriquecimiento y autorización del operador
> siguen usando el puerto Fake hasta la integración E3.

#### `GET /events/{id}`
* **Descripción:** Detalle operativo del evento: datos de la locación, observaciones, extras, elencos asignados, desglose económico y pagos registrados.
* **Seguridad:** Autenticado. `OPERADOR` solo para eventos propios.
* **Response `200 OK`:**
  ```json
  {
    "event_id": "evt-77a8...",
    "event_code": "EVT-2026-0042",
    "event_date": "2026-10-15",
    "start_time": "21:30",
    "end_time": "22:30",
    "address": "Av. Benavides 2150",
    "district": "Miraflores",
    "client": {"full_name": "Carlos Rodríguez", "phone": "+51999888777"},
    "package_name": "Hora Loca Medium",
    "theme_name": "Selva",
    "extras": [{"name": "Muñeco Gorila Gigante", "quantity": 1}],
    "client_observations": "MÚSICA PROHIBIDA: Reggaetón. Salida sorpresa del gorila al min 45.",
    "status": "SCHEDULED",
    "final_total_amount": 1080.50,
    "advance_paid": 100.00,
    "pending_balance_to_collect": 980.50,
    "crew_assignments": [
      {"assignment_id": "ca-01...", "crew_id": "crew-01...", "leader_name": "Luis Torres", "transit_interval_minutes": 75, "transit_interval_overridden": false}
    ],
    "payments": [{"payment_id": "pay-11a2...", "concept": "ADVANCE", "amount": 100.00, "validation_status": "VERIFIED"}]
  }
  ```
  El teléfono del cliente y los pagos se devuelven solo a `ENCARGADO` y `SUPERADMIN`.

#### `POST /events/{id}/crew-assignments`
* **Descripción:** Asigna un elenco al evento (RF-09, RF-10, RN-05). El sistema calcula el intervalo de tránsito respecto del evento anterior del mismo elenco en el día (tránsito de Google Maps más 30 minutos de desarme y descanso). Si el intervalo disponible es menor que el mínimo, responde `409` (`transit-interval-insufficient`) con el mínimo requerido; el encargado puede reintentar indicando `transit_interval_override_minutes` y `reason` (RF-22, PC-02), lo que registra `OVERRIDE_TRANSIT_INTERVAL` en `audit_logs`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "crew_id": "crew-01...",
    "transit_interval_override_minutes": null,
    "reason": null
  }
  ```
  Con override: `{"crew_id": "crew-01...", "transit_interval_override_minutes": 45, "reason": "Ruta alterna sin tráfico confirmada por el elenco."}` (`reason` obligatorio si hay override).
* **Response `201 Created`:**
  ```json
  {
    "assignment_id": "ca-01...",
    "event_id": "evt-77a8...",
    "crew_id": "crew-01...",
    "transit_interval_minutes": 75,
    "transit_interval_overridden": false
  }
  ```
* **Errores:** `409` (`transit-interval-insufficient`; `duplicate-resource` si el elenco ya está asignado al evento), `422` (`validation-error`, por ejemplo categoría del elenco incompatible con el paquete).

#### `DELETE /events/{id}/crew-assignments/{assignment_id}`
* **Descripción:** Quita la asignación de un elenco al evento (solo antes de `IN_PROGRESS`).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Response `204 No Content`.** **Errores:** `409` (`invalid-event-state`).

#### `POST /events/{id}/start` — US-17 parcial
* **Descripción:** Inicia desde `SCHEDULED` o `AWAITING_BALANCE`, previa
  verificación del 100% del saldo de servicios y movilidad mediante un puerto.
  Actualiza juntos `status = IN_PROGRESS`, `pre_show_balance_paid` (total
  verificado, sin volver a sumarlo) y `actual_start_time` (hora UTC del servidor).
  Un inicio repetido responde `409` y conserva el primer instante registrado.
* **Seguridad:** `ENCARGADO` y `SUPERADMIN` para cualquier evento existente;
  `OPERADOR` solo con asignación. En esta ruta provisional un operador fuera
  de alcance recibe `403` antes de buscar el evento, incluso si el ID no existe.
* **Request Body:** ausente o `{}`. Los campos adicionales se rechazan con `422`;
  no se aceptan importes, indicadores de pago ni una hora enviada por el cliente.
* **Response `200 OK`:**
  ```json
  {
    "event_id": "77a88888-8888-4888-8888-888888888888",
    "status": "IN_PROGRESS",
    "actual_start_time": "2026-10-15T21:35:00Z"
  }
  ```
* **Errores:** `400` (`balance-pending`), `401` (`invalid-credentials`),
  `403` (`forbidden`, sin asignación), `404` (`not-found`, evento inexistente
  dentro del alcance autorizado), `409` (`invalid-event-state`),
  `422` (`validation-error`, UUID/cuerpo inválidos).
* **Dependencias provisionales:** se reutiliza el Fake de asignaciones de US-16.
  `FakePreShowPaymentVerificationAdapter` recibe un mapa `event_id -> Money`
  con el total `BALANCE` verificado; sin entrada devuelve cero. La DI por defecto
  usa un mapa vacío: no autoriza un evento con saldo pendiente, aunque
  `events.pre_show_balance_paid` aparente estar pagado. Para una demostración o
  test se inyecta un Fake configurado mediante `get_pre_show_payment_verification_port`
  y `get_crew_schedule_read_port`; no hay un endpoint para simular pagos.
  E5 sustituirá el Fake por su lectura real de pagos `BALANCE` en `VERIFIED`.
* **Límite de la entrega:** no crea pagos ni recibe evidencia; el flujo completo
  de US-17 requiere los endpoints siguientes. `show_started_at` corresponde a
  `/check-in-and-collect`, mientras esta ruta nueva expone `actual_start_time`.

#### `POST /events/{id}/arrive`
* **Descripción:** El personal registra su llegada al lugar del evento (`SCHEDULED` → `AWAITING_BALANCE`). A partir de este estado se habilita el cobro del saldo.
* **Seguridad:** Roles `OPERADOR` (solo eventos propios), `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** vacío.
* **Response `200 OK`:** `{"event_id": "evt-77a8...", "status": "AWAITING_BALANCE"}`
* **Errores:** `409` (`invalid-event-state`; por ejemplo, el evento sigue en `AWAITING_SIGNATURE` porque el contrato no está firmado).

#### `POST /events/{id}/check-in-and-collect`
* **Descripción:** Registra el cobro in situ del saldo pendiente total (servicios + movilidad) antes de iniciar el show (RF-18, RN-06, PC-07). Crea un pago de concepto `BALANCE` directamente en `VERIFIED`, con `audit_status = UNREVIEWED` y la evidencia obligatoria, y pasa el evento de `AWAITING_BALANCE` a `IN_PROGRESS`. El show nunca queda bloqueado esperando a un encargado; la auditoría es posterior (`PATCH /payments/{id}/audit`).
* **Seguridad:** Roles `OPERADOR` (solo eventos propios), `ENCARGADO` o `SUPERADMIN`.
* **Content-Type:** `multipart/form-data`
* **Form Data:**
  * `amount`: `980.50` (debe completar exactamente el 100% del saldo pendiente).
  * `payment_method`: `YAPE`, `PLIN`, `BANK_TRANSFER` o `CASH`.
  * `evidence_file`: **obligatorio**. Fotografía de la pantalla de Yape/Plin o del efectivo recibido (JPEG, PNG o WebP; máximo 5 MB; tipo validado por contenido). En el móvil se captura con la cámara (`<input capture>`).
  * `transaction_reference`: número de operación (opcional).
  * `notes`: texto libre (opcional), por ejemplo `Cobrado completo al llegar al local.`
* **Response `201 Created`:**
  ```json
  {
    "event_id": "evt-77a8...",
    "status": "IN_PROGRESS",
    "show_started_at": "2026-10-15T21:35:00Z",
    "payment": {
      "payment_id": "pay-22b3...",
      "concept": "BALANCE",
      "amount": 980.50,
      "validation_status": "VERIFIED",
      "audit_status": "UNREVIEWED"
    }
  }
  ```
* **Errores:** `400` (`balance-amount-mismatch`, el monto no completa el saldo pendiente), `409` (`invalid-event-state`, el evento no está en `AWAITING_BALANCE`), `422` (`invalid-file`, `validation-error`, falta la evidencia).

#### `POST /events/{id}/extensions`
* **Descripción:** Registra extensiones de tiempo de show en caliente (RF-19, RN-07, PC-08). Crea un pago de concepto `EXTENSION` directamente en `VERIFIED` (`audit_status = UNREVIEWED`) con evidencia obligatoria, la extensión en `event_extensions` vinculada a ese pago, y pasa el evento a `EXTENDED`.
* **Seguridad:** Roles `OPERADOR` (solo eventos propios), `ENCARGADO` o `SUPERADMIN`.
* **Content-Type:** `multipart/form-data`
* **Form Data:**
  * `extra_minutes`: `30`; entero positivo, hasta el límite de `INTEGER`.
  * `agreed_rate`: `100.00`; **importe total pactado por esos minutos**, positivo en PEN y con hasta dos decimales. No se prorratea por hora.
  * `payment_method`: `YAPE`, `PLIN`, `BANK_TRANSFER` o `CASH`.
  * `evidence_file`: **obligatorio** (imagen JPEG, PNG o WebP; máximo 5 MB).
  * `transaction_reference`: opcional.
* **Response `201 Created`:**
  ```json
  {
    "event_id": "evt-77a8...",
    "status": "EXTENDED",
    "extension_id": "ext-01...",
    "payment": {
      "payment_id": "pay-44d5...",
      "concept": "EXTENSION",
      "amount": 100.00,
      "validation_status": "VERIFIED",
      "audit_status": "UNREVIEWED"
    }
  }
  ```
* **Errores:** `401` (autenticación), `403` (`forbidden`, rol no permitido), `404` (`not-found`, inexistente o fuera del alcance del operador), `409` (`invalid-event-state`, el evento no está `IN_PROGRESS` ni `EXTENDED`; `extension-payment-mismatch`, vínculos inconsistentes; `extension-resource-conflict`, conflicto de elenco, stock, traslado desconocido/insuficiente o sobrecupo que requiere aprobación manual), `422` (`invalid-file`, `validation-error`).
* **Comportamiento US-18:** permite extensiones sucesivas; acumula minutos y cargos conservando el horario original. La fotografía se valida por contenido, exclusivamente JPEG, PNG o WebP, hasta 5 MiB. La referencia opcional admite entre 1 y 60 caracteres y no puede contener solo espacios. Los campos adicionales se rechazan. El servidor obtiene la fecha UTC y el usuario registrador del JWT. Los importes acumulados deben caber en `NUMERIC(10,2)` y el fin calculado debe ser representable.
* **Transacción y reintentos:** cada registro exitoso crea una extensión y un pago distinto. No hay clave de idempotencia en esta entrega. La evidencia se almacena antes de bloquear. Pago, detalle, reservas activas prolongadas y evento se confirman conjuntamente bajo candado transaccional de disponibilidad y bloqueo de fila. Datos independientes de persistencia inválidos responden `422` antes de evaluar el estado. Un conflicto posterior compensa el archivo; si hubo intento de commit, solo se elimina al confirmar que el pago no quedó persistido. Un commit incierto conserva la evidencia y se registra. El formulario rechaza campos adicionales y sus errores no exponen entradas ni URLs internas.

#### `POST /events/{id}/settle`
* **Descripción:** Cierra definitivamente el evento marcándolo como `SETTLED` (desde `IN_PROGRESS` o `EXTENDED`) y consolida los totales cobrados.
* **Seguridad:** Roles `OPERADOR` (solo eventos propios), `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** vacío o `{}`; se rechazan campos adicionales.
* **Response `200 OK`:** `{"event_id": "evt-77a8...", "status": "SETTLED"}`
* **Errores:** `401` (autenticación), `403` (`forbidden`, rol no permitido), `404` (`not-found`, inexistente o fuera del alcance del operador), `400` (`balance-pending`, cobros insuficientes), `409` (`invalid-event-state`, incluido un segundo cierre; `extension-payment-mismatch`, extensiones y pagos inconsistentes), `422` (`validation-error`, cuerpo inválido).
* **Cobertura US-18:** usa `advance_paid` y `pre_show_balance_paid` guardados para los cobros base y contrasta las extensiones con pagos reales `EXTENSION` `VERIFIED`. Los minutos, importes y vínculos deben coincidir; ningún pago de extensión puede carecer de detalle asociado. El crédito `legacy_extra_hours_amount`, fijado por la migración para históricos sin pagos de extensión, se incluye en la cobertura y en la igualdad de importes; no puede editarse públicamente. La auditoría `UNREVIEWED` o `FLAGGED` no impide el cierre. Liquidar no suma cargos nuevamente y bloquea nuevas extensiones. La consulta y transición se serializan con los registros de extensiones mediante el mismo bloqueo de fila.

#### `POST /events/{id}/cancel`
* **Descripción:** Cancela el evento desde cualquier estado previo a `IN_PROGRESS` (`AWAITING_SIGNATURE`, `SCHEDULED` o `AWAITING_BALANCE`). Libera sus reservas de inventario (`RELEASED`), anula el contrato vigente (`VOIDED`) y deja de contar para el umbral de simultaneidad. El destino del adelanto se resuelve fuera de este endpoint.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"reason": "El cliente canceló la celebración."}`
* **Response `200 OK`:** `{"event_id": "evt-77a8...", "status": "CANCELLED", "contract_status": "VOIDED"}`
* **Errores:** `409` (`invalid-event-state`).

---

### 2.12 Módulo: Procesos de Control y Overrides (`/overrides`)

#### `PATCH /overrides/quotes/{id}/mobility`
* **Descripción:** Sobrescritura manual del costo de movilidad por el encargado (RF-21, PC-04). Solo antes de emitir el contrato (la cotización no puede estar `CONVERTED`). El adelanto del 10% no se altera. Registra `OVERRIDE_MOBILITY` en `audit_logs` y marca `mobility_overridden = true`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "manual_mobility_amount": 95.00,
    "reason": "Zona de alto tráfico con peajes no computados."
  }
  ```
* **Response `200 OK`:** Retorna la cotización recalculada con el nuevo total y saldo.
* **Errores:** `409` (`invalid-quote-state`), `422` (`validation-error`, monto negativo o motivo vacío).

#### `PATCH /overrides/crew-assignments/{id}/transit-interval`
* **Descripción:** Ajuste manual del intervalo de tránsito de una asignación existente (RF-22, PC-02). Actualiza la validación de solapamiento para ese elenco, marca `transit_interval_overridden = true` y registra `OVERRIDE_TRANSIT_INTERVAL` en `audit_logs` con la justificación.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "transit_interval_minutes": 45,
    "reason": "Ruta alterna sin tráfico confirmada por el elenco."
  }
  ```
* **Response `200 OK`:** `{"assignment_id": "ca-01...", "transit_interval_minutes": 45, "transit_interval_overridden": true}`
* **Errores:** `409` (`invalid-event-state`, el evento ya está `IN_PROGRESS` o finalizado), `422` (`validation-error`).

#### `POST /overrides/payments/{id}/approve-simultaneous`
* **Descripción:** Resolución manual de un pago en estado `REQUIRES_MANUAL_APPROVAL`, ya sea por superar el umbral `SIMULTANEOUS_SHOWS_THRESHOLD` (3 por defecto) o por cupo lleno al validar (RF-20, RN-04, RN-09, PC-03). La aprobación es un estado del pago, no del evento. Registra `APPROVE_OVERBOOKED_PAYMENT` o `REJECT_OVERBOOKED_PAYMENT` en `audit_logs`. El rechazo por comprobante inválido se hace con `PATCH /payments/{id}/verify`, no con este endpoint.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** `{"action": "APPROVE", "notes": "Se contrató elenco adicional freelance."}` o `{"action": "REJECT", "notes": "Sin elenco de respaldo."}`
* **Response `200 OK`:** con `APPROVE`: `{"payment_id": "...", "validation_status": "VERIFIED", "event_created_id": "evt-77a8..."}`; con `REJECT`: `{"payment_id": "...", "validation_status": "REFUND_PENDING"}`
* **Errores:** `409` (`invalid-payment-state`, el pago no está en `REQUIRES_MANUAL_APPROVAL`).

---

### 2.13 Módulo: Analítica Financiera y BI (`/reports`)

#### `GET /reports/dashboard`
* **Descripción:** Indicadores clave (KPIs) del dashboard ejecutivo (RF-25): utilidad neta mensual comparada con meses anteriores, volumen de eventos por paquete y temática, ranking de extras y distribución por distrito. Solo considera eventos `SETTLED`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `year=2026`, `month=10`, `compare_months=3` (cantidad de meses previos a comparar; por defecto `3`).
* **Response `200 OK`:**
  ```json
  {
    "period": "2026-10",
    "net_profit_by_month": [
      {"period": "2026-08", "net_profit": 9400.00},
      {"period": "2026-09", "net_profit": 10250.00},
      {"period": "2026-10", "net_profit": 11000.00}
    ],
    "events_by_package": [{"package_id": "e4b2d5a1-...", "name": "Hora Loca Medium", "events": 11}],
    "events_by_theme": [{"theme_id": "t1-...", "name": "Selva", "events": 9}],
    "top_extras": [{"extra_id": "x1-...", "name": "Muñeco Gorila Gigante", "times_hired": 14}],
    "events_by_district": [{"district": "Miraflores", "events": 7}]
  }
  ```

#### `GET /reports/financial/pnl`
* **Descripción:** Reporte semanal o mensual de Ingresos vs. Costos Fijos y Utilidad Neta (RF-24).
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `period_type=MONTHLY`, `year=2026`, `month=10` (para `WEEKLY` se usa `week=42` en lugar de `month`).
* **Response `200 OK`:**
  ```json
  {
    "period": "2026-10",
    "total_events_settled": 24,
    "gross_revenue": 28450.00,
    "direct_costs": {
      "fixed_packages_cost": 12200.00,
      "fixed_extras_cost": 3100.00,
      "mobility_operational_cost": 2150.00,
      "total_costs": 17450.00
    },
    "net_profit": 11000.00,
    "profit_margin_percentage": 38.66
  }
  ```

---

### 2.14 Módulo: Conversaciones (`/conversations`)

Bandeja de conversaciones de WhatsApp dentro de EventPro (ADR-10). Chatwoot es la fuente de verdad de mensajes, medios, estados de entrega y `status`; EventPro solo almacena el vínculo de negocio en `conversation_links`. Todos los endpoints exigen rol `ENCARGADO` o `SUPERADMIN`, y el `{id}` de la ruta es el `chatwoot_conversation_id` (entero).

**Modo y estado de la conversación:** el `status` de Chatwoot se proyecta al `mode` de EventPro: `pending` → `BOT` (responde el bot), `open` → `HUMAN` (un encargado atiende) y `resolved` → `BOT` (si el cliente vuelve a escribir, la conversación se reabre en `pending`). Una conversación `open` sin `assigned_user_id` es una derivación pendiente de toma.

**Ventana de servicio de 24 h:** `service_window_open` es `true` mientras no hayan pasado 24 horas desde el último mensaje entrante del cliente; `service_window_expires_at` es esa marca más 24 h (`null` si el cliente nunca escribió). Con la ventana cerrada solo se pueden enviar plantillas aprobadas.

**Disponibilidad:** `GET /conversations`, `GET /conversations/{id}/messages`, `GET /conversations/{id}/attachments/{attachment_id}`, `takeover` y `release` consultan o modifican Chatwoot de forma síncrona; si no responde, devuelven `503` (`messaging-gateway-unavailable`). El envío de mensajes pasa por `outbox_messages` y tolera la caída de Chatwoot.

#### `GET /conversations`
* **Descripción:** Bandeja de conversaciones, ordenada por `last_message_at` descendente. Por defecto excluye las conversaciones `resolved`.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `mode=HUMAN` (`BOT` | `HUMAN`), `assigned=me` (`me` = asignadas al usuario autenticado | `unassigned` = sin asignar), `include_resolved=false`, `page`, `page_size` (paginado).
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "chatwoot_conversation_id": 57,
        "client": {"id": "c3d1a7f2-...", "name": "Carlos Ramírez", "phone": "+51999888777"},
        "quote_id": "q9c8a1b2-...",
        "status": "open",
        "mode": "HUMAN",
        "assigned_user_id": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
        "handoff_reason": "CLIENT_REQUEST",
        "handed_off_at": "2026-10-03T16:40:12Z",
        "last_message_preview": "Quisiera cambiar la hora del show",
        "last_message_at": "2026-10-03T16:52:30Z",
        "service_window_open": true,
        "service_window_expires_at": "2026-10-04T16:52:30Z"
      }
    ],
    "page": 1,
    "page_size": 20,
    "total": 1
  }
  ```
  `status` es `pending`, `open` o `resolved`; `handoff_reason` es `CLIENT_REQUEST`, `BOT_NOT_UNDERSTOOD`, `MANUAL_TAKEOVER`, `BOT_ERROR` o `null`; `quote_id`, `assigned_user_id` y `handed_off_at` son `null` cuando no aplican.
* **Errores:** `503` (`messaging-gateway-unavailable`).

#### `GET /conversations/{id}/messages`
* **Descripción:** Mensajes de la conversación, consultados a Chatwoot (EventPro no los almacena). Se devuelven del más reciente al más antiguo.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Query Params:** `before=<message_id>` (devuelve los mensajes anteriores a ese identificador; sin valor, los más recientes), `limit=30` (máximo `100`). Se usa paginación por cursor en lugar de `page` porque la lista se consulta a Chatwoot, donde el historial crece con mensajes nuevos.
* **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "id": 4830,
        "direction": "OUTGOING",
        "author_type": "AGENT",
        "content": "Claro, con gusto lo reprogramamos.",
        "attachments": [],
        "delivery_status": "READ",
        "failure_reason": null,
        "created_at": "2026-10-03T16:52:30Z"
      },
      {
        "id": 4821,
        "direction": "INCOMING",
        "author_type": "CLIENT",
        "content": "Adjunto mi comprobante",
        "attachments": [
          {"id": 311, "file_type": "image", "content_type": "image/jpeg", "url": "/api/v1/conversations/57/attachments/311"}
        ],
        "delivery_status": null,
        "failure_reason": null,
        "created_at": "2026-10-03T16:40:02Z"
      }
    ],
    "has_more": true
  }
  ```
  `attachments[].url` es la ruta de EventPro del medio (`GET /conversations/{id}/attachments/{attachment_id}`); las URL de Chatwoot nunca se exponen al navegador. `direction` es `INCOMING` u `OUTGOING`; `author_type` es `CLIENT`, `BOT` o `AGENT`; `delivery_status` es `SENT`, `DELIVERED`, `READ` o `FAILED` (`null` en mensajes entrantes). Con `FAILED`, `failure_reason` es un texto legible en español (por ejemplo, «La ventana de 24 horas está cerrada» o «El número no está entre los destinatarios de prueba»).
* **Errores:** `404` (`not-found`, la conversación no existe), `503` (`messaging-gateway-unavailable`).

#### `GET /conversations/{id}/attachments/{attachment_id}`
* **Descripción:** Proxy de los medios de la conversación (imágenes, comprobantes, documentos). El backend obtiene el archivo de Chatwoot por la red interna y lo transmite al cliente con el `Content-Type` original y `Content-Disposition: inline; filename=...`. Valida que el adjunto pertenezca a la conversación indicada. Las URL de Chatwoot nunca se exponen al navegador.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`. La lectura no exige que la conversación esté tomada.
* **Response `200 OK`:** el contenido binario del archivo.
* **Errores:** `404` (`not-found`, el adjunto no existe o no pertenece a la conversación), `503` (`messaging-gateway-unavailable`).
* **Nota:** este endpoint sirve los medios del chat. Si el bot ya almacenó un comprobante de pago en el almacenamiento de EventPro (RF-11), la fuente para la revisión del pago sigue siendo `GET /payments/{id}/evidence`.

#### `POST /conversations/{id}/messages`
* **Descripción:** Envía un mensaje al cliente como el agente de servicio de Chatwoot. El autor real (el usuario autenticado) se registra en `audit_logs` con la acción `SEND_CONVERSATION_MESSAGE`. El envío pasa por `outbox_messages` con reintentos (ver especificación del gateway, sección 4): el mensaje se acepta y se entrega de forma asíncrona. Si agota los reintentos queda `FAILED` y el encargado puede reenviarlo con una nueva petición.
* **Reglas:**
  * La conversación debe estar tomada por el usuario autenticado: `status = open` y `assigned_user_id` igual al usuario. No se puede escribir en una conversación en modo `BOT`; hay que ejecutar antes `POST /conversations/{id}/takeover`.
  * Si la ventana de 24 h está cerrada, solo se admite una plantilla aprobada (objeto `template`); con texto libre responde `422` (`service-window-closed`). Con la ventana abierta, el objeto `template` también es válido.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Content-Type:** `application/json` (texto o plantilla) o `multipart/form-data` (adjunto).
* **Request Body (texto):**
  ```json
  {
    "content": "Claro, con gusto lo reprogramamos."
  }
  ```
* **Request Body (plantilla, para ventana cerrada):**
  ```json
  {
    "template": {
      "name": "contract_reminder",
      "language": "es",
      "params": {"1": "Carlos", "2": "15 de octubre"}
    }
  }
  ```
* **Request multipart:** campos `attachment` (archivo, obligatorio) y `content` (texto opcional que acompaña al adjunto). Aplican las reglas de subida de archivos de la sección 1: máximo 5 MB, validación por contenido y tipos JPEG, PNG, WebP o PDF.
* **Response `202 Accepted`:**
  ```json
  {
    "outbox_id": "ob-91c2...",
    "chatwoot_conversation_id": 57,
    "delivery_status": "QUEUED"
  }
  ```
  `QUEUED` es el estado previo a la aceptación por Chatwoot; una vez enviado, el mensaje aparece en `GET /conversations/{id}/messages` y el avance de su estado (`SENT`, `DELIVERED`, `READ` o `FAILED`) llega por el evento `message.updated` del stream.
* **Errores:** `404` (`not-found`), `409` (`conversation-not-taken`, la conversación no está `open` o no está asignada; `conversation-taken-by-other`, está asignada a otro usuario), `422` (`service-window-closed`; `invalid-file`; `validation-error`, por ejemplo cuerpo sin `content`, `attachment` ni `template`).

#### `POST /conversations/{id}/takeover`
* **Descripción:** Un encargado toma la conversación: pasa a `open` en Chatwoot, se asigna al usuario autenticado (`assigned_user_id`) y el bot deja de responder. Si la conversación estaba en modo `BOT` registra `handoff_reason = MANUAL_TAKEOVER` y `handed_off_at`; si ya había sido derivada (`open` sin asignar), conserva el motivo original. Es idempotente: si ya está tomada por el mismo usuario, responde `200` sin cambios.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`. Una conversación tomada por otro usuario responde `409` (`conversation-taken-by-other`) para un `ENCARGADO`; un `SUPERADMIN` puede reasignarla a sí mismo y la acción se registra en `audit_logs` como `OVERRIDE_CONVERSATION_ASSIGNMENT` con el usuario anterior.
* **Request Body:** vacío.
* **Response `200 OK`:** la conversación actualizada (mismo formato que un ítem de `GET /conversations`).
* **Errores:** `404` (`not-found`), `409` (`conversation-taken-by-other`), `503` (`messaging-gateway-unavailable`).

#### `POST /conversations/{id}/release`
* **Descripción:** Devuelve la conversación al bot: pasa a `pending` en Chatwoot y se limpia `assigned_user_id`; el bot retoma las respuestas. Solo la puede liberar el usuario asignado o un `SUPERADMIN`. Es idempotente: si ya está en `pending`, responde `200` sin cambios. `handoff_reason` y `handed_off_at` se conservan como historial de la última derivación.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`.
* **Request Body:** vacío.
* **Response `200 OK`:** la conversación actualizada (mismo formato que un ítem de `GET /conversations`).
* **Errores:** `404` (`not-found`), `409` (`conversation-taken-by-other`, un `ENCARGADO` intenta liberar una conversación asignada a otro), `503` (`messaging-gateway-unavailable`).

#### `GET /conversations/stream`
* **Descripción:** Eventos en tiempo real para la bandeja mediante Server-Sent Events (`Content-Type: text/event-stream`). El stream es de solo lectura; las acciones se ejecutan con los demás endpoints del módulo. Se publican los eventos que el worker recibe de Chatwoot (ver `POST /webhooks/chatwoot`), incluidos los cambios hechos desde EventPro.
* **Seguridad:** Roles `ENCARGADO` o `SUPERADMIN`, con el access token JWT enviado en el parámetro `access_token`. `EventSource` del navegador no permite cabeceras personalizadas, y el modelo de autenticación de la API no usa cookies, por lo que se admite el parámetro de consulta en lugar de `Authorization`. El mismo access token de 60 minutos se reutiliza, sin endpoint adicional; el proxy no debe registrar la cadena de consulta de esta ruta. El servidor cierra el stream cuando el token vence: el cliente renueva el token con `POST /auth/refresh` y se reconecta. Este es el único endpoint que acepta el token fuera de la cabecera.
* **Query Params:** `access_token=<jwt_access_token>`.
* **Tipos de evento** (`event:`; el campo `data:` es JSON):

  | Evento | Cuándo se emite | `data` |
  | :--- | :--- | :--- |
  | `conversation.updated` | Cambia el `status`, la asignación, el modo o la vista previa de una conversación. | Ítem de bandeja (formato de `GET /conversations`). |
  | `message.created` | Llega o se registra un mensaje nuevo. | `{"chatwoot_conversation_id": 57, "message": {...}}` (formato de mensaje de `GET /conversations/{id}/messages`). |
  | `message.updated` | Cambia el estado de entrega de un mensaje. | `{"chatwoot_conversation_id": 57, "message": {...}}`. |
  | `handoff.requested` | El bot deriva la conversación a un humano. | `{"chatwoot_conversation_id": 57, "handoff_reason": "CLIENT_REQUEST", "handoff_summary": "...", "client": {"id": "c3d1a7f2-...", "name": "Carlos Ramírez", "phone": "+51999888777"}, "handed_off_at": "2026-10-03T16:40:12Z"}`. |

  Ejemplo de trama:
  ```text
  event: handoff.requested
  data: {"chatwoot_conversation_id": 57, "handoff_reason": "CLIENT_REQUEST", "handoff_summary": "Cotización q9c8a1b2: Hora Loca Medium, 15/10", "client": {"id": "c3d1a7f2-...", "name": "Carlos Ramírez", "phone": "+51999888777"}, "handed_off_at": "2026-10-03T16:40:12Z"}
  ```
* **Reconexión:** no existe búfer de reenvío. El servidor envía un comentario de latido (`: keepalive`) cada 25 segundos; ante una desconexión, el cliente se reconecta automáticamente y, al reconectar, vuelve a solicitar `GET /conversations` para recuperar el estado.
* **Errores (antes de abrir el stream):** `401` (`invalid-credentials`, token ausente, inválido o vencido), `403` (`forbidden`).

---

## 3. Catálogo de Errores de Dominio (RFC 7807)

Todos los errores usan `Content-Type: application/problem+json` con los campos `type`, `title`, `status`, `detail` e `instance`. El `type` es una URL estable bajo `https://errors.eventpro.pe/`. Algunos errores añaden miembros de extensión (por ejemplo, `alternatives`, `attempts_remaining` o `minimum_interval_minutes`).

| `type` (sufijo) | Estado | Cuándo se produce |
| :--- | :---: | :--- |
| `validation-error` | `422` | El cuerpo, los parámetros o los campos del formulario no cumplen el esquema o las reglas de formato. Incluye la lista de campos inválidos. |
| `invalid-file` | `422` | El archivo supera 5 MB, o su contenido no corresponde a un tipo permitido para ese endpoint. |
| `invalid-credentials` | `401` | Correo o contraseña incorrectos, o refresh token inválido, revocado o vencido. |
| `user-inactive` | `403` | El usuario está desactivado (`is_active = false`). |
| `forbidden` | `403` | El rol no tiene permiso para el endpoint (ver Matriz RBAC). |
| `not-found` | `404` | El recurso no existe o está fuera del alcance del rol (por ejemplo, un evento no asignado a un `OPERADOR`). |
| `duplicate-resource` | `409` | Violación de unicidad (correo, teléfono, nombre de catálogo, elenco ya asignado). |
| `rate-limit-exceeded` | `429` | Se superó el límite de peticiones del endpoint (login, cotización, OTP, enlace de firma). |
| `invalid-webhook-signature` | `401` | Falta la cabecera `X-Chatwoot-Signature` o `X-Chatwoot-Timestamp` del webhook de Chatwoot, su HMAC no coincide o la marca de tiempo tiene más de 5 minutos de antigüedad. |
| `invalid-advance-amount` | `400` | El adelanto no es exactamente el 10% del subtotal de servicios. |
| `availability-conflict` | `409` | No hay cupo (artistas o inventario) para la fecha y el horario solicitados (RF-09). Puede incluir `alternatives` y `handoff_available`. |
| `simultaneous-threshold-exceeded` | `409` | Se superaría `SIMULTANEOUS_SHOWS_THRESHOLD` shows simultáneos (RN-04); requiere aprobación manual de un encargado. |
| `quote-expired` | `410` | La cotización está `EXPIRED` (venció `ADVANCE_DEADLINE_HOURS`). |
| `invalid-quote-state` | `409` | La acción no es válida en el estado actual de la cotización. |
| `invalid-payment-state` | `409` | La acción no es válida en el estado actual del pago (por ejemplo, verificar un pago ya `VERIFIED`, o auditar un `ADVANCE`). |
| `invalid-event-state` | `409` | La acción no es válida en el estado actual del evento. |
| `invalid-contract-state` | `409` | La acción no es válida en el estado actual del contrato (por ejemplo, firmar un contrato `VOIDED`). |
| `balance-amount-mismatch` | `400` | El monto cobrado in situ no completa el 100% del saldo pendiente. |
| `balance-pending` | `400` | El total BALANCE verificado no cubre el saldo de servicios y movilidad requerido para iniciar. |
| `transit-interval-insufficient` | `409` | El intervalo entre shows del mismo elenco es menor que el mínimo (RN-05). Incluye `minimum_interval_minutes`. |
| `inventory-in-use` | `409` | El ítem de inventario está consumido por paquetes activos o tiene reservas `ACTIVE` futuras. |
| `invalid-signature-token` | `404` | El token del enlace de firma no existe. |
| `signature-token-expired` | `410` | El enlace de firma venció (`signature_token_expires_at`). |
| `invalid-otp` | `422` / `401` | El código OTP es incorrecto (`422`, con `attempts_remaining`) o la prueba de OTP presentada al firmar falta, es inválida o venció (`401`). |
| `otp-expired` | `410` | El OTP venció; debe solicitarse uno nuevo. |
| `otp-attempts-exceeded` | `429` | Se superó el máximo de intentos fallidos (5); el OTP queda invalidado. |
| `service-window-closed` | `422` | La ventana de servicio de 24 h de WhatsApp está cerrada y el mensaje no es una plantilla aprobada. Incluye `service_window_expires_at`. |
| `conversation-not-taken` | `409` | La conversación no está tomada por un humano (`status` distinto de `open`) o está abierta sin asignar; hay que ejecutar `takeover` antes de enviar mensajes. |
| `conversation-taken-by-other` | `409` | La conversación está asignada a otro encargado. Incluye `assigned_user_id`. |
| `messaging-gateway-unavailable` | `503` | Chatwoot no responde y la operación requiere una consulta o un cambio de estado síncrono (bandeja, mensajes, `takeover`, `release`). |
