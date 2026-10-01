# 01. Diseño Arquitectónico Global y Modelo C4

---

## 1. Visión General del Sistema

El ecosistema **EventPro** está diseñado bajo una arquitectura desacoplada y orientada al dominio:
* **Backend:** Implementado en **Python con FastAPI** bajo el patrón de **Arquitectura Hexagonal (Ports & Adapters)**, garantizando que las reglas de negocio (cálculo de cotizaciones, validaciones de disponibilidad, liquidación y control) sean completamente independientes del framework web, de la base de datos y de las APIs externas.
* **Frontend:** Implementado bajo la metodología **Feature-Sliced Design (FSD)**, organizando el código por responsabilidades de negocio y capas jerárquicas estrictas para máxima escalabilidad y mantenibilidad.

---

## 2. Modelo C4: Nivel 1 — Diagrama de Contexto del Sistema

Describe cómo interactúan los diferentes actores y sistemas externos con la plataforma EventPro.

```mermaid
flowchart TD
    subgraph Actores["Actores Humanos"]
        Cliente["Cliente Final<br/><i>[Persona]</i><br/>Solicita shows, cotiza, paga adelanto y firma contrato."]
        Encargado["Encargado / Administrador<br/><i>[Persona]</i><br/>Gestiona eventos, aprueba shows simultáneos, aplica overrides y audita finanzas."]
        Elenco["Personal de Elenco / Operador<br/><i>[Persona]</i><br/>Ejecuta shows, cobra saldo in-situ (web móvil) e informa extensiones."]
    end

    subgraph SistemaEventPro["Sistema EventPro"]
        EventProApp["Plataforma EventPro<br/><i>[Software System]</i><br/>Automatiza cotizaciones, contratos, agenda y finanzas con controles manuales."]
    end

    subgraph Externos["Sistemas y Servicios Externos"]
        WhatsAppAPI["WhatsApp Business Cloud API<br/><i>[External Service]</i><br/>Canal conversacional y webhooks para atención de clientes."]
        GoogleMaps["Google Maps Platform<br/><i>[External Service]</i><br/>Cálculo de distancias y tiempos de tránsito para movilidad e intervalos."]
    end

    Cliente -->|"Chatea, consulta y envía comprobantes"| WhatsAppAPI
    WhatsAppAPI -->|"Dispara eventos vía Webhook"| EventProApp
    EventProApp -->|"Envía mensajes, cotizaciones y contratos"| WhatsAppAPI

    Cliente -->|"Revisa y firma electrónicamente el contrato (web móvil)"| EventProApp
    Encargado -->|"Administra cronograma, contratos manuales, overrides y dashboards"| EventProApp
    Elenco -->|"Consulta su agenda, observaciones y confirma cobro pre-show (web móvil)"| EventProApp

    EventProApp -->|"Consulta matrices de distancia y rutas"| GoogleMaps
```

---

## 3. Modelo C4: Nivel 2 — Diagrama de Contenedores

Describe las aplicaciones de software, almacenes de datos y servicios que componen EventPro.

```mermaid
flowchart TB
    subgraph Usuarios["Usuarios"]
        UserWeb["Encargado (escritorio) / Operador y Cliente (web móvil)"]
        UserWhatsApp["Cliente en WhatsApp"]
    end

    subgraph FrontendApp["Frontend (Feature-Sliced Design)"]
        SPA["EventPro Web App (FSD)<br/><i>[Container: TypeScript / React / Next.js]</i><br/>Panel del encargado, vista móvil del operador (agenda, cobro, extensiones), firma electrónica del contrato por el cliente y dashboards."]
    end

    subgraph BackendApp["Backend (Arquitectura Hexagonal)"]
        API["EventPro API Server<br/><i>[Container: Python / FastAPI]</i><br/>Expone el núcleo de dominio, procesa webhooks, calcula tarifas, coordina persistencia, genera PDFs y publica GET /health (estado de PostgreSQL y Redis)."]
        Worker["EventPro Worker<br/><i>[Container: Python / arq]</i><br/>Proceso aparte (servicio worker de Docker Compose): vencimiento de cotizaciones, cola outbox_messages hacia WhatsApp con reintentos, reportes semanales y mensuales y, opcionalmente, el renderizado de PDFs."]
    end

    subgraph Almacenamiento["Persistencia y Caché"]
        DB[("Base de Datos Relacional<br/><i>[Container: PostgreSQL]</i><br/>Persistencia transaccional de eventos, clientes, contratos, pagos y catálogo.")]
        Cache[("Caché, Concurrencia y Cola<br/><i>[Container: Redis]</i><br/>Sesiones de chatbot, caché de rutas de Google Maps, locks distribuidos y cola de tareas de arq.")]
        Storage[("Repositorio de Archivos<br/><i>[Container: Object Storage / Local Volume]</i><br/>Almacenamiento seguro de comprobantes de pago y PDFs de contratos.")]
    end

    subgraph ServiciosTerceros["Servicios de Terceros"]
        ExtWhatsApp["Meta / WhatsApp Cloud API"]
        ExtMaps["Google Maps Platform"]
    end

    UserWeb -->|"HTTPS / JSON"| SPA
    SPA -->|"HTTPS / REST API (JWT)"| API
    UserWhatsApp -->|"Mensajería Instantánea"| ExtWhatsApp
    ExtWhatsApp -->|"HTTPS POST (Webhooks)"| API
    API -->|"HTTPS POST (Envío de mensajes)"| ExtWhatsApp

    API -->|"SQLAlchemy ORM (TCP: 5432)"| DB
    API -->|"Redis Protocol (TCP: 6379)"| Cache
    API -->|"Lectura / Escritura de binarios"| Storage
    API -->|"Encola tareas (arq)"| Cache
    Worker -->|"Consume tareas (arq)"| Cache
    Worker -->|"SQLAlchemy ORM (TCP: 5432)"| DB
    Worker -->|"Lectura / Escritura de binarios"| Storage
    Worker -->|"HTTPS POST (outbox_messages)"| ExtWhatsApp
    API -->|"REST API / HTTPS"| ExtMaps
```

---

## 4. Modelo C4: Nivel 3 — Diagrama de Componentes del Backend (Hexagonal)

El siguiente diagrama detalla cómo se organizan los componentes internos del Backend siguiendo los preceptos de la Arquitectura Hexagonal (*Ports & Adapters*).

```mermaid
flowchart LR
    subgraph AdaptadoresEntrada["Adaptadores Primarios (Driving Adapters)"]
        HttpRouters["FastAPI Routers<br/><i>[Controllers REST]</i><br/>/api/v1/auth, /users, /audit-logs, /catalog, /crews, /clients, /quotes, /payments, /contracts, /events, /overrides, /reports"]
        WebhookController["WhatsApp Webhook Controller<br/><i>[HTTP Handler]</i><br/>/api/v1/webhooks/whatsapp"]
        HealthController["Health Controller<br/><i>[HTTP Handler]</i><br/>GET /health (fuera de /api/v1)"]
        ArqWorker["arq Worker (jobs/worker.py)<br/><i>[Tareas programadas y diferidas]</i><br/>Vencimiento de cotizaciones, outbox_messages, reportes"]
    end

    subgraph PuertosEntrada["Puertos de Entrada (Driving Ports / Use Cases)"]
        UCQuote["quote_use_cases<br/>ICotizarEvento, IRecalcularMovilidad"]
        UCPay["payment_use_cases<br/>IRegistrarAdelanto, IValidarComprobante"]
        UCContract["contract_use_cases<br/>IGenerarContratoPdf, IFirmarContrato"]
        UCSchedule["event_use_cases<br/>IAgendarEvento, IConfirmarCobroPreShow, ILiquidarEvento"]
        UCOverride["override_use_cases<br/>IAjustarMovilidadManual, IAprobarShowSimultaneo"]
        UCReport["financial_use_cases<br/>IGenerarReporteFinanciero"]
    end

    subgraph Dominio["NÚCLEO DE DOMINIO (Core Domain)"]
        direction TB
        Entities["Entidades de Dominio<br/>- Event<br/>- Quote<br/>- Contract<br/>- Payment<br/>- Package / Extra"]
        ValueObjects["Value Objects<br/>- Money<br/>- Coordinates<br/>- TimeWindow<br/>- QuoteStatus / PaymentStatus<br/>- EventStatus / ContractStatus"]
        DomainServices["Servicios de Dominio<br/>- FinancialEngine<br/>- TravelIntervalService<br/>- ConcurrencyEvaluator"]
    end

    subgraph PuertosSalida["Puertos de Salida (Driven Ports / Interfaces)"]
        PortRepo["IEventRepository<br/>IQuoteRepository<br/>IContractRepository"]
        PortMaps["IMapsServicePort"]
        PortWhatsApp["IWhatsAppServicePort"]
        PortPdf["IPdfGeneratorPort"]
        PortStorage["IFileStoragePort"]
        PortCache["ICacheLockPort"]
        PortSignature["SignaturePort"]
    end

    subgraph AdaptadoresSalida["Adaptadores Secundarios (Driven Adapters)"]
        SqlAlchemyRepo["PostgreSQL Adapter<br/><i>[SQLAlchemy Models & Repos]</i>"]
        GoogleMapsAdapter["Google Maps Adapter<br/><i>[HTTPX / REST Client]</i>"]
        WhatsAppAdapter["WhatsApp Cloud Adapter<br/><i>[HTTPX Client]</i>"]
        WeasyPrintAdapter["PDF Generation Adapter<br/><i>[WeasyPrint / Jinja2]</i>"]
        FileSystemAdapter["File Storage Adapter<br/><i>[Local / S3 Compatible]</i>"]
        RedisAdapter["Redis Cache & Lock Adapter<br/><i>[Redis-py]</i>"]
        PadesAdapter["PAdES Signature Adapter<br/><i>[pyHanko / PKCS#12]</i>"]
    end

    %% Relaciones Driving
    HttpRouters --> UCQuote & UCPay & UCContract & UCSchedule & UCOverride & UCReport
    WebhookController --> UCQuote & UCPay
    ArqWorker --> UCQuote & UCReport
    HealthController -.-> PortRepo & PortCache

    %% Relaciones Ports -> Domain
    UCQuote & UCPay & UCContract & UCSchedule & UCOverride & UCReport --> DomainServices
    DomainServices --> Entities & ValueObjects

    %% Relaciones Domain/UseCases -> Driven Ports
    UCQuote & UCPay & UCContract & UCSchedule & UCOverride & UCReport -.-> PortRepo & PortMaps & PortWhatsApp & PortPdf & PortStorage & PortCache & PortSignature

    %% Relaciones Driven Ports -> Driven Adapters
    PortRepo --> SqlAlchemyRepo
    PortMaps --> GoogleMapsAdapter
    PortWhatsApp --> WhatsAppAdapter
    PortPdf --> WeasyPrintAdapter
    PortStorage --> FileSystemAdapter
    PortCache --> RedisAdapter
    PortSignature --> PadesAdapter
```

> **Nota sobre nombres:** los puertos y entidades de este diagrama usan los nombres canónicos de la [arquitectura hexagonal](02-backend-arquitectura-hexagonal.md) (`IPdfGeneratorPort`, `IFileStoragePort`, `EventStatus`, etc.), que es la fuente de verdad. Los módulos `/users`, `/audit-logs`, `/crews` y `/clients` se exponen como routers adicionales dentro del mismo adaptador web.
>
> **Renderizado de PDFs:** WeasyPrint es síncrono y consume CPU (ver RNF-01.3); el adaptador de PDF se ejecuta en el *worker* de arq o en un *threadpool*, nunca en el *event loop* de la API.
