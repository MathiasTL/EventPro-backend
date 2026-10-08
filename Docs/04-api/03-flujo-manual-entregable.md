# Flujo administrativo de solicitud, adelanto y contrato

## Alcance y estados

El encargado captura la solicitud que normalmente llegaría por WhatsApp. El proceso implementado es solicitud → presupuesto → comprobante → revisión humana del ingreso de dinero → reserva del evento e inventario → contrato PDF `ISSUED`. El evento queda `AWAITING_SIGNATURE`. Firma electrónica, transferencia bancaria y envío por WhatsApp no se presentan como automatizados.

Los precios de servicios proceden del catálogo. `ADVANCE_PERCENT` configura el adelanto sobre servicios (10 por defecto); movilidad no aumenta ese adelanto. `pending_balance` representa el saldo de servicios; movilidad se paga adicionalmente. Si el cliente aporta transporte, movilidad es cero. Si no, el encargado declara `manual_mobility_amount > 0` y `mobility_override_reason` (10..500 caracteres); queda auditado como `OVERRIDE_MOBILITY`. No se simula una tarifa de Maps.

## API implementada

Prefijo `/api/v1`. Todas las rutas requieren `ENCARGADO` o `SUPERADMIN` con cuenta activa y rol vigente en BD.

| Método y ruta | Resultado |
| --- | --- |
| `POST /budgets/prepare` | Presupuesto calculado, disponibilidad y PDF persistido; no reserva ni crea cotización comercial |
| `GET /budgets/{budget_id}/document` | Recupera el mismo PDF mediante su referencia |
| `POST /manual-bookings` | Cliente, cotización PAYMENT_STARTED, extras, comprobante y adelanto |
| `GET /manual-bookings?page=1&page_size=20` | Array paginado (máximo 100), compatible con el panel |
| `POST /manual-bookings/{quote_id}/confirm` | Verifica adelanto, reserva recursos y emite contrato en una transacción |
| `POST /manual-bookings/{quote_id}/refund` | Solicita o confirma devolución de un adelanto sin reserva |
| `GET /manual-bookings/{quote_id}/contract` | Nombre y PDF del contrato en base64 |

El presupuesto recibe `client_name`, `event_date`, `start_time`, `address`, `package_id`, `theme_id` opcional, `extra_ids`, `client_provides_transport` y los campos opcionales de movilidad manual.

El registro recibe multipart `payload_json` y `receipt_file`. El JSON agrega `quote_id` (UUID de idempotencia), `phone`, `district`, `payment_method` y `paid_amount`. Los teléfonos locales de nueve dígitos se normalizan a +51; se reconoce el teléfono legado sin modificar datos ajenos. El nombre del contacto existente se conserva como nombre maestro. El importe debe coincidir con el adelanto calculado en el servidor.

Un replay idéntico retorna 200; creación, 201. La huella incluye todos los campos normalizados y SHA-256 del comprobante. Reutilizar la referencia con datos diferentes o presentar la misma solicitud activa con otra referencia retorna 409. Se respalda con un índice único en PostgreSQL.

La confirmación recibe `{"receipt_verified":true}`. Quien registró el pago no puede verificarlo: únicamente SUPERADMIN puede exceptuar esta separación con `override_reason`, registrado en bitácora. Un sobrecupo exige además `approve_overbooking=true` y motivo. El override permite superar el umbral de simultaneidad; nunca inventa stock.

Si no hay disponibilidad al recibir el comprobante o al confirmar, se conserva el pago en REQUIRES_MANUAL_APPROVAL, sin evento ni contrato. Para rechazar ese sobrecupo se usa refund con `{"action":"REQUEST","reason":"Motivo documentado"}`: REFUND_PENDING y cotización CANCELLED. Después de realizar realmente la devolución se declara `{"action":"CONFIRM","reason":"Referencia de devolución realizada"}`: REFUNDED. El backend registra la decisión; no efectúa una transferencia bancaria.

## Integridad y concurrencia

- Confirmación exige cotización PAYMENT_STARTED, vigente durante 24 horas, evento futuro y pago pendiente o en revisión. El vencimiento se valida al confirmar, sin depender de un job de expiración.
- El dominio Payment valida verificación, aprobación, revisión y reembolso. Se registran capturador, verificador, cambios del pago, conversión de cotización y emisión del contrato.
- Se utiliza AVAILABILITY_LOCK_KEY=180018, compartido con otros escritores de ocupación, y bloqueo de cotización. Disponibilidad y store reciben la misma sesión cacheada de FastAPI. No se abre otra conexión bajo el candado.
- El comprobante se lee antes del bloqueo por clave. El PDF se renderiza antes del candado global en un threadpool. Bajo el candado se revalidan estados, capacidad y catálogo y se guardan las filas.
- Cada operación tiene commit explícito antes de responder HTTP. get_session conserva su comportamiento original. Las escrituras de catálogo se corrigen en un PR independiente.
- Repetir confirmación devuelve el mismo evento y contrato. El listado usa dos consultas para cualquier tamaño de página.
- Documentos nuevos se almacenan en espacios separados de booking_documents dentro de PostgreSQL. Rollback revierte conjuntamente archivo y filas comerciales. No se elimina un PDF durable tras un resultado de commit incierto.

## Migración y despliegue

Requiere Alembic `0003_manual_booking_documents`, posterior a 0002_event_extensions: columna de idempotencia, índice único y archivos privados de hasta 5 MiB. No elimina ni reescribe datos comerciales existentes. Los permisos de PUBLIC, anon, authenticated y service_role sobre documentos se revocan. El navegador accede solo al backend autenticado.

La migración se valida en PostgreSQL efímero/Testcontainers. Aplicarla a la base compartida corresponde al despliegue autorizado después de revisar los PRs. La base compartida no se migra como parte de las pruebas. No usar downgrade en el entorno compartido sin coordinación.

Los archivos anteriores conservan lectura por el adaptador local. Antes de desplegar múltiples instancias con datos anteriores, deben copiarse esos archivos y actualizarse sus referencias mediante una migración operativa coordinada. Los documentos nuevos son compartidos y se incluyen en el respaldo de PostgreSQL; con volúmenes altos convendrá sustituir el puerto por almacenamiento de objetos.

ReportLab es el único motor PDF de runtime, con plantilla manual-v1. El texto contractual requiere aprobación del responsable del negocio antes de usarlo con clientes reales. No acredita firma ni sello PAdES. ADR-11 explica las decisiones y diferencias respecto a pagos genéricos.
