# Renzo — Integración E4 con E2

Seguir la [guía de integración E2](README.md). E4 adapta sus overrides a la seguridad y auditoría existentes de E2, preservando el documento que el cliente firmó.

## Contratos existentes

- [`require_role(...)`](../../../app/infrastructure/adapters/primary/web/deps.py) verifica cuenta y rol vigentes; no confiar únicamente en el claim de rol del JWT.
- [`AuditService.record(...)`](../../../app/application/services/audit_service.py) recibe acción, entidad, UUID, usuario y valores anteriores/nuevos. Las acciones deben existir en `AUDIT_ACTIONS` y en el CHECK de PostgreSQL.
- `SQLAlchemyAuditLogAdapter(session_factory, session=session)` participa en la transacción comercial mediante `flush`; el modo con solo fábrica confirma por separado y no satisface una operación que deba ser atómica.

## Entregables de Renzo

- [ ] Proteger las rutas con los roles de la matriz RBAC, reutilizando dependencias E2; conservar rechazo de cuenta inactiva o rol degradado.
- [ ] Auditar movilidad e intervalos con `OVERRIDE_MOBILITY` y `OVERRIDE_TRANSIT_INTERVAL`, actor, motivo y valores anteriores/nuevos.
- [ ] Vincular auditoría a la misma transacción cuando la operación requiera atomicidad. Un fallo de auditoría debe impedir confirmar el override.
- [ ] Usar las acciones del vocabulario y el puerto de auditoría existentes. Coordinar con Diego las nuevas acciones, manteniendo código y migración coherentes.
- [ ] No cambiar importes, cláusulas o evidencia del contrato firmado mediante un override. Canalizar cambios previos a firma por los casos de uso E2; una edición de notas E2 regenera PDF y rota el enlace.
- [ ] Verificar permisos, motivo registrado, rollback y conservación del documento sellado; entregar evidencia en el PR de integración.

E4 adapta sus DTO y servicios a estos contratos, reutilizando el sistema de auditoría y los roles existentes de E2.
