# 01. Diagrama Entidad-Relación (DER)

---

## 1. Visión General del Modelo de Persistencia

El modelo de datos de **EventPro** está diseñado para garantizar la integridad transaccional (cumplimiento ACID) de la promotora de eventos. Utiliza **PostgreSQL** como motor relacional, claves primarias basadas en **UUIDv4** para evitar enumeración y desacoplar la generación de identificadores, y tipos de datos numéricos exactos (`DECIMAL(10,2)`) para evitar cualquier distorsión por coma flotante en cotizaciones y balances.

---

## 2. Diagrama Entidad-Relación (Mermaid)

```mermaid
erDiagram
    USERS ||--o{ REFRESH_TOKENS : has
    ROLES ||--o{ USERS : assigns
    
    PACKAGES ||--o{ PACKAGE_THEMES : contains
    THEMES ||--o{ PACKAGE_THEMES : defines
    
    QUOTES ||--o{ QUOTE_EXTRAS : includes
    EXTRAS ||--o{ QUOTE_EXTRAS : references
    PACKAGES ||--o{ QUOTES : selects
    THEMES ||--o{ QUOTES : configures
    
    QUOTES ||--o| EVENTS : generates
    EVENTS ||--o| CONTRACTS : formalizes
    EVENTS ||--o{ PAYMENTS : receives
    EVENTS ||--o{ EVENT_EXTENSIONS : logs
    EVENTS ||--o{ CREW_ASSIGNMENTS : assigns
    
    CREWS ||--o{ CREW_ASSIGNMENTS : participates
    USERS ||--o{ AUDIT_LOGS : performs

    ROLES {
        uuid id PK
        string code UK "SUPERADMIN, ENCARGADO, OPERADOR"
        string name
        string description
    }

    USERS {
        uuid id PK
        uuid role_id FK
        string full_name
        string email UK
        string phone UK
        string hashed_password
        boolean is_active
        timestamp created_at
    }

    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash UK
        timestamp expires_at
        boolean is_revoked
    }

    PACKAGES {
        uuid id PK
        string name "Hora Loca Medium, Show Infantil, etc."
        string category "SHOW, DECORACION, TOLDOS, DJ"
        text description
        decimal base_price "Precio de venta"
        decimal direct_cost "Costo fijo del elenco/proveedor"
        integer duration_minutes
        boolean is_active
    }

    THEMES {
        uuid id PK
        string name "Selva, Neón, Retro 80s, etc."
        text description
        boolean is_active
    }

    PACKAGE_THEMES {
        uuid id PK
        uuid package_id FK
        uuid theme_id FK
    }

    EXTRAS {
        uuid id PK
        string name "Gorila Gigante, Robot LED, etc."
        text description
        decimal sale_price "Precio cobrado al cliente"
        decimal direct_cost "Costo fijo pagado al artista"
        boolean is_active
    }

    QUOTES {
        uuid id PK
        string client_name
        string client_phone
        date event_date
        time event_time
        string location_address
        string location_district
        decimal latitude
        decimal longitude
        uuid package_id FK
        uuid theme_id FK
        boolean client_provides_mobility
        decimal calculated_distance_km
        decimal calculated_transit_minutes
        decimal base_mobility_amount
        decimal final_mobility_amount
        boolean mobility_overridden
        string mobility_override_reason
        decimal services_subtotal
        decimal total_amount
        decimal advance_amount "10% de subtotal servicios"
        decimal pending_balance
        string status "BORRADOR, COTIZADO, ACEPTADO, VENCIDO"
        timestamp created_at
    }

    QUOTE_EXTRAS {
        uuid id PK
        uuid quote_id FK
        uuid extra_id FK
        integer quantity
        decimal unit_price
        decimal subtotal
    }

    EVENTS {
        uuid id PK
        string event_code UK "EVT-2026-0001"
        uuid quote_id FK UK
        date event_date
        time start_time
        time end_time
        string address
        string district
        text client_observations "Notas especiales"
        string status "AGENDADO, EN_ESPERA_COBRO, EN_EJECUCION, CON_EXTENSION, LIQUIDADO, CANCELADO"
        boolean requires_manual_approval "Umbral > 3 shows"
        boolean is_manually_approved
        uuid approved_by_user_id FK
        decimal total_services_amount
        decimal total_mobility_amount
        decimal final_total_amount
        decimal advance_paid
        decimal pre_show_balance_paid
        decimal extra_hours_amount
        timestamp created_at
    }

    CONTRACTS {
        uuid id PK
        string contract_number UK "CTR-2026-0001"
        uuid event_id FK UK
        string pdf_storage_path
        string signature_token UK
        text signature_image_url
        string signer_ip
        timestamp signed_at
        string status "BORRADOR, EMITIDO, FIRMADO, ANULADO"
        boolean is_manual_mode "Emitido manualmente"
        text custom_clauses
        timestamp created_at
    }

    PAYMENTS {
        uuid id PK
        uuid event_id FK
        string payment_concept "ADELANTO_10, SALDO_PRE_SHOW, EXTENSION_EN_VIVO"
        string payment_method "YAPE, PLIN, TRANSFERENCIA, EFECTIVO"
        decimal amount
        string receipt_image_url
        string transaction_reference
        string validation_status "PENDIENTE, VERIFICADO, RECHAZADO"
        string rejection_reason
        uuid verified_by_user_id FK
        timestamp verified_at
        timestamp created_at
    }

    CREWS {
        uuid id PK
        string leader_name
        string phone
        string crew_type "HORA_LOCA, SHOW_INFANTIL, DJ, TOLDOS"
        boolean is_active
    }

    CREW_ASSIGNMENTS {
        uuid id PK
        uuid event_id FK
        uuid crew_id FK
        integer transit_interval_minutes
        boolean transit_interval_overridden
        timestamp assigned_at
    }

    EVENT_EXTENSIONS {
        uuid id PK
        uuid event_id FK
        integer extra_minutes
        decimal agreed_rate
        string payment_method
        boolean is_paid
        timestamp requested_at
    }

    AUDIT_LOGS {
        uuid id PK
        uuid user_id FK
        string action "OVERRIDE_MOBILITY, APPROVE_SIMULTANEOUS, MANUAL_CONTRACT"
        string entity_name
        string entity_id
        jsonb old_values
        jsonb new_values
        timestamp created_at
    }
```
