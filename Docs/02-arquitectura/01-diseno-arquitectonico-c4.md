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
        Elenco["Personal de Elenco / Operador<br/><i>[Persona]</i><br/>Ejecuta shows, cobra saldo in-situ e informa extensiones."]
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

    Cliente -->|"Visualiza y firma digitalmente contrato web"| EventProApp
    Encargado -->|"Administra cronograma, contratos manuales, overrides y dashboards"| EventProApp
    Elenco -->|"Consulta observaciones y confirma cobro pre-show"| EventProApp

    EventProApp -->|"Consulta matrices de distancia y rutas"| GoogleMaps
```

---

## 3. Modelo C4: Nivel 2 — Diagrama de Contenedores

Describe las aplicaciones de software, almacenes de datos y servicios que componen EventPro.

```mermaid
flowchart TB
    subgraph Usuarios["Usuarios"]
        UserWeb["Encargado / Cliente en Navegador"]
        UserWhatsApp["Cliente en WhatsApp"]
    end

    subgraph FrontendApp["Frontend (Feature-Sliced Design)"]
        SPA["EventPro Web App (FSD)<br/><i>[Container: TypeScript / React / Next.js]</i><br/>Panel administrativo, visor de cronograma, creación manual de contratos, firma digital de clientes y dashboards."]
    end

    subgraph BackendApp["Backend (Arquitectura Hexagonal)"]
        API["EventPro API Server<br/><i>[Container: Python / FastAPI]</i><br/>Exprime el núcleo de dominio, procesa webhooks, calcula tarifas, coordina persistencia y genera PDFs."]
    end

    subgraph Almacenamiento["Persistencia y Caché"]
        DB[("Base de Datos Relacional<br/><i>[Container: PostgreSQL]</i><br/>Persistencia transaccional de eventos, clientes, contratos, pagos y catálogo.")]
        Cache[("Caché y Concurrencia<br/><i>[Container: Redis]</i><br/>Almacenamiento de sesiones de chatbot, caché de rutas de Google Maps y locks distribuidos.")]
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
    API -->|"REST API / HTTPS"| ExtMaps
```

---

## 4. Modelo C4: Nivel 3 — Diagrama de Componentes del Backend (Hexagonal)

El siguiente diagrama detalla cómo se organizan los componentes internos del Backend siguiendo los preceptos de la Arquitectura Hexagonal (*Ports & Adapters*).

```mermaid
flowchart LR
    subgraph AdaptadoresEntrada["Adaptadores Primarios (Driving Adapters)"]
        HttpRouters["FastAPI Routers<br/><i>[Controllers REST]</i><br/>/api/v1/events, /quotes, /contracts"]
        WebhookController["WhatsApp Webhook Controller<br/><i>[HTTP Handler]</i><br/>/api/v1/webhooks/whatsapp"]
        AdminCli["CLI & Tasks Controller<br/><i>[Scripts / Cron Jobs]</i><br/>Reportes semanales/mensuales"]
    end

    subgraph PuertosEntrada["Puertos de Entrada (Driving Ports / Use Cases)"]
        UCQuote["CotizarEventoPort"]
        UCPay["ValidarPagoAdelantoPort"]
        UCContract["GenerarContratoPort"]
        UCSchedule["GestionarCronogramaPort"]
        UCOverride["AplicarOverridePort"]
        UCReport["CalcularFinanzasPort"]
    end

    subgraph Dominio["NÚCLEO DE DOMINIO (Core Domain)"]
        direction TB
        Entities["Entidades de Dominio<br/>- Evento<br/>- Cotizacion<br/>- Contrato<br/>- Pago<br/>- Paquete / Extra"]
        ValueObjects["Value Objects<br/>- MontoDinero<br/>- UbicacionEvento<br/>- IntervaloTiempo<br/>- EstadoEvento"]
        DomainServices["Servicios de Dominio<br/>- MotorLiquidacionFinanciera<br/>- CalculadorIntervaloShow<br/>- EvaluadorUmbralConcurrencia"]
    end

    subgraph PuertosSalida["Puertos de Salida (Driven Ports / Interfaces)"]
        PortRepo["IEventRepository<br/>IQuoteRepository<br/>IContractRepository"]
        PortMaps["IGoogleMapsClient"]
        PortWhatsApp["IWhatsAppNotificationClient"]
        PortPdf["IPdfGeneratorService"]
        PortStorage["IFileStorageService"]
        PortCache["ICacheLockService"]
    end

    subgraph AdaptadoresSalida["Adaptadores Secundarios (Driven Adapters)"]
        SqlAlchemyRepo["PostgreSQL Adapter<br/><i>[SQLAlchemy Models & Repos]</i>"]
        GoogleMapsAdapter["Google Maps Adapter<br/><i>[HTTPX / REST Client]</i>"]
        WhatsAppAdapter["WhatsApp Cloud Adapter<br/><i>[HTTPX Client]</i>"]
        WeasyPrintAdapter["PDF Generation Adapter<br/><i>[WeasyPrint / Jinja2]</i>"]
        FileSystemAdapter["File Storage Adapter<br/><i>[Local / S3 Compatible]</i>"]
        RedisAdapter["Redis Cache & Lock Adapter<br/><i>[Redis-py]</i>"]
    end

    %% Relaciones Driving
    HttpRouters --> UCQuote & UCPay & UCContract & UCSchedule & UCOverride & UCReport
    WebhookController --> UCQuote & UCPay
    AdminCli --> UCReport

    %% Relaciones Ports -> Domain
    UCQuote & UCPay & UCContract & UCSchedule & UCOverride & UCReport --> DomainServices
    DomainServices --> Entities & ValueObjects

    %% Relaciones Domain/UseCases -> Driven Ports
    UCQuote & UCPay & UCContract & UCSchedule & UCOverride & UCReport -.-> PortRepo & PortMaps & PortWhatsApp & PortPdf & PortStorage & PortCache

    %% Relaciones Driven Ports -> Driven Adapters
    PortRepo --> SqlAlchemyRepo
    PortMaps --> GoogleMapsAdapter
    PortWhatsApp --> WhatsAppAdapter
    PortPdf --> WeasyPrintAdapter
    PortStorage --> FileSystemAdapter
    PortCache --> RedisAdapter
```
