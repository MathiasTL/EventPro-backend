"""Las cuatro suites compartidas contra casos reales y PostgreSQL temporal."""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.application.dtos.availability_dto import AvailabilityResult, AvailabilityStatus
from app.application.dtos.quote_dto import (
    BankTransferInstructionDTO,
    PaymentInstructionsDTO,
    WalletInstructionDTO,
)
from app.application.use_cases.quote.cancel_quote import CancelQuoteUseCase
from app.application.use_cases.quote.create_quote import CreateQuoteUseCase
from app.application.use_cases.quote.expire_due_quotes import ExpireDueQuotesUseCase
from app.application.use_cases.quote.get_quote import GetQuoteUseCase
from app.application.use_cases.quote.list_quotes import ListQuotesUseCase
from app.application.use_cases.quote.pay_advance import PayAdvanceUseCase
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import RouteEstimationError
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.mobility import RouteLocation
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeScenario,
)
from app.infrastructure.adapters.secondary.external_services.fake_route_estimator_adapter import (
    FakeRouteEstimatorAdapter,
)
from app.infrastructure.adapters.secondary.mobility.district_zones import zone_for_district
from app.infrastructure.adapters.secondary.persistence.database import build_engine
from app.infrastructure.adapters.secondary.persistence.mappers.quote_mapper import quote_to_model
from app.infrastructure.adapters.secondary.persistence.models import (
    ClientModel,
    ExtraModel,
    PackageModel,
    PaymentModel,
    QuoteModel,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_catalog_repository import (  # noqa: E501
    SqlAlchemyCatalogReadRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_client_repository import (  # noqa: E501
    SqlAlchemyClientRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_quote_repository import (  # noqa: E501
    SqlAlchemyQuoteRepository,
)
from tests.application.quote_ports_contract import (
    PACKAGE_ID,
    CancelQuoteContract,
    CreateQuoteContract,
    ExpireDueQuotesContract,
    GetQuoteContract,
    ListQuotesContract,
    PayAdvanceContract,
    create_input,
)
from tests.domain.financial_support import default_engine
from tests.domain.quote_support import NOW, make_quote

from ._support import insert_user, run_migrations

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def migrated_url(database_url):
    run_migrations(database_url)
    return database_url


class RecordingRepository(SqlAlchemyQuoteRepository):
    """Solo registra ids para el gancho síncrono de la suite; toda escritura usa SQL real."""

    def __init__(self, session):
        super().__init__(session)
        self.added = []

    async def add(self, quote):
        result = await super().add(quote)
        self.added.append(quote.id)
        return result


class RealHooks:
    @pytest.fixture(autouse=True)
    async def setup_real(self, migrated_url, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("DATABASE_URL", migrated_url)
        get_settings.cache_clear()
        self.sync = create_engine(migrated_url.replace("+asyncpg", "+pg8000"))
        self.engine = build_engine(migrated_url)
        with self.sync.begin() as conn:
            conn.execute(text("TRUNCATE clients, packages, extras CASCADE"))
        self.extra_id = uuid4()
        with Session(self.sync) as session:
            session.add(
                PackageModel(
                    id=PACKAGE_ID,
                    name="Paquete",
                    service_category="SHOW",
                    base_price=Decimal("1000"),
                    direct_cost=Decimal("400"),
                    duration_minutes=90,
                )
            )
            session.add(
                ExtraModel(
                    id=self.extra_id,
                    name="Extra",
                    sale_price=Decimal("50.25"),
                    direct_cost=Decimal("20"),
                )
            )
            session.commit()
        self.user_id = await insert_user(self.engine, "ENCARGADO")
        self.session = AsyncSession(self.engine, expire_on_commit=False)
        self.repository = RecordingRepository(self.session)
        self.now = NOW
        self.clock = SimpleNamespace(utcnow=lambda: self.now)
        self.availability = SimpleNamespace(
            check_availability=AsyncMock(
                return_value=AvailabilityResult(AvailabilityStatus.AVAILABLE)
            )
        )
        self.routes = FakeRouteEstimatorAdapter()
        self.seeded = 0
        yield
        await self.session.rollback()
        await self.session.close()
        await self.engine.dispose()
        self.sync.dispose()
        get_settings.cache_clear()

    def create_port(self):
        return CreateQuoteUseCase(
            self.repository,
            SqlAlchemyClientRepository(self.session),
            SqlAlchemyCatalogReadRepository(self.session),
            self.availability,
            self.routes,
            default_engine(),
            self.clock,
            RouteLocation(address="Lima"),
            zone_for_district,
        )

    def seed_client(self, phone, full_name):
        phone = PhoneNumber.parse(phone).value
        with Session(self.sync) as session:
            existing = session.scalar(select(ClientModel).where(ClientModel.phone == phone))
            if existing:
                return existing.id
            client = ClientModel(id=uuid4(), phone=phone, full_name=full_name)
            session.add(client)
            session.commit()
            return client.id

    def seed_quote(
        self,
        status,
        *,
        payment_in_verification=False,
        age=timedelta(0),
        client_id=None,
        event_date=None,
    ):
        client_id = client_id or self.seed_client("999888777", "Cliente")
        quote = make_quote(
            now=self.now - age,
            client_id=client_id,
            package_id=PACKAGE_ID,
            extra_id=self.extra_id,
            event_date=event_date or date(2026, 10, 15),
        )
        quote.status = status
        with Session(self.sync) as session:
            session.add(quote_to_model(quote))
            session.flush()
            if payment_in_verification:
                session.add(
                    PaymentModel(
                        id=uuid4(),
                        quote_id=quote.id,
                        concept="ADVANCE",
                        payment_method="YAPE",
                        amount=quote.liquidation.advance_amount.amount,
                        evidence_path="receipt.png",
                        validation_status="PENDING_VERIFICATION",
                        registered_by_user_id=self.user_id,
                    )
                )
            session.commit()
        self.seeded += 1
        return quote.id

    def arrange(self, port, scenario):
        async def check(request):
            status = AvailabilityStatus.AVAILABLE
            if request.event_date == date(2026, 10, 15):
                if scenario is FakeScenario.AVAILABILITY_CONFLICT:
                    status = AvailabilityStatus.CONFLICT
                elif scenario is FakeScenario.SIMULTANEOUS_THRESHOLD:
                    status = AvailabilityStatus.REQUIRES_MANUAL_APPROVAL
            return AvailabilityResult(status)

        self.availability.check_availability.side_effect = check

    def quote_count(self):
        return self.seeded + len(self.repository.added)

    def assert_nothing_committed(self):
        with Session(self.sync) as session:
            assert session.scalar(select(func.count()).select_from(QuoteModel)) == self.seeded


class TestRealCreateQuote(RealHooks, CreateQuoteContract):
    def make_port(self):
        return self.create_port()

    async def test_observations_and_prices_survive_catalog_changes(self):
        created = await self.create_port().execute(
            create_input(observations="Acceso por puerta lateral")
        )
        await self.session.execute(
            text("UPDATE packages SET base_price=5000 WHERE id=:id"), {"id": PACKAGE_ID}
        )
        detail = await GetQuoteUseCase(self.repository).execute(created.quote_id)
        assert detail.observations == "Acceso por puerta lateral"
        assert detail.package.base_price == Decimal("1000.00")
        self.assert_nothing_committed()

    async def test_duration_comes_from_package_and_event_is_local_lima(self):
        self.now = datetime(2026, 10, 16, 4, 0, tzinfo=UTC)  # 23:00 del día 15 en Lima.
        await self.create_port().execute(create_input(event_time=time(23, 30)))
        assert self.availability.check_availability.await_args.args[0].duration_minutes == 90
        with pytest.raises(ValidationError):
            await self.create_port().execute(create_input(event_time=time(22, 0)))

    async def test_route_failure_uses_zone_without_contacting_maps(self):
        port = self.create_port()
        port._routes = SimpleNamespace(
            estimate=AsyncMock(side_effect=RouteEstimationError("offline"))
        )
        result = await port.execute(create_input(location_district="Distrito desconocido"))
        assert result.calculated_distance_km is None
        assert result.final_mobility_amount == Decimal("70.00")

    async def test_transaction_rollback_removes_quote_and_new_client(self):
        await self.create_port().execute(create_input())
        await self.session.rollback()
        with Session(self.sync) as session:
            assert session.scalar(select(func.count()).select_from(QuoteModel)) == 0
            assert session.scalar(select(func.count()).select_from(ClientModel)) == 0


class TestRealGetQuote(RealHooks, GetQuoteContract):
    def make_port(self):
        return GetQuoteUseCase(self.repository)


class TestRealListQuotes(RealHooks, ListQuotesContract):
    def make_port(self):
        return ListQuotesUseCase(self.repository)


class TestRealExpireQuotes(RealHooks, ExpireDueQuotesContract):
    def make_port(self):
        return ExpireDueQuotesUseCase(self.repository, self.clock)

    async def test_manual_approval_also_prevents_expiry_at_exact_boundary(self):
        quote_id = self.seed_quote(
            QuoteStatus.PAYMENT_STARTED, age=timedelta(hours=24), payment_in_verification=True
        )
        with self.sync.begin() as conn:
            conn.execute(
                text(
                    "UPDATE payments SET validation_status='REQUIRES_MANUAL_APPROVAL' "
                    "WHERE quote_id=:id"
                ),
                {"id": quote_id},
            )
        assert await self.make_port().execute() == 0
        assert (await self.repository.get_by_id(quote_id)).status is QuoteStatus.PAYMENT_STARTED

    async def test_skip_locked_quote_then_expires_after_lock_is_released(self):
        quote_id = self.seed_quote(QuoteStatus.SENT, age=timedelta(hours=25))
        with self.sync.connect() as conn:
            tx = conn.begin()
            conn.execute(text("SELECT id FROM quotes WHERE id=:id FOR UPDATE"), {"id": quote_id})
            assert await self.make_port().execute() == 0
            tx.rollback()
        assert await self.make_port().execute() == 1
        self.assert_nothing_committed()

    async def test_cron_commits_and_runs_every_minute(self, monkeypatch):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.infrastructure.adapters.primary.jobs import worker
        from app.infrastructure.di import containers

        quote_id = self.seed_quote(QuoteStatus.SENT, age=timedelta(hours=25))
        monkeypatch.setattr(worker, "get_sessionmaker", lambda: async_sessionmaker(self.engine))
        monkeypatch.setattr(containers, "get_clock_port", lru_cache()(lambda: self.clock))
        assert await worker.expire_due_quotes({}) == 1
        assert await worker.expire_due_quotes({}) == 0
        with Session(self.sync) as session:
            assert session.get(QuoteModel, quote_id).status == "EXPIRED"
        job = next(
            job for job in worker.WorkerSettings.cron_jobs if job.name == "expire_due_quotes"
        )
        assert job.second == 0
        assert job.minute is None


class TestRealPayAdvance(RealHooks, PayAdvanceContract):
    def make_port(self):
        return PayAdvanceUseCase(
            self.repository,
            SqlAlchemyCatalogReadRepository(self.session),
            self.availability,
            self.clock,
            PaymentInstructionsDTO(
                yape=WalletInstructionDTO(phone="900000000", holder="Titular"),
                plin=WalletInstructionDTO(phone="900000000", holder="Titular"),
                bank_transfer=BankTransferInstructionDTO(
                    bank="Banco",
                    account="000-00000000-0-00",
                    cci="00000000000000000000",
                    holder="Titular",
                ),
            ),
            recheck_minutes=60,
        )

    def arrange(self, port, scenario):
        # El contrato siembra una cotización recién enviada; para forzar la revalidación
        # en los escenarios de disponibilidad se adelanta la ventana de comprobación.
        if scenario in (FakeScenario.AVAILABILITY_CONFLICT, FakeScenario.SIMULTANEOUS_THRESHOLD):
            port._recheck_minutes = -1
        else:
            port._recheck_minutes = 60
        super().arrange(port, scenario)


class TestRealCancelQuote(RealHooks, CancelQuoteContract):
    def make_port(self):
        return CancelQuoteUseCase(self.repository)


class TestQuoteHttp(RealHooks):
    @pytest.fixture
    async def http(self, monkeypatch):
        from httpx import ASGITransport, AsyncClient

        from app.domain.value_objects.role import Role
        from app.infrastructure.adapters.primary.web.deps import AuthContext, get_auth_context
        from app.infrastructure.adapters.secondary.persistence.database import get_session
        from app.infrastructure.di import containers
        from app.main import create_app

        app = create_app()
        self.app = app
        self.auth = AuthContext(self.user_id, Role.ENCARGADO)
        app.dependency_overrides[get_auth_context] = lambda: self.auth
        monkeypatch.setattr(containers, "get_clock_port", lru_cache()(lambda: self.clock))
        monkeypatch.setattr(containers, "get_availability_port", lambda session: self.availability)

        async def write():
            async with (
                AsyncSession(self.engine, expire_on_commit=False) as session,
                session.begin(),
            ):
                yield session

        async def read():
            async with AsyncSession(self.engine) as session:
                yield session

        app.dependency_overrides[containers.get_quote_write_session] = write
        app.dependency_overrides[get_session] = read
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            yield client

    def payload(self):
        return {
            "package_id": str(PACKAGE_ID),
            "event_date": "2026-10-15",
            "event_time": "21:30",
            "location_address": "Av. Principal",
            "location_district": "Miraflores",
            "client": {"full_name": "Cliente HTTP", "phone": "999888777", "dni": "12345678"},
            "observations": "Puerta lateral",
        }

    async def test_create_list_detail_and_decimal_serialization(self, http):
        response = await http.post("/api/v1/quotes", json=self.payload())
        assert response.status_code == 201, response.text
        created = response.json()
        assert isinstance(created["total_amount"], str)
        detail = await http.get("/api/v1/quotes/" + created["quote_id"])
        assert detail.status_code == 200
        assert detail.json()["observations"] == "Puerta lateral"
        page = await http.get("/api/v1/quotes", params={"status": "SENT", "page_size": 1})
        assert page.status_code == 200
        assert page.json()["total"] == 1
        with Session(self.sync) as session:
            assert session.scalar(select(func.count()).select_from(QuoteModel)) == 1
            assert session.scalar(select(ClientModel)).dni == "12345678"

    async def test_operator_is_forbidden_and_unknown_quote_is_not_found(self, http):
        from app.domain.value_objects.role import Role
        from app.infrastructure.adapters.primary.web.deps import AuthContext

        self.auth = AuthContext(self.user_id, Role.OPERADOR)
        assert (await http.get("/api/v1/quotes")).status_code == 403
        assert (await http.post("/api/v1/quotes", json=self.payload())).status_code == 403
        self.auth = AuthContext(self.user_id, Role.SUPERADMIN)
        assert (await http.get(f"/api/v1/quotes/{uuid4()}")).status_code == 404

    async def test_validation_and_availability_problem_extensions(self, http):
        response = await http.get("/api/v1/quotes?from_date=2026-11-01&to_date=2026-10-01")
        assert response.status_code == 422
        self.arrange(None, FakeScenario.AVAILABILITY_CONFLICT)
        response = await http.post("/api/v1/quotes", json=self.payload())
        assert response.status_code == 409
        assert response.json()["handoff_available"] is True
        assert response.json()["alternatives"]

    async def test_pay_advance_and_cancel_http_flow(self, http):
        created = await http.post("/api/v1/quotes", json=self.payload())
        assert created.status_code == 201, created.text
        quote_id = created.json()["quote_id"]
        paid = await http.post(f"/api/v1/quotes/{quote_id}/pay-advance")
        assert paid.status_code == 200, paid.text
        body = paid.json()
        assert body["status"] == "PAYMENT_STARTED"
        assert body["rechecked"] is False
        assert body["payment_instructions"]["yape"]["phone"] == "900000000"
        assert body["payment_instructions"]["bank_transfer"]["cci"] == "00000000000000000000"
        again = await http.post(f"/api/v1/quotes/{quote_id}/pay-advance")
        assert again.status_code == 200
        assert again.json()["payment_deadline"] == body["payment_deadline"]
        cancelled = await http.post(
            f"/api/v1/quotes/{quote_id}/cancel", json={"reason": "Cliente desistió"}
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
        repeated = await http.post(f"/api/v1/quotes/{quote_id}/cancel")
        assert repeated.status_code == 409
        assert repeated.json()["type"].endswith("invalid-quote-state")
        with Session(self.sync) as session:
            assert session.get(QuoteModel, UUID(quote_id)).status == "CANCELLED"

    async def test_pay_advance_rechecks_availability_and_hides_payment_data(self, http):
        created = await http.post("/api/v1/quotes", json=self.payload())
        quote_id = created.json()["quote_id"]
        with self.sync.begin() as conn:
            conn.execute(
                text("UPDATE quotes SET sent_at = sent_at - interval '90 minutes' WHERE id=:id"),
                {"id": quote_id},
            )
        self.arrange(None, FakeScenario.AVAILABILITY_CONFLICT)
        response = await http.post(f"/api/v1/quotes/{quote_id}/pay-advance")
        assert response.status_code == 409, response.text
        problem = response.json()
        assert problem["alternatives"]
        assert problem["handoff_available"] is True
        assert "payment_instructions" not in problem
        self.arrange(None, FakeScenario.OK)
        paid = await http.post(f"/api/v1/quotes/{quote_id}/pay-advance")
        assert paid.status_code == 200, paid.text
        assert paid.json()["status"] == "PAYMENT_STARTED"
        assert paid.json()["rechecked"] is True

    async def test_lifecycle_endpoints_require_manager_role(self, http):
        from app.domain.value_objects.role import Role
        from app.infrastructure.adapters.primary.web.deps import AuthContext

        self.auth = AuthContext(self.user_id, Role.OPERADOR)
        unknown = uuid4()
        assert (await http.post(f"/api/v1/quotes/{unknown}/pay-advance")).status_code == 403
        assert (await http.post(f"/api/v1/quotes/{unknown}/cancel")).status_code == 403
        self.auth = AuthContext(self.user_id, Role.ENCARGADO)
        assert (await http.post(f"/api/v1/quotes/{unknown}/pay-advance")).status_code == 404
        assert (await http.post(f"/api/v1/quotes/{unknown}/cancel")).status_code == 404

    async def test_http_rollback_after_persistence_failure(self, http, monkeypatch):
        original = SqlAlchemyQuoteRepository.add

        async def fail_after_flush(repo, quote):
            await original(repo, quote)
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(SqlAlchemyQuoteRepository, "add", fail_after_flush)
        assert (await http.post("/api/v1/quotes", json=self.payload())).status_code == 500
        with Session(self.sync) as session:
            assert session.scalar(select(func.count()).select_from(QuoteModel)) == 0
            assert session.scalar(select(func.count()).select_from(ClientModel)) == 0

    async def test_anonymous_request_is_unauthorized(self, http):
        from app.infrastructure.adapters.primary.web.deps import get_auth_context

        self.app.dependency_overrides.pop(get_auth_context)
        assert (await http.get("/api/v1/quotes")).status_code == 401


def test_observations_migration_round_trip(migrated_url):
    from pathlib import Path

    from alembic.config import Config
    from sqlalchemy import inspect

    from alembic import command

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", migrated_url)
    engine = create_engine(migrated_url.replace("+asyncpg", "+pg8000"))
    try:
        assert "observations" in {c["name"] for c in inspect(engine).get_columns("quotes")}
        command.downgrade(config, "0005_event_financial_snapshots")
        assert "observations" not in {c["name"] for c in inspect(engine).get_columns("quotes")}
    finally:
        command.upgrade(config, "head")
        engine.dispose()
    with create_engine(migrated_url.replace("+asyncpg", "+pg8000")).connect() as connection:
        assert "observations" in {c["name"] for c in inspect(connection).get_columns("quotes")}
