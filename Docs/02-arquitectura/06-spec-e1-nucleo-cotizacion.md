# 06. Especificación: Núcleo de Cotización de E1 (Bloque 1)

* **Estado:** Propuesto (pendiente de revisión).
* **Fecha:** 2026-10-07.
* **Épica:** E1 — Bot de WhatsApp, Cotizador y Bandeja de Conversaciones (dueño: Mathias).
* **Historias cubiertas (parcialmente, capa de dominio y persistencia):** US-04, US-05, US-06, US-25 (identidad de cliente).
* **Requerimientos:** RF-05, RF-06, RF-07, RN-01, RN-02, RN-03, RN-09, RNF-04.2.

---

## 1. Contexto y objetivo

E1 es demasiado grande para un solo ciclo de diseño. Se divide en bloques; este es el **Bloque 1: núcleo de dominio y persistencia**. Su objetivo es que el resto del equipo deje de depender de implementaciones propias de la cotización:

1. **Flujo manual (PR #22, ya en `develop`):** escribe la tabla `quotes` con SQL crudo y estados literales. Con este bloque podrá usar el agregado `Quote`, el `FinancialEngine` y los repositorios de E1, dejando a E1 como único dueño de `quotes`.
2. **E2 (contratos, OTP) y E5 (avisos de pago):** necesitan enviar mensajes por WhatsApp. Con el puerto `IMessagingPort` y su adaptador falso pueden integrar y probar sin esperar a Meta ni a Chatwoot.

### 1.1 Criterios de éxito

* El agregado `Quote` aplica la máquina de estados documentada (RN §3.1) y rechaza transiciones inválidas con errores de dominio tipados.
* El `FinancialEngine` reproduce los vectores de US-06 y del ejemplo de la API, con **100 % de cobertura** (RNF-04.2).
* `Quote` y `Client` se persisten sobre el esquema existente sin migración nueva.
* `IMessagingPort` está publicado con un adaptador falso utilizable en pruebas y en desarrollo.

### 1.2 Fuera de alcance

* Cola `outbox_messages` y su worker (arq).
* Webhook de Chatwoot, flujo conversacional del bot y `ChatwootMessagingAdapter`.
* Endpoints `/quotes`, `/clients` y `/conversations`.
* Adaptador real de Google Maps (o alternativa). El bloque solo publica el puerto y un adaptador falso.
* Casos de uso que coordinan cotización y pagos (cancelar, vencer, pagar adelanto); se implementan en bloques posteriores sobre este núcleo.
* Migración del flujo manual (PR #22) al nuevo núcleo; la realiza su autor en un PR posterior.
* Frontend.

---

## 2. Decisiones de negocio

### 2.1 Tarifa de movilidad (RN-03)

La documentación define `Costo Movilidad = Movilidad Base × 1.15` con `Movilidad Base = f(D, T)` (ida y vuelta), pero no define la función `f`. Se adopta:

* **Cálculo principal (escenario A):** `Movilidad Base = max(D × tarifa_km + T × tarifa_minuto, monto_mínimo)`.
* **Contingencia (escenario C):** si el estimador de rutas falla, se aplica un monto fijo por **zona** del distrito del evento. El monto de la zona ya es final (no se le aplica el margen).

Valores iniciales, configurables por variables de entorno y **registrados como supuestos pendientes de validación con el negocio**:

| Variable | Valor inicial |
| :--- | :--- |
| `MOBILITY_RATE_PER_KM` | `1.00` |
| `MOBILITY_RATE_PER_MINUTE` | `0.30` |
| `MOBILITY_MINIMUM_AMOUNT` | `20.00` |
| `MOBILITY_MARGIN_PERCENT` | `15` |
| `MOBILITY_ZONE_1_AMOUNT` | `25.00` |
| `MOBILITY_ZONE_2_AMOUNT` | `45.00` |
| `MOBILITY_ZONE_3_AMOUNT` | `70.00` |
| `ADVANCE_PERCENT` | `10` (ya existe) |
| `ADVANCE_DEADLINE_HOURS` | `24` |

La tabla de distritos por zona (Lima Metropolitana y Callao) vive en infraestructura. Un distrito desconocido se asigna a la **zona 3** para no cobrar de menos; el encargado puede corregirlo con el *override* de movilidad (E4).

RN-03 en [`01-requisitos/04-reglas-de-negocio-y-control.md`](../01-requisitos/04-reglas-de-negocio-y-control.md) se actualiza con esta fórmula, los valores y la nota de supuesto.

### 2.2 Integración con Google Maps

La documentación prevé Google Maps Platform (Distance Matrix / Directions). Como su habilitación (cuenta con facturación) no está confirmada, el bloque define el puerto `IRouteEstimatorPort` con un adaptador falso. El adaptador real (Google u otro proveedor) se decide en el bloque del bot; el dominio no cambia.

---

## 3. Diseño

### 3.1 Componentes

**Dominio (`app/domain/`)** — sin dependencias de FastAPI, SQLAlchemy ni clientes externos.

| Archivo | Contenido |
| :--- | :--- |
| `entities/quote.py` | Agregado `Quote`, `QuoteStatus` y `QuoteSource` (`StrEnum`), línea `QuoteExtraLine`. |
| `entities/client.py` | Entidad `Client` (teléfono, nombre, DNI y RUC opcionales). |
| `value_objects/phone_number.py` | `PhoneNumber`: normalización a E.164 peruano. |
| `value_objects/liquidation.py` | `Liquidation`: resultado inmutable de la liquidación. |
| `value_objects/mobility.py` | `MobilityTariff`, `RouteEstimate`, `MobilityResult` y `MobilityZone`. |
| `services/financial_engine.py` | `FinancialEngine`: cálculo de movilidad y liquidación (funciones puras). |
| `exceptions/quote_exceptions.py` | `InvalidQuoteStateError` (`invalid-quote-state`) y `QuoteExpiredError` (`quote-expired`). |

**Aplicación (`app/application/ports/output/`)** — puertos con `typing.Protocol`, siguiendo la convención vigente del código.

| Archivo | Contenido |
| :--- | :--- |
| `quote_repository_port.py` | `IQuoteRepositoryPort`: `add`, `save`, `get_by_id`. |
| `client_repository_port.py` | `IClientRepositoryPort`: `get_by_id`, `get_by_phone`, `get_or_create`. |
| `route_estimator_port.py` | `IRouteEstimatorPort.estimate(origin, destination) -> RouteEstimate`; lanza `RouteEstimationError`. |
| `messaging_port.py` | `IMessagingPort` (sección 3.5). |

**Infraestructura (`app/infrastructure/`)**

* Modelos ORM `ClientModel`, `QuoteModel` y `QuoteExtraModel`, fieles a `0001_initial_schema` y `0003_manual_booking_documents` (incluida `quotes.manual_request_hash`), con los mismos nombres de `CHECK` e índices.
* Mappers `client_mapper.py` y `quote_mapper.py`.
* Repositorios `SqlAlchemyClientRepository` y `SqlAlchemyQuoteRepository`.
* `FakeRouteEstimatorAdapter` y `FakeMessagingAdapter` en `adapters/secondary/external_services/`.
* Tabla de zonas por distrito.
* Nuevos campos en `app/core/config.py` (sección 2.1) y cableado en `app/infrastructure/di/containers.py`.

**Sin migración nueva:** las tablas `clients`, `quotes` y `quote_extras` ya existen.

### 3.2 Ciclo de vida de `Quote`

Todas las fechas son *timezone-aware* en UTC.

| Operación | Transición | Reglas |
| :--- | :--- | :--- |
| `Quote.create(..., now, deadline_hours)` | nace en `SENT` | `sent_at = now`; `expires_at = now + deadline_hours`. La liquidación se congela al crear. |
| `start_payment(now)` | `SENT → PAYMENT_STARTED` | Idempotente si ya está en `PAYMENT_STARTED`. Si `now ≥ expires_at` o el estado es `EXPIRED`: `QuoteExpiredError`. Desde `CONVERTED` o `CANCELLED`: `InvalidQuoteStateError`. |
| `convert()` | `PAYMENT_STARTED → CONVERTED` | Solo desde `PAYMENT_STARTED`. |
| `expire(now)` | `SENT` o `PAYMENT_STARTED → EXPIRED` | Solo si `now ≥ expires_at`. |
| `cancel(reason)` | `SENT` o `PAYMENT_STARTED → CANCELLED` | `reason` opcional. |

`CONVERTED`, `EXPIRED` y `CANCELLED` son terminales.

**Cotizaciones manuales:** se crean con `source = MANUAL` y a continuación llaman a `start_payment()`, quedando en `PAYMENT_STARTED`, el mismo estado que produce hoy el flujo manual.

**Reglas que dependen de pagos** (no cancelar ni vencer con un pago en `PENDING_VERIFICATION` o `REQUIRES_MANUAL_APPROVAL`; revalidar disponibilidad antes de revelar los datos de pago) se aplican en los casos de uso de bloques posteriores. El agregado `Quote` no conoce a `Payment`.

### 3.3 `FinancialEngine`

Funciones puras y deterministas. Todo importe es `Money` (cuantizado a 0.01 con `ROUND_HALF_UP`).

```
movilidad_base  = max(D × tarifa_km + T × tarifa_minuto, monto_mínimo)
movilidad_final = movilidad_base × (1 + margen / 100)
servicios       = precio_paquete + Σ (precio_unitario_extra × cantidad)
total           = servicios + movilidad_final
adelanto        = servicios × ADVANCE_PERCENT / 100      (sin movilidad, RN-01)
saldo           = total − adelanto                       (90 % servicios + 100 % movilidad)
desglose_saldo  = { servicios: servicios − adelanto, movilidad: movilidad_final }
```

Validaciones: precio del paquete `> 0`; extras `≥ 0`; cantidad `> 0`; km y minutos `≥ 0`.

**Resolución de la movilidad (`resolve_mobility`):**

1. El cliente provee transporte → `0.00` (RF-06); km y minutos en `NULL`.
2. El estimador responde → escenario A; se registran km, minutos, movilidad base y final.
3. El estimador falla → escenario C con el monto de la zona; km y minutos en `NULL` (marca de contingencia); movilidad base igual a la final.
4. Distrito desconocido → zona 3.

### 3.4 Persistencia

* `SqlAlchemyQuoteRepository` persiste `Quote` junto con sus filas de `quote_extras` y **no hace `commit`**: la transacción pertenece al caso de uso o a la sesión por petición (criterio alineado con ADR-11).
* `SqlAlchemyClientRepository.get_or_create(phone, full_name)` normaliza el teléfono con `PhoneNumber` y **no sobrescribe el nombre** de un cliente existente.
* `PhoneNumber` es la única fuente de la regla de normalización: 9 dígitos → `+51` + dígitos; `51…` y `+51…` → `+51…`. Es la misma regla que aplica hoy el esquema web del flujo manual, que debe pasar a reutilizarla.

### 3.5 `IMessagingPort`

Contrato alineado con la [especificación del gateway](05-spec-chatwoot-gateway.md):

```python
async def send_text(to: PhoneNumber, body: str) -> MessageReceipt
async def send_interactive_list(to: PhoneNumber, body: str, sections: Sequence[ListSection]) -> MessageReceipt
async def send_template(to: PhoneNumber, name: str, params: Mapping[str, str]) -> MessageReceipt
async def send_attachment(to: PhoneNumber, data: bytes, filename: str, content_type: str, caption: str | None) -> MessageReceipt
async def set_conversation_status(conversation_id: int, status: ConversationStatus) -> None  # BOT | HUMAN
async def list_conversations(...) -> Sequence[ConversationSummary]
async def list_messages(conversation_id: int, ...) -> Sequence[ConversationMessage]
```

Errores del puerto:

* `ServiceWindowClosedError` (`service-window-closed`, RN-11): fuera de la ventana de 24 h solo se admiten plantillas.
* `MessagingUnavailableError`: el gateway no responde. El reintento lo asumirá la cola `outbox_messages` en un bloque posterior.

`FakeMessagingAdapter`: registra en memoria los mensajes enviados para aserciones, permite simular ventana cerrada o gateway caído, y en desarrollo escribe cada mensaje en el log estructurado en lugar de enviarlo.

> [!NOTE]
> En producción, E2 y E5 deben **encolar** en `outbox_messages` en lugar de invocar el puerto directamente. Mientras la cola no exista, usan el puerto con el adaptador falso; el paso a la cola no cambia la firma de los mensajes.

### 3.6 Errores de dominio y su mapeo HTTP

| Error | Código | HTTP |
| :--- | :--- | :--- |
| `InvalidQuoteStateError` | `invalid-quote-state` | 409 |
| `QuoteExpiredError` | `quote-expired` | 410 |
| `ValidationError` | `validation-error` | 422 |
| `RouteEstimationError` | — (no sale del caso de uso: activa la contingencia) | — |

---

## 4. Pruebas

Se aplica **TDD** (rojo → verde → refactor) en el dominio y en el `FinancialEngine`.

| Nivel | Ubicación | Casos |
| :--- | :--- | :--- |
| Dominio | `tests/domain/` | Todas las transiciones válidas e inválidas de `Quote`; vencimiento en el límite exacto de `expires_at`; idempotencia de `start_payment`; `PhoneNumber` con 9 dígitos, `51…` y `+51…`; DNI y RUC de `Client`. |
| `FinancialEngine` | `tests/domain/` | **100 % de cobertura.** Vector US-06 (1000 + 200, movilidad 100 → total 1300.00, adelanto 120.00, saldo 1180.00); vector de la API (1000, movilidad 80.50 → total 1080.50, adelanto 100.00, saldo 980.50); mínimo de movilidad; redondeo `HALF_UP`; exención; contingencia por zona; distrito desconocido. |
| Integración | `tests/integration/` (Postgres real con Testcontainers) | Guardar y recuperar `Quote` con extras; el repositorio no hace `commit`; `get_or_create` no duplica clientes con formatos de teléfono distintos ni sobrescribe el nombre. |
| Contrato | `tests/infrastructure/` | Suite de contrato de `IMessagingPort` que ejecuta el adaptador falso y que deberá pasar el adaptador real de Chatwoot. |

Puertas de calidad: `ruff check`, `ruff format --check`, `mypy --strict` y cobertura global ≥ 75 %.

---

## 5. Pendientes abiertos

1. **Comprobante tardío aprobado:** un comprobante recibido después del vencimiento entra en `REQUIRES_MANUAL_APPROVAL` (RF-11). La documentación no define si, al aprobarse, la cotización pasa de `EXPIRED` a `CONVERTED`. En este bloque **no se permite** esa transición; debe resolverse con E5 antes de implementar la aprobación de comprobantes tardíos.
2. **Valores de tarifa de movilidad y montos por zona:** supuestos iniciales (sección 2.1) a validar con el negocio.
3. **Proveedor de rutas:** Google Maps Platform u alternativa; se decide en el bloque del bot.
4. **Migración del flujo manual (PR #22):** reemplazar su SQL crudo sobre `quotes` y `clients` por los repositorios de este bloque, y corregir su `pending_balance`, que hoy omite la movilidad (contradice RN-02 cuando la movilidad es distinta de cero). Detalle en la sección 5.1.

### 5.1 Acción para el flujo manual (responsable: autor del PR #22)

El flujo administrativo manual ([`04-api/03-flujo-manual-entregable.md`](../04-api/03-flujo-manual-entregable.md)) se implementó antes de este núcleo. Para que E1 sea el único dueño de `quotes` y `clients`, debe migrarse en un PR propio:

| Hoy en el flujo manual | Reemplazo en este núcleo |
| :--- | :--- |
| `INSERT`/`UPDATE` crudos sobre `quotes` con estados literales (`'PAYMENT_STARTED'`, `'CONVERTED'`, `'CANCELLED'`) | `Quote.create(..., source=QuoteSource.MANUAL)` + `start_payment()`, `convert()`, `cancel()`; persistencia con `IQuoteRepositoryPort` (`SqlAlchemyQuoteRepository`, que no hace `commit`) |
| `INSERT ... ON CONFLICT (phone)` sobre `clients` | `IClientRepositoryPort.get_or_create(phone, full_name)` (misma regla: normaliza el teléfono y no sobrescribe el nombre) |
| `PrepareBudgetUseCase`: subtotal, adelanto y saldo calculados a mano | `FinancialEngine.liquidate(...)` con `resolve_mobility(...)`; el monto manual de movilidad puede seguir como *override* auditado |
| `pending_balance = servicios − adelanto` (sin movilidad) | `pending_balance = total − adelanto` (90 % servicios + 100 % movilidad, RN-02) |

Mientras no se migre, las filas existentes con `source = 'MANUAL'` se cargan tal como están guardadas: el mapper de E1 **no recalcula** `pending_balance`. El esquema web del flujo manual ya reutiliza `PhoneNumber`, que además trata el prefijo `00` como prefijo internacional (`0051999999999` → `+51999999999`) y responde 422 ante `+0…`.

---

## 6. Impacto en la documentación

| Documento | Cambio |
| :--- | :--- |
| `01-requisitos/04-reglas-de-negocio-y-control.md` | RN-03: fórmula de `f(D, T)`, contingencia por zona y valores como supuestos. |
| `05-operaciones/01-guia-entorno-y-configuracion.md` | Nuevas variables de movilidad y zonas. |
| `02-arquitectura/02-backend-arquitectura-hexagonal.md` | `IRouteEstimatorPort` y `FinancialEngine` en el árbol de módulos. |
| `README.md` de `Docs/` | Enlace a esta especificación. |
