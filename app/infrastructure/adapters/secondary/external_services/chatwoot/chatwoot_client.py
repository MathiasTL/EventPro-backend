"""Cliente HTTP de la API de aplicación de Chatwoot.

Es el único lugar donde se adjuntan los tokens y se clasifican los errores del gateway.
Los mensajes de excepción y los logs llevan solo la operación y el código de estado: nunca
tokens, cuerpos de respuesta, teléfonos ni URLs con parámetros de consulta.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.logging import get_logger
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError

# Chatwoot v4 autentica con este encabezado; `Authorization: Bearer` no se acepta.
TOKEN_HEADER = "api_access_token"
_AUTH_REJECTED_STATUSES = frozenset({401, 403})
# Los adjuntos de WhatsApp llegan a 100 MB; el proxy de la bandeja acota la lectura.
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_DOWNLOAD_REDIRECTS = 3
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class DownloadedFile:
    data: bytes
    content_type: str | None


class ChatwootToken(StrEnum):
    """Token a usar en cada llamada: el bot crea mensajes, el agente lee y administra."""

    BOT = "bot"
    AGENT = "agent"


def build_chatwoot_http_client(
    *,
    base_url: str,
    account_id: int,
    timeout_seconds: float,
    connect_timeout_seconds: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Crea el cliente compartido: URL de la cuenta, timeouts finitos y sin redirecciones."""

    return httpx.AsyncClient(
        base_url=f"{base_url.rstrip('/')}/api/v1/accounts/{account_id}",
        timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
        follow_redirects=False,
        transport=transport,
    )


class ChatwootClient:
    """Envía peticiones a Chatwoot y traduce los fallos a errores de dominio."""

    def __init__(self, http: httpx.AsyncClient, *, bot_token: str, agent_token: str) -> None:
        self._http = http
        self._tokens = {ChatwootToken.BOT: bot_token, ChatwootToken.AGENT: agent_token}

    async def request(
        self,
        method: str,
        path: str,
        *,
        token: ChatwootToken,
        operation: str,
        params: Mapping[str, str | int] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, str] | None = None,
        files: Sequence[tuple[str, tuple[str, bytes, str]]] | None = None,
        not_found_is_missing: bool = False,
        required_keys: Sequence[str] = (),
    ) -> Any:
        """Devuelve el JSON de la respuesta; `required_keys` exige claves en el objeto raíz."""

        log = get_logger("chatwoot")
        try:
            response = await self._http.request(
                method,
                path,
                headers={TOKEN_HEADER: self._tokens[token]},
                params=params,
                json=json,
                data=data,
                files=files,
            )
        except httpx.TimeoutException as exc:
            log.warning(
                "chatwoot_request_failed", operation=operation, error_type=type(exc).__name__
            )
            raise MessagingUnavailableError(
                f"Chatwoot no respondió a tiempo en {operation}"
            ) from None
        except httpx.HTTPError as exc:
            log.warning(
                "chatwoot_request_failed", operation=operation, error_type=type(exc).__name__
            )
            raise MessagingUnavailableError(
                f"No se pudo conectar con Chatwoot en {operation}"
            ) from None

        status = response.status_code
        if status == 404 and not_found_is_missing:
            raise ResourceNotFoundError(f"Chatwoot no encontró el recurso en {operation}")
        if status in _AUTH_REJECTED_STATUSES:
            log.error("chatwoot_auth_rejected", operation=operation, status=status)
        elif status >= 400:
            log.warning("chatwoot_request_rejected", operation=operation, status=status)
        if status >= 400:
            raise MessagingUnavailableError(f"Chatwoot respondió {status} en {operation}")

        return self._parse_json(response, operation=operation, required_keys=required_keys)

    async def download(self, public_url: str, *, operation: str) -> DownloadedFile:
        """Descarga un archivo que Chatwoot publica en su URL pública (D17), sin el token.

        La URL pública se reescribe al esquema y anfitrión de `CHATWOOT_BASE_URL` (conservando
        `Host` y `X-Forwarded-Proto` originales, como pide Rails) y las redirecciones solo se
        siguen si son relativas o apuntan a ese anfitrión o al público; cualquier otro destino se
        rechaza como `ResourceNotFoundError` para no convertir el proxy en un SSRF.
        """

        log = get_logger("chatwoot")
        public = urlsplit(public_url)
        base = self._http.base_url
        base_netloc = base.netloc.decode("ascii")
        if public.scheme not in ("http", "https") or not public.netloc:
            raise self._rejected(log, operation, "invalid_url")
        trusted = {base_netloc, public.netloc}
        headers = {"Host": public.netloc, "X-Forwarded-Proto": public.scheme}
        url = urlunsplit((base.scheme, base_netloc, public.path, public.query, ""))
        for _ in range(MAX_DOWNLOAD_REDIRECTS + 1):
            try:
                async with self._http.stream("GET", url, headers=headers) as response:
                    status = response.status_code
                    if status in _REDIRECT_STATUSES and "location" in response.headers:
                        target = urlsplit(urljoin(url, response.headers["location"]))
                        if target.netloc not in trusted or target.scheme not in ("http", "https"):
                            raise self._rejected(log, operation, "foreign_redirect")
                        url = urlunsplit((base.scheme, base_netloc, target.path, target.query, ""))
                        continue
                    return await self._read_download(response, operation=operation)
            except httpx.HTTPError as exc:
                raise self._transport_error(log, operation, exc) from None
        raise self._rejected(log, operation, "too_many_redirects")

    async def _read_download(self, response: httpx.Response, *, operation: str) -> DownloadedFile:
        log = get_logger("chatwoot")
        status = response.status_code
        if status == 404:
            raise ResourceNotFoundError(f"Chatwoot no encontró el recurso en {operation}")
        if status != 200:
            log.warning("chatwoot_request_rejected", operation=operation, status=status)
            raise MessagingUnavailableError(f"Chatwoot respondió {status} en {operation}")
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                log.warning("chatwoot_download_too_large", operation=operation)
                raise MessagingUnavailableError(f"Archivo demasiado grande en {operation}")
            chunks.append(chunk)
        content_type = response.headers.get("content-type", "").split(";")[0].strip() or None
        return DownloadedFile(b"".join(chunks), content_type)

    @staticmethod
    def _rejected(log: Any, operation: str, reason: str) -> ResourceNotFoundError:
        log.warning("chatwoot_download_rejected", operation=operation, reason=reason)
        return ResourceNotFoundError(f"Destino de descarga no permitido en {operation}")

    @staticmethod
    def _transport_error(
        log: Any, operation: str, exc: httpx.HTTPError
    ) -> MessagingUnavailableError:
        log.warning("chatwoot_request_failed", operation=operation, error_type=type(exc).__name__)
        if isinstance(exc, httpx.TimeoutException):
            return MessagingUnavailableError(f"Chatwoot no respondió a tiempo en {operation}")
        return MessagingUnavailableError(f"No se pudo conectar con Chatwoot en {operation}")

    @staticmethod
    def _parse_json(
        response: httpx.Response, *, operation: str, required_keys: Sequence[str]
    ) -> Any:
        log = get_logger("chatwoot")
        try:
            body = response.json()
        except ValueError:
            log.error("chatwoot_unexpected_response", operation=operation, reason="not_json")
            raise MessagingUnavailableError(
                f"Respuesta inesperada de Chatwoot en {operation}"
            ) from None
        for key in required_keys:
            if not isinstance(body, dict) or key not in body:
                log.error(
                    "chatwoot_unexpected_response",
                    operation=operation,
                    reason="missing_key",
                    key=key,
                )
                raise MessagingUnavailableError(f"Respuesta inesperada de Chatwoot en {operation}")
        return body
