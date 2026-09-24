# 01. Especificación de Endpoints RESTful (API v1)

---

## 1. Convenciones Globales de la API

* **URL Base:** `https://api.eventpro.pe/api/v1` (o `http://localhost:8000/api/v1` en local).
* **Formato de Intercambio:** `application/json` (UTF-8). Excepción: `multipart/form-data` para subida de comprobantes.
* **Autenticación:** Cabecera HTTP `Authorization: Bearer <jwt_access_token>`.
* **Respuestas Exitosas:** `200 OK` (lecturas y actualizaciones), `201 Created` (creaciones de recursos).
* **Respuestas de Error:** Estandarizadas bajo la norma **RFC 7807 (Problem Details)**:
  ```json
  {
    "type": "https://errors.eventpro.pe/invalid-advance-amount",
    "title": "Monto de adelanto inválido",
    "status": 400,
    "detail": "El adelanto debe ser exactamente el 10% de los servicios contratados (S/. 120.00).",
    "instance": "/api/v1/payments/advance"
  }
  ```

---

## 2. Catálogo de Endpoints

### 2.1 Módulo: Autenticación y Cuentas (`/auth`)

#### `POST /auth/login`
* **Descripción:** Autentica a un encargado u operador y emite tokens JWT.
* **Seguridad:** Público.
* **Request Body:**
  ```json
  {
    "email": "encargado@eventpro.pe",
    "password": "PasswordSeguro123!"
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
    "refresh_token": "d8f9a2b1-5c3e-4f8a-9b1d...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "id": "b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22",
      "full_name": "Juan Pérez",
      "role": "ENCARGADO"
    }
  }
  ```

#### `POST /auth/refresh`
* **Descripción:** Rota el Refresh Token y entrega un nuevo Access Token.
* **Request Body:** `{"refresh_token": "d8f9a2b1-5c3e-4f8a-9b1d..."}`
* **Response `200 OK`:** `{"access_token": "...", "refresh_token": "...", "expires_in": 3600}`

---

### 2.2 Módulo: Catálogo Comercial (`/catalog`)

#### `GET /catalog/packages`
* **Descripción:** Lista los paquetes disponibles para venta con sus temáticas compatibles.
* **Seguridad:** Público / Autenticado.
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "e4b2d5a1-...",
      "name": "Hora Loca Medium",
      "category": "SHOW",
      "description": "Show completo con 4 bailarines, animador, DJ y cotillón.",
      "base_price": 750.00,
      "duration_minutes": 60,
      "compatible_themes": [
        {"id": "t1-...", "name": "Selva"},
        {"id": "t2-...", "name": "Neón Glow"}
      ]
    }
  ]
  ```

#### `GET /catalog/extras`
* **Descripción:** Lista los extras y muñecos disponibles con su precio de venta.
* **Response `200 OK`:**
  ```json
  [
    {
      "id": "x1-...",
      "name": "Muñeco Gorila Gigante",
      "sale_price": 250.00,
      "description": "Personaje estrella gigante para ingreso sorpresa."
    }
  ]
  ```

---

### 2.3 Módulo: Cotizador y Motor de Movilidad (`/quotes`)

#### `POST /quotes`
* **Descripción:** Calcula y crea una cotización aplicando las reglas financieras (RF-05, RF-07).
* **Seguridad:** Autenticado o invocado por el webhook de WhatsApp.
* **Request Body:**
  ```json
  {
    "client_name": "Carlos Rodríguez",
    "client_phone": "+51999888777",
    "event_date": "2026-10-15",
    "event_time": "21:30:00",
    "location_address": "Av. Benavides 2150",
    "location_district": "Miraflores",
    "package_id": "e4b2d5a1-...",
    "theme_id": "t1-...",
    "extra_ids": ["x1-..."],
    "client_provides_mobility": false
  }
  ```
* **Response `201 Created`:**
  ```json
  {
    "quote_id": "q9c8a1b2-...",
    "services_subtotal": 1000.00,
    "calculated_distance_km": 18.40,
    "calculated_transit_minutes": 55,
    "final_mobility_amount": 80.50,
    "total_amount": 1080.50,
    "advance_amount": 100.00,
    "pending_balance": 980.50,
    "breakdown": {
      "services_balance_due": 900.00,
      "mobility_due": 80.50
    },
    "status": "COTIZADO"
  }
  ```

---

### 2.4 Módulo: Integración con WhatsApp Business (`/webhooks/whatsapp`)

#### `GET /webhooks/whatsapp`
* **Descripción:** Verificación de Webhook para la API de Meta / WhatsApp Cloud.
* **Query Params:** `hub.mode=subscribe`, `hub.challenge=...`, `hub.verify_token=...`
* **Response `200 OK`:** Retorna el valor `hub.challenge` como texto plano.

#### `POST /webhooks/whatsapp`
* **Descripción:** Receptor de eventos de mensajes entrantes, clics de botones y subida de imágenes (comprobantes de pago).
* **Request Body:** Payload estándar de WhatsApp Cloud API.
* **Response `200 OK`:** `{"status": "EVENT_RECEIVED"}` (procesamiento asíncrono en menos de 1.5s).

---

### 2.5 Módulo: Gestión de Pagos y Comprobantes (`/payments`)

#### `POST /payments/advance`
* **Descripción:** Recibe la captura del comprobante de adelanto del 10% (RF-11).
* **Content-Type:** `multipart/form-data`
* **Form Data:**
  * `quote_id`: UUID de la cotización.
  * `payment_method`: `YAPE`, `PLIN` o `TRANSFERENCIA`.
  * `amount`: `100.00`
  * `receipt_file`: Archivo binario (JPEG/PNG/PDF).
* **Response `201 Created`:**
  ```json
  {
    "payment_id": "pay-11a2...",
    "validation_status": "PENDIENTE",
    "message": "Comprobante recibido con éxito. En cola de validación."
  }
  ```

#### `PATCH /payments/{id}/verify`
* **Descripción:** El encargado aprueba o rechaza el comprobante (RF-12, PC-06).
* **Seguridad:** Requiere rol `ENCARGADO` o `SUPERADMIN`.
* **Request Body:**
  ```json
  {
    "status": "VERIFICADO",
    "rejection_reason": null
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "payment_id": "pay-11a2...",
    "validation_status": "VERIFICADO",
    "event_created_id": "evt-77a8...",
    "contract_status": "EMITIDO"
  }
  ```

---

### 2.6 Módulo: Contratos y Firma Digital (`/contracts`)

#### `GET /contracts/{id}/pdf`
* **Descripción:** Descarga el archivo PDF compilado del contrato (RF-13).
* **Response `200 OK`:** Archivo binario `application/pdf`.

#### `POST /contracts/sign/{token}`
* **Descripción:** El cliente estampa su firma manuscrita electrónica en el contrato (RF-15).
* **Seguridad:** Público con token temporal de un solo uso.
* **Request Body:**
  ```json
  {
    "signature_base64": "data:image/png;base64,iVBORw0KGgoAAA...",
    "signer_full_name": "Carlos Rodríguez",
    "accept_terms": true
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "contract_number": "CTR-2026-0042",
    "status": "FIRMADO",
    "signed_at": "2026-09-23T20:15:00Z",
    "message": "Contrato firmado satisfactoriamente. Se ha enviado una copia a su WhatsApp."
  }
  ```

#### `POST /contracts/manual`
* **Descripción:** Generación directa de contrato en modo manual de contingencia (RF-23, PC-05).
* **Seguridad:** Requiere rol `ENCARGADO`.

---

### 2.7 Módulo: Cronograma y Operación en Evento (`/events`)

#### `GET /events/schedule`
* **Descripción:** Consulta el calendario operativo con filtros avanzados (RF-16, RF-17).
* **Query Params:** `from_date=2026-10-01`, `to_date=2026-10-31`, `district=Miraflores`, `status=AGENDADO`
* **Response `200 OK`:**
  ```json
  [
    {
      "event_id": "evt-77a8...",
      "event_code": "EVT-2026-0042",
      "event_date": "2026-10-15",
      "start_time": "21:30",
      "end_time": "22:30",
      "district": "Miraflores",
      "client_name": "Carlos Rodríguez",
      "package_name": "Hora Loca Medium",
      "theme_name": "Selva",
      "client_observations": "MÚSICA PROHIBIDA: Reggaetón. Salida sorpresa del gorila al min 45.",
      "status": "AGENDADO",
      "pending_balance_to_collect": 980.50
    }
  ]
  ```

#### `PATCH /events/{id}/check-in-and-collect`
* **Descripción:** Confirma el cobro in-situ del saldo pendiente antes de iniciar el show (RF-18, PC-07).
* **Seguridad:** `OPERADOR` o `ENCARGADO`.
* **Request Body:**
  ```json
  {
    "amount_collected": 980.50,
    "payment_method": "YAPE",
    "notes": "Cobrado completo al llegar al local."
  }
  ```
* **Response `200 OK`:**
  ```json
  {
    "event_id": "evt-77a8...",
    "status": "EN_EJECUCION",
    "show_started_at": "2026-10-15T21:35:00Z"
  }
  ```

#### `POST /events/{id}/extensions`
* **Descripción:** Registra extensiones de tiempo de show en caliente (RF-19, PC-08).
* **Request Body:** `{"extra_minutes": 30, "agreed_rate": 100.00, "payment_method": "EFECTIVO"}`
* **Response `201 Created`:** `{"event_id": "...", "status": "CON_EXTENSION"}`

#### `POST /events/{id}/settle`
* **Descripción:** Cierra definitivamente el evento marcándolo como `LIQUIDADO`.
* **Response `200 OK`:** `{"event_id": "...", "status": "LIQUIDADO"}`

---

### 2.8 Módulo: Procesos de Control y Overrides (`/overrides`)

#### `PATCH /overrides/quotes/{id}/mobility`
* **Descripción:** Sobrescritura manual del costo de movilidad por el encargado (RF-21, PC-04).
* **Request Body:**
  ```json
  {
    "manual_mobility_amount": 95.00,
    "reason": "Zona de alto tráfico con peajes no computados."
  }
  ```
* **Response `200 OK`:** Retorna la cotización recalculada con el nuevo total y saldo.

#### `POST /overrides/events/{id}/approve-simultaneous`
* **Descripción:** Aprobación manual de un evento que excede el umbral de 3 shows simultáneos (RF-20, PC-03).
* **Request Body:** `{"action": "APROBADO", "notes": "Se contrató elenco adicional freelance."}`
* **Response `200 OK`:** `{"status": "AGENDADO", "is_manually_approved": true}`

---

### 2.9 Módulo: Analítica Financiera y BI (`/reports`)

#### `GET /reports/financial/pnl`
* **Descripción:** Reporte semanal o mensual de Ingresos vs. Costos Fijos y Utilidad Neta (RF-24).
* **Query Params:** `period_type=MONTHLY`, `year=2026`, `month=10`
* **Response `200 OK`:**
  ```json
  {
    "period": "2026-10",
    "total_events_settled": 24,
    "gross_revenue": 28450.00,
    "direct_costs": {
      "fixed_packages_cost": 12200.00,
      "fixed_extras_cost": 3100.00,
      "mobility_operational_cost": 2150.00,
      "total_costs": 17450.00
    },
    "net_profit": 11000.00,
    "profit_margin_percentage": 38.66
  }
  ```
