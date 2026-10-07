# Códigos fuente de los diagramas — Diseño de la solución (EventPro)

Estos códigos generan las figuras que se insertan en `02-diseno-de-solucion.md`.
Cada figura se renderiza y se guarda como imagen en `figuras/` con el nombre indicado.

## Instrucciones de renderizado

| Figura | Herramienta recomendada | Exportar a |
| :--- | :--- | :--- |
| 01 · Casos de uso (PlantUML) | <https://www.plantuml.com/plantuml/uml> o extensión PlantUML de VS Code | `figuras/01-casos-de-uso.png` |
| 02 · Diagrama de actividad (PlantUML) | Ídem | `figuras/02-diagrama-actividad.png` |
| 03 · BPMN TO-BE | Bizagi Modeler (modelado con los carriles indicados) o <https://mermaid.live> como apoyo | `figuras/03-bpmn-to-be.png` |
| 04 · Arquitectura hexagonal (PlantUML) | <https://www.plantuml.com/plantuml/uml> | `figuras/04-arquitectura.png` |
| 05 · Entidad-relación (Mermaid) | <https://mermaid.live> o extensión Markdown Preview Mermaid de VS Code | `figuras/05-er.png` |

---

## Figura 1 — Diagrama general de casos de uso (PlantUML)

```plantuml
@startuml DiagramaCasosDeUso_EventPro
left to right direction
skinparam packageStyle rectangle

actor "Cliente" as CLI
actor "Encargado" as ENC
actor "Operador de campo" as OPE
actor "Superadministrador" as SAD
actor "Bot de WhatsApp" as BOT
actor "Worker de tareas" as WRK

rectangle "EventPro" {
  usecase "UC-01 Cotizar evento por WhatsApp" as UC01
  usecase "UC-02 Calcular movilidad y liquidar" as UC02
  usecase "UC-03 Enviar resumen de cotizacion" as UC03
  usecase "UC-04 Verificar disponibilidad" as UC04
  usecase "UC-05 Validar intervalo de traslado" as UC05
  usecase "UC-06 Aprobar sobrecupo (>3 simultaneos)" as UC06
  usecase "UC-07 Registrar/verificar adelanto" as UC07
  usecase "UC-08 Generar contrato PDF" as UC08
  usecase "UC-09 Firmar contrato (OTP + PAdES)" as UC09
  usecase "UC-10 Consultar cronograma" as UC10
  usecase "UC-11 Cobro pre-show y bloqueo de inicio" as UC11
  usecase "UC-12 Registrar extension y liquidar" as UC12
  usecase "UC-13 Aplicar ajustes manuales" as UC13
  usecase "UC-14 Consolidar y visualizar dashboards" as UC14
  usecase "UC-15 Gestionar usuarios/clientes/elencos" as UC15
  usecase "UC-16 Consultar auditoria" as UC16
  usecase "UC-17 Derivar/devolver conversacion" as UC17
  usecase "UC-18 Operar bandeja en tiempo real" as UC18
}

CLI --> UC01
CLI --> UC07
CLI --> UC09
BOT --> UC01
BOT --> UC02
BOT --> UC03
BOT --> UC04
BOT --> UC17
WRK --> UC04
WRK --> UC14
UC02 ..> UC04 : <<include>>
UC05 ..> UC04 : <<extend>>
UC06 ..> UC04 : <<extend>>
ENC --> UC06
ENC --> UC08
ENC --> UC10
ENC --> UC13
ENC --> UC15
ENC --> UC16
ENC --> UC18
ENC --> UC17
OPE --> UC10
OPE --> UC11
OPE --> UC12
SAD --> UC15
SAD --> UC16
@enduml
```

---

## Figura 2 — Diagrama de actividad (PlantUML)

```plantuml
@startuml Actividad_Cotizacion_EventPro
skinparam activityBackgroundColor #FFFFFF
skinparam activityBorderColor #6D28D9
skinparam swimlaneTitleBackgroundColor #4C1D95
skinparam swimlaneTitleFontColor #FFFFFF

|#EEF2FF|Cliente|
start
:Mensaje por WhatsApp;
|#EDE9FE|Bot EventPro|
:Saludo y catalogo de servicios;
|#EEF2FF|Cliente|
:Selecciona paquete, tematica y extras;
:Ingresa datos, fecha, hora y lugar;
|#EDE9FE|Bot EventPro|
:Verifica disponibilidad y movilidad;
if (Cupo disponible?) then (No)
  :Sugiere otro horario o deriva a encargado;
  stop
else (Si)
endif
:Liquida total, adelanto (10% de servicios) y saldo;
:Envia cotizacion por WhatsApp [SENT];
|#EEF2FF|Cliente|
if (Paga adelanto en 24 h?) then (No)
  |#EDE9FE|Bot EventPro|
  :Cotizacion EXPIRED;
  stop
else (Si)
  :Sube comprobante de pago;
endif
|#EDE9FE|Bot EventPro|
:Revalidacion atomica de disponibilidad (lock Redis);
if (Cupo y umbral OK?) then (Si)
  :Pago VERIFIED y cotizacion CONVERTED;
else (No)
  |#FEF3C7|Encargado|
  if (Aprueba el sobrecupo?) then (Si)
    |#EDE9FE|Bot EventPro|
    :Pago VERIFIED;
  else (No)
    |#EDE9FE|Bot EventPro|
    :Pago REFUND_PENDING -> REFUNDED;
    stop
  endif
endif
|#EDE9FE|Bot EventPro|
:Genera contrato PDF y envia enlace de firma;
|#EEF2FF|Cliente|
:Firma con OTP y firma manuscrita;
|#EDE9FE|Bot EventPro|
:Sella PAdES, contrato SIGNED y evento SCHEDULED;
|#DBEAFE|Operador|
:Cobra saldo + movilidad con evidencia;
if (Saldo cobrado al 100%?) then (No)
  :Show bloqueado;
  stop
else (Si)
  :Evento IN_PROGRESS;
endif
if (Solicita extension?) then (Si)
  :Registra cobro EXTENSION;
endif
:Evento SETTLED;
|#EDE9FE|Bot EventPro|
:Consolidacion semanal/mensual y dashboards;
stop
@enduml
```

---

## Figura 3 — BPMN TO-BE (Mermaid de apoyo / estructura para Bizagi)

En Bizagi, crear **5 carriles** (Cliente, Bot/Orquestador, Encargado, Operador de campo, Finanzas y reportes) y modelar las tareas y compuertas descritas en `02-diseno-de-solucion.md`, sección 3.3. Como apoyo visual se puede usar el siguiente diagrama:

```mermaid
flowchart TB
    subgraph CLIENTE["Pool: Cliente"]
        C1([Inicio: escribe por WhatsApp]) --> C2["Elige paquete, tematica y extras"]
        C2 --> C3["Ingresa fecha, hora y lugar"]
        C3 --> C4["Recibe cotizacion"]
        C4 --> C5{"Acepta y paga el 10%?"}
        C5 -->|No| C6(["Fin: sin contratacion"])
        C5 -->|Si| C7["Sube comprobante de pago"]
        C7 --> C8["Firma contrato (OTP + firma)"]
        C8 --> C15["Paga saldo + movilidad el dia del evento"]
        C15 --> C16(["Fin: evento cumplido"])
    end

    subgraph BOT["Pool: EventPro - Bot / Orquestador"]
        B1([Webhook de mensaje entrante]) --> B2["Saludo + catalogo"]
        B2 --> B3["Captura de datos del evento"]
        B3 --> B4["Verifica disponibilidad (elencos + inventario)"]
        B4 --> B5{"Cupo disponible?"}
        B5 -->|No| B6["Recomienda otro horario / deriva a encargado"]
        B5 -->|Si| B7["Calcula movilidad: Maps ida+vuelta + 15%"]
        B7 --> B8["Liquida total, adelanto 10% y saldo"]
        B8 --> B9["Envia cotizacion (SENT)"]
        B9 --> B10["Evento temporizador: 24 h"]
        B10 --> B11["Revalidacion atomica con lock Redis"]
        B11 --> B12{"Cupo y umbral OK?"}
        B12 -->|Si| B13["Pago VERIFIED y cotizacion CONVERTED"]
        B12 -->|No| B14["Pago REQUIRES_MANUAL_APPROVAL"]
        B13 --> B15["Genera contrato PDF (DRAFT a ISSUED)"]
        B15 --> B16["Envia enlace de firma + OTP"]
        B16 --> B17["Verifica OTP y sella PAdES"]
        B17 --> B18["Evento SCHEDULED en cronograma"]
    end

    subgraph ENCARGADO["Pool: Encargado (panel)"]
        E1["Aprueba o rechaza sobrecupo"]
        E2["Edita movilidad o intervalo (override)"]
        E3["Emite contrato manual"]
        E4["Verifica y audita pagos"]
        E5["Atiende bandeja de conversaciones"]
    end

    subgraph CAMPO["Pool: Operador de campo"]
        O1["Llega a la locacion"]
        O2["Cobra saldo + movilidad con evidencia"]
        O3{"Saldo 100%?"}
        O4["Show bloqueado"]
        O5["Inicia show (IN_PROGRESS)"]
        O6["Registra extension (EXTENDED)"]
        O7["Cierra evento (SETTLED)"]
    end

    subgraph FINANZAS["Pool: Finanzas y reportes"]
        F1["Evento temporizador: cierre semanal/mensual"]
        F2["Consolida ingresos - costos fijos"]
        F3(["Dashboards ejecutivos"])
    end

    C3 --> B1
    B2 --> C4
    B6 --> E5
    B9 --> C4
    C7 --> B11
    B12 -->|No| E1
    E1 -->|Aprueba| B13
    E1 -->|Rechaza| B6
    B16 --> C8
    B18 --> O1
    C15 --> O2
    O2 --> O3
    O3 -->|No| O4
    O3 -->|Si| O5
    O5 --> O6
    O6 --> O7
    O7 --> F1
    F1 --> F2
    F2 --> F3
```

---

## Figura 4 — Arquitectura hexagonal (PlantUML)

```plantuml
@startuml ArquitecturaHexagonal_EventPro
skinparam componentStyle rectangle
skinparam packageStyle rectangle
skinparam shadowing false

package "Adaptadores primarios (entrada)" #E0E7FF {
  [Routers REST /api/v1] as REST
  [Webhook de mensajeria] as WH
  [Worker de tareas] as JOBS
}

package "Aplicacion - Nucleo" #EDE9FE {
  [Puertos de entrada\n(casos de uso)] as IN
  [Casos de uso] as UC
  [Puertos de salida\n(SPI)] as OUT
}

package "Dominio - Nucleo" #F5F3FF {
  [Entidades y Value Objects] as DOM
  [Servicios de dominio] as SDS
}

package "Adaptadores secundarios (salida)" #F1F5F9 {
  [Repositorios SQLAlchemy / PostgreSQL] as PG
  [Google Maps] as MAPS
  [Adaptador de mensajeria] as CHAT
  [WeasyPrint / PDF] as PDF
  [pyHanko / PAdES] as SIGN
  [Almacenamiento local o S3] as STO
  [Redis / locks y cache] as REDIS
}

REST --> IN
WH --> IN
JOBS --> IN
IN --> UC
UC --> OUT
UC --> DOM
UC --> SDS
DOM --> SDS
OUT <|.. PG
OUT <|.. MAPS
OUT <|.. CHAT
OUT <|.. PDF
OUT <|.. SIGN
OUT <|.. STO
OUT <|.. REDIS
@enduml
```

---

## Figura 5 — Modelo entidad-relación (Mermaid)

```mermaid
erDiagram
    ROLES ||--o{ USERS : asigna
    CLIENTS ||--o{ QUOTES : solicita
    PACKAGES ||--o{ QUOTES : selecciona
    THEMES |o--o{ QUOTES : configura
    QUOTES ||--o{ QUOTE_EXTRAS : incluye
    EXTRAS ||--o{ QUOTE_EXTRAS : referencia
    QUOTES ||--o| EVENTS : genera
    QUOTES ||--o{ PAYMENTS : registra
    EVENTS ||--o{ PAYMENTS : recibe
    EVENTS ||--o{ CONTRACTS : formaliza
    EVENTS ||--o{ CREW_ASSIGNMENTS : asigna
    CREWS ||--o{ CREW_ASSIGNMENTS : participa
    EVENTS ||--o{ INVENTORY_RESERVATIONS : reserva
    INVENTORY_ITEMS ||--o{ INVENTORY_RESERVATIONS : reservado_en
    PACKAGES ||--o{ PACKAGE_INVENTORY_ITEMS : consume
    INVENTORY_ITEMS ||--o{ PACKAGE_INVENTORY_ITEMS : consumido_por
    PACKAGES ||--o{ PACKAGE_THEMES : compatible
    THEMES ||--o{ PACKAGE_THEMES : define
    EVENTS ||--o{ EVENT_EXTENSIONS : extiende
    PAYMENTS ||--o| EVENT_EXTENSIONS : cobra
    USERS |o--o| CREWS : opera
    CLIENTS ||--o{ CONVERSATION_LINKS : vincula
    QUOTES |o--o{ CONVERSATION_LINKS : vigente
```
