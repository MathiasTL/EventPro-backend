from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError, QuoteExpiredError
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
