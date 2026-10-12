"""Cliente HTTP de la API de aplicación de Chatwoot.

Es el único lugar donde se adjuntan los tokens y se clasifican los errores del gateway.
Los mensajes de excepción y los logs llevan solo la operación y el código de estado: nunca
tokens, cuerpos de respuesta, teléfonos ni URLs con parámetros de consulta.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

import httpx

from app.core.logging import get_logger
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError

# Chatwoot v4 autentica con este encabezado; `Authorization: Bearer` no se acepta.
TOKEN_HEADER = "api_access_token"
_AUTH_REJECTED_STATUSES = frozenset({401, 403})


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
