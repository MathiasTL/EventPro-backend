from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions.quote_exceptions import (
    AvailabilityConflictError,
    AvailabilityRejectedError,
    ClientNotFoundError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ValidationError

ERROR_TYPE_BASE = "https://errors.eventpro.pe/"

_STATUS_TITLES = {
    400: "Solicitud inválida",
    401: "No autorizado",
    403: "Prohibido",
    404: "No encontrado",
    409: "Conflicto",
    410: "Recurso expirado",
    422: "Error de validación",
    429: "Límite de peticiones excedido",
    500: "Error interno",
    503: "Servicio no disponible",
}

_STATUS_SUFFIXES = {
    401: "invalid-credentials",
    403: "forbidden",
    404: "not-found",
    409: "duplicate-resource",
    422: "validation-error",
    429: "rate-limit-exceeded",
}


class ProblemError(Exception):
    """Error de dominio web que se serializa como RFC 7807 problem+json."""

    def __init__(
        self,
        status: int,
        suffix: str,
        title: str,
        detail: str,
        *,
        headers: dict[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.suffix = suffix
        self.title = title
        self.detail = detail
        self.headers = headers or {}
        self.extensions = extensions

    def __str__(self) -> str:
        return self.detail


QuoteContractError = (
    AvailabilityConflictError
    | SimultaneousThresholdExceededError
    | QuoteExpiredError
    | InvalidQuoteStateError
    | QuoteNotFoundError
    | ClientNotFoundError
    | ValidationError
)

_AVAILABILITY_TITLE = "Sin disponibilidad para la fecha y el horario"


def quote_error_to_problem(exc: QuoteContractError) -> ProblemError:
    """Traduce los errores del contrato de cotización a su problema HTTP.

    Disponibilidad y estado inválido: 409; vencida: 410; cotización o cliente inexistente:
    404 (``not-found``); validación: 422. Los errores de disponibilidad añaden las
    extensiones ``alternatives`` y ``handoff_available``.
    """

    if isinstance(exc, AvailabilityRejectedError):
        return ProblemError(
            409,
            exc.code,
            _AVAILABILITY_TITLE,
            str(exc),
            alternatives=[
                {
                    "event_date": alternative.event_date.isoformat(),
                    "event_time": alternative.event_time.isoformat(),
                }
                for alternative in exc.alternatives
            ],
            handoff_available=exc.handoff_available,
        )
    if isinstance(exc, QuoteNotFoundError | ClientNotFoundError):
        return ProblemError(404, "not-found", _STATUS_TITLES[404], str(exc))
    if isinstance(exc, ValidationError):
        return ProblemError(422, exc.code, _STATUS_TITLES[422], str(exc))
    status = 410 if isinstance(exc, QuoteExpiredError) else 409
    return ProblemError(status, exc.code, _STATUS_TITLES[status], str(exc))


def problem_response(
    request: Request,
    status: int,
    suffix: str,
    title: str,
    detail: str,
    *,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{ERROR_TYPE_BASE}{suffix}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    body.update(extensions)
    return JSONResponse(
        status_code=status,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(
            request,
            exc.status,
            exc.suffix,
            exc.title,
            exc.detail,
            headers=exc.headers,
            **exc.extensions,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return problem_response(
            request,
            422,
            "validation-error",
            _STATUS_TITLES[422],
            "El cuerpo o los parámetros no cumplen el esquema.",
            errors=fields,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        suffix = _STATUS_SUFFIXES.get(exc.status_code, "http-error")
        title = _STATUS_TITLES.get(exc.status_code, "Error HTTP")
        detail = exc.detail if isinstance(exc.detail, str) else title
        return problem_response(
            request,
            exc.status_code,
            suffix,
            title,
            detail,
            headers=exc.headers,
        )
