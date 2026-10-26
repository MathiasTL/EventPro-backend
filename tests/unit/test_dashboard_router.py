from uuid import uuid4

import httpx
import pytest

from app.application.use_cases.financial.get_executive_dashboard import GetExecutiveDashboardUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.dashboard import DashboardReadData, MonthlyTotals, ThemeMetric
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers
from app.main import create_app
from tests.auth_support import CURRENT, install, set_role
from tests.dashboard_support import DashboardReadPort, totals


@pytest.fixture
def setup():
    app, port = create_app(), DashboardReadPort()
    install(app)
    old_role, old_active = CURRENT.role, CURRENT.is_active
    CURRENT.is_active = True
    app.dependency_overrides[containers.get_executive_dashboard_use_case] = lambda: (
        GetExecutiveDashboardUseCase(port)
    )
    yield app, port
    CURRENT.role, CURRENT.is_active = old_role, old_active
    app.dependency_overrides.clear()


def auth(role=Role.ENCARGADO):
    set_role(role)
    return {
        "Authorization": "Bearer "
        + create_access_token(
            subject=str(uuid4()),
            role=role.value,
            secret_key=get_settings().secret_key,
            expires_minutes=60,
        )
    }


async def get(app, params=None, headers=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get("/api/v1/reports/dashboard", params=params, headers=headers)


@pytest.mark.parametrize("role", [Role.ENCARGADO, Role.SUPERADMIN])
async def test_contract_and_default_window(setup, role):
    app, port = setup
    response = await get(app, {"year": 2026, "month": 10}, auth(role))
    assert response.status_code == 200
    assert response.json() == {
        "period": "2026-10",
        "net_profit_by_month": [
            {"period": f"2026-{month:02}", "net_profit": 0.0} for month in range(7, 11)
        ],
        "net_profit_comparison": {
            "previous_period": "2026-09",
            "current_net_profit": 0.0,
            "previous_net_profit": 0.0,
            "absolute_change": 0.0,
            "percentage_change": 0.0,
        },
        "events_by_package": [],
        "events_by_theme": [],
        "top_extras": [],
        "events_by_district": [],
    }
    assert len(port.windows) == 1


async def test_nullable_percentage_theme_and_numeric_money(setup):
    app, port = setup
    port.data = DashboardReadData(
        months=(MonthlyTotals("2026-10", totals("-12.35")),),
        themes=(ThemeMetric(None, "Sin temática", 1),),
    )
    response = await get(app, {"year": 2026, "month": 10, "compare_months": 1}, auth())
    assert response.status_code == 200
    body = response.json()
    assert len(body["net_profit_by_month"]) == 2
    assert body["net_profit_comparison"]["percentage_change"] is None
    assert body["net_profit_comparison"]["current_net_profit"] == -12.35
    assert body["events_by_theme"] == [{"theme_id": None, "name": "Sin temática", "events": 1}]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"year": 2026},
        {"month": 10},
        {"year": 0, "month": 1},
        {"year": 9999, "month": 1},
        {"year": 2026, "month": 13},
        {"year": 2026, "month": 10, "compare_months": 0},
        {"year": 2026, "month": 10, "compare_months": 13},
        {"year": 2026, "month": 10, "compare_months": "abc"},
        {"year": 1, "month": 1},
        {"year": 2026, "month": 10, "week": 42},
    ],
)
async def test_invalid_parameters_problem_details_without_read(setup, params):
    app, port = setup
    response = await get(app, params, auth())
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/validation-error")
    assert port.windows == []


@pytest.mark.parametrize("status", [401, 403])
async def test_access_denied_before_dashboard_read(setup, status):
    app, port = setup
    response = await get(
        app, {"year": 2026, "month": 10}, None if status == 401 else auth(Role.OPERADOR)
    )
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert port.windows == []


async def test_account_role_and_activation_are_fresh(setup):
    app, port = setup
    headers = auth(Role.SUPERADMIN)
    set_role(Role.OPERADOR)
    assert (await get(app, {"year": 2026, "month": 10}, headers)).status_code == 403
    CURRENT.is_active = False
    assert (await get(app, {"year": 2026, "month": 10}, headers)).status_code == 401
    assert port.windows == []


async def test_inconsistent_data_problem_details(setup):
    app, port = setup
    port.error = FinancialDataInconsistentError("Missing snapshot")
    response = await get(app, {"year": 2026, "month": 10}, auth())
    assert response.status_code == 409
    body = response.json()
    assert body["type"].endswith("/financial-data-inconsistent")
    assert body["instance"] == "/api/v1/reports/dashboard"
    assert {"type", "title", "status", "detail", "instance"} <= body.keys()


def test_openapi(setup):
    app, _ = setup
    operation = app.openapi()["paths"]["/api/v1/reports/dashboard"]["get"]
    assert {"200", "401", "403", "409", "422"} <= operation["responses"].keys()
    params = {item["name"]: item for item in operation["parameters"]}
    assert params["year"]["required"] and params["month"]["required"]
    assert params["compare_months"]["schema"]["default"] == 3
