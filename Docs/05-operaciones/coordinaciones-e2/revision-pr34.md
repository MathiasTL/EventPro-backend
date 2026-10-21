# Seguimiento de revisión técnica — PR #34

Revisión recibida sobre `6c40e00`, base `develop` en `f772a9b`. El revisor confirmó 2058 pruebas aprobadas, cobertura 91,91 %, un solo head y la corrección SQL de `qty`. Ese resultado corresponde al commit revisado, anterior a los ajustes siguientes.

| Observación | Ajuste preparado | Regresión |
| --- | --- | --- |
| P1: identidad de cliente existente | Distinguir campos omitidos y valores explícitos; conservar DNI/RUC omitidos, bloquear la fila de cliente y auditar cambios con actor y valores anteriores/nuevos. | Cliente preexistente: omisión conserva DNI/RUC, nombre explícito se audita y `null` explícito limpia solo el campo indicado. |
| P2: OTP vencido al firmar | Exigir `otp_expires_at` vigente además de la prueba JWT y demás validaciones. Responder 410 sin sellar, programar evento ni consumir enlace. | OTP verificado antes de vencer; firma posterior al vencimiento con prueba aún vigente. |
| P2: estado de emisión incompatible | Emitir únicamente para `AWAITING_SIGNATURE`; rechazar históricos `SCHEDULED` antes de crear PDF, contrato o mensaje. | Evento programado sin contrato: no deja documento, contrato ni encolado. |
| P2: descarga manual sin sello | Reutilizar `ManageContracts.pdf` también desde `/manual-bookings/{quote_id}/contract`. | Ambas rutas retornan el mismo PDF sellado, distinto del original. |
| Texto literal | Excluir observaciones y cláusulas del recorte de espacios del esquema. | Observaciones en cotización/evento y cláusulas en contrato conservan espacios y saltos de línea. |
| Duración del candado global | Preparar el PDF antes del candado de disponibilidad y adoptarlo en la confirmación, manteniendo almacenamiento y rollback transaccionales. | Durante el render no existe el candado global `180018`; se renderiza una sola vez. |

Las regresiones se añadieron sin ejecutar pytest localmente, por indicación de Diego. El resultado del nuevo código debe comprobarse mediante CI o los comandos de terminal indicados en la especificación E2.

## Evidencia y pendientes de integración

- El modo manual copia observaciones a cotización y evento; las regresiones verifican esos valores y el documento vigente. La firma mantiene `SIGNED`/`SCHEDULED`, auditoría y entrega encolada en una transacción.
- E5 debe completar y demostrar la copia inicial de `quotes.observations` al crear el evento del flujo conversacional. Las pruebas del modo manual no acreditan ese flujo de E5. Véase [coordinación con Christian](christian-e5-pagos.md).
- E6 debe demostrar el consumo del estado confirmado y las observaciones en su cronograma; la prueba de transición E2 no acredita por sí sola toda su operación. Véase [coordinación con Nicolas](nicolas-e6-eventos.md).
- Sigue pendiente la validación operativa con certificado de despliegue, worker, gateway y recepción de enlace/OTP/PDF por WhatsApp, incluida la ventana de servicio. La prueba criptográfica con certificado efímero no sustituye esa evidencia. Véase [coordinación con Mathias](mathias-e1-mensajeria.md).

Estos pendientes se mantienen visibles para la revisión y el despliegue; no se registran como completados ni se sustituyen por resultados de mocks.
