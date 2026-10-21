# Coordinaciones de integración E2 — Diego

**Responsable de E2:** Diego. **Fecha:** 20 de octubre de 2026. **Alcance:** backend.

La implementación actual de E2 y su [especificación](../../02-arquitectura/09-spec-e2-contratos-pdf.md) son la referencia de integración. Cada integrante adapta sus casos de uso, adaptadores y configuración a las entradas, salidas y estados que E2 ya utiliza. Las diferencias de formato se resuelven en el módulo del integrante, manteniendo estable la interfaz E2.

Los archivos individuales describen los puntos de conexión, las tareas de cada responsable y las comprobaciones de compatibilidad. El seguimiento registra los avances conforme se incorporen los PR y sus evidencias.

## Base técnica compartida

1. Mantener las rutas, DTO, puertos, estados, validaciones y límites de la entrega E2. Si un módulo usa otro formato, su responsable debe implementar el adaptador en su lado de la frontera.
2. Usar `require_role(...)`, el rol vigente en BD y `AuditService`/puertos existentes. No duplicar autenticación, autorización, emisión de contratos ni firma en otra épica.
3. Conservar la atomicidad: pago, contrato, documentos, auditoría y outbox que pertenezcan a una operación deben compartir la transacción. Ningún adaptador participante debe confirmar por separado. No sustituir la cola por un envío HTTP directo desde la transacción comercial.
4. Respetar `DRAFT → ISSUED → SIGNED` y `VOIDED` bajo las reglas del agregado; solo la firma E2 confirma `SIGNED` y su transición asociada a `SCHEDULED`. Preservar evidencias y consumo único del token.
5. Mantener observaciones literales en `events.client_observations`, importes PEN con decimales y saldo `total − adelanto`, incluida movilidad. Cada productor debe entregar datos compatibles antes de llamar a E2.
6. Respetar los bloqueos y el orden de adquisición de la operación integrada. La reserva de capacidad usa el candado PostgreSQL compartido `AVAILABILITY_LOCK_KEY` y la comprobación existente de disponibilidad; no inventar otro candado incompatible.
7. Coordinar las migraciones con un solo head. La cadena local E2 es `0005_event_financial_snapshots → 0006_contract_management → 0007_contract_signature`. No editar migraciones ya aplicadas ni eliminar evidencia para facilitar un downgrade. Si develop avanza, resolver la cadena en el PR y con revisión de Diego.
8. No incluir token, OTP, `otp_proof`, claves, certificado o firma manuscrita en logs ni respuestas administrativas. Conservar redacción del outbox y configurar redacción equivalente en proxy/APM.

## Responsables y entregables

| Responsable | Guía de coordinación | Resultado de integración |
| --- | --- | --- |
| Christian · E5 | [Pagos y creación de evento](christian-e5-pagos.md) | Evento y adelanto compatibles; emisión de contrato en la misma transacción. |
| Mathias · E1 | [Mensajería y cotización](mathias-e1-mensajeria.md) | Entrega de enlace/OTP/PDF a través del outbox y gateway existentes. |
| Nicolas · E6 | [Evento, observaciones y cronograma](nicolas-e6-eventos.md) | Consumo correcto de `SCHEDULED`, observaciones y documento firmado. |
| David · E3 | [Catálogo, disponibilidad y migraciones](david-e3-disponibilidad.md) | Catálogo compatible y reservas concurrentes sin sobreventa. |
| Renzo · E4 | [Permisos, auditoría y overrides](renzo-e4-auditoria.md) | Cambios auditados que preservan las invariantes de E2. |

La asignación del autor del flujo `/manual-bookings` se conserva según el historial y la especificación 08; no se presupone que sea David. Su responsable debe cumplir las condiciones comunes y coordinar cualquier cambio del almacén reutilizado con Diego.

## Qué debe contener cada PR de integración

- Enlace al archivo de coordinación correspondiente y a la especificación E2.
- Relación de entradas, salidas y estados que consume/provee; ubicación del adaptador del integrante.
- Evidencia de compatibilidad y resultados de las pruebas aplicables, ejecutadas por el integrante. No declarar aprobadas pruebas que solo se escribieron.
- Demostración de rollback, reintento y concurrencia cuando afecte la operación; comprobación de permisos y ausencia de secretos.
- Migraciones y configuración necesarias, sin secretos; riesgos operativos concretos y pendientes explícitos.
- Revisión técnica de la frontera E2 y revisión cruzada según la gobernanza existente.

La comprobación se realiza contra los contratos y adaptadores reales de E2. Los fakes conservan las mismas entradas, salidas, estados y comportamiento transaccional.

## Cambios y discrepancias

Las diferencias entre modelos se resuelven mediante adaptadores en el módulo que conecta con E2. Si aparece un error en E2 o un requisito nuevo que afecte su contrato, documentar el caso, su impacto y la solución con Diego, manteniendo compatibilidad con los consumidores y las restricciones del gateway.

## Seguimiento

| Responsable | Coordinación | PR/enlace de evidencia | Validación de compatibilidad E2 |
| --- | --- | --- | --- |
| Christian | Pendiente | Pendiente | Pendiente |
| Mathias | Pendiente | Pendiente | Pendiente |
| Nicolas | Pendiente | Pendiente | Pendiente |
| David | Pendiente | Pendiente | Pendiente |
| Renzo | Pendiente | Pendiente | Pendiente |

Las casillas de los archivos individuales son entregables pendientes de sus responsables; no certifican fallos actuales ni reasignan toda su épica a Diego.
