# 08. Especificación: Contrato de Casos de Uso de Cotización de E1 (Bloque 4)

* **Estado:** Propuesto (pendiente de revisión).
* **Fecha:** 2026-10-20.
* **Épica:** E1 — Bot de WhatsApp, Cotizador y Bandeja de Conversaciones (dueño: Mathias).
* **Historias:** US-03, US-04, US-05, US-06, US-07, US-25 (casos de uso y endpoints; el flujo conversacional del bot queda con Mathias).
* **Requerimientos:** RF-05, RF-06, RF-07, RF-08, RF-09, RF-28, RN-01, RN-02, RN-03, RN-09.
* **Especificaciones relacionadas:** [06. Núcleo de Cotización](06-spec-e1-nucleo-cotizacion.md), [07. Cola de Mensajes Salientes](07-spec-e1-outbox-mensajeria.md), [División de épicas](../05-operaciones/04-division-de-epicas-del-equipo.md).

---

## 1. Objetivo y por qué contrato primero

Los bloques 1 a 3 de E1 (núcleo de cotización, cola de salida y gateway de Chatwoot) están en `develop`. Lo que falta de E1 es el **bot** y los **casos de uso del ciclo de vida de la cotización** con sus endpoints. Si Mathias construye todo en serie, E1 se convierte en el cuello de botella del proyecto.

Para evitarlo, el trabajo se reparte entre varias personas que avanzan **en paralelo** contra un **contrato** que Mathias fusiona primero. Es el mismo patrón que ya funcionó con `IMessagingPort` + `FakeMessagingAdapter` + `tests/infrastructure/messaging_port_contract.py`.

| Pieza del contrato | Para qué sirve |
| :--- | :--- |
| Puertos de entrada (`app/application/ports/input/`) | Fijan las firmas que consumen el bot y los routers. |
| DTOs (`app/application/dtos/`) | Fijan los datos de entrada y salida, alineados con la API REST. |
| Errores de dominio | Fijan qué errores debe poder tratar el bot y su mapeo HTTP. |
| Fakes configurables | Permiten al bot y al frontend avanzar sin las implementaciones reales. |
| Suite de contrato | Define "terminado": la misma suite pasa contra el fake y contra la implementación real. |
| Proveedores en `containers.py` | Hoy devuelven fakes; cada responsable cambia **una línea** por la real. |

### 1.1 Criterios de éxito

* El bot (Mathias) se escribe y se prueba solo contra los puertos, sin esperar a ninguna implementación real.
* Cada responsable entrega su pieza con la suite de contrato en verde contra su implementación.
* Integrar una pieza real es un cambio de una línea en `containers.py`; el bot no cambia.

### 1.2 Fuera de alcance

* El flujo conversacional del bot, el webhook, la bandeja y la conciliación (Mathias).
* Un cambio en el agregado `Quote`, salvo el campo `observations` (sección 3.2).
* Proveedor real de rutas: se mantiene `FakeRouteEstimatorAdapter` con contingencia por zona en esta fase.
* Resolver la regla de comprobante tardío (sección 6, pregunta 1) antes de que Christian la tome.

---

## 2. El contrato

### 2.1 Puertos de entrada

Siguen la convención vigente de `app/application/ports/input/`: clases `typing.Protocol`, nombre `I<Verbo><Sustantivo>Port`, un único método `async def execute(...)`, con docstring y sin cuerpo (como `IStartEventPort`).

| Archivo | Puerto | Responsable de la implementación real |
| :--- | :--- | :--- |
| `quote_create_port.py` | `ICreateQuotePort` | Brenis |
| `quote_read_port.py` | `IGetQuotePort`, `IListQuotesPort` | Brenis |
| `quote_expiry_port.py` | `IExpireDueQuotesPort` | Brenis |
| `quote_lifecycle_port.py` | `IPayAdvancePort`, `ICancelQuotePort` | Christian |
| `client_read_port.py` | `IFindClientsPort`, `IGetClientPort` | Nicolas |

```python
class ICreateQuotePort(Protocol):
    async def execute(self, dto: CreateQuoteInput) -> CreatedQuoteDTO:
        """Obtiene o crea el cliente, verifica disponibilidad y crea la cotización en SENT."""

class IGetQuotePort(Protocol):
    async def execute(self, quote_id: UUID) -> QuoteDetailDTO:
        """Detalle con desglose, extras congelados y pagos; lanza QuoteNotFoundError."""

class IListQuotesPort(Protocol):
    async def execute(self, filters: ListQuotesFilter) -> PageDTO[QuoteListItemDTO]:
        """Lista paginada con filtros; la más reciente primero."""

class IPayAdvancePort(Protocol):
    async def execute(self, quote_id: UUID) -> PayAdvanceResultDTO:
        """Revalida disponibilidad si corresponde y pasa a PAYMENT_STARTED (idempotente)."""

class ICancelQuotePort(Protocol):
    async def execute(self, quote_id: UUID, reason: str | None = None) -> CancelledQuoteDTO:
        """SENT o PAYMENT_STARTED pasa a CANCELLED; rechaza si hay un pago en verificación."""

class IExpireDueQuotesPort(Protocol):
    async def execute(self) -> int:
        """Vence las cotizaciones con plazo cumplido y devuelve cuántas venció (RN-09)."""

class IFindClientsPort(Protocol):
    async def execute(self, filters: FindClientsFilter) -> PageDTO[ClientDTO]:
        """Búsqueda paginada por texto (nombre o teléfono) o por teléfono exacto."""

class IGetClientPort(Protocol):
    async def execute(self, client_id: UUID) -> ClientDetailDTO:
        """Ficha del cliente con el resumen de sus cotizaciones; lanza ClientNotFoundError."""
```

> [!NOTE]
> El código de aplicación ya usa `IClockPort` para la hora actual; ningún puerto recibe `now`. Los fakes reciben el reloj por constructor, igual que `FakeMessagingAdapter`.

### 2.2 DTOs

Dataclasses inmutables (`@dataclass(frozen=True)`) en `app/application/dtos/`. Importes `Decimal` con dos decimales; fechas de ciclo de vida `datetime` con zona horaria UTC. `event_date` y `event_time` son la hora local del evento (sin zona), como en `Quote`.

**`page_dto.py`**

| DTO | Campos |
| :--- | :--- |
| `PageDTO[T]` | `items: tuple[T, ...]`, `page: int`, `page_size: int`, `total: int` |

**`quote_dto.py` — entradas**

| DTO | Campos | Reglas |
| :--- | :--- | :--- |
| `ClientInput` | `phone: str`, `full_name: str`, `dni: str \| None = None`, `ruc: str \| None = None` | El teléfono se normaliza con `PhoneNumber`; si el cliente existe no se sobrescribe su nombre. |
| `QuoteExtraInput` | `extra_id: UUID`, `quantity: int` | `quantity > 0`. |
| `CreateQuoteInput` | `package_id: UUID`, `event_date: date`, `event_time: time`, `location_address: str`, `location_district: str`, `client: ClientInput \| None = None`, `client_id: UUID \| None = None`, `theme_id: UUID \| None = None`, `extras: tuple[QuoteExtraInput, ...] = ()`, `client_provides_mobility: bool = False`, `latitude: Decimal \| None = None`, `longitude: Decimal \| None = None`, `observations: str \| None = None`, `source: QuoteSource = QuoteSource.WHATSAPP` | Exactamente uno entre `client` y `client_id`; si no, `ValidationError`. `source` solo admite `WHATSAPP` o `MANUAL`. |
| `ListQuotesFilter` | `status: QuoteStatus \| None = None`, `client_id: UUID \| None = None`, `from_date: date \| None = None`, `to_date: date \| None = None`, `page: int = 1`, `page_size: int = 20` | Filtra por `event_date`. `from_date > to_date`, `page < 1` o `page_size` fuera de 1 a 100: `ValidationError`. |

**`quote_dto.py` — salidas**

| DTO | Campos |
| :--- | :--- |
| `QuoteBreakdownDTO` | `services_balance_due`, `mobility_due` |
| `CreatedQuoteDTO` | `quote_id`, `client_id`, `source: QuoteSource`, `availability: AvailabilityStatus`, `services_subtotal`, `calculated_distance_km: Decimal \| None`, `calculated_transit_minutes: int \| None`, `final_mobility_amount`, `total_amount`, `advance_amount`, `pending_balance`, `breakdown: QuoteBreakdownDTO`, `status: QuoteStatus`, `sent_at`, `expires_at` |
| `ClientSummaryDTO` | `id`, `full_name`, `phone: str` |
| `QuoteListItemDTO` | `quote_id`, `client: ClientSummaryDTO`, `event_date`, `package_name`, `total_amount`, `status`, `expires_at` |
| `QuotePackageDTO` | `id`, `name`, `base_price` |
| `QuoteThemeDTO` | `id`, `name` |
| `QuoteExtraDetailDTO` | `extra_id`, `name`, `quantity`, `unit_price`, `subtotal` |
| `QuotePaymentDTO` | `payment_id`, `concept: PaymentConcept`, `validation_status: PaymentValidationStatus` |
| `QuoteDetailDTO` | `quote_id`, `client: ClientSummaryDTO`, `source`, `event_date`, `event_time`, `location_address`, `location_district`, `package: QuotePackageDTO`, `theme: QuoteThemeDTO \| None`, `extras: tuple[QuoteExtraDetailDTO, ...]`, `services_subtotal`, `final_mobility_amount`, `mobility_overridden: bool`, `total_amount`, `advance_amount`, `pending_balance`, `status`, `sent_at`, `expires_at`, `observations: str \| None`, `payments: tuple[QuotePaymentDTO, ...]`, `event_id: UUID \| None` |
| `WalletInstructionDTO` | `phone: str`, `holder: str` |
| `BankTransferInstructionDTO` | `bank`, `account`, `cci`, `holder` |
| `PaymentInstructionsDTO` | `yape: WalletInstructionDTO`, `plin: WalletInstructionDTO`, `bank_transfer: BankTransferInstructionDTO` |
| `PayAdvanceResultDTO` | `quote_id`, `status`, `availability: AvailabilityStatus`, `rechecked: bool`, `advance_amount`, `payment_deadline` (igual a `expires_at`), `payment_instructions: PaymentInstructionsDTO` |
| `CancelledQuoteDTO` | `quote_id`, `status` |

**`client_dto.py`**

| DTO | Campos |
| :--- | :--- |
| `FindClientsFilter` | `q: str \| None = None`, `phone: str \| None = None`, `page: int = 1`, `page_size: int = 20` |
| `ClientDTO` | `id`, `phone: str`, `full_name`, `dni: str \| None`, `ruc: str \| None`, `created_at` |
| `ClientQuoteSummaryDTO` | `quote_id`, `event_date`, `total_amount`, `status` |
| `ClientDetailDTO` | los campos de `ClientDTO` más `quotes: tuple[ClientQuoteSummaryDTO, ...]` |

Cada DTO de salida reproduce los nombres y los tipos del cuerpo de respuesta de [`01-especificacion-endpoints-rest.md`](../04-api/01-especificacion-endpoints-rest.md) (secciones 2.6 y 2.7), de modo que el router solo serializa.

> [!IMPORTANT]
> **`observations` es nuevo:** la API REST de `POST /quotes` y `GET /quotes/{id}` no lo incluye todavía. El contrato lo añade porque US-03 lo exige; el responsable de `CreateQuote` actualiza la especificación REST en su PR (sección 3.2).

### 2.3 Errores y su mapeo HTTP

Todos extienden `DomainError` y exponen `code`. Se reutilizan los existentes; los nuevos van en `app/domain/exceptions/quote_exceptions.py`.

| Error | `code` | HTTP | Origen | Estado |
| :--- | :--- | :---: | :--- | :--- |
| `AvailabilityConflictError` | `availability-conflict` | 409 | `CreateQuote`, `PayAdvance` | Nuevo |
| `SimultaneousThresholdExceededError` | `simultaneous-threshold-exceeded` | 409 | `CreateQuote`, `PayAdvance` | Nuevo |
| `QuoteExpiredError` | `quote-expired` | 410 | `PayAdvance` | Existe |
| `InvalidQuoteStateError` | `invalid-quote-state` | 409 | `PayAdvance`, `CancelQuote` | Existe |
| `QuoteNotFoundError` | `quote-not-found` (URL de error `not-found`) | 404 | `GetQuote`, `PayAdvance`, `CancelQuote` | Nuevo; subclase de `ResourceNotFoundError` |
| `ClientNotFoundError` | `client-not-found` (URL de error `not-found`) | 404 | `GetClient`, `CreateQuote` con `client_id` | Nuevo; subclase de `ResourceNotFoundError` |
| `ValidationError` | `validation-error` | 422 | todos | Existe |

Detalles de los errores nuevos:

* `AvailabilityConflictError` y `SimultaneousThresholdExceededError` comparten una base `AvailabilityRejectedError` con `alternatives: tuple[AvailabilityAlternative, ...]` (`event_date`, `event_time`) y `handoff_available: bool` (por defecto `True`). El bot ofrece las alternativas o deriva a un encargado. Equivalencia con `IAvailabilityPort`: `AvailabilityStatus.CONFLICT` produce `availability-conflict`; `REQUIRES_MANUAL_APPROVAL` produce `simultaneous-threshold-exceeded`.
* Los `*NotFoundError` heredan de `ResourceNotFoundError` para que el código existente que ya captura esa clase (por ejemplo, los routers actuales) siga funcionando; la URL del problema es `not-found`, como el resto de la API.
* `quote_error_to_problem` en `app/infrastructure/adapters/primary/web/problem.py` se amplía para cubrir **todos** los errores de la tabla. Los dos errores de disponibilidad añaden al problema las extensiones `alternatives` y `handoff_available`, con el formato del ejemplo de `POST /quotes/{id}/pay-advance`. Así los tres responsables de routers comparten un solo mapeo.

### 2.4 Regla de transacción

Los casos de uso del contrato **no hacen `commit`** y **no envían mensajes de WhatsApp**. El llamador es dueño de la transacción:

* **Router HTTP:** usa una sesión que confirma antes de responder, con el patrón de `get_catalog_write_session` (`session.begin()` y `Depends(..., scope="function")`), o `await session.commit()` explícito como en `budgets_router.py`.
* **Bot o tarea programada de arq:** abre su propia transacción con `get_sessionmaker()`, ejecuta el caso de uso y confirma.
* **Mensaje de la cotización (US-07):** lo encola el bot con `EnqueueMessage` **en la misma transacción** que `CreateQuote`. Si falla cualquiera de los dos, no queda ninguno. `CreateQuote` nunca llama a `IMessagingPort` ni a `EnqueueMessage`.

Esto coincide con la convención vigente: `IQuoteRepositoryPort` e `IClientRepositoryPort` no confirman, `EnqueueMessage` documenta "no hace `commit`" y `get_enqueue_message_use_case` comparte la sesión de la petición con los demás repositorios. No se encontró un conflicto; la única brecha es que fuera de HTTP no existe todavía un ayudante de transacción para el bot (sección 6, pregunta 5).

### 2.5 Fakes y escenarios

Un solo módulo: `app/infrastructure/adapters/secondary/external_services/fake_quote_use_cases.py`, junto a los demás fakes (`fake_messaging_adapter.py`, `fake_schedule_adapters.py`).

* `FakeQuoteStore`: almacén en memoria compartido (cotizaciones y clientes). Así `CreateQuote` seguido de `GetQuote`, `PayAdvance` o `GetClient` se comporta de forma coherente.
* `FakeCreateQuote`, `FakeGetQuote`, `FakeListQuotes`, `FakePayAdvance`, `FakeCancelQuote`, `FakeExpireDueQuotes`, `FakeFindClients`, `FakeGetClient`: reciben `store`, `clock` (`IClockPort`, con un reloj fijo por defecto) y exponen el atributo `scenario: FakeScenario`.
* **Deterministas:** los identificadores salen de un contador (`uuid5`), no de `uuid4`, y los importes de `CreateQuote` son siempre los del vector de la API (servicios 1000.00, movilidad 80.50, total 1080.50, adelanto 100.00, saldo 980.50); `expires_at = clock.utcnow() + 24 h`.
* **Escenario no aplicable:** pedir un escenario que el puerto no puede producir lanza `ValueError` (error de programación), nunca pasa en silencio.

| `FakeScenario` | Efecto | Puertos donde aplica |
| :--- | :--- | :--- |
| `OK` | Camino feliz con estado en memoria. | todos |
| `AVAILABILITY_CONFLICT` | Lanza `AvailabilityConflictError` con una alternativa y `handoff_available=True`. | `CreateQuote`, `PayAdvance` |
| `SIMULTANEOUS_THRESHOLD` | Lanza `SimultaneousThresholdExceededError` con las mismas extensiones. | `CreateQuote`, `PayAdvance` |
| `VALIDATION_ERROR` | Lanza `ValidationError`. | `CreateQuote`, `ListQuotes` |
| `QUOTE_NOT_FOUND` | Lanza `QuoteNotFoundError`. | `GetQuote`, `PayAdvance`, `CancelQuote` |
| `QUOTE_EXPIRED` | Lanza `QuoteExpiredError`. | `PayAdvance` |
| `INVALID_QUOTE_STATE` | Lanza `InvalidQuoteStateError`. | `PayAdvance`, `CancelQuote` |
| `PAYMENT_IN_VERIFICATION` | `CancelQuote` lanza `InvalidQuoteStateError`; `ExpireDueQuotes` omite la cotización y no la cuenta. | `CancelQuote`, `ExpireDueQuotes` |
| `CLIENT_NOT_FOUND` | Lanza `ClientNotFoundError`. | `GetClient`, `CreateQuote` con `client_id` |

Además, `FakeExpireDueQuotes` vence las cotizaciones del almacén cuyo plazo ya pasó (sin pago en verificación) y `due_count` suma cotizaciones adicionales "vencidas" que se consumen en la primera ejecución. `FakePayAdvance.rechecked` es `None` por defecto y entonces se deriva de la antigüedad de la cotización (más de 60 minutos desde `sent_at`, como `AVAILABILITY_RECHECK_MINUTES`); asignarle `True` o `False` fuerza el indicador.

### 2.6 Suite de contrato

Archivo: `tests/application/quote_ports_contract.py`. Una clase por puerto (`CreateQuoteContract`, `GetQuoteContract`, `ListQuotesContract`, `PayAdvanceContract`, `CancelQuoteContract`, `ExpireDueQuotesContract`, `FindClientsContract`, `GetClientContract`). Ninguna empieza por `Test`, así que pytest no las recolecta; funcionan igual que `MessagingPortContract`.

Cada clase abstracta define ganchos que la prueba concreta implementa:

| Gancho | Qué hace |
| :--- | :--- |
| `make_port()` | Devuelve el puerto bajo prueba (fake o implementación real). |
| `seed_quote(status, *, payment_in_verification=False, age=timedelta(0), client_id=None, event_date=None)` | Deja una cotización en el estado pedido (para el real, filas en una base de prueba) y devuelve su `id`. `age` es cuánto tiempo atrás se envió (con `age` de 25 horas el plazo de 24 horas ya venció; con 90 minutos ya pasó la ventana de revalidación); `client_id` y `event_date` fijan su cliente y su fecha de evento. |
| `seed_client(phone, full_name)` | Deja un cliente y devuelve su `id`. |
| `arrange(port, scenario)` | Configura el escenario: el fake asigna `scenario`; la implementación real prepara sus dobles (por ejemplo, un `IAvailabilityPort` que devuelve `CONFLICT`). |
| `quote_count()` | Cuántas cotizaciones existen; permite comprobar que un error no creó ninguna. |
| `assert_nothing_committed()` | Verifica que, tras ejecutar un caso de uso sin que el llamador confirme, otra sesión no ve cambios. El fake lo cumple por construcción; la implementación real lo prueba con una base de integración. |

Uso:

```python
# Fake (lo entrega el contrato)
class TestFakeCreateQuote(CreateQuoteContract):
    def make_port(self) -> ICreateQuotePort:
        return FakeCreateQuote(FakeQuoteStore())

# Implementación real (la entrega cada responsable, en su propio PR)
class TestCreateQuoteUseCase(CreateQuoteContract):
    def make_port(self) -> ICreateQuotePort:
        return CreateQuoteUseCase(...)
```

Casos mínimos por puerto:

| Puerto | Casos (el nombre completo vive en la suite) |
| :--- | :--- |
| `CreateQuote` | no confirma la transacción; resultado en `SENT` con `expires_at = sent_at + 24 h` con zona horaria UTC; `total = servicios + movilidad` y `pending_balance = total − adelanto`; cliente nuevo y cliente existente por teléfono no se duplica; `client` y `client_id` a la vez o ninguno: `ValidationError`; exención de movilidad: importe 0.00; `AVAILABILITY_CONFLICT` y `SIMULTANEOUS_THRESHOLD`: error con `alternatives` y `handoff_available`; no se crea la cotización cuando hay error; `CLIENT_NOT_FOUND` con `client_id` desconocido. |
| `GetQuote` | detalle coherente con lo creado; `QUOTE_NOT_FOUND`. |
| `ListQuotes` | filtros por `status`, `client_id`, `from_date`, `to_date`; paginación y `total`; `from_date > to_date`: `ValidationError`. |
| `PayAdvance` | no confirma la transacción; de `SENT` a `PAYMENT_STARTED` con instrucciones; segunda llamada idempotente; `rechecked` solo si pasaron más de `AVAILABILITY_RECHECK_MINUTES`; `AVAILABILITY_CONFLICT` y `SIMULTANEOUS_THRESHOLD` no revelan datos de pago y conservan estado y vencimiento; `QUOTE_EXPIRED`; `INVALID_QUOTE_STATE` desde `CONVERTED` y `CANCELLED`; `QUOTE_NOT_FOUND`. |
| `CancelQuote` | no confirma la transacción; desde `SENT` y desde `PAYMENT_STARTED`; con y sin motivo; cancelar una cotización ya cancelada no es idempotente (`InvalidQuoteStateError`); `PAYMENT_IN_VERIFICATION`, estados terminales y `QUOTE_NOT_FOUND`. |
| `ExpireDueQuotes` | devuelve el conteo; segunda ejecución devuelve 0 (idempotente); no vence una cotización con plazo vigente; `PAYMENT_IN_VERIFICATION` no se vence (RN-09). |
| `FindClients` | búsqueda por `q` (nombre y teléfono) y por `phone` exacto; paginación y `total`. |
| `GetClient` | ficha con el resumen de cotizaciones; `CLIENT_NOT_FOUND`. |

El fake ejecuta la suite completa en `tests/application/test_fake_quote_ports.py`; esa prueba es parte del contrato.

### 2.7 Proveedores en `containers.py`

Cada puerto tiene un proveedor con la anotación del **puerto**, nunca de la clase concreta:

| Proveedor | Devuelve hoy | Cambia |
| :--- | :--- | :--- |
| `get_create_quote_use_case() -> ICreateQuotePort` | `FakeCreateQuote` | Brenis |
| `get_quote_use_case() -> IGetQuotePort` | `FakeGetQuote` | Brenis |
| `get_list_quotes_use_case() -> IListQuotesPort` | `FakeListQuotes` | Brenis |
| `get_expire_due_quotes_use_case() -> IExpireDueQuotesPort` | `FakeExpireDueQuotes` | Brenis |
| `get_pay_advance_use_case() -> IPayAdvancePort` | `FakePayAdvance` | Christian |
| `get_cancel_quote_use_case() -> ICancelQuotePort` | `FakeCancelQuote` | Christian |
| `get_find_clients_use_case() -> IFindClientsPort` | `FakeFindClients` | Nicolas |
| `get_client_use_case() -> IGetClientPort` | `FakeGetClient` | Nicolas |

Todos comparten `get_fake_quote_store()` (con `lru_cache`, igual que los demás singletons). Los proveedores se agrupan en **bloques separados por responsable**, con un comentario de cabecera, para que los cambios de cada persona no choquen en el mismo fragmento del archivo.

---

## 3. División del trabajo

### 3.1 Resumen

| Persona | Entrega | Rama sugerida | Depende de |
| :--- | :--- | :--- | :--- |
| **Mathias** | PR del contrato (se fusiona **primero**), luego el bot, Chatwoot, bandeja, SSE y conciliación. | `feat/e1-quote-contract` | Nada |
| **Brenis** | `CreateQuote`, `GetQuote`, `ListQuotes`, `ExpireDueQuotes` + cron de arq, routers `/quotes`, migración 0006, migración del flujo manual, frontend de cotizaciones. | `feat/e1-quotes-core-usecases` | Contrato fusionado |
| **Christian** | `PayAdvance`, `CancelQuote`, routers `pay-advance` y `cancel`, decisión de comprobante tardío. | `feat/e1-quotes-pay-cancel` | Contrato fusionado; coordinar con Brenis (repositorio de `Quote`) |
| **Nicolas** | `FindClients`, `GetClient`, routers `/clients`, frontend de clientes. | `feat/e1-clients-read` | Contrato fusionado |
| **Diego, Renzo** | Sin carga en este bloque (contratos/PAdES y E4 pendientes). | — | — |

> [!NOTE]
> La épica E3 figura en el documento de épicas con dueño "David", mientras que el autor de git del catálogo, la disponibilidad y el flujo manual es "Brenis". Este documento usa los nombres de git y **no afirma** que sean la misma persona.

Cada responsable trabaja en **una sola rama** desde `develop`; los commits van en esa rama sin crear ramas por tarea.

### 3.2 Brenis — núcleo de cotización

| Aspecto | Detalle |
| :--- | :--- |
| Alcance | `CreateQuote`, `GetQuote`, `ListQuotes`, `ExpireDueQuotes` reales; cron de arq cada minuto; routers; migración 0006; migración del flujo manual; frontend. |
| Historias y reglas | US-03 (observaciones), US-04, US-05, US-06, US-07 (cálculo y vencimiento); RF-05 a RF-09; RN-01, RN-02, RN-03, RN-09. |
| Archivos nuevos | `app/application/use_cases/quote/create_quote.py`, `get_quote.py`, `list_quotes.py`, `expire_due_quotes.py`; `app/infrastructure/adapters/primary/web/v1/quotes_router.py` (`POST /quotes`, `GET /quotes`, `GET /quotes/{id}`); tarea de arq en el módulo del worker; `alembic/versions/0006_quote_observations.py`. |
| Archivos modificados | `app/domain/entities/quote.py` (campo `observations`), `quote_mapper.py`, `QuoteModel`; `IQuoteRepositoryPort` y `SqlAlchemyQuoteRepository` (listar con filtros, buscar vencibles, resumen por cliente); `manual_booking_repository.py` y `PrepareBudgetUseCase`; `containers.py` (sus proveedores); `app/main.py` (registro del router); esta especificación y `01-especificacion-endpoints-rest.md` (`observations`). |
| Endpoints | `POST /quotes`, `GET /quotes`, `GET /quotes/{id}` (ENCARGADO o SUPERADMIN). |
| Pendientes del flujo manual | Reemplazar el SQL crudo de `quotes` y `clients` por los repositorios; `pending_balance = total − adelanto` (corrige la omisión de la movilidad, RN-02); `Quote.create(source=QuoteSource.MANUAL)` seguido de `start_payment()`. Ver [spec 06, sección 5.1](06-spec-e1-nucleo-cotizacion.md). |
| Criterios de aceptación | Las clases `CreateQuoteContract`, `GetQuoteContract`, `ListQuotesContract` y `ExpireDueQuotesContract` pasan contra la implementación real; `observations` se guarda y se devuelve; una cotización con pago en verificación no vence; el cron corre cada minuto; el flujo manual produce el mismo `Quote` que el bot y su `pending_balance` incluye la movilidad; `ruff`, `mypy` y `pytest` en verde. |
| Dependencias | Contrato fusionado; `IAvailabilityPort` y `ICatalogReadPort` ya existen (E3). |
| Frontend | `pages/quotes` con filtros y estados, detalle de cotización, entidad `entities/quote`; consume `GET /quotes` y `GET /quotes/{id}` (mocks de la API mientras no estén). |

**Dos decisiones propias del `CreateQuote` real:**

* **Duración:** la API no recibe duración. Se obtiene del paquete (`PackageReadDTO.duration_minutes`) y se usa en `AvailabilityRequest`. El contrato **no** la incluye en `CreateQuoteInput` para no duplicar el dato del catálogo.
* **Observaciones (US-03):** la tabla `quotes` no tiene la columna. La migración 0006 agrega `observations TEXT NULL`. Esto es un cambio al agregado `Quote`: se avisa al equipo en el PR, como exige la [regla de épicas](../05-operaciones/04-division-de-epicas-del-equipo.md). Antes de generar la migración se hace *rebase* sobre `develop` y debe quedar un solo `head`.

### 3.3 Christian — avance y cancelación

| Aspecto | Detalle |
| :--- | :--- |
| Alcance | `PayAdvance` y `CancelQuote` reales; sus dos routers; decisión de comprobante tardío. |
| Historias y reglas | US-07 (botón «Pagar adelanto» y revalidación); RF-09, RF-11; RN-09. |
| Archivos nuevos | `app/application/use_cases/quote/pay_advance.py`, `cancel_quote.py`; `app/infrastructure/adapters/primary/web/v1/quote_lifecycle_router.py` (`POST /quotes/{id}/pay-advance` y `/cancel`). |
| Archivos modificados | `app/core/config.py` (`AVAILABILITY_RECHECK_MINUTES`, datos de pago de Yape, Plin y cuenta bancaria; revisión de Diego por ser zona compartida) y `.env.example`; `containers.py` (sus proveedores); [spec 06](06-spec-e1-nucleo-cotizacion.md) y [RN](../01-requisitos/04-reglas-de-negocio-y-control.md) con la decisión de la sección 6, pregunta 1; `app/main.py`. |
| Endpoints | `POST /quotes/{id}/pay-advance`, `POST /quotes/{id}/cancel` (ENCARGADO o SUPERADMIN). |
| Criterios de aceptación | `PayAdvanceContract` y `CancelQuoteContract` pasan contra la implementación real; si pasaron más de `AVAILABILITY_RECHECK_MINUTES` desde `sent_at` se revalida con `IAvailabilityPort.check_availability` y, sin cupo, no se revelan datos de pago y la cotización conserva estado y vencimiento; la llamada repetida es idempotente; cancelar con un pago en `PENDING_VERIFICATION` o `REQUIRES_MANUAL_APPROVAL` responde `409 invalid-quote-state`; la decisión de comprobante tardío queda documentada. |
| Dependencias | Contrato fusionado; repositorios de `Quote` y de pagos existentes; coordinar con Brenis si necesita métodos nuevos en `IQuoteRepositoryPort` (un solo PR toca ese puerto a la vez). |
| Frontend | Ninguno obligatorio en este bloque. Si el detalle de cotización de Brenis expone las acciones «Cancelar» y «Pagar adelanto», las llama con la API. |

### 3.4 Nicolas — clientes

| Aspecto | Detalle |
| :--- | :--- |
| Alcance | `FindClients` y `GetClient` reales; routers; frontend. |
| Historias y reglas | US-25; RF-28. |
| Archivos nuevos | `app/application/use_cases/clients/find_clients.py`, `get_client.py`; `app/infrastructure/adapters/primary/web/v1/clients_router.py` (`GET /clients`, `GET /clients/{id}`). |
| Archivos modificados | `IClientRepositoryPort` y `SqlAlchemyClientRepository` (búsqueda paginada y listado de cotizaciones del cliente); `containers.py` (sus proveedores); `app/main.py`. |
| Endpoints | `GET /clients`, `GET /clients/{id}` (solo ENCARGADO o SUPERADMIN; `OPERADOR` recibe `403`, por ser datos personales). |
| Criterios de aceptación | `FindClientsContract` y `GetClientContract` pasan contra la implementación real; búsqueda por nombre (parcial) o por teléfono en cualquier formato aceptado por `PhoneNumber`; la ficha incluye el resumen de cotizaciones; `OPERADOR` recibe `403`; sin endpoint de alta. |
| Dependencias | Contrato fusionado; las cotizaciones de los clientes provienen de `quotes` (lectura). |
| Frontend | `pages/clients` con búsqueda y paginación, ficha del cliente con su historial; `entities/client`. Mocks de la API hasta que el router exista. |

### 3.5 Mathias — contrato y bot

| Aspecto | Detalle |
| :--- | :--- |
| Alcance | Este contrato (paso 0) y después el bot, el webhook, la bandeja, el SSE y la conciliación. |
| Rol sobre el contrato | Revisa **todo** PR que lo cambie. Nadie modifica puertos, DTOs, errores, fakes ni la suite sin su revisión. |
| Rol en el bot | Consume los puertos con los fakes; encola el resumen de US-07 con `EnqueueMessage` en la misma transacción que `CreateQuote`; reacciona a cada error de la sección 2.3 (ofrecer alternativas, derivar a un encargado, informar vencimiento). |

---

## 4. Pasos de integración

1. Mathias fusiona el PR del contrato en `develop`.
2. Cada responsable crea su rama desde `develop` y trabaja **contra el contrato**: escribe primero la prueba concreta que hereda de su clase de contrato y la ve fallar.
3. Implementa el caso de uso real y su router; la suite de contrato pasa contra la implementación real.
4. En el **mismo PR** cambia su(s) línea(s) en `containers.py` de `Fake...` a la implementación real. El bot no cambia.
5. Ejecuta las puertas de calidad (sección 5) y pide revisión de al menos una persona de otra épica.
6. El PR se fusiona; el bot de Mathias empieza a usar la pieza real sin tocar su código.

---

## 5. Reglas

| Tema | Regla |
| :--- | :--- |
| Cambios al contrato | Ningún cambio sin un PR revisado por Mathias. |
| Orden | El contrato se fusiona antes de que cualquiera empiece. |
| Definición de terminado (por pieza) | Pasa la suite de contrato compartida contra la implementación real, más `ruff check .`, `ruff format --check .`, `mypy app` y `pytest -q --cov=app --cov-fail-under=75`. |
| Integración | Se cambia la línea del proveedor en `containers.py` en el mismo PR. |
| Ramas | Una por responsable, desde `develop`, con prefijo `feat/`. |
| Migraciones | *Rebase* sobre `develop` antes de generar; un solo `head`. La 0006 es de Brenis. |
| Transacción | Los casos de uso no confirman ni envían mensajes (sección 2.4). |
| Zonas compartidas | `app/core/` se modifica con revisión de Diego. |
| Idioma | Documentación en español neutro profesional; identificadores y código en inglés. |

---

## 6. Preguntas abiertas

1. **Comprobante tardío aprobado (spec 06, sección 5, punto 1):** un comprobante recibido tras el vencimiento entra en `REQUIRES_MANUAL_APPROVAL` (RF-11). Si el encargado lo aprueba, ¿la cotización pasa de `EXPIRED` a `CONVERTED`? Hoy `Quote` no lo permite (`convert()` solo desde `PAYMENT_STARTED`). Responsable: Christian; hasta resolverlo, el cron de vencimiento y `PayAdvance` conservan el comportamiento actual.
2. **Observaciones hacia el evento y el contrato:** la columna nueva vive en `quotes`, pero el evento ya tiene `client_observations` (visible en el cronograma) y RF-14 exige que pasen al contrato. Hace falta definir quién copia `quotes.observations` a `events.client_observations` al crear el evento, y quién las incluye en el PDF del contrato. Afecta a E2 (Diego) y E6 (Nicolas); no bloquea el contrato.
3. **Valor de `source` desde el bot:** el pedido original mencionaba `BOT`, pero el enumerado `QuoteSource` y la API usan `WHATSAPP` (y `MANUAL` solo para `POST /contracts/manual`). El contrato conserva `WHATSAPP`; si se quiere renombrar, es un cambio de dominio, de esquema y de API.
4. **Auditoría de cancelaciones y creaciones manuales:** los puertos no reciben `actor`. Si el negocio exige registrar en `audit_logs` quién canceló o creó una cotización desde el panel, hay que agregar `actor` a los puertos ahora, porque después sería un cambio de contrato.
5. **Transacción fuera de HTTP:** el bot y el cron necesitan un ayudante de unidad de trabajo (abrir sesión, ejecutar, confirmar). Mathias lo define con el bot; Brenis lo reutiliza o define uno mínimo para el cron.
6. **Configuración ausente:** `AVAILABILITY_RECHECK_MINUTES` y los datos de pago (Yape, Plin, banco) no existen en `app/core/config.py`. Los agrega Christian; falta confirmar con el negocio los datos reales y dónde se guardan (entorno o tabla de configuración).
7. **Fakes en producción:** mientras una pieza no tenga implementación real, su proveedor devuelve un fake. ¿Se agrega una guarda que impida arrancar en `staging` o `production` con fakes de cotización, como ya ocurre con Chatwoot?
8. **Numeración de la spec 06:** el punto "Comprobante tardío" es el punto 1 de la sección 5, y la acción del flujo manual es la sección 5.1. Se citan así en este documento para evitar ambigüedad.

---

## 7. Impacto en la documentación

| Documento | Cambio |
| :--- | :--- |
| `05-operaciones/04-division-de-epicas-del-equipo.md` | Nota en E1 y menciones en E3, E5 y E6 sobre las piezas delegadas según esta especificación. |
| `04-api/01-especificacion-endpoints-rest.md` | Campo `observations` en `POST /quotes` y `GET /quotes/{id}` (lo hace Brenis en su PR). |
| `01-requisitos/04-reglas-de-negocio-y-control.md` | Resolución de la regla de comprobante tardío (lo hace Christian). |
| `README.md` de `Docs/` | Enlace a esta especificación. |
