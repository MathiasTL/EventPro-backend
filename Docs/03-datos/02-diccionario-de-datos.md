# 02. Diccionario de Datos Exhaustivo

---

## 1. Convenciones y Estándares de Base de Datos
* **Motor:** PostgreSQL 16+.
* **Claves Primarias (PK):** `UUIDv4` (`gen_random_uuid()`).
* **Valores Monetarios:** `NUMERIC(10,2)` estricto para prevenir pérdidas de precisión decimal.
* **Marcas Temporales:** `TIMESTAMPTZ` en UTC (`CURRENT_TIMESTAMP`).
* **Nomenclatura:** `snake_case` para nombres de tablas y columnas; nombres en plural para tablas (`quotes`, `events`, `contracts`).

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

### 2.3 Tabla: `packages`
Catálogo de paquetes base comercializados por la promotora.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del paquete. |
| `name` | `VARCHAR(100)` | NO | - | - | Nombre (ej. "Hora Loca Medium", "Show Infantil"). |
| `category` | `VARCHAR(30)` | NO | - | CHECK in (`SHOW`, `DECORACION`, `TOLDOS`, `DJ`) | Categoría del servicio. |
| `description` | `TEXT` | SÍ | `NULL` | - | Detalle de lo que incluye el paquete. |
| `base_price` | `NUMERIC(10,2)` | NO | - | CHECK (`base_price > 0`) | Tarifa de venta al cliente en Soles (PEN). |
| `direct_cost` | `NUMERIC(10,2)` | NO | - | CHECK (`direct_cost >= 0`) | Costo fijo pagado al elenco/proveedor freelance. |
| `duration_minutes`| `INTEGER` | NO | 60 | CHECK (`duration_minutes > 0`) | Duración estándar de la prestación en minutos. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Indica si está activo en el catálogo. |

---

### 2.4 Tabla: `themes`
Temáticas decorativas y conceptuales aplicables a los paquetes.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único de la temática. |
| `name` | `VARCHAR(80)` | NO | - | UNIQUE | Nombre (ej. "Selva", "Neón Glow", "Retro 80s"). |
| `description` | `TEXT` | SÍ | `NULL` | - | Descripción visual de la temática. |
| `is_active` | `BOOLEAN` | NO | `TRUE` | - | Habilitado para cotización. |

---

### 2.5 Tabla: `package_themes`
Relación muchos a muchos entre paquetes y temáticas compatibles.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador de la relación. |
| `package_id` | `UUID` | NO | - | FK (`packages.id`) | Paquete vinculado. |
| `theme_id` | `UUID` | NO | - | FK (`themes.id`) | Temática compatible. |

*Restricción:* `UNIQUE(package_id, theme_id)`

---

### 2.6 Tabla: `extras`
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

### 2.7 Tabla: `quotes`
Registra las solicitudes de cotización generadas por WhatsApp o por panel administrativo.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único de cotización. |
| `client_name` | `VARCHAR(120)` | NO | - | - | Nombre y apellido del cliente. |
| `client_phone` | `VARCHAR(20)` | NO | - | INDEX | Teléfono de WhatsApp del cliente. |
| `event_date` | `DATE` | NO | - | INDEX | Fecha solicitada para el evento. |
| `event_time` | `TIME` | NO | - | - | Hora estimada de inicio. |
| `location_address`| `VARCHAR(255)` | NO | - | - | Dirección de la locación. |
| `location_district`| `VARCHAR(80)` | NO | - | INDEX | Distrito de Lima Metropolitana / Callao. |
| `latitude` | `NUMERIC(10,7)`| SÍ | `NULL` | - | Coordenada de latitud. |
| `longitude`| `NUMERIC(10,7)`| SÍ | `NULL` | - | Coordenada de longitud. |
| `package_id` | `UUID` | NO | - | FK (`packages.id`) | Paquete seleccionado. |
| `theme_id` | `UUID` | SÍ | `NULL` | FK (`themes.id`) | Temática seleccionada. |
| `client_provides_mobility` | `BOOLEAN` | NO | `FALSE` | - | Si el cliente provee movilidad (costo S/. 0). |
| `calculated_distance_km` | `NUMERIC(6,2)` | SÍ | `0.00` | - | Distancia ida y vuelta calculada por Maps. |
| `calculated_transit_minutes` | `INTEGER` | SÍ | 0 | - | Minutos de tránsito ida y vuelta. |
| `base_mobility_amount` | `NUMERIC(10,2)` | NO | `0.00` | - | Costo antes del margen comercial. |
| `final_mobility_amount`| `NUMERIC(10,2)` | NO | `0.00` | - | Costo final (con +15% o ajustado). |
| `mobility_overridden` | `BOOLEAN` | NO | `FALSE` | - | Si el monto fue editado por el encargado. |
| `mobility_override_reason` | `TEXT` | SÍ | `NULL` | - | Justificación del override manual. |
| `services_subtotal` | `NUMERIC(10,2)` | NO | - | - | Paquete + suma de extras. |
| `total_amount` | `NUMERIC(10,2)` | NO | - | - | Subtotal de servicios + movilidad final. |
| `advance_amount` | `NUMERIC(10,2)` | NO | - | - | 10% de subtotal de servicios. |
| `pending_balance` | `NUMERIC(10,2)` | NO | - | - | Total menos adelanto (incluye movilidad). |
| `status` | `VARCHAR(30)` | NO | `'COTIZADO'` | CHECK in (`BORRADOR`, `COTIZADO`, `ACEPTADO`, `VENCIDO`) | Estado de la cotización. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de generación. |

---

### 2.8 Tabla: `quote_extras`
Detalle de extras incluidos en una cotización.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del ítem. |
| `quote_id` | `UUID` | NO | - | FK (`quotes.id` ON DELETE CASCADE) | Cotización vinculada. |
| `extra_id` | `UUID` | NO | - | FK (`extras.id`) | Extra seleccionado. |
| `quantity` | `INTEGER` | NO | 1 | CHECK (`quantity > 0`) | Cantidad contratada. |
| `unit_price` | `NUMERIC(10,2)` | NO | - | - | Precio unitario congelado al cotizar. |
| `subtotal` | `NUMERIC(10,2)` | NO | - | - | Cantidad $\times$ Precio unitario. |

---

### 2.9 Tabla: `events`
Entidad principal del cronograma y ejecución operativa del servicio.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador único del evento. |
| `event_code` | `VARCHAR(30)` | NO | - | UNIQUE | Código correlativo (`EVT-2026-0001`). |
| `quote_id` | `UUID` | NO | - | FK (`quotes.id`), UNIQUE | Cotización originaria. |
| `event_date` | `DATE` | NO | - | INDEX | Fecha confirmada del evento. |
| `start_time` | `TIME` | NO | - | - | Hora de inicio programada. |
| `end_time` | `TIME` | NO | - | - | Hora de término programada. |
| `address` | `VARCHAR(255)` | NO | - | - | Dirección confirmada. |
| `district` | `VARCHAR(80)` | NO | - | INDEX | Distrito. |
| `client_observations` | `TEXT` | SÍ | `NULL` | - | Directrices especiales del cliente (visibles en cronograma). |
| `status` | `VARCHAR(30)` | NO | `'AGENDADO'` | CHECK in (`AGENDADO`, `EN_ESPERA_COBRO`, `EN_EJECUCION`, `CON_EXTENSION`, `LIQUIDADO`, `CANCELADO`) | Estado operativo. |
| `requires_manual_approval`| `BOOLEAN` | NO | `FALSE` | - | Activado si supera el umbral de 3 shows simultáneos. |
| `is_manually_approved` | `BOOLEAN` | NO | `FALSE` | - | Indica si el encargado aprobó el evento concurrente. |
| `approved_by_user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Encargado que autorizó el show concurrente. |
| `total_services_amount`| `NUMERIC(10,2)` | NO | - | - | Monto liquidado de servicios. |
| `total_mobility_amount`| `NUMERIC(10,2)` | NO | - | - | Monto liquidado de movilidad. |
| `final_total_amount` | `NUMERIC(10,2)` | NO | - | - | Total final facturado. |
| `advance_paid` | `NUMERIC(10,2)` | NO | `0.00` | - | Adelanto del 10% verificado. |
| `pre_show_balance_paid`| `NUMERIC(10,2)` | NO | `0.00` | - | Saldo + movilidad cobrado antes de iniciar el show. |
| `extra_hours_amount` | `NUMERIC(10,2)` | NO | `0.00` | - | Monto adicional por extensiones en vivo. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha de registro. |

---

### 2.10 Tabla: `contracts`
Contratos formalizados en PDF con metadatos de firma electrónica.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del contrato. |
| `contract_number` | `VARCHAR(30)` | NO | - | UNIQUE | Número correlativo (`CTR-2026-0001`). |
| `event_id` | `UUID` | NO | - | FK (`events.id`), UNIQUE | Evento asociado. |
| `pdf_storage_path` | `VARCHAR(255)` | NO | - | - | Ruta en el repositorio de archivos. |
| `signature_token` | `VARCHAR(100)` | NO | - | UNIQUE | Token seguro de un solo uso para firma web. |
| `signature_image_url` | `TEXT` | SÍ | `NULL` | - | Imagen de la firma manuscrita capturada. |
| `signer_ip` | `VARCHAR(45)` | SÍ | `NULL` | - | Dirección IPv4/IPv6 de quien firmó. |
| `signed_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Fecha y hora exacta de la firma digital. |
| `status` | `VARCHAR(30)` | NO | `'EMITIDO'` | CHECK in (`BORRADOR`, `EMITIDO`, `FIRMADO`, `ANULADO`) | Estado del contrato. |
| `is_manual_mode` | `BOOLEAN` | NO | `FALSE` | - | Si fue confeccionado manualmente por el encargado. |
| `custom_clauses` | `TEXT` | SÍ | `NULL` | - | Cláusulas contractuales personalizadas. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha de emisión. |

---

### 2.11 Tabla: `payments`
Registro de comprobantes de pago (adelanto, saldo pre-show y horas extra).

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del pago. |
| `event_id` | `UUID` | NO | - | FK (`events.id`) | Evento asociado. |
| `payment_concept` | `VARCHAR(30)` | NO | - | CHECK in (`ADELANTO_10`, `SALDO_PRE_SHOW`, `EXTENSION_EN_VIVO`) | Concepto del pago. |
| `payment_method` | `VARCHAR(30)` | NO | - | CHECK in (`YAPE`, `PLIN`, `TRANSFERENCIA`, `EFECTIVO`) | Medio de pago utilizado. |
| `amount` | `NUMERIC(10,2)` | NO | - | CHECK (`amount > 0`) | Monto pagado en Soles (PEN). |
| `receipt_image_url`| `VARCHAR(255)` | SÍ | `NULL` | - | URL o ruta de la captura del comprobante. |
| `transaction_reference` | `VARCHAR(60)` | SÍ | `NULL` | - | Número de operación bancaria o de Yape. |
| `validation_status`| `VARCHAR(30)` | NO | `'PENDIENTE'` | CHECK in (`PENDIENTE`, `VERIFICADO`, `RECHAZADO`) | Estado de auditoría del pago. |
| `rejection_reason` | `TEXT` | SÍ | `NULL` | - | Motivo de rechazo para el flujo de reintento. |
| `verified_by_user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Usuario que validó el pago. |
| `verified_at` | `TIMESTAMPTZ` | SÍ | `NULL` | - | Fecha de verificación. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha de carga del comprobante. |

---

### 2.12 Tabla: `audit_logs`
Bitácora de auditoría para trazabilidad de decisiones críticas y procesos de control.

| Columna | Tipo | Nulo | Default | Restricciones | Descripción |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `id` | `UUID` | NO | `gen_random_uuid()` | PK | Identificador del log. |
| `user_id` | `UUID` | SÍ | `NULL` | FK (`users.id`) | Usuario responsable de la acción. |
| `action` | `VARCHAR(50)` | NO | - | - | Acción (`OVERRIDE_MOBILITY`, `APPROVE_SIMULTANEOUS`, `MANUAL_CONTRACT`). |
| `entity_name` | `VARCHAR(50)` | NO | - | - | Entidad modificada (`quotes`, `events`, `contracts`). |
| `entity_id` | `VARCHAR(40)` | NO | - | - | UUID de la entidad en cuestión. |
| `old_values` | `JSONB` | SÍ | `NULL` | - | Estado anterior en formato JSON. |
| `new_values` | `JSONB` | SÍ | `NULL` | - | Nuevo estado aplicado en formato JSON. |
| `created_at` | `TIMESTAMPTZ` | NO | `CURRENT_TIMESTAMP` | - | Fecha y hora de la acción. |
