# 02. Arquitectura Hexagonal en el Backend (FastAPI)

---

## 1. Fundamentos y Principios Rectores

La arquitectura del backend de **EventPro** adopta el patrón de **Arquitectura Hexagonal (Puertos y Adaptadores)** formulado por Alistair Cockburn. Su propósito fundamental es desacoplar las reglas de negocio de la infraestructura tecnológica, permitiendo que el núcleo del sistema sea:

1. **Independiente del Framework:** Las entidades y casos de uso no importan ni conocen a FastAPI, SQLAlchemy ni librerías de terceros. FastAPI es un adaptador de entrada; la lógica reside en el núcleo.
2. **Altamente Testeable:** El 100% de la lógica de cotizaciones, validaciones de adelantos y umbrales de shows se puede probar de forma unitaria con mocks o stubs en memoria sin levantar bases de datos ni servidores web.
3. **Sustituible en Infraestructura:** Cambiar PostgreSQL por MySQL, o cambiar el proveedor de envío de WhatsApp no altera una sola línea del dominio ni de los casos de uso.
4. **Regla de Dependencia Inviolable:** Las dependencias del código fuente apuntan **únicamente hacia adentro**, hacia el Dominio:
   $$\text{Infraestructura (Adaptadores)} \longrightarrow \text{Aplicación (Casos de Uso / Puertos)} \longrightarrow \text{Dominio (Entidades / Value Objects)}$$

---

## 2. Estructura de Directorios del Backend

La estructura del código en Python se organiza de acuerdo a las capas hexagonales:

```text
app/
├── core/                                 # Configuración global agnóstica de la app
│   ├── config.py                         # Settings con Pydantic-settings (.env)
│   ├── logging.py                        # Configuración de logging estructurado
│   └── security.py                       # Hashing (Argon2id/Bcrypt), tokens JWT
│
├── domain/                               # CAPA 1: NÚCLEO DE DOMINIO (Zero dependencias externas)
│   ├── entities/                         # Modelos puros de dominio (clases Python / dataclasses)
│   │   ├── event.py                      # Entidad Evento con su ciclo de vida y reglas
│   │   ├── quote.py                      # Entidad Cotización
│   │   ├── contract.py                   # Entidad Contrato
│   │   ├── payment.py                    # Entidad Pago y validaciones
│   │   └── catalog.py                    # Entidades Paquete, Temática y Extra
│   ├── value_objects/                    # Objetos de valor inmutables
│   │   ├── money.py                      # Value Object Money (moneda y decimales exactos)
│   │   ├── location.py                   # Dirección, distrito, coordenadas GPS
│   │   └── time_window.py                # Intervalos de tiempo, inicio y fin de show
│   ├── services/                         # Servicios de Dominio (lógica que involucra múltiples entidades)
│   │   ├── financial_engine.py           # Cálculo determinístico: Total, Adelanto (10%), Saldo y Rentabilidad
│   │   ├── travel_interval_service.py    # Cálculo de tiempos mínimos de traslado entre shows
│   │   └── concurrency_evaluator.py      # Evaluación del umbral de eventos simultáneos (> 3 shows)
│   └── exceptions/                       # Excepciones de negocio de dominio
│       ├── quote_exceptions.py
│       └── resource_exceptions.py
│
├── application/                          # CAPA 2: CASOS DE USO Y PUERTOS (Orquestación)
│   ├── ports/                            # Interfaces abstractas (ABC en Python)
│   │   ├── input/                        # Puertos Primarios (Driving Ports - Casos de uso)
│   │   │   ├── quote_use_cases.py        # ICotizarEvento, IRecalcularMovilidad
│   │   │   ├── payment_use_cases.py      # IRegistrarAdelanto, IValidarComprobante
│   │   │   ├── contract_use_cases.py     # IGenerarContratoPdf, IFirmarContrato
│   │   │   ├── event_use_cases.py        # IAgendarEvento, IConfirmarCobroPreShow, ILiquidarEvento
│   │   │   ├── override_use_cases.py     # IAjustarMovilidadManual, IAprobarShowSimultaneo
│   │   │   └── financial_use_cases.py    # IGenerarReporteFinanciero
│   │   └── output/                       # Puertos Secundarios (Driven Ports - SPI)
│   │       ├── repositories.py           # IEventRepository, IQuoteRepository, IContractRepository
│   │       ├── maps_port.py              # IMapsServicePort (cálculo de distancias y tiempos)
│   │       ├── whatsapp_port.py          # IWhatsAppServicePort (envío de mensajes y plantillas)
│   │       ├── pdf_port.py               # IPdfGeneratorPort (compilación de contratos)
│   │       ├── storage_port.py           # IFileStoragePort (guardar imágenes y PDFs)
│   │       └── cache_lock_port.py        # ICacheLockPort (locks distribuidos y caché)
│   ├── use_cases/                        # Implementaciones concretas de los casos de uso
│   │   ├── quote/
│   │   │   ├── create_quote.py
│   │   │   └── apply_mobility_override.py
│   │   ├── payment/
│   │   │   └── process_advance_payment.py
│   │   ├── contract/
│   │   │   ├── build_contract_pdf.py
│   │   │   └── sign_contract.py
│   │   ├── event/
│   │   │   ├── check_in_and_collect.py
│   │   │   └── settle_extra_time.py
│   │   └── financial/
│   │       └── compute_monthly_pnl.py
│   └── dtos/                             # Data Transfer Objects agnósticos de la capa de aplicación
│       ├── quote_dto.py
│       └── event_dto.py
│
├── infrastructure/                       # CAPA 3: ADAPTADORES E IMPLEMENTACIONES TÉCNICAS
│   ├── adapters/
│   │   ├── primary/                      # Adaptadores de Entrada (Driving Adapters)
│   │   │   ├── web/                      # FastAPI Routers (Controladores HTTP)
│   │   │   │   ├── v1/
│   │   │   │   │   ├── quotes_router.py
│   │   │   │   │   ├── events_router.py
│   │   │   │   │   ├── contracts_router.py
│   │   │   │   │   ├── financial_router.py
│   │   │   │   │   └── overrides_router.py
│   │   │   │   └── schemas/              # Pydantic Schemas (Request/Response HTTP)
│   │   │   └── webhooks/                 # Controladores de Webhooks
│   │   │       └── whatsapp_webhook.py   # Receptor de eventos de WhatsApp Business Cloud
│   │   │
│   │   └── secondary/                    # Adaptadores de Salida (Driven Adapters)
│   │       ├── persistence/              # Base de Datos Relacional (PostgreSQL)
│   │       │   ├── database.py           # Conexión SQLAlchemy / SessionFactory
│   │       │   ├── models/               # Tablas SQLAlchemy (ORM Models)
│   │       │   │   ├── event_model.py
│   │       │   │   └── quote_model.py
│   │       │   ├── mappers/              # Transformadores ORM Model <--> Entidad de Dominio
│   │       │   └── repositories/         # Implementaciones concretas de los repositorios
│   │       │       ├── sqlalchemy_event_repository.py
│   │       │       └── sqlalchemy_quote_repository.py
│   │       ├── external_services/        # Clientes HTTP hacia APIs de terceros
│   │       │   ├── google_maps/          # Adaptador Google Maps Platform (Directions/Distance Matrix)
│   │       │   │   └── google_maps_adapter.py
│   │       │   └── whatsapp/             # Adaptador WhatsApp Cloud API
│   │       │       └── whatsapp_cloud_adapter.py
│   │       ├── documents/                # Generador de contratos
│   │       │   └── weasyprint_adapter.py # Compilador HTML/Jinja2 a PDF
│   │       ├── storage/                  # Adaptador de almacenamiento
│   │       │   └── local_storage_adapter.py (o S3StorageAdapter)
│   │       └── cache/                    # Adaptador de Redis
│   │           └── redis_cache_adapter.py
│   │
│   └── di/                               # Contenedor de Inyección de Dependencias
│       └── containers.py                 # Ensamblador de dependencias y proveedores FastAPI
│
└── main.py                               # Punto de entrada de la aplicación FastAPI (Lifespan & app)
```

---

## 3. Descripción Detallada de las Capas Hexagonales

### 3.1 Capa de Dominio (`app/domain`)
Es el corazón del software. Modela el negocio sin atarse a ninguna tecnología.
* **Entidades (`entities`):** Poseen identidad propia mutable a lo largo del tiempo (ej. `Event`, `Quote`, `Contract`). Contienen invariantes de negocio: no permiten estados imposibles (un evento no puede iniciarse sin cobro de saldo).
* **Objetos de Valor (`value_objects`):** Inmutables y sin identidad propia, modelan características del dominio:
  * `Money(amount: Decimal, currency: str = "PEN")`: Previene errores de coma flotante en cálculos de dinero.
  * `Coordinates(latitude: float, longitude: float)`: Georreferenciación exacta.
  * `EventStatus`: Enumeración estricta de estados (`QUOTED`, `ADVANCE_PAID`, `SCHEDULED`, `RUNNING`, `SETTLED`).
* **Servicios de Dominio (`services`):** Encapsulan operaciones que involucran varias entidades. Por ejemplo:
  * `FinancialEngine`: Ejecuta estrictamente las fórmulas:
    $$\text{Subtotal} = \text{Paquete} + \sum \text{Extras}$$
    $$\text{Adelanto} = 0.10 \times \text{Subtotal}$$
    $$\text{Total} = \text{Subtotal} + \text{Movilidad}$$
    $$\text{Saldo} = \text{Total} - \text{Adelanto}$$

### 3.2 Capa de Aplicación (`app/application`)
Coordina los flujos de interacción del negocio.
* **Puertos de Entrada (*Driving Ports*):** Interfaces abstractas que definen qué operaciones ofrece el sistema a los clientes externos (REST, Webhooks, CLI).
* **Puertos de Salida (*Driven Ports*):** Interfaces abstractas que definen qué necesita el sistema del mundo exterior (guardar datos, consultar mapas, enviar mensajes, compilar PDFs).
* **Casos de Uso (*Use Cases*):** Clases que implementan un puerto de entrada. Cada caso de uso coordina:
  1. Carga de entidades a través de un puerto de salida (repositorio).
  2. Ejecución de lógica de dominio y cambio de estado de la entidad.
  3. Disparo de efectos secundarios a través de puertos de salida (ej. enviar mensaje por WhatsApp, persistir en base de datos).
  4. Retorno de un DTO con el resultado.

### 3.3 Capa de Infraestructura (`app/infrastructure`)
Contiene las implementaciones técnicas concretas de los puertos.
* **Adaptadores Primarios (Controladores):**
  * `quotes_router.py`: Expone endpoints HTTP (`POST /api/v1/quotes`). Recibe payloads validados con Pydantic, invoca al caso de uso correspondiente e inyecta la respuesta serializada.
  * `whatsapp_webhook.py`: Endpoint que valida tokens de verificación de Meta, parsea mensajes y comandos de botones, e invoca los casos de uso del chatbot.
* **Adaptadores Secundarios (Infraestructura de soporte):**
  * `SqlAlchemyQuoteRepository`: Implementa la interfaz `IQuoteRepository` usando transacciones de PostgreSQL.
  * `GoogleMapsAdapter`: Implementa `IMapsServicePort` llamando a la API REST de Google Maps con cliente asíncrono `httpx`.
  * `WeasyPrintAdapter`: Implementa `IPdfGeneratorPort` tomando plantillas Jinja2 y convirtiéndolas a PDF descargable.

---

## 4. Inyección de Dependencias y Desacoplamiento

FastAPI incluye un sistema nativo de inyección de dependencias (`Depends`) que encaja de forma natural con la Arquitectura Hexagonal.

### Flujo de Enlace:
1. El router HTTP inyecta el Caso de Uso a través de una función constructora en `app/infrastructure/di/containers.py`.
2. La función constructora instancia el Caso de Uso pasándole las implementaciones de infraestructura que satisfacen sus Puertos de Salida.
3. El Caso de Uso nunca sabe si el repositorio graba en PostgreSQL, SQLite o un diccionario en memoria para tests.

```python
# Ejemplo conceptual del flujo de Inyección en FastAPI
# app/infrastructure/adapters/primary/web/v1/quotes_router.py

from fastapi import APIRouter, Depends
from app.application.ports.input.quote_use_cases import ICreateQuoteUseCase
from app.infrastructure.di.containers import get_create_quote_use_case
from app.infrastructure.adapters.primary.web.schemas.quote_schemas import QuoteRequest, QuoteResponse

router = APIRouter(prefix="/quotes", tags=["Cotizaciones"])

@router.post("", response_model=QuoteResponse, status_code=201)
async def create_quote(
    payload: QuoteRequest,
    use_case: ICreateQuoteUseCase = Depends(get_create_quote_use_case)
):
    # La capa web solo traduce HTTP a DTO y delega al caso de uso
    result_dto = await use_case.execute(payload.to_dto())
    return QuoteResponse.from_dto(result_dto)
```
