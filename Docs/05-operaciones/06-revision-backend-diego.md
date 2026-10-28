# Revisión del backend de Diego — E2

## Continuación implementada — 28 de octubre de 2026

Base: `34b4e2f`. Los apartados posteriores a esta continuación conservan la revisión inicial del día 27 y sus resultados históricos; los estados siguientes los sustituyen donde exista discrepancia.

### Correcciones completadas

- JWT: se exige `sub`, `iat` y `exp` en el decodificador común. Tokens ausentes/nulos, vencidos y sujetos no UUID tienen regresiones; el control HTTP devuelve 401. El rol sigue procediendo del usuario activo en BD, no del claim informativo. Los tokens normales emitidos por login ya contienen estos claims; no hay migración ni cambio de formato de respuesta.
- OTP: 20 verificaciones por IP/hora conforme a la matriz. La regresión HTTP reveló además que el límite anterior usaba la URL con el token como contador. Las cinco operaciones públicas de firma ahora usan scopes estables por operación e IP, compartidos entre tokens, sin mezclar los límites de operaciones diferentes.
- La prueba de límite verifica 20 aceptadas, bloqueo de la 21 con otro token, respuesta 429 con Retry-After, ausencia de ejecución del caso de uso al bloquear y contador independiente para otra IP. Se ejecuta con memoria aislada y también dispone de una variante con Redis real en integración. Los contadores persistentes por contrato y los cinco fallos por OTP no cambian.
- El plan E2 y la guía de coordinación remiten a esta evidencia y distinguen integración del PR #34, pruebas y despliegue.

### Revisión transversal de permisos y auditoría

Revisión de dependencias en routers y de los productores de auditoría, contrastada con la matriz vigente. Las suites HTTP existentes aportan pruebas de autorización y las de integración aportan persistencia; no se atribuye a esta inspección una validación del proxy o del frontend.

| Grupo | Control observado | Evidencia/resultado de revisión |
| --- | --- | --- |
| Usuarios | SUPERADMIN; cuenta/rol vigente mediante require_role | Cuatro operaciones de usuarios protegidas. Casos de desactivación, revocación y concurrencia en test_users. |
| Bitácora | SUPERADMIN/ENCARGADO, consulta sin escrituras expuestas | ListAuditLogs y router; filtros y rechazo de roles no autorizados en pruebas. |
| Contratos y manual E2 | Staff = SUPERADMIN/ENCARGADO | Listado, emisión, detalle, PDF, reenvío, anulación, observaciones y creación manual reutilizan Staff. La firma pública usa credencial token y OTP. |
| Cotizaciones, clientes, presupuestos y manual heredado | Personal administrativo | Dependencias de sus routers consultan cuenta/rol vigente. No se abren por el token público de firma. |
| Catálogo y elencos | Escrituras para personal; lectura pública del catálogo con filtrado | Mantener pruebas existentes de exclusión de costos/inventario de la vista pública. |
| Pagos y overrides | SUPERADMIN/ENCARGADO; reglas adicionales de autoverificación | Productores AuditPayment, ApproveOverbookedPayment y overrides de movilidad/tránsito utilizan AuditService. |
| Eventos y reportes | Roles administrativos; operador acotado por asignación en eventos | Las excepciones y uso de fakes de E3/E6 están documentados en RBAC. No se declaran cerradas sus integraciones reales por esta revisión. |
| Conversaciones | Staff y reglas de titularidad; SSE con rol vigente y expiración | Productores de envío/toma/reasignación registran acciones mediante AuditService. |
| Contratos: auditoría crítica | Emisión, regeneración, reenvío, anulación, manual y firma | ManageContracts, CreateManualContract y SignContract registran actor/evidencia; la firma pública carece de cuenta de panel y registra evidencia del firmante. Transacción compartida con documentos/evento/outbox y pruebas de rollback existentes. |

No se encontró otra discrepancia de roles en los grupos inspeccionados. Esto no certifica el comportamiento de módulos aún conectados a fakes ni la operación de otras épicas.

### Validación y bloqueos actuales

- Regresiones focalizadas: **28 aprobadas**.
- Ruff, formato y mypy: aprobados (572 archivos conformes; 360 módulos tipados).
- Docker Desktop iniciado y motor 29.5.3 disponible. La indisponibilidad de Docker de la revisión inicial quedó resuelta.
- Suite global con Testcontainers: primera ejecución con **2513 aprobadas**, 51 errores de preparación y un fallo, todos por ausencia de `pg8000`. Se instaló `pg8000 1.31.6`, ya declarado en requirements-dev.txt, sin modificar dependencias versionadas. Reejecución de los dos módulos afectados: **52 aprobadas** (37,82 s). Resultado conjunto: **2565 casos aprobados**, sin fallos pendientes, cobertura acumulada **92,72 %**. No se afirma una segunda ejecución global única: se repitieron los módulos afectados con `--cov-append`.
- Las pruebas incluyen PostgreSQL/Redis efímeros, firma con certificado efímero, rollback/concurrencia y migraciones. Cuatro advertencias en la primera ejecución: limpieza de conexiones SQLAlchemy y deprecaciones de dependencias criptográficas; no se declara ausencia de advertencias. La cobertura global no certifica el 100 % de dominio exigido por la DoD.
- `pip check` y `git diff --check`: aprobados. Logs locales ignorados por Git: `.pytest-e2-validation.log` y `.pytest-e2-retry.log`.
- Preflight local, sin revelar valores secretos: hay ruta y contraseña de certificado configuradas, pero el archivo no está disponible en esa ruta para el host; URL de firma sin HTTPS y Chatwoot sin URL configurada. La disponibilidad del certificado dentro de un despliegue debe comprobarse por separado.
- No se modificaron `.env`, certificados, Supabase ni Jira; no se enviaron mensajes reales. No se inventan credenciales ni se cambia la URL a un dominio ficticio.

### Pendientes que necesitan entorno/evidencia externa

1. Diego: disponer del certificado vigente en la ruta/montaje del servicio y dominio HTTPS real; probar sellado en la imagen de despliegue y revisar TLS/proxy/APM.
2. Diego y Mathias: configurar gateway y destinatario de prueba; demostrar recepción de enlace/OTP/PDF por el worker, con ventana abierta y plantilla fuera de ventana.
3. Christian/Nicolas: acreditar creación del evento y copia/consumo de observaciones en el flujo conversacional y cronograma reales. Diego revisa sus fronteras E2.
4. Equipo: revisión cruzada de estos cambios y despliegue coordinado. No marcar una historia completa solo por superar las pruebas aisladas.

## Revisión inicial — 27 de octubre de 2026

Fecha: 27 de octubre de 2026. Base revisada: `34b4e2f`, rama `feat/e2-integracion-firma-seguridad`.

## Conclusión

Las cinco historias de Diego tienen implementación y pruebas en el repositorio: US-23 usuarios, US-24 auditoría, US-13 PDF, US-14 contingencia manual y US-15 firma. No corresponde volver a implementar esas entregas. Falta cerrar las discrepancias indicadas abajo y acreditar integración y operación. Esta revisión no equivale a certificar el despliegue ni todos los requisitos transversales del sistema.

El PR #34 ya pertenece al historial de develop. El plan anterior usa el corte `97835c1` y todavía describe contratos/firma como implementación local pendiente de PR: esos estados documentales ya no representan la integración actual.

## Hallazgos y acciones de Diego

| Prioridad | Hallazgo y evidencia | Acción y criterio de cierre |
| --- | --- | --- |
| P2 | Verificación OTP permite `30/hour` en `app/infrastructure/adapters/primary/web/v1/contract_signing_router.py:113`; la matriz RBAC exige 20 por IP y hora en `Docs/04-api/02-matriz-rbac-y-seguridad.md:222`. El límite de cinco fallos por OTP existe por separado. | Diego: aplicar el límite documentado y añadir una regresión con Redis aislado: la solicitud 21 debe devolver 429. No eliminar el contador por OTP. |
| P2 | `decode_access_token` en `app/core/security.py` valida firma/algoritmo, pero no exige la presencia de `exp`. Se reprodujo con un JWT HS256 firmado con una clave artificial y sin exp: la función lo acepta. `_authenticate` tampoco exige exp para las rutas normales; SSE sí lo exige. | Diego: exigir los claims temporales/de identidad definidos por el contrato de autenticación y probar rechazo de exp ausente, token vencido y sub inválido. Los tokens emitidos por el login ya incluyen exp. No se demostró falsificación ni acceso sin conocer el secreto. |
| P2 | No hay validación de integración ejecutada en esta revisión: Docker no tiene daemon disponible, incluso fuera del sandbox. | Diego: iniciar Docker y ejecutar las pruebas de integración con PostgreSQL/Redis efímeros; conservar resultado y commit. No sustituir por SQLite ni usar Supabase. |
| P2 | Firma de despliegue y entrega real siguen sin evidencia en el seguimiento E2. Un certificado efímero y un adaptador falso no demuestran entrega WhatsApp. | Diego con Mathias: validar certificado vigente en Docker, dominio público HTTPS, worker y recepción de enlace/OTP/PDF, incluida la ventana de servicio. Guardar evidencia sin secretos. |
| P3 | Plan y tabla de coordinación conservan estados anteriores a la integración de E2 y de PR posteriores. | Diego: actualizar los estados con commits/PR verificables, manteniendo separados integración, pruebas y despliegue. No cerrar una coordinación solo por tener código fusionado. |

No se modificó código de aplicación ni se implementaron estas correcciones durante la revisión.

## Matriz de evidencia

| Responsabilidad | Estado observado | Evidencia y límite |
| --- | --- | --- |
| Identidad, contraseña y RBAC | Implementado; endurecimiento pendiente | `app/core/security.py`, `web/deps.py`: hash mediante pwdlib, JWT HS256, usuario activo y rol consultados en BD en cada petición. Suites de seguridad/auth/users disponibles; persistencia pendiente de ejecutar. |
| US-23 usuarios | Implementado | Rutas restringidas a SUPERADMIN; pruebas de integración incluyen desactivación, revocación y cambios de rol. No se reabre la historia integrada, pero sus garantías concurrentes requieren pruebas con PostgreSQL. |
| US-24 bitácora | Implementado | Router y servicio de auditoría; pruebas de filtros, paginación estable y rechazo de OPERADOR/anónimo. Overrides de movilidad y tránsito invocan AuditService. No constituye un inventario exhaustivo de todas las acciones de las seis épicas. |
| US-13 contratos | Implementado | `ManageContracts`: emisión requiere evento AWAITING_SIGNATURE y adelanto suficiente, contrato vigente, rotación, anulación y observaciones. Suites de gestión y PDF; atomicidad real pendiente. |
| US-14 manual | Implementado | Flujo manual y suites de identidad preservada, cantidades, notas, rollback e idempotencia. No trasladar a Diego las correcciones del flujo heredado asignadas a su autor. |
| US-15 firma | Implementado; validación operativa pendiente | Token almacenado como hash, OTP HMAC, expiración, prueba ligada al enlace/OTP, PNG y aceptación estricta, sello, SHA-256, SIGNED/SCHEDULED y mensaje DOCUMENT. Suites de aplicación cubren OTP vencido tras verificar y prueba antigua. |
| Privacidad y plataforma | Parcialmente verificado | `app/main.py:70` añade no-store/no-referrer a firma; filtro Uvicorn redacta token; adaptador PAdES verifica vigencia y neutraliza errores. TLS, proxy/APM, secretos y logs del despliegue no inspeccionados. |
| Migraciones | Cadena estática verificada | `alembic heads`: único head `0009_inbox_support`, hijo de `0008_contract_signature`. Upgrade/downgrade y correspondencia con modelos requieren BD efímera. El downgrade de 0009 elimina vínculos sin cliente: nunca ejecutarlo sobre la base compartida como comprobación. |

Las referencias abreviadas a web/deps.py y ManageContracts corresponden a los módulos existentes bajo app/infrastructure/adapters/primary y app/application/use_cases/contract respectivamente.

## Dependencias sin reasignación de responsabilidades

| Responsable | Evidencia que falta reunir | Participación de Diego |
| --- | --- | --- |
| Christian · E5 | Creación del evento conversacional y copia inicial de observaciones; pago y emisión compatibles en la misma operación. VerifyPayment/ApproveOverbookedPayment ya llaman al emisor E2. | Revisar la frontera E2 y sus pruebas; no asumir creación del evento de E5. |
| Mathias · E1 | Entrega real por outbox/worker/gateway, manejo de ventana y redacción de datos sensibles. | Proveer/verificar enlace, OTP y PDF firmado y sus configuraciones. |
| Nicolas · E6 | Consumo de SCHEDULED y observaciones en la operación del evento. | Acreditar transición E2 y revisar compatibilidad. La transición sola no demuestra todo el cronograma. |
| David · E3 | Disponibilidad/reservas compatibles y cadena de migraciones vigente. | Revisar pruebas de concurrencia y mantener un head. |
| Renzo · E4 | Evidencia de permisos y auditoría de overrides integrados. | Revisar uso de servicios compartidos y efectos transaccionales. |

## Validación ejecutada

- Ruff: `python -m ruff check .` aprobado.
- Formato: `python -m ruff format --check .` aprobado; 571 archivos conformes.
- Tipado: `python -m mypy app` aprobado; 360 archivos.
- Alembic: `python -m alembic heads` devuelve `0009_inbox_support (head)`; no se conectó a ninguna BD.
- Primera ejecución sin integración: 2139 aprobadas y 113 errores de preparación por acceso denegado al directorio temporal pytest; no representan 113 fallos funcionales. Se repitió fuera del sandbox con cobertura.
- Resultado de la repetición fuera del sandbox: **2252 aprobadas**, 3 advertencias, **84,96 % de cobertura** (112,17 s). Son las suites unit, application, domain e infrastructure; no incluye integration. El umbral del 75 % se superó incluso sin integración, pero no acredita la cobertura de la suite global ni el 100 % de dominio exigido por la DoD.
- Integración y suite global: bloqueadas por Docker no iniciado. No se ejecutaron migraciones compartidas ni llamadas a WhatsApp.

Comando de repetición (Python del entorno `.venv`):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit tests/application tests/domain tests/infrastructure -q --tb=short --cov=app --cov-report=term --cov-fail-under=75
```

Cuando Docker esté disponible, ejecutar `python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=75` desde el mismo entorno tras comprobar que los fixtures siguen usando Testcontainers. Las suites de integración existentes cubren firma concurrente, rollback, errores de PDF/outbox, identidad, pagos y migraciones. Los resultados de mocks no reemplazan esas comprobaciones.

## Orden de cierre recomendado

1. Corregir y probar claims JWT obligatorios y límite OTP.
2. Ejecutar integración aislada, migraciones y suite global; resolver cualquier regresión antes del cierre.
3. Reunir evidencias E1/E5/E6 y completar revisión transversal de permisos/auditoría por endpoint contra la matriz.
4. Validar operación real de firma, TLS y entrega con el equipo.
5. Actualizar seguimiento, documentar resultados y obtener revisión cruzada para los cambios nuevos.
