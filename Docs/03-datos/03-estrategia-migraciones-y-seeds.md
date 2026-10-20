# 03. Estrategia de Migraciones y Datos Semilla (Seeds)

---

## 1. Estrategia de Migraciones con Alembic

Para la evolución del esquema en PostgreSQL, EventPro utiliza **Alembic**, la herramienta de migraciones estándar del ecosistema SQLAlchemy.

### 1.1 Reglas de Gobernanza de Migraciones
1. **Inmutabilidad de Migraciones Aplicadas:** Una migración fusionada en la rama `main` o `develop` no debe ser modificada jamás; cualquier cambio debe aplicarse mediante una nueva migración incremental.
2. **Reversibilidad Obligatoria:** Toda migración generada debe implementar tanto el método `upgrade()` como el método `downgrade()`.
3. **Generación Automatizada y Revisión Manual:** Las migraciones se generan con `alembic revision --autogenerate -m "descripcion"` y deben ser auditadas línea por línea antes de su commit para verificar índices y restricciones `CHECK`.
4. **Una sola cadena:** cada revisión nueva parte del head vigente de `develop`.
   Actualizar y comprobar nuevamente antes de integrar; no modificar revisiones
   ya fusionadas ni generar una segunda rama de migraciones.

### 1.2 Esquema base `0001_initial_schema`
El historial de migraciones parte de una única revisión base, `0001_initial_schema` (`down_revision = None`), que crea las 21 tablas documentadas en el [Diccionario de Datos](02-diccionario-de-datos.md) —todas salvo `event_extensions`, ver más abajo— junto con sus claves foráneas, índices y restricciones `CHECK`. Incluye, entre otras, `clients`, `quotes`, `quote_extras`, `inventory_reservations`, `contracts`, `crew_assignments`, `outbox_messages` y `conversation_links`, de modo que cada épica construye sobre tablas ya existentes.

Particularidades del esquema base:
* `events.quote_id` y `payments.quote_id` tienen FOREIGN KEY a `quotes.id`; ya no quedan FK diferidas.
* `conversation_links` se crea después de `users`, `clients` y `quotes`, con su índice único sobre `chatwoot_conversation_id`, el índice sobre `client_id`, el índice parcial sobre `assigned_user_id` y la restricción `CHECK` de `handoff_reason`. No requiere datos semilla: los vínculos se crean en tiempo de ejecución cuando llega la primera conversación de un cliente.
* El correo de `users` es único sin distinguir mayúsculas (índice único sobre `lower(email)`).
* Toda columna con clave foránea tiene índice (propio o como primera columna de un índice compuesto o único).
* Los importes de `events` son no negativos y `end_time <> start_time`.
* `downgrade()` elimina todas las tablas en orden inverso al de creación.

`alembic/env.py` compara también los valores por defecto del servidor (`compare_server_default`) y omite en el autogenerate las tablas que existen en la base pero aún no tienen modelo ORM, para que `alembic check` no proponga eliminarlas. Las tablas con modelo se comparan con normalidad.

### 1.3 Excepción única de consolidación (2026-10-07)
El 2026-10-07 se reemplazó la cadena incremental `0001`–`0006` por `0001_initial_schema`. Fue una **excepción única** a la regla de inmutabilidad (sección 1.1, regla 1): no existe ninguna base de datos desplegada ni compartida con datos que deba conservarse, por lo que reescribir el historial no tiene costo operativo. Quien tenga una base local creada con las revisiones anteriores debe seguir el procedimiento de la sección 1.4, que distingue datos descartables de datos que requieran conservación.

**Desde esta consolidación la regla 1 vuelve a regir sin excepciones:** `0001_initial_schema` no se modifica una vez fusionada y cualquier cambio de esquema se aplica con una nueva revisión que parte de ella. La siguiente revisión encadena desde `0001_initial_schema`. En particular, la migración de `event_extensions` (y de `events.extra_minutes_total`) del PR #15 debe rebasarse sobre esta revisión: su `down_revision` pasa a ser `"0001_initial_schema"`.

### 1.4 US-18: `0002_event_extensions`

Al cerrar US-18 la cadena era `base → 0001_initial_schema → 0002_event_extensions`, con un
único head. `0002` crea el detalle de extensiones y añade los acumuladores
`extra_minutes_total` y `legacy_extra_hours_amount`. El baseline permanece intacto.

El upgrade copia el importe adicional anterior como crédito histórico únicamente
en eventos sin ningún pago `EXTENSION`. Conserva `final_total_amount` y
`extra_hours_amount`, sin fabricar detalles, pagos, fotos ni minutos. Un pago real
sin detalle requiere reconciliarlo antes del cierre; no recibe crédito automático.
El crédito no tiene entrada pública. El downgrade elimina la tabla y los dos campos
nuevos; conserva los totales, pagos y reservas existentes, pero pierde el detalle
de extensiones: respaldarlo antes de un downgrade con datos que deban conservarse.

Las pruebas usan PostgreSQL 16 efímero: upgrade desde base a `0001`, datos históricos
con cotizaciones válidas, upgrade a head, downgrade a `0001` y nuevo upgrade.
Las fixtures crean `clients`, `packages` y `quotes` antes de sus eventos y pagos.

**Bases locales con revisiones eliminadas (`0006_payments` o `0007_event_extensions`):**

1. Comprobar `alembic_version`, `alembic heads` y la base de destino; respaldar datos
   y evidencias que deban conservarse antes de cualquier recreación.
2. Para datos descartables, crear una base nueva y configurar la conexión hacia ella.
   Ejecutar `alembic upgrade head` y después el seed. Verificar un único head
   `0005_event_financial_snapshots` antes de sustituir la conexión anterior.
3. Para datos que deban conservarse, restaurar una copia aislada y preparar una
   reconciliación explícita del esquema y datos con el baseline, incluidas las FK
   de cotizaciones y detalles de pagos. Validar allí primero. No usar `stamp` para
   aparentar que el esquema fue migrado: solo marca una revisión y no ejecuta DDL.

Este cambio se valida únicamente en bases efímeras; no recrea ni actualiza la base
local del desarrollador automáticamente. Los nuevos escritores de disponibilidad
deben respetar el [protocolo de bloqueo de US-18](../02-arquitectura/02-backend-arquitectura-hexagonal.md).

### 1.5 E1 Bloque 2: `0004_outbox_delivery_tracking`

`0004_outbox_delivery_tracking` parte de `0003_manual_booking_documents` y precede a `0005_event_financial_snapshots`. `0004` solo agrega columnas y restricciones a `outbox_messages` y cambia un valor por defecto, según la [especificación de la cola de mensajes salientes](../02-arquitectura/07-spec-e1-outbox-mensajeria.md):

* Columnas nuevas: `external_message_id` (única), `conversation_id`, `delivery_status` (con `CHECK`), `delivery_error`, `delivered_at`, `read_at` y `redact_after_send` (`NOT NULL`, por defecto `false`).
* `max_attempts` pasa de `5` a `6` por defecto (RNF-03.2: el primer envío más cinco reintentos). Las filas existentes conservan su valor.
* El `downgrade` elimina las restricciones y las columnas nuevas y restaura el valor por defecto `5`. Conserva los mensajes existentes, pero pierde los datos de entrega.

Las pruebas usan PostgreSQL 16 efímero: upgrade a `0003` con un mensaje heredado, upgrade a `0004`, comprobación de columnas, restricciones y valor por defecto, downgrade a `0003` y nuevo upgrade a head.

---

### 1.6 US-21: `0005_event_financial_snapshots`

La cadena vigente es `base → 0001_initial_schema → 0002_event_extensions →
0003_manual_booking_documents → 0004_outbox_delivery_tracking →
0005_event_financial_snapshots`, con un único head `0005_event_financial_snapshots`.

`0003_manual_booking_documents` incorpora documentos privados e idempotencia del
flujo manual. `0005_event_financial_snapshots` agrega exclusivamente la tabla
contable por evento y reconstruye los eventos ya `SETTLED`, sin modificar el
baseline, el catálogo, los pagos ni los defaults de cotizaciones.

La reconstrucción verifica cobertura y correspondencia de extensiones, pagos,
minutos y acumulados. Usa los costos vigentes y marca `LEGACY_BACKFILL`, conservando
identificadores, cantidades y componentes monetarios en JSONB. Durante diagnóstico
y captura, bloqueos `SHARE` evitan escrituras concurrentes en las fuentes. Se fija
`SET LOCAL lock_timeout = '5s'` antes de adquirirlos para abortar si una transacción
concurrente impide el bloqueo; aplicar durante una ventana de despliegue y reintentar
cuando termine la escritura en curso. Una inconsistencia aborta toda la migración
con la lista completa de IDs afectados en un único error. Conciliar cotizaciones,
costos, pagos y extensiones de esos eventos antes de reintentar.

**Rollback y PC-09:** el downgrade de `0005` a `0004_outbox_delivery_tracking`
elimina la tabla `event_financial_snapshots` y todas sus instantáneas, incluidos
los costos históricos congelados al liquidar. Conserva eventos, pagos y outbox.
Respaldar y verificar una copia de las instantáneas antes de revertir si se necesita
conservar el histórico de PC-09. Un posterior upgrade a `0005` reconstruye los
snapshots de eventos `SETTLED` bajo la etiqueta `LEGACY_BACKFILL` tomando los costos
vigentes del catálogo en ese momento; no recupera los costos históricos eliminados.

Si el P&L responde 409 porque hay eventos `SETTLED` sin snapshot, el log
`financial_data_inconsistent` incluye el período y todos los `event_ids` afectados.
Usar esos IDs para conciliar las fuentes y restaurar las instantáneas desde un
respaldo verificado cuando exista. Si no existe respaldo, preparar y validar en
una copia aislada una reconstrucción explícita marcada `LEGACY_BACKFILL` con
costos vigentes, siguiendo las validaciones de `0005`, y verificar después el P&L
del mes y la semana. Evitar un downgrade global como reparación de un evento:
eliminaría también los históricos correctos de los demás eventos.

Validación: Testcontainers PostgreSQL 16, upgrade con históricos válidos e
inconsistentes, rollback, downgrade/upgrade, PK/FK/CHECK y consistencia de revisiones.
La comparación ORM de esta US se limita a `event_financial_snapshots`. Al conservar
`quote_model.py` como en `develop`, el `alembic check` global detecta dos diferencias
preexistentes: los defaults de `quotes.calculated_distance_km` y
`quotes.calculated_transit_minutes` existen en el baseline, pero se omiten en el ORM
para persistir `NULL` explícito en contingencia. Su reconciliación queda fuera de US-21.
La BD compartida solo se migra desde `develop` mediante el flujo manual existente.
Si aún está en `0002`, `upgrade head` aplica `0003`, `0004` y después `0005`.

---

## 2. Datos Semilla Iniciales (Seed Data)

Los siguientes datos corresponden a la realidad operativa de la promotora en Lima, Perú, cargados para permitir el funcionamiento inmediato del sistema:

### 2.1 Roles del Sistema (`roles`)
```sql
INSERT INTO roles (id, code, name, description) VALUES
  ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'SUPERADMIN', 'Super Administrador', 'Acceso total y configuración de parámetros globales.'),
  ('b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22', 'ENCARGADO', 'Encargado del Negocio', 'Gestión de cotizaciones, overrides, aprobación de shows y reportes.'),
  ('c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33', 'OPERADOR', 'Operador de Elenco / Campo', 'Confirmación de cobro in-situ y reporte de extensiones de show.');
```

---

### 2.2 Catálogo de Paquetes Base (`packages`)
*Nota: Los costos fijos representan la tarifa acordada con el personal freelance.*

*Nota: la «Jornada» se siembra como `duration_minutes = 480` (8 horas). Es un supuesto de negocio pendiente de confirmar; al ser un dato de catálogo, se ajusta sin cambiar el esquema. Los paquetes de categoría `TENTS` se vinculan a ítems de inventario mediante filas en `package_inventory_items` (ver sección 2.5).*

| Nombre del Paquete | `service_category` | Precio Venta (S/.) | Costo Fijo (S/.) | Duración |
| :--- | :--- | :---: | :---: | :---: |
| **Hora Loca Básica** | `SHOW` | S/. 450.00 | S/. 250.00 | 45 min |
| **Hora Loca Medium** | `SHOW` | S/. 750.00 | S/. 400.00 | 60 min |
| **Hora Loca Premium** | `SHOW` | S/. 1,200.00 | S/. 650.00 | 60 min |
| **Show Infantil Divertido** | `SHOW` | S/. 650.00 | S/. 350.00 | 90 min |
| **Paquete Baby Shower Especial** | `SHOW` | S/. 550.00 | S/. 300.00 | 90 min |
| **Servicio de DJ y Luces Pro** | `DJ` | S/. 600.00 | S/. 350.00 | 240 min |
| **Ambientación y Toldos Estándar** | `TENTS` | S/. 900.00 | S/. 450.00 | Jornada (480 min) |
| **Combo Full Fiesta (Hora Loca + DJ)** | `SHOW` | S/. 1,300.00 | S/. 700.00 | 240 min |

---

### 2.3 Catálogo de Temáticas (`themes`)
1. **Selva Salvaje (Safari)**: Diseñado para shows dinámicos con accesorios de safari y animales.
2. **Neón Glow / Fluorescente**: Show con luces ultravioleta, cotillón fluorescente y pintura facial neón.
3. **Retro 80s & 90s**: Música clásica bailable y vestimenta retro.
4. **Infantil Superhéroes / Cuentos**: Disfraces y dinámicas para público infantil.
5. **Elegance Black & Gold**: Temática sobria para 40 y 50 años o eventos corporativos.

---

### 2.4 Catálogo de Extras Llamativos (`extras`)
*Elementos personalizables clave del modelo de negocio de EventPro.*

| Nombre del Extra | Precio Venta (S/.) | Costo Fijo Elenco (S/.) | Descripción |
| :--- | :---: | :---: | :--- |
| **Muñeco Gorila Gigante** | S/. 250.00 | S/. 120.00 | Personaje inflable gigante estrella para el clímax de la Hora Loca. |
| **Robot LED con Pistola de CO2** | S/. 350.00 | S/. 180.00 | Personaje con iluminación LED y disparos de humo frío. |
| **Bailarín / Animador Adicional** | S/. 150.00 | S/. 90.00 | Personal extra para eventos con más de 100 invitados. |
| **Cañón de Confeti / Ventilación**| S/. 120.00 | S/. 50.00 | Explosión de papel picado metalizado. |
| **Hora Extra de DJ** | S/. 150.00 | S/. 80.00 | Extensión del servicio musical por hora adicional en vivo. |
| **Media Hora Extra de Espera/Show**| S/. 100.00 | S/. 60.00 | Retraso o extensión solicitada por el cliente in-situ. |

---

### 2.5 Inventario Inicial (`inventory_items`)
*Valores de arranque supuestos; el encargado debe ajustar el stock real antes de operar. Respaldan la verificación de disponibilidad de RF-09.*

| Nombre del Ítem | `service_category` | Stock total | Descripción |
| :--- | :---: | :---: | :--- |
| **Toldo Estándar 3x3 m** | `TENTS` | 10 | Estructura con cobertura para eventos en exteriores. |
| **Kit de Ambientación Estándar** | `DECORATION` | 6 | Telas, globos y elementos decorativos del paquete de ambientación. |

El paquete «Ambientación y Toldos Estándar» se siembra con dos filas en `package_inventory_items`: 1 unidad del «Toldo Estándar 3x3 m» y 1 unidad del «Kit de Ambientación Estándar» (`quantity = 1` en ambas). Los paquetes `SHOW` y `DJ` no tienen filas y, por tanto, no consumen inventario.

---

## 3. Script Idempotente de Sembrado (`seed.py`)

Se implementará un script ejecutable (`python -m app.infrastructure.adapters.secondary.persistence.seed`) que verifica la existencia de registros previos antes de insertar, permitiendo su ejecución segura en cualquier entorno sin duplicar datos.

---

## 4. Comando de Arranque del Usuario `SUPERADMIN`

Los roles se siembran, pero ningún usuario. El primer `SUPERADMIN` se crea con un comando explícito que lee sus credenciales desde variables de entorno, de modo que ninguna contraseña queda escrita en código, en el repositorio ni en los *seeds*:

```bash
SUPERADMIN_EMAIL=admin@eventpro.pe SUPERADMIN_PASSWORD='<contraseña-segura>' \
  python -m app.infrastructure.adapters.secondary.persistence.bootstrap_superadmin
```

| Variable | Obligatoria | Descripción |
| :--- | :---: | :--- |
| `SUPERADMIN_EMAIL` | SÍ | Correo de inicio de sesión del usuario `SUPERADMIN`. |
| `SUPERADMIN_PASSWORD` | SÍ | Contraseña inicial (mínimo 12 caracteres); se almacena como hash Argon2id en `users.hashed_password`. |

Reglas del comando:
1. **Idempotente:** si ya existe un usuario con `SUPERADMIN_EMAIL`, no hace nada y termina con código `0`.
2. **Falla cerrada:** si falta una variable, la contraseña es débil o el rol `SUPERADMIN` aún no fue sembrado, termina con código distinto de `0` sin crear nada.
3. **Valores por defecto:** `full_name = 'Super Administrador'` y `phone = '+51000000000'` (marcador de posición; el usuario lo edita después desde el panel, porque `users.phone` es obligatorio y único).
4. **Sin trazas sensibles:** nunca imprime ni registra la contraseña.
5. **Higiene operativa:** tras el primer arranque, retirar `SUPERADMIN_PASSWORD` del entorno y cambiar la contraseña desde el panel.
