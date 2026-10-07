# Flujo administrativo del entregable

## Alcance

El ingreso manual reemplaza temporalmente la captura por WhatsApp. Implementa solicitud → presupuesto → comprobante → validación del encargado → reserva → contrato PDF sobre las tablas existentes del baseline `0002_event_extensions`.

Aplica RF-03/04 (catálogo), RF-06 (transporte provisto por el cliente), RF-07 (adelanto del 10% sobre servicios), RF-09 (disponibilidad e inventario), RF-11/12 (comprobante y validación), RF-13 (PDF), PC-05 (modo manual) y RN-09 (sin reserva antes de validar).

`source=MANUAL` identifica una cotización presentada en el panel y con comprobante recibido. No representa un envío por WhatsApp. El contrato termina `ISSUED` y el evento `AWAITING_SIGNATURE`; firma OTP/PAdES, chatbot, mensajería, Maps y conciliación bancaria están pendientes.

## API

Todos los endpoints exigen JWT de `ENCARGADO` o `SUPERADMIN`. Prefijo `/api/v1`:

| Método y ruta | Resultado |
| --- | --- |
| `POST /budgets/prepare` | Datos validados, disponibilidad, montos y presupuesto PDF en base64; no reserva |
| `POST /manual-bookings` | Cliente, cotización `PAYMENT_STARTED`, extras y pago `PENDING_VERIFICATION` |
| `GET /manual-bookings` | Últimas 20 solicitudes manuales con pago |
| `POST /manual-bookings/{quote_id}/confirm` | Pago `VERIFIED`, cotización `CONVERTED`, evento reservado y contrato `ISSUED` |
| `GET /manual-bookings/{quote_id}/contract` | Nombre y PDF del contrato guardado en base64 |

El presupuesto recibe `client_name`, `event_date`, `start_time`, `address`, `package_id`, `theme_id` opcional, `extra_ids` y `client_provides_transport=true`.

El registro recibe multipart `payload_json` y `receipt_file`. El JSON contiene los datos anteriores más `quote_id` (UUID generado por el cliente para reintentos), `phone`, `district`, `payment_method` y `paid_amount`. Los precios vienen del catálogo, nunca del navegador. El importe recibido debe coincidir exactamente con el adelanto calculado.

La confirmación exige `{"receipt_verified": true}`: declaración del encargado después de revisar el comprobante y verificar la recepción del dinero.

## Controles

- Fecha/hora futura en Lima, recursos activos, temática compatible y extras sin duplicados.
- Evidencia hasta 5 MiB, MIME detectado por contenido y archivo UUID mediante el almacenamiento existente de E5.
- Confirmación serializada con un candado transaccional PostgreSQL y bloqueo de cotización. Reutiliza el motor de disponibilidad PostgreSQL/Redis.
- Conflicto de inventario o sobrecupo responde `409`: no crea evento ni contrato. Los overrides existentes siguen separados.
- Evento, pago, conversión, inventario, contrato y bitácora se guardan en una misma transacción. Se compensa el archivo PDF si falla la finalización.
- Repetir una confirmación retorna el mismo evento y contrato. Los futuros módulos que creen reservas deben incorporar la misma exclusión.
- Se conservan los importes de la cotización; duración y recursos vigentes del paquete se consultan al confirmar.

## Operación

`DATABASE_URL` privada con SSL conecta a Supabase por SQLAlchemy. No se entregan credenciales al navegador ni se utiliza PostgREST. No requiere migraciones nuevas ni cambios en grants.

En esta máquina Windows alcanza la conexión directa y Docker no tiene ruta a esa dirección. `scripts/start-demo.ps1` del frontend usa venv local y Redis aislado en puerto 56379. No inicia un worker inexistente ni ejecuta seeds o migraciones en la base compartida.

Evidencias y PDFs están en `LOCAL_STORAGE_PATH`; sus rutas están en Supabase. Un despliegue con varios servidores necesita almacenamiento compartido y respaldo. Los tests de integración continúan usando PostgreSQL local/Testcontainers.

El guion y la evidencia de la demostración están en `eventpro-frontend/EventPro-frontend/ENTREGABLE.md`.
