from datetime import date, time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.exceptions.quote_exceptions import (
    AvailabilityAlternative,
    AvailabilityConflictError,
    ClientNotFoundError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.infrastructure.adapters.primary.web.problem import (
    install_exception_handlers,
    quote_error_to_problem,
)


def test_invalid_quote_state_maps_to_409() -> None:
    problem = quote_error_to_problem(InvalidQuoteStateError("La cotización está CANCELLED."))
    assert problem.status == 409
    assert problem.suffix == "invalid-quote-state"
    assert problem.title == "Conflicto"
    assert problem.detail == "La cotización está CANCELLED."


def test_quote_expired_maps_to_410() -> None:
    problem = quote_error_to_problem(QuoteExpiredError("La cotización venció."))
    assert problem.status == 410
    assert problem.suffix == "quote-expired"
    assert problem.title == "Recurso expirado"


def test_problem_json_is_rendered_by_the_installed_handler() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/expired")
    async def expired() -> None:
        raise quote_error_to_problem(QuoteExpiredError("La cotización venció."))

    response = TestClient(app).get("/expired")
    assert response.status_code == 410
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "https://errors.eventpro.pe/quote-expired"
    assert body["status"] == 410
    assert body["instance"] == "/expired"


_ALTERNATIVES = (AvailabilityAlternative(date(2026, 10, 15), time(18, 0)),)
_EXPECTED_ALTERNATIVES = [{"event_date": "2026-10-15", "event_time": "18:00:00"}]


def test_availability_conflict_maps_to_409_with_alternatives_and_handoff() -> None:
    problem = quote_error_to_problem(
        AvailabilityConflictError("El cupo ya no está disponible.", alternatives=_ALTERNATIVES)
    )
    assert problem.status == 409
    assert problem.suffix == "availability-conflict"
    assert problem.extensions["alternatives"] == _EXPECTED_ALTERNATIVES
    assert problem.extensions["handoff_available"] is True


def test_simultaneous_threshold_maps_to_409_with_its_slug() -> None:
    problem = quote_error_to_problem(
        SimultaneousThresholdExceededError("Demasiados shows.", alternatives=_ALTERNATIVES)
    )
    assert problem.status == 409
    assert problem.suffix == "simultaneous-threshold-exceeded"
    assert problem.extensions["alternatives"] == _EXPECTED_ALTERNATIVES


def test_availability_extensions_survive_the_http_mapping() -> None:
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/quotes/pay-advance")
    async def pay_advance() -> None:
        try:
            raise AvailabilityConflictError(
                "El cupo ya no está disponible.",
                alternatives=_ALTERNATIVES,
                handoff_available=False,
            )
        except AvailabilityConflictError as error:
            raise quote_error_to_problem(error) from error

    response = TestClient(app).post("/quotes/pay-advance")
    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "https://errors.eventpro.pe/availability-conflict"
    assert body["alternatives"] == _EXPECTED_ALTERNATIVES
    assert body["handoff_available"] is False


def test_not_found_errors_map_to_404_not_found() -> None:
    for error in (QuoteNotFoundError("No existe."), ClientNotFoundError("No existe.")):
        problem = quote_error_to_problem(error)
        assert problem.status == 404
        assert problem.suffix == "not-found"
        assert problem.title == "No encontrado"


def test_validation_error_maps_to_422() -> None:
    problem = quote_error_to_problem(ValidationError("Fecha pasada."))
    assert problem.status == 422
    assert problem.suffix == "validation-error"
    assert problem.detail == "Fecha pasada."
