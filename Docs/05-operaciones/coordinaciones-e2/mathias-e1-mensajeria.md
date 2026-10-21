# Mathias — Integración E1 con E2

Seguir la [guía de integración E2](README.md). E1 adapta el transporte para consumir los mensajes que E2 produce mediante el outbox existente y enviarlos por el gateway.

## Formatos existentes que debes soportar

| Tipo | Payload de E2 | Tratamiento requerido |
| --- | --- | --- |
| `TEXT`, enlace u OTP | `body`, `contract_id` | Despachar mediante `send_text`; respetar `redact_after_send=True`. `contract_id` permite invalidar mensajes sensibles aún pendientes. |
| `DOCUMENT`, PDF firmado | `path`, `filename`, `content_type`, `caption` | Leer `path` con `IDocumentSourcePort`/`StorageDocumentSource`; enviar bytes mediante `send_attachment`. No tratar `database/...` como URL pública. |
| `TEMPLATE` | `name`, `params` | Formato ya soportado por el despachador para plantillas aprobadas. No confundirlo con un `TEXT` fuera de ventana. |

Referencias: [`EnqueueMessage`](../../../app/application/use_cases/messaging/enqueue_message.py), [`DispatchDueMessages`](../../../app/application/use_cases/messaging/dispatch_due_messages.py), [`IMessagingPort`](../../../app/application/ports/output/messaging_port.py).

## Entregables de Mathias

- [ ] Configurar y demostrar worker, gateway y entrega real de enlace, OTP y PDF firmado con estos formatos. `SENT` significa aceptación por Chatwoot, no recepción confirmada por WhatsApp.
- [ ] Conservar reintentos, idempotencia de transporte y redacción; no registrar cuerpos OTP, tokens, pruebas OTP o adjuntos de firma.
- [ ] Resolver la entrega fuera de ventana de 24 horas con plantillas aprobadas y un adaptador de mensajería/orquestación compatible. Entregar nombres, idioma, variables, mapeo y evidencia para revisión de Diego. No afirmar que la plantilla ya está configurada: E2 hoy encola enlaces/OTP como `TEXT` y el PDF como `DOCUMENT`.
- [ ] Respetar las restricciones del proveedor y reflejar el estado real del envío. Documentar con Diego cualquier requisito nuevo que afecte al contrato de aplicación.
- [ ] Proveer cotización, cliente y catálogo con los campos que lee `SqlAlchemyContractRepository.event_data`; coordinar con Christian el origen de observaciones sin reescribirlas.
- [ ] Entregar evidencia de lectura privada de documentos y del comportamiento de mensajes pendientes cuando se rota/anula el enlace.

E1 resuelve el mapeo de transporte y su configuración a partir del payload existente de E2. Los requisitos adicionales del proveedor se documentan con su impacto en la integración.
