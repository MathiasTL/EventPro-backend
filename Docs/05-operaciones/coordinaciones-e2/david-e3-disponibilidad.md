# David — Integración E3 con E2

Seguir la [guía de integración E2](README.md). E3 adapta sus modelos internos a los puertos y DTO existentes que E2 consume para catálogo y disponibilidad.

## Contratos existentes

- [`ICatalogReadPort`](../../../app/application/ports/output/catalog_read_port.py): paquetes activos, duración, precios, temáticas compatibles, extras y requerimientos de inventario.
- [`IAvailabilityPort`](../../../app/application/ports/output/availability_port.py): disponibilidad para fecha/hora/duración/paquete, faltantes y necesidad de aprobación manual.
- `AVAILABILITY_LOCK_KEY` en `sqlalchemy_event_occupancy.py`: candado transaccional PostgreSQL compartido para escritores de reservas. Los flujos existentes combinan este candado con el adaptador de disponibilidad y sus locks Redis.

## Entregables de David

- [ ] Mantener DTO de lectura, UUID, importes decimales y compatibilidad de temáticas usados por la emisión y el modo manual E2.
- [ ] Asegurar que todo nuevo escritor de reservas participe en el mismo protocolo y orden de bloqueo, preservando consultas autoritativas dentro de la operación.
- [ ] Probar concurrencia entre escritores, paquetes distintos que comparten inventario y eventos que cruzan medianoche; no limitar la demostración a dos peticiones idénticas.
- [ ] Conservar el rechazo atómico de `/contracts/manual` ante falta de capacidad/sobrecupo; su aprobación pertenece al flujo específico existente, no a una rebaja de validaciones en E2.
- [ ] Coordinar catálogo/seeds y migraciones sin cambiar PK, campos o restricciones consumidos por E2 de manera incompatible. Revisar la cadena local `0006`/`0007` antes de crear la siguiente revisión.
- [ ] Coordinar con el autor identificado del flujo manual cualquier cambio en `SqlAlchemyManualBookingStore`: `/contracts/manual` lo reutiliza sin commits internos y admite `draft=True` con PDF nulo. No retirar estas capacidades al migrar el flujo a repositorios de E1.
- [ ] Entregar evidencia de que una operación fallida no deja reservas, pago, documento o contrato parciales.

La adaptación de los modelos de catálogo/capacidad se realiza en E3. Los cambios del flujo manual se coordinan con su autor, identificando al responsable en el PR.
