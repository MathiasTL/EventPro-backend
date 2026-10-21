# E2 — Contratos PDF, contingencia y firma (US-13, US-14 y US-15)

## Capacidad implementada

El backend emite contratos a partir de un **evento existente con adelanto verificado** y permite listarlos, consultar su detalle, descargar su PDF, regenerar observaciones, reenviar el enlace y anularlos. También implementa creación manual atómica (US-14) y la API pública de firma con OTP y sello PAdES (US-15). El agregado `Contract` aplica `DRAFT`, `ISSUED`, `SIGNED` y `VOIDED`. Esta entrega comprende solo backend, está sin publicar y requiere validación de Diego.

La generación usa ReportLab, el motor PDF ya presente en runtime y en el flujo manual (ADR-11), en un threadpool para no bloquear el event loop. No añade WeasyPrint ni bibliotecas GTK. El documento incluye correlativo, cliente/DNI/RUC/teléfono, fecha y horario, dirección, paquete, temática, extras, subtotal de servicios, movilidad, total, adelanto efectivamente verificado y saldo `total − adelanto`; las observaciones literales tienen una sección propia. El PDF emitido declara que está pendiente de firma. El contenido contractual debe contar con la revisión del negocio antes del uso con clientes reales.

## API administrativa

Prefijo `/api/v1`; todas las rutas requieren cuenta activa `ENCARGADO` o `SUPERADMIN`. `OPERADOR` recibe 403 y una petición sin JWT, 401. No se devuelven rutas privadas, hashes del token, OTP ni secretos del outbox.

| Método y ruta | Entrada / comportamiento |
| --- | --- |
| `GET /contracts` | Filtros `status`, `event_id`, `is_manual_mode`, `page >= 1`, `page_size` de 1 a 100; respuesta `items`, `page`, `page_size`, `total`. Orden descendente por fecha e ID. |
| `POST /contracts` | `{"event_id":"<uuid>"}`; emite o recupera el contrato vigente con 200. Sirve para recuperar eventos anteriores al despliegue o emitir después de una anulación. No crea eventos ni verifica pagos. |
| `GET /contracts/{id}` | Estado, número, evento, modo manual y metadatos administrativos de firma. |
| `GET /contracts/{id}/pdf` | PDF binario con `Cache-Control: private, no-store`. Un borrador devuelve 404. Si hay evidencia de firma devuelve el PDF sellado, incluso después de anular; conserva la evidencia anterior. |
| `POST /contracts/{id}/resend-link` | Solo `ISSUED`: reemplaza token, reinicia OTP y encola el nuevo enlace; la respuesta incluye su vencimiento, nunca el token en claro. |
| `PATCH /contracts/{id}/observations` | `{"client_observations":"texto o null"}` (campo obligatorio, máximo 5000 caracteres). Cambia la nota del evento, que lee el cronograma, y regenera PDF con auditoría. En `ISSUED` rota el enlace; un borrador permanece `DRAFT` sin enviar enlace. Un cambio idéntico no regenera. |
| `POST /contracts/{id}/void` | `{"reason":"motivo"}`; invalida enlace y OTP. Un firmado exige evento cancelado antes de su ejecución. No anula contratos durante o después de un evento iniciado. |

Recursos inexistentes responden 404; estados o adelanto incompatible, 409 `invalid-contract-state`; entradas inválidas, 422. Un contrato firmado o anulado no admite editar sus observaciones ni reenviar el enlace. Los contratos anteriores emitidos por el flujo manual conservan su PDF y correlativo al incorporarse a este módulo.

## Transacciones e integración

- Los puertos de contrato, almacenamiento privado y outbox usan la misma sesión PostgreSQL. La ruta confirma antes de enviar la respuesta HTTP (`scope="function"`); un fallo de render, almacenamiento, auditoría o cola revierte la operación completa.
- El evento se bloquea para serializar emisión, regeneración, reenvío y anulación. El índice único parcial existente asegura un solo contrato no anulado por evento. Repetir una emisión devuelve el mismo contrato y no vuelve a generar PDF ni mensaje.
- E5 entrega el evento: la ruta genérica `PATCH /payments/{id}/verify` exige `event_id` al verificar; comprueba que pertenece a la cotización del pago. Guarda pago y contrato juntos. Esta integración no implementa la creación de evento ni las reservas de inventario del flujo conversacional de E5. La aprobación de sobrecupo aplica la misma integración.
- La confirmación del flujo `/manual-bookings` ya crea evento, reservas y PDF; ahora incorpora enlace y auditoría de emisión en esa misma confirmación. El PDF sigue renderizándose antes del candado global de disponibilidad. Los números nuevos usan el correlativo común; los antiguos no se renumeran.
- El enlace usa un token criptográfico de 32 bytes, hash SHA-256 en `contracts`, y `SIGNATURE_LINK_TTL_HOURS` (168 por defecto). El token solo se incluye en el mensaje pendiente del outbox, marcado para redacción tras envío. Rotar o anular también marca como fallidos y redacta los mensajes anteriores aún pendientes; un mensaje ya enviado o en vuelo puede contener el enlace anterior, que queda inválido.
- El envío es **encolado**, no confirmado por WhatsApp: el worker y Chatwoot determinan la entrega. Enlaces y OTP usan texto libre, sujeto a la ventana de 24 horas del gateway; el envío fuera de ventana requiere integrar una plantilla aprobada con E1. El PDF firmado usa `DOCUMENT` y el lector privado de `booking_documents` ya existente.
- La fuente de observaciones es `events.client_observations`. La copia inicial desde cotizaciones sigue siendo responsabilidad de la creación del evento en E1/E5/E6; esta entrega permite corregirlas y reflejarlas en cronograma y PDF antes de firmar.

## Migración y configuración

Aplicar **solo al desplegar** `0007_contract_management` después de `0006_quote_observations` (PR #32 de develop). La revisión crea `contract_number_seq`, inicializada por encima de los correlativos numéricos existentes, y agrega `CONTRACT_ISSUED`, `CONTRACT_LINK_RESENT`, `CONTRACT_REGENERATED` y `CONTRACT_VOIDED` al vocabulario de auditoría. Los números nuevos tienen formato `CTR-año-0001` con secuencia global creciente; no se reinicia por año y puede tener saltos tras rollback. Se permite anular un borrador sin PDF. Las pruebas usan bases efímeras; no aplican migraciones a Supabase compartido.

El downgrade conserva los datos; se rechaza si ya existen las nuevas acciones de auditoría o borradores anulados sin PDF que el baseline no admite. No se borra ni transforma evidencia para forzarlo.

`CONTRACT_FRONTEND_URL` configura el origen web de los enlaces (por defecto `http://localhost:3000`; configurar el dominio del frontend al desplegar). `SIGNATURE_LINK_TTL_HOURS` debe ser positivo. El almacenamiento `booking_documents` existente mantiene PDF y fila comercial en la misma transacción.

La nueva migración `0008_contract_signature`, posterior a `0007_contract_management`, añade `otp_last_requested_at`, `otp_window_started_at` y `otp_request_count`. Estos límites sobreviven a reinicios, múltiples procesos y rotación del enlace. El único head esperado ahora es `0008_contract_signature`. No se aplicó a ninguna base compartida.

## Contingencia manual (US-14, backend)

`POST /api/v1/contracts/manual` requiere JWT de `ENCARGADO` o `SUPERADMIN`, cabecera **`Idempotency-Key: <UUID>`** y multipart con `payload` (JSON según la especificación REST) y `advance_evidence_file` (imagen/PDF, máximo 5 MiB, tipo comprobado por contenido). La clave se usa como ID de cotización. Con la misma clave y contenido retorna 200 sin duplicar; con contenido distinto, 409. La primera creación retorna 201 e incluye IDs de cliente, cotización, pago, evento y contrato, estado e importes. Conservar la clave al reintentar una petición cuyo resultado se desconoce.

Se reutiliza `SqlAlchemyManualBookingStore` sin commits internos. Crea/actualiza datos del cliente, cotización `MANUAL`, extras con cantidades, evidencia, adelanto verificado por el encargado, evento, reservas de inventario, contrato y auditoría en una sola transacción. Este endpoint es la contingencia autoritativa de RF-23: permite que el encargado registre y verifique la evidencia en el mismo acto, dejando constancia de esa decisión. `/manual-bookings` conserva su revisión separada y su restricción de verificación propia.

En un cliente existente, los campos DNI/RUC omitidos se conservan. Enviar explícitamente `null` limpia ese campo; suministrar un valor lo actualiza. Nombre y datos de identidad explícitamente modificados se auditan con actor, valores anteriores/nuevos y cotización mediante `MANUAL_CONTRACT` sobre la entidad `clients`. La distinción entre omisión y valor explícito también forma parte de la huella de idempotencia. Observaciones y cláusulas conservan espacios y saltos de línea tal como se reciben.

El precio de servicios viene del catálogo o del importe acordado con motivo. El adelanto debe coincidir exactamente con el porcentaje configurado sobre servicios (10% por defecto); un importe distinto responde 400 `invalid-advance-amount`. El saldo incluye movilidad. Sin importe pactado, la movilidad usa la tarifa de contingencia por distrito de RN-03; si el cliente aporta transporte es cero. Observaciones y cláusulas se incorporan antes de renderizar el PDF.

La revalidación autoritativa usa Redis a través del puerto de disponibilidad y el mismo candado transaccional PostgreSQL global que las demás reservas manuales. Un conflicto devuelve 409 y revierte todo; no aprueba sobrecupo desde esta ruta. `issue_contract=false` deja `DRAFT` sin PDF ni enlace; `POST /contracts` permite emitirlo después.

El PDF se prepara con la instantánea comercial y la identidad persistida **antes de adquirir el candado global**. Tras adquirirlo se revalida capacidad, se reservan recursos y se adopta ese documento; la emisión agrega enlace/auditoría sin volver a renderizar. El documento permanece en la misma transacción PostgreSQL: cualquier conflicto posterior revierte también el PDF preparado. La preparación aún mantiene la transacción, el candado de idempotencia y, si corresponde, el del cliente; lo que se reduce es la sección global de disponibilidad.

La emisión requiere evento `AWAITING_SIGNATURE`; un histórico `SCHEDULED` sin contrato se rechaza antes de generar documento o enlace. Las dos rutas de descarga, `/contracts/{id}/pdf` y `/manual-bookings/{quote_id}/contract`, usan `ManageContracts.pdf` para elegir el documento vigente y entregar el PDF sellado tras la firma.

## Firma pública (US-15, backend)

| Ruta | Comportamiento |
| --- | --- |
| `GET /contracts/sign/{token}` | Resumen del contrato, evento e importes; no expone hashes ni rutas privadas. |
| `GET /contracts/sign/{token}/pdf` | PDF original para revisión; token válido y contrato emitido obligatorios. |
| `POST /contracts/sign/{token}/otp` | Código criptográfico de seis dígitos, TTL 10 minutos, HMAC en BD y mensaje redactable en outbox. Espera de 60 segundos, máximo 3 solicitudes por contrato cada 10 minutos y 10 por IP/hora. |
| `POST /contracts/sign/{token}/otp/verify` | `{"otp_code":"123456"}`; máximo 5 intentos. Emite `otp_proof` HS256 con audiencia y propósito exclusivos, TTL 15 minutos, ligado al contrato, enlace y generación del OTP. Los errores de código confirman el contador antes de responder. |
| `POST /contracts/sign/{token}` | `otp_proof`, `signature_base64` PNG hasta 1 MiB, `signer_full_name` y `accept_terms=true`. Valida prueba, imagen, estado y adelanto; estampa firma y sella, guarda evidencia, audita `CONTRACT_SIGNED`, cambia evento a `SCHEDULED` y encola copia PDF. |

El token se consume al firmar; una petición repetida devuelve 404 y no vuelve a sellar ni encolar. Reenviar el enlace, regenerar el contrato o solicitar otro OTP invalida pruebas anteriores. La expiración del enlace devuelve 410. Cinco errores de OTP bloquean esa generación hasta pedir otra dentro de los límites. Las escrituras se serializan por evento, por lo que dos firmas concurrentes no pueden confirmar dos veces.

US-15 exige que el OTP siga vigente al firmar: una prueba JWT todavía válida no extiende su vencimiento. Si el código vence entre la verificación y la firma, se devuelve 410 `otp-expired`, se conserva el enlace y se permite solicitar/verificar un nuevo OTP dentro de los límites existentes.

Las respuestas públicas llevan `Cache-Control: private, no-store` y `Referrer-Policy: no-referrer`. El access log de Uvicorn redacta el token; el proxy y cualquier APM deben aplicar la misma redacción de `/contracts/sign/*` y excluir cuerpos OTP/firma. Los límites por IP requieren que el proxy de confianza configure correctamente la IP de cliente.

`PadesSignatureAdapter` añade una hoja de constancia y usa una apariencia con la imagen manuscrita; el sello cubre todas las páginas. Implementa el puerto `ISignatureSeal` con [pyHanko](https://docs.pyhanko.eu/en/stable/api-docs/pyhanko.sign.signers.html), subfiltro `/ETSI.CAdES.detached`, SHA-256 y certificado PKCS#12. Se guarda SHA-256 del PDF sellado, hash del original y nombre/aceptación/OTP verificado/IP/User-Agent/fecha en auditoría. El certificado representa al negocio, como define ADR-07.

Configurar `SIGNATURE_PKCS12_PATH`, `SIGNATURE_PKCS12_PASSWORD` y opcionalmente `SIGNATURE_TSA_URL` (RFC 3161). Sin certificado, con certificado fuera de vigencia o si falla el sellado/TSA, responde 503 `signature-unavailable` y conserva el contrato emitido, el enlace y el evento para reintentar. No genera un certificado ni simula una firma cuando falta configuración. Montar el `.p12` como secreto en API/Docker; no versionarlo. `SIGNATURE_OTP_TTL_MINUTES`, `SIGNATURE_OTP_MAX_ATTEMPTS` y `SIGNATURE_OTP_PROOF_TTL_MINUTES` admiten los valores de `.env.example`.

## Validación

Pruebas de dominio y aplicación cubren estados, autorización del adelanto, correlativo, reintento idempotente, renovación de enlace, regeneración de observaciones, invariantes de anulación y descarga del documento sellado. Las pruebas de PDF extraen su texto para comprobar importes y observaciones. La suite HTTP prueba roles y ausencia de secretos. PostgreSQL/Redis reales de Testcontainers verifican concurrencia, rollback conjunto, compatibilidad del flujo manual y upgrade/downgrade conservando datos anteriores.

Diego confirma que las pruebas de la entrega están bien, tras ejecutar la validación desde su terminal. El agente no volvió a ejecutar pruebas. Se corrigieron los identificadores extensos de parametrización en Windows y la llamada al validador asíncrono de pyHanko. La firma real con certificado configurado, gateway y entrega WhatsApp sigue pendiente de integración; las pruebas automatizadas no acreditan esa operación real. Los comandos siguientes quedan como referencia para regresiones, incluida cualquier actualización posterior de la base de la rama.

Al preparar la PR se incorporó `origin/develop` en `f772a9b` (PR #32), conservando los repositorios reales de cotización y las transacciones E2. Se ajustó la cadena E2 a `0007`/`0008` y se añadió un caso de compatibilidad de cantidades/notas del contrato manual. Después de esa incorporación se comprobaron lint, formato, tipos y head de Alembic; no se reejecutó pytest. La confirmación anterior de Diego corresponde a la entrega previa a esta actualización de base.

## Comandos para Diego (PowerShell)

Desde `D:\Proyectos\EventPro-backend`, preparar dependencias y comprobar calidad sin modificar formato:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m alembic heads
```

`alembic heads` debe mostrar un único head: `0008_contract_signature`; no aplica cambios a la base de datos.

Pruebas del nuevo módulo sin contenedores:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/domain/test_contract.py tests/application/test_manage_contracts.py tests/unit/test_contracts_router.py
.\.venv\Scripts\python.exe -m pytest -q tests/application/test_sign_contract.py tests/unit/test_pades_signature.py tests/unit/test_signature_privacy.py
```

Con Docker Desktop iniciado, pruebas de integración y regresión del flujo manual (Testcontainers crea y elimina sus propias bases efímeras):

```powershell
docker version
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_contract_management.py tests/integration/test_contract_migration.py tests/integration/test_manual_booking_flow.py tests/integration/test_manual_booking_concurrency.py
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_contract_signing.py
```

Suite completa con el umbral de cobertura de CI:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=75
```

Las pruebas de migración fijan explícitamente una URL efímera. Aplicar `alembic upgrade head` sobre el entorno compartido corresponde al despliegue coordinado, no a estos comandos de verificación. Configurar `CONTRACT_FRONTEND_URL` antes de desplegar.
