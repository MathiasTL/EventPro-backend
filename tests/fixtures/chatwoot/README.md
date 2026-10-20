# Fixtures de Chatwoot

Cada archivo JSON describe una respuesta de la API de Chatwoot (v4.18.0) o un evento de webhook.
Todos tienen la misma forma:

```json
{
  "provisional": true,
  "headers": {},
  "body": {}
}
```

- `provisional`: `true` mientras el archivo se haya redactado a mano a partir del código fuente de
  Chatwoot; `false` cuando provenga de una captura real ya saneada (todos lo son hoy).
- `headers`: solo los nombres y valores inocuos de los encabezados. Nunca una firma real: el valor de
  `X-Chatwoot-Signature` es siempre `REDACTED`. Las pruebas firman el cuerpo con un secreto propio.
- `body`: el JSON tal como lo entrega Chatwoot.

## Estado actual

Los 12 archivos son **capturas reales saneadas** del 2026-10-19, tomadas de una instancia de
Chatwoot v4.18.0 (`"provisional": false`). El saneamiento sustituyó teléfonos, nombres, correos,
tokens, identificadores de WhatsApp (`wamid`) y firmas por valores inventados y estables. Los
adjuntos no se capturaron: su forma (`attachments[].data_url`) sigue el código de Chatwoot y las
pruebas la arman a mano.

Hallazgos de las capturas que el código ya recoge:

- En los webhooks de mensaje, `status` y la hora de actualización **no** están en el nivel superior
  del cuerpo: viajan en `conversation.messages[]` (la entrada con el mismo `id`).
- `content_attributes.external_error` aparece en el nivel superior y en el mensaje incrustado.
- En la API, un mensaje sin adjuntos no trae la clave `attachments`, y una conversación recién
  creada trae `messages: []`.
- Las plantillas llevan `additional_attributes.template_params`.

| Archivo | Origen |
| --- | --- |
| `message_created_incoming`, `message_created_outgoing` | Webhook `message_created` |
| `message_updated_sent`, `_delivered`, `_read`, `_failed` | Webhook `message_updated` |
| `api_contact_search`, `api_contact_created` | `POST /contacts/search`, `POST /contacts` |
| `api_conversation_created`, `api_conversation_list` | `POST /conversations`, `GET /conversations` |
| `api_message_created`, `api_message_list` | `POST` y `GET /conversations/{id}/messages` |

## Pasos de captura

La captura la hace una persona con acceso a su propia instancia de Chatwoot; el repositorio no
accede a ella.

1. Levantar un receptor de peticiones (un contenedor sencillo que registre método, encabezados y
   cuerpo crudo) en la misma red que Chatwoot. Su nombre de host debe tener un punto y no llevar
   guion bajo (por ejemplo, `receptor.local`): el panel valida la URL y rechaza lo contrario.
2. Activar `SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true` en el entorno de Chatwoot (ver
   `chatwoot.env.example`). Sin ella, Chatwoot descarta los webhooks hacia hosts de red privada y
   el receptor no recibe nada.
3. Crear en Chatwoot un webhook de cuenta hacia ese receptor, con un secreto, suscrito a
   `message_created` y `message_updated`.
4. Provocar cuatro acciones desde la bandeja: un mensaje entrante del cliente, un mensaje saliente
   del bot, y la entrega y la lectura de un mensaje saliente. Provocar también una falla (por
   ejemplo, una plantilla hacia un número fuera de la lista de destinatarios de prueba).
5. Guardar las tres lecturas de la API con el encabezado `api_access_token`: búsqueda de contacto,
   listado de conversaciones y listado de mensajes. Guardar también las respuestas de crear
   contacto, conversación y mensaje. Detalles que fallaron en la práctica:
   - La imagen de Rails no trae `curl`: hacer las llamadas con `ruby` (`Net::HTTP`) dentro del
     contenedor.
   - Llamar directamente a `chatwoot-rails:3000` con el encabezado `X-Forwarded-Proto: https`. El
     proxy auxiliar HTTPS descarta `api_access_token` porque el nombre lleva guion bajo.
6. Entregar los archivos crudos fuera del repositorio. Nunca copiar capturas sin sanear a
   `tests/fixtures/`.

## Lista de saneamiento

Antes de que un archivo entre al repositorio, reemplazar o eliminar:

- [ ] Teléfonos: usar solo `+51999111222` y `+51999333444` (con o sin `+`, también en `source_id`).
- [ ] Nombres de personas y de la cuenta: usar nombres genéricos (`Cliente Demo`).
- [ ] Correos electrónicos: dejar `null`.
- [ ] Tokens de acceso, identificadores de sesión y cualquier clave con `token`, `secret` o
      `password` en el nombre.
- [ ] Secreto del webhook y valor de `X-Chatwoot-Signature` (dejar `REDACTED`).
- [ ] URLs de adjuntos firmadas (`X-Amz-*`, `Signature=`, `Expires=`) y nombres de host reales:
      usar `https://files.example.org/...`.
- [ ] Identificadores largos o aleatorios (por ejemplo, el identificador firmado de ActiveStorage).
- [ ] Identificadores de cuenta y de bandeja: opcionales, no son sensibles.
- [ ] Cambiar `"provisional"` a `false` y conservar los nombres de los encabezados capturados
      (por ejemplo, la presencia de `X-Chatwoot-Delivery`).

`tests/infrastructure/test_chatwoot_fixtures.py` rechaza teléfonos distintos de los permitidos,
correos, claves con aspecto de token, firmas reales, URLs firmadas y hosts reales. Ejecutarlo
después de cada cambio:

```bash
python -m pytest -q tests/infrastructure/test_chatwoot_fixtures.py
```
