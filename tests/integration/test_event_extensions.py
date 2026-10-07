"""US-18 sobre PostgreSQL 16: migración, API, atomicidad y concurrencia."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from itertools import count
from typing import Annotated
from uuid import uuid4

import httpx
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from app.application.dtos.event_schedule_dto import ScheduleActor
from app.application.services.audit_service import AuditService
from app.application.use_cases.event.register_event_extension import RegisterEventExtensionUseCase
from app.application.use_cases.event.settle_event import SettleEventUseCase
from app.application.use_cases.payment.audit_payment import AuditPaymentUseCase
from app.application.use_cases.payment.get_payment_evidence import GetPaymentEvidenceUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.exceptions.event_exceptions import (
    ExtensionPaymentMismatchError,
    InvalidEventStateError,
)
from app.domain.value_objects.event_status import EventStatus
from app.domain.value_objects.money import Money
from app.domain.value_objects.role import Role
from app.infrastructure.adapters.secondary.external_services.fake_schedule_adapters import (
    FakeCrewScheduleReadAdapter,
)
from app.infrastructure.adapters.secondary.persistence.audit_log_adapter import (
    SQLAlchemyAuditLogAdapter,
)
from app.infrastructure.adapters.secondary.persistence.database import build_engine, get_session
from app.infrastructure.adapters.secondary.persistence.mappers.event_mapper import event_to_model
from app.infrastructure.adapters.secondary.persistence.models.event_extension_model import (
    EventExtensionModel,
)
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.models.role import Role as RoleModel
from app.infrastructure.adapters.secondary.persistence.models.user import User
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_repository,
    sqlalchemy_payment_repository,
)
from app.infrastructure.adapters.secondary.storage.local_evidence_storage import (
    LocalEvidenceStorage,
)
from app.infrastructure.di import containers
from app.main import create_app
from tests.event_support import make_event
from tests.extension_support import PNG_BYTES, extension_input
from tests.start_event_support import STARTED_AT, FixedClock

from ._support import insert_quotes, run_migrations

_SEED_COUNT = count()

pytestmark = pytest.mark.integration
SqlAlchemyEventRepository = sqlalchemy_event_repository.SqlAlchemyEventRepository
SqlAlchemyPaymentRepository = sqlalchemy_payment_repository.SqlAlchemyPaymentRepository


async def seed_event(factory):
    event = make_event(
        status=EventStatus.IN_PROGRESS,
        pre_show_balance_paid=Money(Decimal("980.50")),
        event_date=date(2026, 10, 15) + timedelta(days=next(_SEED_COUNT)),
    )
    await insert_quotes(factory.kw["bind"], [event.quote_id])
    actor = ScheduleActor(uuid4(), Role.ENCARGADO)
    async with factory() as session:
        role_id = await session.scalar(select(RoleModel.id).where(RoleModel.code == "ENCARGADO"))
        if role_id is None:
            role_id = uuid4()
            session.add(RoleModel(id=role_id, code="ENCARGADO", name="Encargado"))
            await session.flush()
        session.add(
            User(
                id=actor.user_id,
                role_id=role_id,
                full_name="Operador de prueba",
                email=f"{actor.user_id}@example.test",
                phone=actor.user_id.hex[:20],
                hashed_password="unused-test-hash",
            )
        )
        session.add(event_to_model(event))
        await session.commit()
    return event, actor


def storage_at(tmp_path):
    return LocalEvidenceStorage(tmp_path, allowed_mime={"image/jpeg", "image/png", "image/webp"})


def test_migration_extends_previous_head_and_preserves_existing_events(database_url):
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0002_event_extensions"]
    assert scripts.get_revision("0002_event_extensions").down_revision == "0001_initial_schema"
    command.upgrade(config, "0001_initial_schema")
    event_id, quote_id, orphan_id, orphan_quote_id, user_id = [uuid4() for _ in range(5)]

    async def legacy_insert():
        engine = build_engine(database_url)
        try:
            await insert_quotes(engine, [quote_id, orphan_quote_id])
            async with engine.begin() as connection:
                for id_, quote, code in (
                    (event_id, quote_id, "US18-LEGACY"),
                    (orphan_id, orphan_quote_id, "US18-ORPHAN"),
                ):
                    await connection.execute(
                        text(
                            "INSERT INTO events (id, event_code, quote_id, event_date, start_time, "
                            "end_time, address, district, status, total_services_amount, "
                            "total_mobility_amount, final_total_amount, extra_hours_amount, "
                            "pre_show_balance_paid) VALUES (:id, :code, "
                            ":quote_id, '2026-10-15', '23:00', '00:00', 'Local', 'Lima', "
                            "'IN_PROGRESS', 100, 0, 180, 80, 100)"
                        ),
                        {"id": id_, "quote_id": quote, "code": code},
                    )
                role_id = await connection.scalar(
                    text(
                        "INSERT INTO roles (code, name) "
                        "VALUES ('ENCARGADO', 'Encargado') RETURNING id"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO users (id, role_id, full_name, email, phone, hashed_password) "
                        "VALUES (:id, :role, 'Test', 'legacy@example.test', 'legacy-test', 'test')"
                    ),
                    {"id": user_id, "role": role_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO payments "
                        "(quote_id, event_id, concept, payment_method, amount, "
                        "evidence_path, validation_status, audit_status, registered_by_user_id) "
                        "VALUES (:quote, :event, 'EXTENSION', 'CASH', 80, 'evidence/legacy.png', "
                        "'VERIFIED', 'UNREVIEWED', :user)"
                    ),
                    {"quote": orphan_quote_id, "event": orphan_id, "user": user_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(legacy_insert())
    command.upgrade(config, "head")

    async def check(expected):
        engine = build_engine(database_url)
        try:
            async with engine.connect() as connection:
                assert (
                    await connection.run_sync(
                        lambda conn: inspect(conn).has_table("event_extensions")
                    )
                    is expected
                )
                cols = await connection.run_sync(lambda conn: inspect(conn).get_columns("events"))
                assert ("extra_minutes_total" in {col["name"] for col in cols}) is expected
                assert ("legacy_extra_hours_amount" in {col["name"] for col in cols}) is expected
                assert await connection.scalar(
                    text("SELECT final_total_amount FROM events WHERE id=:id"), {"id": event_id}
                ) == Decimal("180")
                assert await connection.scalar(
                    text("SELECT extra_hours_amount FROM events WHERE id=:id"), {"id": event_id}
                ) == Decimal("80")
                if expected:
                    assert (
                        await connection.scalar(
                            text("SELECT extra_minutes_total FROM events WHERE id=:id"),
                            {"id": event_id},
                        )
                        == 0
                    )
                    assert await connection.scalar(
                        text("SELECT legacy_extra_hours_amount FROM events WHERE id=:id"),
                        {"id": event_id},
                    ) == Decimal("80")
                    assert (
                        await connection.scalar(
                            text("SELECT legacy_extra_hours_amount FROM events WHERE id=:id"),
                            {"id": orphan_id},
                        )
                        == 0
                    )
                    fks = await connection.run_sync(
                        lambda conn: inspect(conn).get_foreign_keys("event_extensions")
                    )
                    assert {fk["referred_table"] for fk in fks} == {"events", "payments"}
                    uniques = await connection.run_sync(
                        lambda conn: inspect(conn).get_unique_constraints("event_extensions")
                    )
                    assert ["payment_id"] in [constraint["column_names"] for constraint in uniques]
                    indexes = await connection.run_sync(
                        lambda conn: inspect(conn).get_indexes("event_extensions")
                    )
                    assert "ix_event_extensions_event_id" in {index["name"] for index in indexes}
                assert (
                    await connection.scalar(
                        text("SELECT status FROM events WHERE id=:id"), {"id": event_id}
                    )
                    == "IN_PROGRESS"
                )
                assert await connection.run_sync(lambda conn: inspect(conn).has_table("payments"))
        finally:
            await engine.dispose()

    asyncio.run(check(True))
    command.downgrade(config, "0001_initial_schema")
    asyncio.run(check(False))
    command.upgrade(config, "head")

    async def settle_historical():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                with pytest.raises(ExtensionPaymentMismatchError):
                    await SqlAlchemyEventRepository(session).get_verified_extension_totals(
                        orphan_id
                    )
            async with factory() as session:
                result = await SettleEventUseCase(
                    SqlAlchemyEventRepository(session), FakeCrewScheduleReadAdapter()
                ).execute(event_id, ScheduleActor(user_id, Role.ENCARGADO))
                assert result.status is EventStatus.SETTLED
        finally:
            await engine.dispose()

    asyncio.run(settle_historical())


def test_real_api_payment_audit_and_settlement(database_url, tmp_path):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()
        storage = storage_at(tmp_path)
        try:
            event, actor = await seed_event(factory)
            crews = FakeCrewScheduleReadAdapter(
                assigned_events_by_user={actor.user_id: frozenset({event.id})}
            )

            async def session_override():
                async with factory() as session:
                    yield session

            app.dependency_overrides[get_session] = session_override
            app.dependency_overrides[containers.get_clock_port] = FixedClock
            app.dependency_overrides[containers.get_crew_schedule_read_port] = lambda: crews
            app.dependency_overrides[containers.get_extension_evidence_storage] = lambda: storage

            def audit_use_case(session: Annotated[AsyncSession, Depends(get_session)]):
                return AuditPaymentUseCase(
                    SqlAlchemyPaymentRepository(session),
                    AuditService(SQLAlchemyAuditLogAdapter(factory)),
                )

            def evidence_use_case(session: Annotated[AsyncSession, Depends(get_session)]):
                return GetPaymentEvidenceUseCase(SqlAlchemyPaymentRepository(session), storage)

            app.dependency_overrides[containers.get_audit_payment_use_case] = audit_use_case
            app.dependency_overrides[containers.get_get_payment_evidence_use_case] = (
                evidence_use_case
            )
            token = create_access_token(
                subject=str(actor.user_id), role="OPERADOR", secret_key=get_settings().secret_key
            )
            headers = {"Authorization": f"Bearer {token}"}
            admin = {
                "Authorization": "Bearer "
                + create_access_token(
                    subject=str(actor.user_id),
                    role="ENCARGADO",
                    secret_key=get_settings().secret_key,
                )
            }
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/api/v1/events/{event.id}/extensions",
                    headers=headers,
                    data={"extra_minutes": "30", "agreed_rate": "100", "payment_method": "CASH"},
                    files={"evidence_file": ("photo.png", PNG_BYTES, "image/png")},
                )
                assert response.status_code == 201, response.text
                payment_id = response.json()["payment"]["payment_id"]
                evidence = await client.get(
                    f"/api/v1/payments/{payment_id}/evidence", headers=admin
                )
                assert evidence.status_code == 200
                assert evidence.content == PNG_BYTES
                audited = await client.patch(
                    f"/api/v1/payments/{payment_id}/audit",
                    headers=admin,
                    json={"audit_status": "FLAGGED", "audit_notes": "Revisar fotografía"},
                )
                assert audited.status_code == 200, audited.text
                closed = await client.post(f"/api/v1/events/{event.id}/settle", headers=headers)
                assert closed.status_code == 200, closed.text
                assert (
                    await client.post(f"/api/v1/events/{event.id}/settle", headers=headers)
                ).status_code == 409
            async with factory() as session:
                row = await session.get(EventModel, event.id)
                assert row.status == "SETTLED"
                assert row.extra_minutes_total == 30
                assert row.extra_hours_amount == Decimal("100")
                assert row.final_total_amount == Decimal("1180.50")
                assert row.end_time == event.end_time
                extension = await session.scalar(
                    select(EventExtensionModel).where(EventExtensionModel.event_id == event.id)
                )
                payment = await session.get(PaymentModel, extension.payment_id)
                assert extension.requested_at == payment.created_at == STARTED_AT
                assert payment.validation_status == "VERIFIED"
                assert payment.audit_status == "FLAGGED"
                assert payment.registered_by_user_id == actor.user_id
                assert payment.verified_at is payment.verified_by_user_id is None
                assert extension.agreed_rate == payment.amount
                for changes in (
                    {"extra_minutes": 0},
                    {"agreed_rate": 0},
                    {"event_id": uuid4()},
                    {"payment_id": uuid4()},
                    {},
                ):
                    async with factory() as invalid_session:
                        values = dict(
                            event_id=event.id,
                            payment_id=payment.id,
                            extra_minutes=30,
                            agreed_rate=Decimal("100"),
                        )
                        values.update(changes)
                        invalid_session.add(EventExtensionModel(**values))
                        with pytest.raises(IntegrityError):
                            await invalid_session.commit()
                        await invalid_session.rollback()
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize("failure", ["commit", "foreign-key", "stale-update"])
def test_failed_extension_rolls_back_all_three_writes_and_removes_evidence(
    database_url, tmp_path, failure
):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        storage = storage_at(tmp_path)
        try:
            event, actor = await seed_event(factory)
            async with factory() as session:

                class StaleRepository(SqlAlchemyEventRepository):
                    async def save_extension(self, event, extension, payment):
                        event.extra_minutes_total += 1
                        await super().save_extension(event, extension, payment)

                repo = (
                    StaleRepository(session)
                    if failure == "stale-update"
                    else SqlAlchemyEventRepository(session)
                )

                def reject_commit(_session):
                    raise RuntimeError("commit failed")

                if failure == "commit":
                    sqlalchemy_event.listen(session.sync_session, "before_commit", reject_commit)
                if failure == "foreign-key":
                    actor = ScheduleActor(uuid4(), Role.ENCARGADO)
                error = {
                    "commit": RuntimeError,
                    "foreign-key": IntegrityError,
                    "stale-update": InvalidEventStateError,
                }[failure]
                with pytest.raises(error):
                    await RegisterEventExtensionUseCase(
                        repo, storage, FakeCrewScheduleReadAdapter(), FixedClock()
                    ).execute(extension_input(event.id), actor)
            assert list((tmp_path / "evidence").iterdir()) == []
            async with factory() as session:
                row = await session.get(EventModel, event.id)
                assert row.status == "IN_PROGRESS"
                assert row.extra_hours_amount == row.extra_minutes_total == 0
                assert row.final_total_amount == event.final_total_amount.amount
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(PaymentModel)
                        .where(PaymentModel.event_id == event.id)
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(EventExtensionModel)
                        .where(EventExtensionModel.event_id == event.id)
                    )
                    == 0
                )
        finally:
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "first,second", [("extend", "extend"), ("extend", "settle"), ("settle", "extend")]
)
def test_concurrent_operations_serialize_without_lost_updates(
    database_url, tmp_path, first, second
):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        storage = storage_at(tmp_path)
        first_locked, second_query, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        tasks = []

        def observe(_conn, _cursor, statement, _parameters, _context, _executemany):
            if (
                len(tasks) > 1
                and asyncio.current_task() is tasks[1]
                and ("FOR UPDATE" in statement or "pg_advisory_xact_lock" in statement)
            ):
                second_query.set()

        try:
            event, actor = await seed_event(factory)

            class BlockingRepository(SqlAlchemyEventRepository):
                async def get_by_id_for_update(self, event_id):
                    found = await super().get_by_id_for_update(event_id)
                    first_locked.set()
                    await release.wait()
                    return found

            async def attempt(operation, is_first):
                async with factory() as session:
                    repo = (
                        BlockingRepository(session)
                        if is_first
                        else SqlAlchemyEventRepository(session)
                    )
                    try:
                        if operation == "extend":
                            return await RegisterEventExtensionUseCase(
                                repo, storage, FakeCrewScheduleReadAdapter(), FixedClock()
                            ).execute(
                                extension_input(
                                    event.id,
                                    extra_minutes=30 if is_first else 60,
                                    agreed_rate=Decimal("100") if is_first else Decimal("50"),
                                ),
                                actor,
                            )
                        return await SettleEventUseCase(
                            repo, FakeCrewScheduleReadAdapter()
                        ).execute(event.id, actor)
                    except InvalidEventStateError as exc:
                        return exc

            sqlalchemy_event.listen(engine.sync_engine, "before_cursor_execute", observe)
            tasks.append(asyncio.create_task(attempt(first, True)))
            await asyncio.wait_for(first_locked.wait(), timeout=10)
            tasks.append(asyncio.create_task(attempt(second, False)))
            await asyncio.wait_for(second_query.wait(), timeout=10)
            assert not tasks[1].done()
            release.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
            if first == "settle":
                assert isinstance(results[1], InvalidEventStateError)
            async with factory() as session:
                row = await session.get(EventModel, event.id)
                expected_minutes = (
                    90 if second == first == "extend" else 30 if first == "extend" else 0
                )
                expected_amount = (
                    Decimal("150")
                    if expected_minutes == 90
                    else Decimal("100")
                    if expected_minutes
                    else Decimal("0")
                )
                assert row.extra_minutes_total == expected_minutes
                assert row.extra_hours_amount == expected_amount
                assert row.final_total_amount == event.final_total_amount.amount + expected_amount
                assert row.status == ("EXTENDED" if first == second else "SETTLED")
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await engine.dispose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "corruption", ["amount", "quote", "event", "concept", "nonverified", "cached-minutes", "orphan"]
)
def test_settlement_rejects_inconsistent_payments(database_url, tmp_path, corruption):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            event, actor = await seed_event(factory)
            async with factory() as session:
                await RegisterEventExtensionUseCase(
                    SqlAlchemyEventRepository(session),
                    storage_at(tmp_path),
                    FakeCrewScheduleReadAdapter(),
                    FixedClock(),
                ).execute(extension_input(event.id), actor)
            wrong_quote = uuid4()
            if corruption == "quote":
                await insert_quotes(engine, [wrong_quote])
            wrong_event = None
            if corruption == "event":
                wrong_event, _ = await seed_event(factory)
            async with factory() as session:
                if corruption == "amount":
                    await session.execute(
                        update(PaymentModel)
                        .where(PaymentModel.event_id == event.id)
                        .values(amount=Decimal("101"))
                    )
                elif corruption == "quote":
                    await session.execute(
                        update(PaymentModel)
                        .where(PaymentModel.event_id == event.id)
                        .values(quote_id=wrong_quote)
                    )
                elif corruption == "cached-minutes":
                    await session.execute(
                        update(EventModel)
                        .where(EventModel.id == event.id)
                        .values(extra_minutes_total=31)
                    )
                elif corruption == "event":
                    await session.execute(
                        update(PaymentModel)
                        .where(PaymentModel.event_id == event.id)
                        .values(event_id=wrong_event.id)
                    )
                elif corruption in {"concept", "nonverified"}:
                    # El baseline solo permite estados no verificados en ADVANCE.
                    await session.execute(
                        update(PaymentModel)
                        .where(PaymentModel.event_id == event.id)
                        .values(
                            concept="ADVANCE",
                            audit_status=None,
                            validation_status="PENDING_VERIFICATION"
                            if corruption == "nonverified"
                            else "VERIFIED",
                        )
                    )
                else:
                    await session.execute(
                        text("DELETE FROM event_extensions WHERE event_id=:id"), {"id": event.id}
                    )
                await session.commit()
            async with factory() as session:
                with pytest.raises(ExtensionPaymentMismatchError):
                    await SettleEventUseCase(
                        SqlAlchemyEventRepository(session), FakeCrewScheduleReadAdapter()
                    ).execute(event.id, actor)
            async with factory() as session:
                assert (await session.get(EventModel, event.id)).status == "EXTENDED"
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_failed_settlement_commit_preserves_state_and_releases_lock(database_url):
    run_migrations(database_url)

    async def exercise():
        engine = build_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            event, actor = await seed_event(factory)
            async with factory() as session:

                def reject_commit(_session):
                    raise RuntimeError("settlement commit failed")

                sqlalchemy_event.listen(session.sync_session, "before_commit", reject_commit)
                with pytest.raises(RuntimeError, match="settlement commit failed"):
                    await SettleEventUseCase(
                        SqlAlchemyEventRepository(session), FakeCrewScheduleReadAdapter()
                    ).execute(event.id, actor)
                assert not session.in_transaction()
            async with factory() as session:
                assert (await session.get(EventModel, event.id)).status == "IN_PROGRESS"
                closed = await asyncio.wait_for(
                    SettleEventUseCase(
                        SqlAlchemyEventRepository(session), FakeCrewScheduleReadAdapter()
                    ).execute(event.id, actor),
                    timeout=5,
                )
                assert closed.status is EventStatus.SETTLED
        finally:
            await engine.dispose()

    asyncio.run(exercise())
