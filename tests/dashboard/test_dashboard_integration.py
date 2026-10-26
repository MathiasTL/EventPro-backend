"""US-22: PostgreSQL efímero explícito, sin fixtures de infraestructura de otras épicas."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, text, update
from sqlalchemy import event as sql_event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from app.application.dtos.dashboard_dto import ExecutiveDashboardRequest
from app.application.dtos.financial_dto import FinancialPnlRequest
from app.application.use_cases.financial.get_executive_dashboard import GetExecutiveDashboardUseCase
from app.application.use_cases.financial.get_financial_pnl import GetFinancialPnlUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.dashboard import DashboardWindow
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.financial_reporting import PeriodType
from app.infrastructure.adapters.secondary.persistence.database import build_engine, get_session
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.models.catalog_models import (
    ExtraModel,
    PackageModel,
    ThemeModel,
)
from app.infrastructure.adapters.secondary.persistence.models.client_model import ClientModel
from app.infrastructure.adapters.secondary.persistence.models.event_financial_snapshot_model import (  # noqa: E501
    EventFinancialSnapshotModel,
)
from app.infrastructure.adapters.secondary.persistence.models.quote_model import (
    QuoteExtraModel,
    QuoteModel,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_dashboard_repository import (  # noqa: E501
    SqlAlchemyDashboardRepository,
    dashboard_statement,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_financial_repository import (  # noqa: E501
    SqlAlchemyFinancialRepository,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)
from app.infrastructure.di import containers
from app.main import create_app
from tests.event_support import make_event
from tests.integration._support import insert_user, run_migrations

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def dashboard_database_url():
    with PostgresContainer("postgres:16-alpine") as postgres:
        url = postgres.get_connection_url().replace("+psycopg2", "+asyncpg")
        run_migrations(url)
        yield url


@pytest.fixture
async def db(dashboard_database_url):
    engine = build_engine(dashboard_database_url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            yield session, engine
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def catalog(db):
    session, _ = db
    package = PackageModel(
        name="Paquete", service_category="SHOW", base_price=1000, direct_cost=400
    )
    theme = ThemeModel(name="Selva")
    gorilla = ExtraModel(name="Muñeco Gorila Gigante", sale_price=100, direct_cost=20)
    dj = ExtraModel(name="DJ", sale_price=100, direct_cost=20)
    client = ClientModel(
        phone="+519" + str(uuid4().int % 10**8).zfill(8), full_name="Cliente US-22"
    )
    session.add_all([package, theme, gorilla, dj, client])
    await session.flush()
    return package, theme, gorilla, dj, client


async def seed(
    session,
    catalog,
    *,
    day=date(2026, 10, 15),
    status=EventStatus.SETTLED,
    snapshot=True,
    with_theme=True,
    revenue="1000.00",
    origin="SETTLEMENT",
):
    package, theme, gorilla, dj, client = catalog
    now = datetime(2030, 1, 1, tzinfo=UTC)
    quote = QuoteModel(
        id=uuid4(),
        client_id=client.id,
        package_id=package.id,
        theme_id=theme.id if with_theme else None,
        event_date=day,
        event_time=datetime.now().time(),
        location_address="Av. Prueba",
        location_district="Otro",
        services_subtotal=950,
        total_amount=1000,
        advance_amount=100,
        pending_balance=900,
        sent_at=now,
        expires_at=now,
        base_mobility_amount=50,
    )
    session.add(quote)
    await session.flush()
    evt = event_to_model(make_event(quote_id=quote.id, event_date=day, status=status))
    session.add(evt)
    for extra, quantity in ((gorilla, 3), (dj, 2)):
        session.add(
            QuoteExtraModel(
                quote_id=quote.id,
                extra_id=extra.id,
                quantity=quantity,
                unit_price=100,
                subtotal=100 * quantity,
            )
        )
    await session.flush()
    if snapshot:
        session.add(
            EventFinancialSnapshotModel(
                event_id=evt.id,
                gross_revenue=Decimal(revenue),
                fixed_packages_cost=400,
                fixed_extras_cost=100,
                mobility_operational_cost=50,
                recorded_at=now,
                origin=origin,
                details={},
            )
        )
    await session.flush()
    return evt, quote


async def report(session, year=2026, month=10, compare_months=3):
    return await GetExecutiveDashboardUseCase(SqlAlchemyDashboardRepository(session)).execute(
        ExecutiveDashboardRequest(year, month, compare_months)
    )


async def test_aggregates_exactly_once_and_matches_pnl(db, catalog):
    session, engine = db
    for index in range(12):
        await seed(
            session,
            catalog,
            day=date(2026, 10, 1 if index % 2 else 31),
            with_theme=index < 6,
            origin="LEGACY_BACKFILL" if index % 2 else "SETTLEMENT",
        )
    await seed(session, catalog, day=date(2026, 9, 30), revenue="1450")
    await seed(session, catalog, day=date(2026, 7, 1), revenue="800")
    for day in (date(2026, 6, 30), date(2026, 11, 1)):
        await seed(session, catalog, day=day)
    for status in EventStatus:
        if status != EventStatus.SETTLED:
            await seed(session, catalog, status=status, snapshot=False)
    statements = []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    sql_event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        result = await report(session)
    finally:
        sql_event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert len(statements) == 1 and statements[0].lstrip().startswith("WITH")
    assert [row.net_profit for row in result.net_profit_by_month] == [250, 0, 900, 5400]
    assert result.net_profit_comparison.percentage_change == Decimal("500.00")
    assert result.events_by_package[0].events == 12
    assert [row.events for row in result.events_by_theme] == [6, 6]
    assert result.events_by_theme[1].theme_id is None
    assert [row.times_hired for row in result.top_extras] == [36, 24]
    assert result.events_by_district[0].district == "Miraflores"
    assert result.events_by_district[0].events == 12
    assert result.events_by_district[0].net_profit == 5400
    pnl = await GetFinancialPnlUseCase(SqlAlchemyFinancialRepository(session)).execute(
        FinancialPnlRequest(PeriodType.MONTHLY, 2026, month=10)
    )
    assert pnl.net_profit == result.net_profit_by_month[-1].net_profit

    await session.execute(update(PackageModel).values(direct_cost=999, is_active=False))
    await session.execute(update(ExtraModel).values(direct_cost=999, is_active=False))
    await session.execute(update(ThemeModel).values(is_active=False))
    await session.execute(update(QuoteModel).values(base_mobility_amount=999))
    assert await report(session) == result
    # Consulta de solo lectura, también verificada por el motor (no por búsqueda textual).
    await session.execute(text("SET LOCAL transaction_read_only = on"))
    assert await report(session) == result


@pytest.mark.parametrize("month", [7, 9, 10])
async def test_missing_snapshot_anywhere_in_window_aborts(db, catalog, month):
    session, _ = db
    await seed(session, catalog, day=date(2026, 6, 30), snapshot=False)
    assert (await report(session)).net_profit_by_month[-1].net_profit == 0
    await seed(session, catalog, day=date(2026, month, 1), snapshot=False)
    with pytest.raises(FinancialDataInconsistentError):
        await report(session)


@pytest.mark.parametrize(
    "year,month,previous,inside,following",
    [
        (2026, 1, date(2025, 12, 31), date(2026, 1, 31), date(2026, 2, 1)),
        (2024, 2, date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 1)),
    ],
)
async def test_calendar_boundaries(db, catalog, year, month, previous, inside, following):
    session, _ = db
    for day in (previous, inside, following):
        await seed(session, catalog, day=day)
    result = await report(session, year, month, 1)
    assert [row.net_profit for row in result.net_profit_by_month] == [450, 450]
    assert result.events_by_package[0].events == 1


async def test_empty_current_month_and_negative_profit_precision(db, catalog):
    session, _ = db
    await seed(session, catalog, day=date(2026, 9, 15), revenue="0.01")
    result = await report(session)
    assert result.net_profit_by_month[-2].net_profit == Decimal("-549.99")
    assert result.net_profit_comparison.percentage_change == 100
    assert not result.events_by_package and not result.events_by_district and not result.top_extras


async def test_district_profit_ranking_and_large_decimal_are_exact(db, catalog):
    session, _ = db
    first, _ = await seed(session, catalog, revenue="90071992547409.93")
    first.district = "Surco"
    second, _ = await seed(session, catalog, revenue="0")
    second.district = "Barranco"
    third, _ = await seed(session, catalog, revenue="600")
    third.district = "Barranco"
    await session.flush()
    result = await report(session)
    assert [(row.district, row.events, row.net_profit) for row in result.events_by_district] == [
        ("Surco", 1, Decimal("90071992546859.93")),
        ("Barranco", 2, Decimal("-500.00")),
    ]
    assert result.net_profit_by_month[-1].net_profit == Decimal("90071992546359.93")


async def test_package_groups_and_name_uuid_tie_breakers(db, catalog):
    session, _ = db
    package, theme, gorilla, dj, client = catalog
    other = PackageModel(
        name=package.name, service_category="SHOW", base_price=1000, direct_cost=400
    )
    session.add(other)
    await session.flush()
    await seed(session, catalog)
    await seed(session, (other, theme, gorilla, dj, client))
    result = await report(session)
    assert [row.package_id for row in result.events_by_package] == sorted([package.id, other.id])
    assert [row.events for row in result.events_by_package] == [1, 1]


async def test_query_plan_for_aggregated_read(db, catalog, record_property):
    session, engine = db
    for _ in range(80):
        await seed(session, catalog)
    statement = dashboard_statement(DashboardWindow.create(2026, 10)).compile(
        dialect=engine.dialect, compile_kwargs={"literal_binds": True}
    )
    plan = (
        await session.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(statement)))
    ).scalar_one()
    record_property("dashboard_query_plan", plan)
    assert plan[0]["Plan"]["Actual Rows"] == 1
    assert (await report(session)).events_by_package[0].events == 80


async def test_api_real_repository_and_fresh_rbac(db, catalog):
    session, engine = db
    await seed(session, catalog)
    user_id = await insert_user(engine, "ENCARGADO")
    app = create_app()

    async def session_dependency():
        yield session

    factory = async_sessionmaker(engine, expire_on_commit=False)
    app.dependency_overrides[get_session] = session_dependency
    app.dependency_overrides[containers.get_user_repository] = lambda: SQLAlchemyUserRepository(
        factory
    )
    token = create_access_token(
        subject=str(user_id),
        role="ENCARGADO",
        secret_key=get_settings().secret_key,
        expires_minutes=60,
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            params = {"year": 2026, "month": 10}
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get("/api/v1/reports/dashboard", params=params, headers=headers)
            assert response.status_code == 200
            assert response.json()["net_profit_by_month"][-1]["net_profit"] == 450.0
            await session.execute(delete(EventFinancialSnapshotModel))
            inconsistent = await client.get(
                "/api/v1/reports/dashboard", params=params, headers=headers
            )
            assert inconsistent.status_code == 409
            assert inconsistent.headers["content-type"].startswith("application/problem+json")
            assert inconsistent.json()["type"].endswith("/financial-data-inconsistent")
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE users SET role_id=(SELECT id FROM roles WHERE code='OPERADOR') "
                        "WHERE id=:id"
                    ),
                    {"id": user_id},
                )
            assert (
                await client.get("/api/v1/reports/dashboard", params=params, headers=headers)
            ).status_code == 403
    finally:
        app.dependency_overrides.clear()
