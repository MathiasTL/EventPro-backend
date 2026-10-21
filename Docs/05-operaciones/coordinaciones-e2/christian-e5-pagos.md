# Christian — Integración E5 con E2

Seguir la [guía de integración E2](README.md). E5 adapta su flujo al puerto existente de E2, manteniendo la creación y reserva del evento del flujo conversacional en su propia orquestación.

## Contrato que debes proveer

- `event_id` existente, vinculado a la misma `quote_id` del pago, estado `AWAITING_SIGNATURE`, datos comerciales completos e importes consistentes.
- Pago `ADVANCE` que solo se verifica tras revisar evidencia y disponibilidad. E2 suma exclusivamente pagos `VERIFIED` vinculados al evento y a su cotización; requiere un adelanto positivo que alcance el importe exigido.
- Observaciones iniciales copiadas literalmente de `quotes.observations` a `events.client_observations` antes de emitir. La columna de cotización ya está integrada en develop mediante `0006_quote_observations`; E5 completa la copia en su creación del evento con Mathias/Nicolas.

## Punto de integración existente

[`IContractIssuer`](../../../app/application/ports/output/contract_port.py) expone:

```python
await issuer.prepare_payment_event(event_id, quote_id)
# Guardar la verificación del pago con flush, sin commit independiente.
await issuer.issue_for_event(event_id, verified_by_user_id)
# La unidad transaccional confirma pago, documentos, contrato y outbox juntos.
```

Usar los casos de uso y proveedores ya conectados en `VerifyPaymentUseCase`, `ApproveOverbookedPaymentUseCase` y `containers.py`. El pseudocódigo describe el contrato, no ordena agregar una segunda llamada a los flujos que ya emiten. `PATCH /payments/{id}/verify` exige `event_id` cuando verifica con la integración E2 activa.

## Entregables de Christian

- [ ] Completar o demostrar la creación del evento y sus reservas del flujo conversacional, compartiendo la transacción de verificación/emisión y los bloqueos de disponibilidad.
- [ ] Mantener `commit_on_save=False` para el repositorio de pagos participante; no quitar el emisor del proveedor de producción para evitar errores de integración.
- [ ] Adaptar entradas propias a UUID/estados/importes E2; rechazar evento de otra cotización y adelanto insuficiente.
- [ ] Conservar el flujo de aprobación/rechazo de sobrecupo; no marcar un contrato como firmado para saltarse la firma.
- [ ] Entregar evidencia de rollback si fallan PDF, documentos, auditoría o encolado; verificar que un reintento no duplica contrato ni mensaje.
- [ ] Coordinar con Diego los cambios que afecten a los proveedores compartidos de verificación o emisión.

E5 entrega el evento y la verificación en la transacción que consume E2. `/contracts/manual` conserva su creación atómica para contingencia; el flujo conversacional utiliza la orquestación de E5.
