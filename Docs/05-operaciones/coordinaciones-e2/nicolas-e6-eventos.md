# Nicolas — Integración E6 con E2

Seguir la [guía de integración E2](README.md). E6 consume la confirmación producida por la firma E2 y adapta sus consultas y procesos a ese estado.

## Contrato de evento

- El evento previo a firma es `AWAITING_SIGNATURE`. La firma exitosa E2 confirma, en la misma transacción, contrato `SIGNED` y evento `SCHEDULED`.
- La nota operativa canónica es `events.client_observations`. El cronograma debe presentar su texto literal; el PDF obtiene la misma fuente. El endpoint E2 de edición de observaciones la actualiza y regenera el documento antes de firmar.
- El PDF administrativo se obtiene por `GET /api/v1/contracts/{id}/pdf` con rol permitido; E2 devuelve el sellado cuando hay evidencia de firma. No construir URLs públicas a rutas privadas de almacenamiento.
- La cancelación previa a ejecución puede permitir anular un contrato firmado según las reglas E2. El inicio real y estados de ejecución impiden esa anulación; no borrar la evidencia al cancelar.

## Entregables de Nicolas

- [ ] Consumir `SCHEDULED` sin agregar una segunda transición ni solicitar que E2 escriba otro estado para acomodar E6.
- [ ] Mantener las condiciones de asignación/pre-show/inicio; no iniciar un evento pendiente de firma por marcar manualmente `SIGNED` o `SCHEDULED`.
- [ ] Coordinar con Christian la carga inicial literal de observaciones y comprobar igualdad entre evento, cronograma y PDF. No atribuir a E2 la lectura de una columna de cotización todavía inexistente.
- [ ] Probar la lectura tras una firma confirmada y tras rollback de sellado: el segundo caso debe permanecer pendiente de firma.
- [ ] Verificar cancelación/anulación conservando contrato, PDF sellado, hash y auditoría; respetar el bloqueo de evento usado por E2.
- [ ] Entregar PR/evidencia de compatibilidad y coordinar con Diego los cambios de la frontera de estados o seguridad.

E6 reutiliza la firma y validación de token/OTP de E2. Sus consultas y procesos se conectan a esos resultados mediante adaptadores propios.
