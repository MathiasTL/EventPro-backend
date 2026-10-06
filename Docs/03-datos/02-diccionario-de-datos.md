# 02. Diccionario de Datos Exhaustivo

---

## 1. Convenciones y Estándares de Base de Datos
* **Motor:** PostgreSQL 16+.
* **Claves Primarias (PK):** `UUIDv4` (`gen_random_uuid()`).
* **Valores Monetarios:** `NUMERIC(10,2)` estricto para prevenir pérdidas de precisión decimal.
* **Marcas Temporales:** `TIMESTAMPTZ` en UTC (`CURRENT_TIMESTAMP`).
* **Nomenclatura:** `snake_case` para nombres de tablas y columnas; nombres en plural para tablas (`quotes`, `events`, `contracts`).
* **Códigos de enumeración:** valores en inglés `UPPER_SNAKE_CASE`, implementados como `VARCHAR` con restricción `CHECK` (no como tipo `ENUM` nativo, para facilitar migraciones). Las etiquetas en español son solo de interfaz (ver [RN, sección 3.5](../01-requisitos/04-reglas-de-negocio-y-control.md#35-tabla-de-mapeo-código-etiqueta-de-interfaz-y-significado)).
* **Enumeración `service_category`:** única para elencos, paquetes e inventario. Valores: `SHOW` (Hora Loca y shows infantiles), `DJ`, `DECORATION` y `TENTS` (toldos). `inventory_items` solo admite `DECORATION` y `TENTS`.
* **Conceptos de pago (`payments.concept`):** `ADVANCE`, `BALANCE`, `EXTENSION`. UI: «Adelanto», «Saldo pre-show», «Extensión en vivo».
* **Sincronía con el ERD:** el [Diagrama Entidad-Relación](01-diagrama-entidad-relacion.md) y este diccionario describen exactamente las mismas tablas, columnas, tipos, nulabilidad y restricciones. Cualquier cambio debe aplicarse en ambos documentos.

---

## 2. Catálogo de Tablas

### 2.1 Tabla: `roles`
Almacena los perfiles de usuario y niveles de privilegio en el sistema.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del rol. |
| `code` | `VARCHAR(30)` | NO | - | UNIQUE | Código del rol (`SUPERADMIN`, `ENCARGADO`, `OPERADOR`). |
| `name` | `VARCHAR(60)` | NO | - | - | Nombre legible del rol. |
| `description` | `TEXT` | SÍ | `NULL` | - | Alcance de responsabilidades del rol. |

---

### 2.2 Tabla: `users`
Almacena los administradores (encargados) y personal operativo del negocio.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del usuario. |
| `role_id` | `UUID` | NO | - | FK (`roles.id`) | Rol asignado al usuario. |
| `full_name` | `VARCHAR(120)` | NO | - | - | Nombres y apellidos completos. |
| `email` | `VARCHAR(150)` | NO | - | UNIQUE | Correo electrónico de inicio de sesión. |
| `phone` | `VARCHAR(20)` | NO | - | UNIQUE | Teléfono móvil de contacto. |
| `hashed_password` | `VARCHAR(255)` | NO | - | - | Hash de contraseña con Argon2id/Bcrypt. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Indica si el usuario está habilitado en el sistema. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de creación. |

---

### 2.3 Tabla: `refresh_tokens`
Tokens de refresco rotativos para la sesión de los usuarios del panel (RNF-02.1). Solo se almacena el hash del token.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del token de refresco. |
| `user_id` | `UUID` | NO | - | FK (`users.id` ON DELETE CASCADE), INDEX | Usuario propietario de la sesión. |
| `token_hash` | `VARCHAR(64)` | NO | - | UNIQUE | Hash SHA-256 (hexadecimal) del token entregado al cliente; el token en claro nunca se persiste. |
| `expires_at` | `TIMESTAMPTZ` | NO | - | INDEX | Fecha y hora de expiración del token. |
| `is_revoked` | `BOOLEAN` | NO | `FALSE` | - | Indica si el token fue revocado por rotación o cierre de sesión. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de emisión. |

---

### 2.4 Tabla: `clients`
Clientes finales identificados por su número de WhatsApp. Un mismo cliente puede tener varias cotizaciones.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del cliente. |
| `phone` | `VARCHAR(20)` | NO | - | UNIQUE | Teléfono de WhatsApp en formato E.164 (`+51999888777`); clave natural del cliente. |
| `full_name` | `VARCHAR(120)` | NO | - | - | Nombre y apellido del cliente. |
| `dni` | `VARCHAR(8)` | SÍ | `NULL` | CHECK (`dni ~ '^[0-9]+$' AND length(dni) = 8`) | Documento Nacional de Identidad (opcional; para el contrato). |
| `ruc` | `VARCHAR(11)` | SÍ | `NULL` | CHECK (`ruc ~ '^[0-9]+$' AND length(ruc) = 11`) | RUC del cliente (opcional; para contratos a nombre de una empresa). |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora del primer contacto. |

---

### 2.5 Tabla: `packages`
Catálogo de paquetes base comercializados por la promotora.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del paquete. |
| `name` | `VARCHAR(100)` | NO | - | - | Nombre (ej. "Hora Loca Medium", "Show Infantil"). |
| `service_category` | `VARCHAR(30)` | NO | - | CHECK in (`SHOW`, `DJ`, `DECORATION`, `TENTS`) | Categoría del servicio; enumeración `service_category` compartida con `crews` e `inventory_items`. |
| `description` | `TEXT` | SÍ | `NULL` | - | Detalle de lo que incluye el paquete. |
| `base_price` | `NUMERIC(10,2)` | NO | - | CHECK (`base_price > 0`) | Tarifa de venta al cliente en Soles (PEN). |
| `direct_cost` | `NUMERIC(10,2)` | NO | - | CHECK (`direct_cost >= 0`) | Costo fijo pagado al elenco/proveedor freelance. |
| `duration_minutes` | `INTEGER` | NO | `60` | CHECK (`duration_minutes > 0`) | Duración estándar de la prestación en minutos; define `fin = inicio + duración` para la simultaneidad. La «Jornada» equivale a 480 minutos. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Indica si está activo en el catálogo. |

*Nota:* el inventario que consume un paquete se declara en `package_inventory_items` (sección 2.21); un paquete puede consumir varios ítems.

---

### 2.6 Tabla: `themes`
Temáticas decorativas y conceptuales aplicables a los paquetes.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único de la temática. |
| `name` | `VARCHAR(80)` | NO | - | UNIQUE | Nombre (ej. "Selva", "Neón Glow", "Retro 80s"). |
| `description` | `TEXT` | SÍ | `NULL` | - | Descripción visual de la temática. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Habilitado para cotización. |

---

### 2.7 Tabla: `package_themes`
Relación muchos a muchos entre paquetes y temáticas compatibles.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador de la relación. |
| `package_id` | `UUID` | NO | - | FK (`packages.id`) | Paquete vinculado. |
| `theme_id` | `UUID` | NO | - | FK (`themes.id`) | Temática compatible. |

*Restricciones de tabla:*
* `UNIQUE(package_id, theme_id)`

---

### 2.8 Tabla: `extras`
Elementos adicionales contratables (muñecos gigantes, bailarines extra, efectos).

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del extra. |
| `name` | `VARCHAR(100)` | NO | - | - | Nombre (ej. "Muñeco Gorila Gigante", "Robot LED"). |
| `description` | `TEXT` | SÍ | `NULL` | - | Descripción operativa del extra. |
| `sale_price` | `NUMERIC(10,2)` | NO | - | CHECK (`sale_price >= 0`) | Precio facturado al cliente. |
| `direct_cost` | `NUMERIC(10,2)` | NO | - | CHECK (`direct_cost >= 0`) | Tarifa fija pagada al artista/operador del muñeco. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Habilitado para cotizar. |

---

### 2.9 Tabla: `inventory_items`
Inventario físico con stock limitado (toldos, estructuras y piezas de decoración). Respalda la verificación de disponibilidad de RF-09.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del ítem de inventario. |
| `name` | `VARCHAR(100)` | NO | - | UNIQUE | Nombre del ítem (ej. "Toldo 3x3 m"). |
| `service_category` | `VARCHAR(30)` | NO | - | CHECK in (`DECORATION`, `TENTS`) | Categoría del servicio (subconjunto de `service_category`). |
| `total_stock` | `INTEGER` | NO | - | CHECK (`total_stock >= 0`) | Unidades físicas disponibles en total. |
| `description` | `TEXT` | SÍ | `NULL` | - | Descripción del ítem. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Habilitado para reservas. |

---

### 2.10 Tabla: `inventory_reservations`
Reservas de unidades de inventario por evento, ítem y ventana de tiempo. Al crear el evento (al validar el adelanto) se crea una fila por cada fila de `package_inventory_items` del paquete, copiando `quantity`; se liberan si el evento se cancela.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único de la reserva. |
| `event_id` | `UUID` | NO | - | FK (`events.id`), INDEX | Evento que consume el inventario. |
| `inventory_item_id` | `UUID` | NO | - | FK (`inventory_items.id`) | Ítem reservado. |
| `quantity` | `INTEGER` | NO | `1` | CHECK (`quantity > 0`) | Unidades reservadas. |
| `starts_at` | `TIMESTAMPTZ` | NO | - | - | Inicio de la ventana de reserva (incluye armado). |
| `ends_at` | `TIMESTAMPTZ` | NO | - | CHECK (`ends_at > starts_at`) | Fin de la ventana de reserva (incluye desarme). |
| `status` | `VARCHAR(20)` | NO | `'ACTIVE'` | CHECK in (`ACTIVE`, `RELEASED`) | `ACTIVE` ocupa stock; `RELEASED` lo devuelve (evento cancelado). |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de registro. |

*Restricciones de tabla:*
* `INDEX(inventory_item_id, starts_at, ends_at)` para calcular el stock disponible en una ventana. La verificación se ejecuta bajo el lock distribuido de ADR-06: `total_stock` menos la suma de `quantity` de reservas `ACTIVE` solapadas debe cubrir la cantidad solicitada.

---

### 2.11 Tabla: `quotes`
Registra las solicitudes de cotización generadas por WhatsApp o por panel administrativo (contrato manual).

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único de cotización. |
| `client_id` | `UUID` | NO | - | FK (`clients.id`), INDEX | Cliente titular de la cotización (nombre y teléfono viven en `clients`). |
| `source` | `VARCHAR(20)` | NO | `'WHATSAPP'` | CHECK in (`WHATSAPP`, `MANUAL`) | Origen: `WHATSAPP` (bot) o `MANUAL` (modo manual de contrato, RF-23). |
| `event_date` | `DATE` | NO | - | INDEX | Fecha solicitada para el evento. |
| `event_time` | `TIME` | NO | - | - | Hora estimada de inicio. |
| `location_address` | `VARCHAR(255)` | NO | - | - | Dirección de la locación. |
| `location_district` | `VARCHAR(80)` | NO | - | INDEX | Distrito de Lima Metropolitana / Callao. |
| `latitude` | `NUMERIC(10,7)` | SÍ | `NULL` | - | Coordenada de latitud. |
| `longitude` | `NUMERIC(10,7)` | SÍ | `NULL` | - | Coordenada de longitud. |
| `package_id` | `UUID` | NO | - | FK (`packages.id`) | Paquete seleccionado. |
| `theme_id` | `UUID` | SÍ | `NULL` | FK (`themes.id`) | Temática seleccionada. |
| `client_provides_mobility` | `BOOLEAN` | NO | `FALSE` | - | Si el cliente provee movilidad (costo S/. 0). |
| `calculated_distance_km` | `NUMERIC(6,2)` | SÍ | `0.00` | - | Distancia ida y vuelta calculada por Maps. |
| `calculated_transit_minutes` | `INTEGER` | SÍ | `0` | - | Minutos de tránsito ida y vuelta. |
| `base_mobility_amount` | `NUMERIC(10,2)` | NO | `0.00` | - | Costo antes del margen comercial. |
| `final_mobility_amount` | `NUMERIC(10,2)` | NO | `0.00` | - | Costo final (con +15% o ajustado). |
| `mobility_overridden` | `BOOLEAN` | NO | `FALSE` | - | Si el monto fue editado por el encargado. |
| `mobility_override_reason` | `TEXT` | SÍ | `NULL` | - | Justificación del override manual. |
| `services_subtotal` | `NUMERIC(10,2)` | NO | - | - | Paquete + suma de extras. |
| `total_amount` | `NUMERIC(10,2)` | NO | - | - | Subtotal de servicios + movilidad final. |
| `advance_amount` | `NUMERIC(10,2)` | NO | - | - | 10% del subtotal de servicios. |
| `pending_balance` | `NUMERIC(10,2)` | NO | - | - | Total menos adelanto (incluye movilidad). |
| `status` | `VARCHAR(30)` | NO | `'SENT'` | CHECK in (`SENT`, `PAYMENT_STARTED`, `CONVERTED`, `EXPIRED`, `CANCELLED`) | Estado de la cotización (ver RN, sección 3.1). |
| `sent_at` | `TIMESTAMPTZ` | NO | - | - | Momento de envío al cliente; inicia el plazo del adelanto y el cómputo de `AVAILABILITY_RECHECK_MINUTES`. |
| `expires_at` | `TIMESTAMPTZ` | NO | - | INDEX | `sent_at` + `ADVANCE_DEADLINE_HOURS`; al vencer sin comprobante la cotización pasa a `EXPIRED`. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de generación. |

*Restricciones de tabla:*
* Una cotización `MANUAL` (RF-23) sigue el mismo ciclo de vida; el evento y el contrato se crean cuando el adelanto es registrado y validado.

---

### 2.12 Tabla: `quote_extras`
Detalle de extras incluidos en una cotización.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del ítem. |
| `quote_id` | `UUID` | NO | - | FK (`quotes.id` ON DELETE CASCADE) | Cotización vinculada. |
| `extra_id` | `UUID` | NO | - | FK (`extras.id`) | Extra seleccionado. |
| `quantity` | `INTEGER` | NO | `1` | CHECK (`quantity > 0`) | Cantidad contratada. |
| `unit_price` | `NUMERIC(10,2)` | NO | - | - | Precio unitario congelado al cotizar. |
| `subtotal` | `NUMERIC(10,2)` | NO | - | - | Cantidad × Precio unitario. |

---

### 2.13 Tabla: `events`
Entidad principal del cronograma y ejecución operativa del servicio. Se crea únicamente cuando el adelanto es validado.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del evento. |
| `event_code` | `VARCHAR(30)` | NO | - | UNIQUE | Código correlativo (`EVT-2026-0001`). |
| `quote_id` | `UUID` | NO | - | FK (`quotes.id`), UNIQUE | Cotización originaria (también para contratos manuales, que generan una cotización `MANUAL`). |
| `event_date` | `DATE` | NO | - | INDEX | Fecha confirmada del evento. |
| `start_time` | `TIME` | NO | - | - | Hora de inicio programada. |
| `end_time` | `TIME` | NO | - | - | Hora de término programada. |
| `address` | `VARCHAR(255)` | NO | - | - | Dirección confirmada. |
| `district` | `VARCHAR(80)` | NO | - | INDEX | Distrito. |
| `client_observations` | `TEXT` | SÍ | `NULL` | - | Directrices especiales del cliente (visibles en cronograma). |
| `status` | `VARCHAR(30)` | NO | `'AWAITING_SIGNATURE'` | CHECK in (`AWAITING_SIGNATURE`, `SCHEDULED`, `AWAITING_BALANCE`, `IN_PROGRESS`, `EXTENDED`, `SETTLED`, `CANCELLED`) | Estado operativo (ver RN, sección 3.3). La aprobación manual por umbral de simultaneidad es un estado del pago (`REQUIRES_MANUAL_APPROVAL`), no un campo del evento; el aprobador queda en `payments.verified_by_user_id`. |
| `total_services_amount` | `NUMERIC(10,2)` | NO | - | - | Monto liquidado de servicios. |
| `total_mobility_amount` | `NUMERIC(10,2)` | NO | - | - | Monto liquidado de movilidad. |
| `final_total_amount` | `NUMERIC(10,2)` | NO | - | - | Total final facturado. |
| `advance_paid` | `NUMERIC(10,2)` | NO | `0.00` | - | Adelanto verificado (suma de pagos `ADVANCE` en `VERIFIED`). |
| `pre_show_balance_paid` | `NUMERIC(10,2)` | NO | `0.00` | - | Saldo + movilidad cobrado antes de iniciar el show (suma de pagos `BALANCE`). |
| `extra_hours_amount` | `NUMERIC(10,2)` | NO | `0.00` | - | Monto adicional por extensiones en vivo (suma de pagos `EXTENSION`). |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha de registro. |
| `actual_start_time` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Inicio real en UTC, registrado por el servidor al pasar a `IN_PROGRESS` (US-17 parcial). Eventos históricos conservan `NULL`. |

> **US-16, Slice 1:** la revisión `0004_events` crea `events` con sus columnas,
> defaults, índices, CHECK de estados y unicidad de `event_code`/`quote_id`.
> Por acuerdo de integración, `quote_id` es UUID obligatorio y único pero aún
> **no tiene FOREIGN KEY**: `quotes` no existe en develop. Una revisión posterior,
> después de integrar E1 y verificar referencias existentes, añadirá esa FK.
> No se crean tablas de E1/E3/E5 en esta revisión; `events.id` ya puede ser
> referenciado por `payments.event_id` y `crew_assignments.event_id`.

> **US-17 parcial:** `0005_event_actual_start_time` añade únicamente la columna
> de inicio real. `/start` sincroniza `pre_show_balance_paid` con el total
> `BALANCE` verificado por el puerto de E5, no con una declaración del cliente.
> Estado, total verificado e instante se persisten en una misma transacción
> bajo bloqueo de fila. La revisión `0004_events` permanece inmutable.

---

### 2.14 Tabla: `contracts`
Contratos formalizados en PDF con firma electrónica propia: enlace por WhatsApp, OTP, firma manuscrita y sello PAdES (ADR-07). Los reintentos tras una anulación crean un contrato nuevo.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del contrato. |
| `contract_number` | `VARCHAR(30)` | NO | - | UNIQUE | Número correlativo (`CTR-2026-0001`). |
| `event_id` | `UUID` | NO | - | FK (`events.id`), INDEX | Evento asociado. Solo puede existir un contrato no `VOIDED` por evento (índice único parcial). |
| `pdf_storage_path` | `VARCHAR(255)` | SÍ | `NULL` | CHECK (`status = 'DRAFT'` OR `pdf_storage_path IS NOT NULL`) | Ruta del PDF compilado; nulo mientras el contrato está en `DRAFT`. |
| `signature_token_hash` | `VARCHAR(64)` | SÍ | `NULL` | UNIQUE | Hash SHA-256 del token de un solo uso del enlace de firma; el token en claro solo viaja por WhatsApp. |
| `signature_token_expires_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Expiración del enlace de firma. |
| `otp_hash` | `VARCHAR(255)` | SÍ | `NULL` | - | Hash del código OTP de 6 dígitos enviado por WhatsApp; nulo si no hay un OTP vigente. |
| `otp_expires_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Expiración del OTP vigente. |
| `otp_attempts` | `INTEGER` | NO | `0` | CHECK (`otp_attempts >= 0`) | Intentos fallidos del OTP vigente; al superar el máximo permitido se invalida el OTP. |
| `signature_image_path` | `VARCHAR(255)` | SÍ | `NULL` | - | Ruta de la imagen de la firma manuscrita capturada. |
| `signer_ip` | `VARCHAR(45)` | SÍ | `NULL` | - | Dirección IPv4/IPv6 de quien firmó. |
| `signer_user_agent` | `VARCHAR(255)` | SÍ | `NULL` | - | Agente de usuario (navegador y dispositivo) de quien firmó. |
| `signed_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Fecha y hora exacta de la firma electrónica. |
| `sealed_pdf_storage_path` | `VARCHAR(255)` | SÍ | `NULL` | - | Ruta del PDF sellado con PAdES (pyHanko + PKCS#12). |
| `sealed_pdf_sha256` | `CHAR(64)` | SÍ | `NULL` | - | Hash SHA-256 (hexadecimal) del PDF sellado; también se registra en `audit_logs`. |
| `is_timestamped` | `BOOLEAN` | NO | `FALSE` | - | Si el sello incluye una marca de tiempo RFC 3161 (opcional). |
| `status` | `VARCHAR(30)` | NO | `'DRAFT'` | CHECK in (`DRAFT`, `ISSUED`, `SIGNED`, `VOIDED`) | Estado del contrato (ver RN, sección 3.4). |
| `is_manual_mode` | `BOOLEAN` | NO | `FALSE` | - | Si fue confeccionado manualmente por el encargado. |
| `custom_clauses` | `TEXT` | SÍ | `NULL` | - | Cláusulas contractuales personalizadas. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha de emisión. |

*Restricciones de tabla:*
* `CREATE UNIQUE INDEX uq_contracts_event_active ON contracts (event_id) WHERE status <> 'VOIDED'`: un solo contrato vigente por evento; tras anular, se puede emitir uno nuevo.
* `CHECK (status <> 'SIGNED' OR (signed_at IS NOT NULL AND sealed_pdf_storage_path IS NOT NULL AND sealed_pdf_sha256 IS NOT NULL))`

---

### 2.15 Tabla: `payments`
Registro de pagos de una cotización: adelanto (`ADVANCE`, con ciclo de verificación completo), saldo pre-show (`BALANCE`) y extensiones en vivo (`EXTENSION`), estos dos últimos registrados in situ como `VERIFIED` con evidencia obligatoria y auditados después por el encargado.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del pago. |
| `quote_id` | `UUID` | NO | - | FK (`quotes.id`), INDEX | Cotización a la que pertenece el pago. |
| `event_id` | `UUID` | SÍ | `NULL` | FK (`events.id`), INDEX | Evento asociado; nulo mientras el adelanto no se valida (el evento aún no existe). |
| `concept` | `VARCHAR(20)` | NO | - | CHECK in (`ADVANCE`, `BALANCE`, `EXTENSION`) | Concepto del pago. |
| `payment_method` | `VARCHAR(30)` | NO | - | CHECK in (`YAPE`, `PLIN`, `BANK_TRANSFER`, `CASH`) | Medio de pago utilizado. UI: «Yape», «Plin», «Transferencia bancaria», «Efectivo». |
| `amount` | `NUMERIC(10,2)` | NO | - | CHECK (`amount > 0`) | Monto pagado en Soles (PEN). |
| `evidence_path` | `VARCHAR(255)` | NO | - | - | Ruta de la evidencia: captura del comprobante (`ADVANCE`) o foto tomada in situ de la pantalla de Yape/Plin o del efectivo (`BALANCE`, `EXTENSION`). |
| `transaction_reference` | `VARCHAR(60)` | SÍ | `NULL` | - | Número de operación bancaria o de Yape. |
| `validation_status` | `VARCHAR(30)` | NO | `'PENDING_VERIFICATION'` | CHECK in (`PENDING_VERIFICATION`, `REQUIRES_MANUAL_APPROVAL`, `VERIFIED`, `REJECTED`, `REFUND_PENDING`, `REFUNDED`) | Estado del pago (ver RN, sección 3.2). Los pagos `BALANCE` y `EXTENSION` nacen en `VERIFIED`. |
| `rejection_reason` | `TEXT` | SÍ | `NULL` | - | Motivo de rechazo para el flujo de reintento. |
| `verified_by_user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Encargado que validó el adelanto o aprobó el sobrecupo. |
| `verified_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Fecha de verificación. |
| `registered_by_user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Operador o encargado que registró el cobro in situ; nulo en `ADVANCE` (lo envía el cliente por WhatsApp). |
| `audit_status` | `VARCHAR(20)` | SÍ | `NULL` | CHECK in (`UNREVIEWED`, `REVIEWED`, `FLAGGED`) | Auditoría posterior del encargado (ver RN, sección 3.2); nulo en `ADVANCE`, `UNREVIEWED` al registrar un `BALANCE` o `EXTENSION`. |
| `audited_by_user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Encargado que revisó o marcó el cobro. |
| `audited_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Fecha y hora de la auditoría. |
| `audit_notes` | `TEXT` | SÍ | `NULL` | - | Observaciones de la auditoría (obligatorias al marcar `FLAGGED`). |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha de carga o registro del pago. |

*Restricciones de tabla:*
* `CHECK ((concept = 'ADVANCE') = (audit_status IS NULL))`: solo los cobros in situ se auditan.
* `CHECK (concept = 'ADVANCE' OR (validation_status = 'VERIFIED' AND registered_by_user_id IS NOT NULL AND event_id IS NOT NULL))`: `BALANCE` y `EXTENSION` se registran como verificados, por un usuario identificado y sobre un evento existente.
* `CHECK (audit_status IS DISTINCT FROM 'FLAGGED' OR audit_notes IS NOT NULL)`

---

### 2.16 Tabla: `crews`
Elencos y proveedores freelance asignables a eventos.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del elenco. |
| `user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`), UNIQUE | Usuario `OPERADOR` que opera en nombre del elenco; define los eventos propios que puede ver y operar. Nulo si el elenco no usa el sistema. |
| `leader_name` | `VARCHAR(120)` | NO | - | - | Nombre del líder o responsable del elenco. |
| `phone` | `VARCHAR(20)` | NO | - | - | Teléfono de contacto del líder. |
| `service_category` | `VARCHAR(30)` | NO | - | CHECK in (`SHOW`, `DJ`, `DECORATION`, `TENTS`) | Tipo de servicio que presta el elenco; enumeración `service_category` compartida con `packages`. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Indica si el elenco está disponible para asignaciones. |

---

### 2.17 Tabla: `crew_assignments`
Asignación de un elenco a un evento, con el intervalo de tránsito aplicado (RF-10, RF-22).

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador de la asignación. |
| `event_id` | `UUID` | NO | - | FK (`events.id`), INDEX | Evento atendido. |
| `crew_id` | `UUID` | NO | - | FK (`crews.id`), INDEX | Elenco asignado. |
| `transit_interval_minutes` | `INTEGER` | SÍ | `NULL` | CHECK (`transit_interval_minutes >= 0`) | Intervalo de tránsito aplicado respecto del evento anterior del elenco; nulo si es el primero del día. |
| `transit_interval_overridden` | `BOOLEAN` | NO | `FALSE` | - | Si el encargado modificó el intervalo sugerido (la justificación se registra en `audit_logs`). |
| `assigned_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de la asignación. |

*Restricciones de tabla:*
* `UNIQUE(event_id, crew_id)`

---

### 2.18 Tabla: `event_extensions`
Extensiones de tiempo registradas durante el show (RF-19). El cobro vive en `payments` con concepto `EXTENSION`.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador de la extensión. |
| `event_id` | `UUID` | NO | - | FK (`events.id`), INDEX | Evento extendido. |
| `payment_id` | `UUID` | NO | - | FK (`payments.id`), UNIQUE | Pago `EXTENSION` que cubre la extensión (medio, evidencia y auditoría). |
| `extra_minutes` | `INTEGER` | NO | - | CHECK (`extra_minutes > 0`) | Minutos adicionales acordados. |
| `agreed_rate` | `NUMERIC(10,2)` | NO | - | CHECK (`agreed_rate > 0`) | Tarifa pactada por la extensión. |
| `requested_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora del pedido del cliente. |

---

### 2.19 Tabla: `outbox_messages`
Cola de mensajes salientes con reintentos (patrón *outbox*). Desacopla las transacciones de negocio de la disponibilidad de la pasarela de mensajería: el despachador entrega cada mensaje a Chatwoot mediante `IMessagingPort`, y Chatwoot lo envía por WhatsApp (ADR-05, ADR-10).

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del mensaje. |
| `recipient_phone` | `VARCHAR(20)` | NO | - | - | Teléfono de destino en formato E.164. |
| `message_type` | `VARCHAR(30)` | NO | - | CHECK in (`TEXT`, `TEMPLATE`, `INTERACTIVE`, `DOCUMENT`) | Tipo de mensaje de WhatsApp enviado a través de la pasarela. |
| `payload` | `JSONB` | SÍ | `NULL` | - | Contenido estructurado del mensaje; se anula (`NULL`) tras el envío de mensajes con OTP. |
| `status` | `VARCHAR(20)` | NO | `'PENDING'` | CHECK in (`PENDING`, `SENT`, `FAILED`) | `PENDING` en cola, `SENT` entregado a la pasarela (Chatwoot), `FAILED` reintentos agotados. |
| `attempts` | `INTEGER` | NO | `0` | CHECK (`attempts >= 0`) | Intentos de envío realizados. |
| `max_attempts` | `INTEGER` | NO | `5` | CHECK (`max_attempts > 0`) | Máximo de intentos antes de marcar `FAILED`. |
| `next_attempt_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | INDEX | Momento del próximo intento (retroceso exponencial). |
| `last_error` | `TEXT` | SÍ | `NULL` | - | Último error devuelto por la pasarela de mensajería. |
| `sent_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Momento del envío exitoso. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de encolado. |

*Restricciones de tabla:*
* `INDEX(status, next_attempt_at)` para el despachador de mensajes pendientes.

---

### 2.20 Tabla: `audit_logs`
Bitácora de auditoría para trazabilidad de decisiones críticas y procesos de control.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del log. |
| `user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Usuario responsable de la acción; nulo en acciones del sistema o del cliente (por ejemplo, la firma). |
| `action` | `VARCHAR(50)` | NO | - | CHECK in (`OVERRIDE_MOBILITY`, `OVERRIDE_TRANSIT_INTERVAL`, `APPROVE_OVERBOOKED_PAYMENT`, `REJECT_OVERBOOKED_PAYMENT`, `AUDIT_PAYMENT`, `MANUAL_CONTRACT`, `CONTRACT_SIGNED`, `SEND_CONVERSATION_MESSAGE`, `OVERRIDE_CONVERSATION_ASSIGNMENT`) | Acción registrada. `SEND_CONVERSATION_MESSAGE` identifica al encargado que escribió un mensaje enviado con el agente de servicio de Chatwoot (ADR-10). `OVERRIDE_CONVERSATION_ASSIGNMENT` registra la reasignación de una conversación por un `SUPERADMIN`. `CONTRACT_SIGNED` guarda en `new_values` el SHA-256 del PDF sellado, la verificación del OTP, la IP, el agente de usuario y las marcas de tiempo. |
| `entity_name` | `VARCHAR(50)` | NO | - | - | Entidad modificada (`quotes`, `events`, `contracts`, `payments`, `crew_assignments`). |
| `entity_id` | `UUID` | NO | - | INDEX (`entity_name`, `entity_id`) | UUID de la entidad en cuestión. |
| `old_values` | `JSONB` | SÍ | `NULL` | - | Estado anterior en formato JSON. |
| `new_values` | `JSONB` | SÍ | `NULL` | - | Nuevo estado aplicado en formato JSON. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de la acción. |

---

### 2.21 Tabla: `package_inventory_items`
Ítems de inventario que consume cada paquete, con la cantidad por evento. Un paquete puede consumir varios ítems (por ejemplo, un toldo y un kit de decoración); un paquete sin filas (`SHOW`, `DJ`) no consume inventario. Respalda la verificación de disponibilidad de RF-09 y es el origen de las filas de `inventory_reservations` al crear el evento.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador de la relación. |
| `package_id` | `UUID` | NO | - | FK (`packages.id` ON DELETE CASCADE) | Paquete que consume el ítem. |
| `inventory_item_id` | `UUID` | NO | - | FK (`inventory_items.id`), INDEX | Ítem de inventario consumido. |
| `quantity` | `INTEGER` | NO | `1` | CHECK (`quantity > 0`) | Unidades del ítem que consume el paquete por evento. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de registro. |

*Restricciones de tabla:*
* `UNIQUE(package_id, inventory_item_id)`
* `INDEX(inventory_item_id)`

---

### 2.22 Tabla: `conversation_links`
Vínculo entre una conversación de Chatwoot y los datos de negocio de EventPro (cliente, cotización vigente y encargado que la tomó). Es la única información de conversaciones que persiste EventPro (ADR-10).

**EventPro no almacena mensajes.** Chatwoot es la fuente de verdad de los mensajes, los medios, los estados de entrega y el estado de la conversación (`pending` o `open`); EventPro los consulta por API y los recibe por webhook.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del vínculo. |
| `chatwoot_conversation_id` | `BIGINT` | NO | - | UNIQUE | Identificador de la conversación en Chatwoot. |
| `client_id` | `UUID` | NO | - | FK (`clients.id`), INDEX | Cliente de la conversación (el teléfono de WhatsApp es su clave natural). |
| `quote_id` | `UUID` | SÍ | `NULL` | FK (`quotes.id`) | Cotización vigente de la conversación, si existe. |
| `assigned_user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`), INDEX parcial | Encargado que tomó la conversación; nulo mientras responde el bot o si está derivada sin asignar. |
| `handoff_reason` | `VARCHAR(30)` | SÍ | `NULL` | CHECK in (`CLIENT_REQUEST`, `BOT_NOT_UNDERSTOOD`, `MANUAL_TAKEOVER`, `BOT_ERROR`) | Motivo de la última derivación a un humano; nulo si nunca fue derivada. UI: «Solicitud del cliente», «Bot no entendió», «Toma manual», «Error del bot». |
| `handoff_summary` | `TEXT` | SÍ | `NULL` | - | Resumen generado al derivar (datos capturados y cotización vigente). |
| `handed_off_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Fecha y hora de la última derivación; permite ordenar la bandeja. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de creación del vínculo. |
| `updated_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de la última modificación del vínculo. |

*Restricciones de tabla:*
* `UNIQUE(chatwoot_conversation_id)`
* `INDEX(client_id)`
* `CREATE INDEX ix_conversation_links_assigned_user ON conversation_links (assigned_user_id) WHERE assigned_user_id IS NOT NULL` para el filtro «asignadas a mí» de la bandeja.
