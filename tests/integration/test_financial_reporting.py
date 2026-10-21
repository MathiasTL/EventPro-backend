"""US-21: PostgreSQL real, reportes, cierre atómico y migración histórica."""

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from alembic import command
from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.dtos.financial_dto import FinancialPnlRequest
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.application.use_cases.financial.get_financial_pnl import GetFinancialPnlUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.exceptions.event_exceptions import InvalidEventStateError
from app.domain.exceptions.financial_exceptions import FinancialDataInconsistentError
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.financial_reporting import AccountingPeriod, PeriodType
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine, get_session
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.models.event_financial_snapshot_model import (  # noqa: E501
    EventFinancialSnapshotModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_financial_repository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_event_repository import (  # noqa: E501
    SqlAlchemyEventRepository,
)
from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_financial_repository import (  # noqa: E501
    SqlAlchemyFinancialRepository,
)
from app.infrastructure.adapters.secondary.persistence.user_repository import (
    SQLAlchemyUserRepository,
)  # noqa: E501
from app.infrastructure.di import containers
from app.main import create_app
from tests.event_support import make_event
from tests.start_event_support import FixedClock

from ._support import insert_quotes, insert_user, run_migrations

pytestmark = pytest.mark.integration


@pytest.fixture
def db(database_url):
    run_migrations(database_url)

    async def clean():
        engine = build_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("TRUNCATE events CASCADE"))
        finally:
            await engine.dispose()

    asyncio.run(clean())
    return database_url


async def seed(
    factory,
    *,
    day=date(2026, 10, 15),
    status=EventStatus.IN_PROGRESS,
    extension=False,
    legacy=False,
):
    engine = factory.kw["bind"]
    evt = make_event(
        event_date=day,
        status=status,
        total_services_amount=Money(Decimal(950)),
        total_mobility_amount=Money(Decimal(50)),
        final_total_amount=Money(Decimal(1000)),
        pre_show_balance_paid=Money(Decimal(800 if extension or legacy else 900)),
        extra_hours_amount=Money(Decimal(100 if extension or legacy else 0)),
        extra_minutes_total=30 if extension else 0,
        legacy_extra_hours_amount=Money(Decimal(100 if legacy else 0)),
    )
    await insert_quotes(engine, [evt.quote_id])
    actor = ScheduleActor(await insert_user(engine, "ENCARGADO"), Role.ENCARGADO)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE packages SET direct_cost=400 WHERE id=(SELECT package_id FROM "
                "quotes WHERE id=:q)"
            ),
            {"q": evt.quote_id},
        )
        await connection.execute(
            text("UPDATE quotes SET base_mobility_amount=50 WHERE id=:q"), {"q": evt.quote_id}
        )
        for _ in range(2):
            extra = await connection.scalar(
                text(
                    "INSERT INTO extras (name,sale_price,direct_cost) VALUES "
                    "('Extra',100,50) RETURNING id"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO quote_extras "
                    "(quote_id,extra_id,quantity,unit_price,subtotal) VALUES "
                    "(:q,:x,1,100,100)"
                ),
                {"q": evt.quote_id, "x": extra},
            )
    async with factory() as session:
        session.add(event_to_model(evt))
        await session.commit()
        if extension:
            payment_id = uuid4()
            await session.execute(
                text(
                    """INSERT INTO payments
                (id,quote_id,event_id,concept,payment_method,amount,evidence_path,validation_status,audit_status,registered_by_user_id)
                VALUES (:p,:q,:e,'EXTENSION','CASH',100,'existing.png','VERIFIED','UNREVIEWED',:u)
            """
                ),
                {"p": payment_id, "q": evt.quote_id, "e": evt.id, "u": actor.user_id},
            )
            await session.execute(
                text(
                    "INSERT INTO event_extensions "
                    "(event_id,payment_id,extra_minutes,agreed_rate,requested_at) "
                    "VALUES (:e,:p,30,100,now())"
                ),
                {"e": evt.id, "p": payment_id},
            )
            await session.commit()
    return evt, actor


async def settle(factory, evt, actor):
    async with factory() as session:
        return await SettleEventUseCase(
            SqlAlchemyEventRepository(session), FakeCrewScheduleReadAdapter(), FixedClock()
        ).execute(evt.id, actor)


async def report(factory, year=2026, month=10, week=None):
    async with factory() as session:
        return await GetFinancialPnlUseCase(SqlAlchemyFinancialRepository(session)).execute(
            FinancialPnlRequest(
                PeriodType.MONTHLY if week is None else PeriodType.WEEKLY,
                year,
                month=month if week is None else None,
                week=week,
            )
        )


def test_ten_settled_events_have_exact_profit_and_no_join_multiplication(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            for index in range(10):
                evt, actor = await seed(factory, extension=index % 2 == 0)
                await settle(factory, evt, actor)
            for status in (EventStatus.IN_PROGRESS, EventStatus.CANCELLED, EventStatus.SCHEDULED):
                await seed(factory, status=status)
            outside, actor = await seed(factory, day=date(2026, 11, 1))
            await settle(factory, outside, actor)
            for pnl in (await report(factory), await report(factory, week=42)):
                assert pnl.total_events_settled == 10
                assert pnl.gross_revenue == Decimal(10000)
                assert pnl.direct_costs.total_costs == Decimal(5500)
                assert pnl.net_profit == Decimal(4500)
                assert pnl.profit_margin_percentage == Decimal(45)
            assert (await report(factory, month=9)).total_events_settled == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_costs_remain_frozen_after_catalog_changes_and_ignore_inactive(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            evt, actor = await seed(factory, legacy=True)
            async with factory() as session:
                await session.execute(
                    text(
                        "UPDATE extras SET is_active=false WHERE id IN (SELECT "
                        "extra_id FROM quote_extras WHERE quote_id=:q)"
                    ),
                    {"q": evt.quote_id},
                )
                await session.execute(
                    text("UPDATE quote_extras SET quantity=2 WHERE quote_id=:q"),
                    {"q": evt.quote_id},
                )
                await session.commit()
            await settle(factory, evt, actor)
            before = await report(factory)
            async with factory() as session:
                await session.execute(text("UPDATE packages SET direct_cost=999"))
                await session.execute(text("UPDATE extras SET direct_cost=999"))
                await session.execute(text("UPDATE quotes SET base_mobility_amount=999"))
                await session.commit()
                snapshot = await session.get(EventFinancialSnapshotModel, evt.id)
                assert snapshot.details["revenue"]["legacy_extra_hours_amount"] == "100.00"
                assert snapshot.details["extras"][0]["quantity"] == 2
            assert await report(factory) == before
            assert before.gross_revenue == Decimal(1000)
            assert before.direct_costs.fixed_extras_cost == Decimal(200)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_client_transport_and_large_accumulated_revenue(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            for _ in range(2):
                evt, actor = await seed(factory)
                async with factory() as session:
                    await session.execute(
                        text("UPDATE quotes SET client_provides_mobility=true WHERE id=:q"),
                        {"q": evt.quote_id},
                    )
                    await session.execute(
                        text(
                            "UPDATE events SET advance_paid=99999999, "
                            "pre_show_balance_paid=99999999 WHERE id=:e"
                        ),
                        {"e": evt.id},
                    )
                    await session.commit()
                await settle(factory, evt, actor)
            pnl = await report(factory)
            assert pnl.gross_revenue == Decimal(399999996)
            assert pnl.direct_costs.mobility_operational_cost == 0
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_missing_snapshot_rejects_period_instead_of_partial_report(db, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(sqlalchemy_financial_repository, "logger", logger)

    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            first, _ = await seed(factory, status=EventStatus.SETTLED)
            second, _ = await seed(factory, status=EventStatus.SETTLED)
            await seed(factory, day=date(2026, 11, 1), status=EventStatus.SETTLED)
            with pytest.raises(FinancialDataInconsistentError):
                await report(factory)
            logger.warning.assert_called_once_with(
                "financial_data_inconsistent",
                period="2026-10",
                missing_snapshots=2,
                event_ids=sorted([str(first.id), str(second.id)]),
            )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", ["insert", "commit"])
def test_failed_snapshot_rolls_back_event_and_releases_lock(db, failure):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            evt, actor = await seed(factory)
            async with factory() as session:

                def fail(*args):
                    raise RuntimeError("forced failure")

                if failure == "commit":
                    sqlalchemy_event.listen(session.sync_session, "before_commit", fail)
                else:
                    await session.execute(
                        text("""CREATE FUNCTION reject_snapshot() RETURNS trigger
                            LANGUAGE plpgsql AS $$
                        BEGIN RAISE EXCEPTION 'forced failure'; END; $$""")
                    )
                    await session.execute(
                        text(
                            "CREATE TRIGGER reject_snapshot BEFORE INSERT ON "
                            "event_financial_snapshots FOR EACH ROW EXECUTE FUNCTION "
                            "reject_snapshot()"
                        )
                    )
                    await session.commit()
                with pytest.raises(Exception, match="forced failure"):
                    await SettleEventUseCase(
                        SqlAlchemyEventRepository(session),
                        FakeCrewScheduleReadAdapter(),
                        FixedClock(),
                    ).execute(evt.id, actor)
            async with factory() as session:
                assert (await session.get(EventModel, evt.id)).status == "IN_PROGRESS"
                assert await session.get(EventFinancialSnapshotModel, evt.id) is None
                if failure == "insert":
                    await session.execute(
                        text("DROP TRIGGER reject_snapshot ON event_financial_snapshots")
                    )
                    await session.execute(text("DROP FUNCTION reject_snapshot()"))
                    await session.commit()
            await asyncio.wait_for(settle(factory, evt, actor), timeout=5)
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_two_closures_and_report_during_pending_commit(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        locked, release = asyncio.Event(), asyncio.Event()
        tasks = []
        try:
            evt, actor = await seed(factory)

            class BlockingRepository(SqlAlchemyEventRepository):
                async def save_settlement(self, event, snapshot):
                    locked.set()
                    await release.wait()
                    await super().save_settlement(event, snapshot)

            async def attempt(first):
                async with factory() as session:
                    repo = (
                        BlockingRepository(session) if first else SqlAlchemyEventRepository(session)
                    )
                    try:
                        return await SettleEventUseCase(
                            repo, FakeCrewScheduleReadAdapter(), FixedClock()
                        ).execute(evt.id, actor)
                    except InvalidEventStateError as exc:
                        return exc

            tasks.append(asyncio.create_task(attempt(True)))
            await asyncio.wait_for(locked.wait(), 5)
            assert (await report(factory)).total_events_settled == 0
            tasks.append(asyncio.create_task(attempt(False)))
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
            assert isinstance(results[1], InvalidEventStateError)
            assert (await report(factory)).total_events_settled == 1
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await engine.dispose()

    asyncio.run(exercise())


def test_api_reads_postgres_with_fresh_rbac(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()

        async def session_dependency():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_session] = session_dependency
        app.dependency_overrides[containers.get_user_repository] = lambda: SQLAlchemyUserRepository(
            factory
        )
        try:
            evt, actor = await seed(factory)
            await settle(factory, evt, actor)
            token = create_access_token(
                subject=str(actor.user_id),
                role="ENCARGADO",
                secret_key=get_settings().secret_key,
                expires_minutes=60,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/reports/financial/pnl",
                    params={"period_type": "MONTHLY", "year": 2026, "month": 10},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert response.status_code == 200
                assert response.json()["net_profit"] == 450
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(exercise())


def test_migration_backfills_and_is_reversible(db):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db)
    command.downgrade(config, "0004_outbox_delivery_tracking")

    async def seed_historical():
        engine = build_engine(db)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            evt, _ = await seed(factory, status=EventStatus.SETTLED, extension=True)
            await seed(factory, status=EventStatus.SETTLED, legacy=True)
            return evt.id
        finally:
            await engine.dispose()

    event_id = asyncio.run(seed_historical())
    command.upgrade(config, "head")
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0007_contract_signature"]
    assert (
        scripts.get_revision("0005_event_financial_snapshots").down_revision
        == "0004_outbox_delivery_tracking"
    )

    async def check():
        engine = build_engine(db)
        try:
            # US-21 valida su tabla sin incluir los defaults de movilidad de develop.
            def schema_diff(connection):
                context = MigrationContext.configure(
                    connection,
                    opts={
                        "compare_type": True,
                        "compare_server_default": True,
                        "include_object": lambda obj, name, type_, reflected, compare_to: (
                            name == "event_financial_snapshots"
                            if type_ == "table"
                            else obj.table.name == "event_financial_snapshots"
                        ),
                    },
                )
                return compare_metadata(context, EventFinancialSnapshotModel.metadata)

            async with engine.connect() as connection:
                assert await connection.run_sync(schema_diff) == []
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0007_contract_signature"
                )
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                snapshot = await session.get(EventFinancialSnapshotModel, event_id)
                assert snapshot.origin == "LEGACY_BACKFILL"
                assert snapshot.gross_revenue == Decimal(1000)
                assert snapshot.fixed_extras_cost == Decimal(100)
                assert snapshot.details["revenue"]["verified_extension_amount"] == "100.00"
                totals = await SqlAlchemyFinancialRepository(session).get_totals(
                    AccountingPeriod.create(PeriodType.MONTHLY, 2026, month=10)
                )
                assert totals.total_events_settled == 2
                assert totals.gross_revenue.amount == Decimal(2000)
        finally:
            await engine.dispose()

    asyncio.run(check())
    command.downgrade(config, "0004_outbox_delivery_tracking")
    command.upgrade(config, "head")
    asyncio.run(check())


def test_downgrade_loses_frozen_costs_and_upgrade_uses_current_catalog(db):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db)

    async def seed_settlement():
        engine = build_engine(db)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            evt, actor = await seed(factory)
            await settle(factory, evt, actor)
            async with factory() as session:
                snapshot = await session.get(EventFinancialSnapshotModel, evt.id)
                assert snapshot.origin == "SETTLEMENT"
                assert snapshot.fixed_packages_cost == Decimal(400)
                await session.execute(
                    text(
                        "UPDATE packages SET direct_cost=700 WHERE id=("
                        "SELECT package_id FROM quotes WHERE id=:q)"
                    ),
                    {"q": evt.quote_id},
                )
                await session.commit()
            return evt.id
        finally:
            await engine.dispose()

    event_id = asyncio.run(seed_settlement())
    command.downgrade(config, "0004_outbox_delivery_tracking")

    async def check_downgrade():
        engine = build_engine(db)
        try:
            async with engine.connect() as connection:
                assert not await connection.run_sync(
                    lambda conn: inspect(conn).has_table("event_financial_snapshots")
                )
                assert await connection.run_sync(
                    lambda conn: (
                        "delivery_status"
                        in {col["name"] for col in inspect(conn).get_columns("outbox_messages")}
                    )
                )
                assert (
                    await connection.scalar(
                        text("SELECT status FROM events WHERE id=:e"), {"e": event_id}
                    )
                    == "SETTLED"
                )
        finally:
            await engine.dispose()

    try:
        asyncio.run(check_downgrade())
    finally:
        command.upgrade(config, "head")

    async def check_rebuilt():
        engine = build_engine(db)
        try:
            async with async_sessionmaker(engine)() as session:
                snapshot = await session.get(EventFinancialSnapshotModel, event_id)
                assert snapshot.origin == "LEGACY_BACKFILL"
                assert snapshot.fixed_packages_cost == Decimal(700)
                assert snapshot.gross_revenue == Decimal(1000)
        finally:
            await engine.dispose()

    asyncio.run(check_rebuilt())


def test_migration_times_out_on_concurrent_writer_and_can_be_retried(db):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db)
    command.downgrade(config, "0004_outbox_delivery_tracking")

    async def exercise():
        engine = build_engine(db)
        try:
            async with engine.begin() as writer:
                await writer.execute(text("LOCK TABLE events IN ROW EXCLUSIVE MODE"))
                with pytest.raises(Exception, match="lock timeout"):
                    await asyncio.wait_for(
                        asyncio.to_thread(command.upgrade, config, "head"), timeout=15
                    )
            async with engine.connect() as connection:
                assert (
                    await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == "0004_outbox_delivery_tracking"
                )
                assert not await connection.run_sync(
                    lambda conn: inspect(conn).has_table("event_financial_snapshots")
                )
        finally:
            await engine.dispose()

    try:
        asyncio.run(exercise())
    finally:
        command.upgrade(config, "head")


def test_iso_week_and_month_boundaries_use_event_date(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            for day in (date(2020, 12, 27), date(2020, 12, 28), date(2021, 1, 3), date(2021, 1, 4)):
                evt, actor = await seed(factory, day=day)
                await settle(factory, evt, actor)
            assert (await report(factory, year=2020, week=53)).total_events_settled == 2
            assert (await report(factory, year=2020, month=12)).total_events_settled == 2
            assert (await report(factory, year=2021, month=1)).total_events_settled == 2
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_catalog_update_during_capture_keeps_one_coherent_cost_read(db):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        read, release = asyncio.Event(), asyncio.Event()
        task = None
        try:
            evt, actor = await seed(factory)

            class PausingRepository(SqlAlchemyEventRepository):
                async def get_settlement_costs(self, event_id):
                    costs = await super().get_settlement_costs(event_id)
                    read.set()
                    await release.wait()
                    return costs

            async def close():
                async with factory() as session:
                    await SettleEventUseCase(
                        PausingRepository(session), FakeCrewScheduleReadAdapter(), FixedClock()
                    ).execute(evt.id, actor)

            task = asyncio.create_task(close())
            await asyncio.wait_for(read.wait(), 5)
            async with factory() as session:
                await session.execute(text("UPDATE packages SET direct_cost=900"))
                await session.execute(text("UPDATE extras SET direct_cost=900"))
                await session.commit()
            release.set()
            await asyncio.wait_for(task, 5)
            pnl = await report(factory)
            assert pnl.direct_costs.fixed_packages_cost == Decimal(400)
            assert pnl.direct_costs.fixed_extras_cost == Decimal(100)
        finally:
            release.set()
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("corruption", ["amount", "orphan", "nonverified", "mobility"])
def test_migration_inconsistent_history_is_atomic(db, corruption):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", db)
    command.downgrade(config, "0004_outbox_delivery_tracking")

    async def corrupt():
        engine = build_engine(db)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            events = [
                (await seed(factory, status=EventStatus.SETTLED, extension=True))[0]
                for _ in range(2)
            ]
            async with factory() as session:
                statements = {
                    "amount": "UPDATE events SET extra_hours_amount=200 WHERE id=:e",
                    "orphan": "DELETE FROM event_extensions WHERE event_id=:e",
                    "nonverified": "UPDATE payments SET concept='ADVANCE', audit_status=NULL, "
                    "validation_status='PENDING_VERIFICATION' WHERE event_id=:e",
                    "mobility": "UPDATE quotes SET base_mobility_amount=-1 WHERE id=:q",
                }
                for evt in events:
                    await session.execute(
                        text(statements[corruption]), {"e": evt.id, "q": evt.quote_id}
                    )
                await session.commit()
            return [evt.id for evt in events]
        finally:
            await engine.dispose()

    event_ids = asyncio.run(corrupt())
    try:
        with pytest.raises(Exception, match="financial-data-inconsistent") as error:
            command.upgrade(config, "head")
        for event_id in event_ids:
            assert str(event_id) in str(error.value)

        async def check_and_restore():
            engine = build_engine(db)
            try:
                async with engine.begin() as connection:
                    assert (
                        await connection.scalar(text("SELECT version_num FROM alembic_version"))
                        == "0004_outbox_delivery_tracking"
                    )
                    assert not await connection.run_sync(
                        lambda conn: inspect(conn).has_table("event_financial_snapshots")
                    )
                    for event_id in event_ids:
                        assert (
                            await connection.scalar(
                                text("SELECT status FROM events WHERE id=:e"), {"e": event_id}
                            )
                            == "SETTLED"
                        )
                        await connection.execute(
                            text("UPDATE events SET status='IN_PROGRESS' WHERE id=:e"),
                            {"e": event_id},
                        )
            finally:
                await engine.dispose()

        asyncio.run(check_and_restore())
    finally:
        command.upgrade(config, "head")


@pytest.mark.parametrize(
    "column,value",
    [
        ("gross_revenue", "-1"),
        ("gross_revenue", "'NaN'::numeric"),
        ("origin", "'UNRECOGNIZED'"),
        ("details", "'[]'::jsonb"),
    ],
)
def test_snapshot_database_checks(db, column, value):
    async def exercise():
        engine = build_engine(db)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            evt, actor = await seed(factory)
            await settle(factory, evt, actor)
            async with factory() as session:
                with pytest.raises(IntegrityError):
                    await session.execute(
                        text(
                            f"UPDATE event_financial_snapshots SET {column}={value} "
                            "WHERE event_id=:e"
                        ),
                        {"e": evt.id},
                    )
                await session.rollback()
            async with factory() as session:
                row = await session.get(EventFinancialSnapshotModel, evt.id)
                session.expunge(row)
                session.add(
                    EventFinancialSnapshotModel(
                        event_id=evt.id,
                        gross_revenue=0,
                        fixed_packages_cost=0,
                        fixed_extras_cost=0,
                        mobility_operational_cost=0,
                        recorded_at=row.recorded_at,
                        origin="SETTLEMENT",
                        details={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
