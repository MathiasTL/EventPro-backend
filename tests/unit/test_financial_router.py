from uuid import uuid4

import httpx
import pytest

from app.application.use_cases.financial.get_financial_pnl import GetFinancialPnlUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers
from app.main import create_app
from tests.application.test_financial_reporting import ReadPort
from tests.auth_support import CURRENT, install, set_role


@pytest.fixture
def setup():
    app, port = create_app(), ReadPort()
    install(app)
    CURRENT.is_active = True
    app.dependency_overrides[containers.get_financial_pnl_use_case] = lambda: (
        GetFinancialPnlUseCase(port)
    )
    yield app, port
    CURRENT.is_active = True
    app.dependency_overrides.clear()


def auth(role=Role.ENCARGADO):
    set_role(role)
    token = create_access_token(
        subject=str(uuid4()),
        role=role.value,
        secret_key=get_settings().secret_key,
        expires_minutes=60,
    )
    return {"Authorization": f"Bearer {token}"}


async def get(app, *, params=None, headers=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get("/api/v1/reports/financial/pnl", params=params, headers=headers)


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.SUPERADMIN])
async def test_report_contract(setup, role):
    app, _ = setup
    response = await get(
        app, params={"period_type": "MONTHLY", "year": 2026, "month": 10}, headers=auth(role)
    )
    assert response.status_code == 200
    assert response.json() == {
        "period": "2026-10",
        "total_events_settled": 10,
        "gross_revenue": 10000.0,
        "direct_costs": {
            "fixed_packages_cost": 4000.0,
            "fixed_extras_cost": 1000.0,
            "mobility_operational_cost": 500.0,
            "total_costs": 5500.0,
        },
        "net_profit": 4500.0,
        "profit_margin_percentage": 45.0,
    }


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"period_type": "INVALID", "year": 2026, "month": 10},
        {"period_type": "MONTHLY", "year": 2026},
        {"period_type": "MONTHLY", "year": 2026, "month": 10, "week": 42},
        {"period_type": "MONTHLY", "year": 9999, "month": 10},
        {"period_type": "MONTHLY", "year": 2026, "month": 13},
        {"period_type": "WEEKLY", "year": 2021, "week": 53},
        {"period_type": "WEEKLY", "year": 2026, "week": 42, "month": 10},
        {"period_type": "MONTHLY", "year": 2026, "month": 10, "extra": 1},
    ],
)
async def test_invalid_period_uses_problem_details_without_read(setup, params):
    app, port = setup
    response = await get(app, params=params, headers=auth())
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/validation-error")
    assert port.periods == []


@pytest.mark.parametrize("status", [401, 403])
async def test_access_denied_before_read(setup, status):
    app, port = setup
    response = await get(
        app,
        params={"period_type": "MONTHLY", "year": 2026, "month": 10},
        headers=None if status == 401 else auth(Role.OPERADOR),
    )
    assert response.status_code == status
    assert port.periods == []


async def test_fresh_account_state_and_role(setup):
    app, port = setup
    headers = auth(Role.SUPERADMIN)
    set_role(Role.OPERADOR)
    params = {"period_type": "MONTHLY", "year": 2026, "month": 10}
    assert (await get(app, params=params, headers=headers)).status_code == 403
    CURRENT.is_active = False
    assert (await get(app, params=params, headers=headers)).status_code == 401
    assert port.periods == []


async def test_incomplete_data_is_409(setup):
    app, port = setup
    port.error = FinancialDataInconsistentError("Missing snapshot")
    response = await get(
        app, params={"period_type": "WEEKLY", "year": 2026, "week": 42}, headers=auth()
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("/financial-data-inconsistent")


def test_openapi(setup):
    app, _ = setup
    op = app.openapi()["paths"]["/api/v1/reports/financial/pnl"]["get"]
    assert {"200", "401", "403", "409", "422"} <= set(op["responses"])
    params = {param["name"]: param for param in op["parameters"]}
    assert params["period_type"]["required"] and params["year"]["required"]
