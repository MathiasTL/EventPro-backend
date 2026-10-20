"""Flujo nuevo sobre PostgreSQL/Redis efímeros; nunca sobre Supabase compartido."""

import asyncio
import base64
import json
from datetime import date, timedelta
from itertools import count
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.availability_dto import AvailabilityResult, AvailabilityStatus
from app.core.config import get_settings
from app.core.security import create_access_token
from app.infrastructure.adapters.secondary.persistence.database import get_sessionmaker
from app.infrastructure.adapters.secondary.persistence.manual_booking_repository import (
    SqlAlchemyManualBookingStore,
)
from app.infrastructure.di import containers
from app.main import create_app

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SEQUENCE = count()
PREFIX = "/api/v1/manual-bookings"
pytestmark = pytest.mark.integration


@pytest.fixture
async def scenario(infra):
    app = create_app()
    factory = get_sessionmaker()
    users = {role: uuid4() for role in ["SUPERADMIN", "ENCARGADO", "OPERADOR"]}
    package, inventory = uuid4(), uuid4()
    async with factory() as session:
        for role, actor in users.items():
            await session.execute(
                text(
                    "INSERT INTO roles(code,name) VALUES (:role,:role) "
                    "ON CONFLICT (code) DO NOTHING"
                ),
                {"role": role},
            )
            await session.execute(
                text(
                    "INSERT INTO users(id,role_id,full_name,email,phone,hashed_password) "
                    "SELECT :id,id,'Prueba',:email,:phone,'test' FROM roles WHERE code=:role"
                ),
                {
                    "id": actor,
                    "email": f"{actor}@test.invalid",
                    "phone": actor.hex[:20],
                    "role": role,
                },
            )
        await session.execute(
            text(
                "INSERT INTO packages(id,name,service_category,base_price,direct_cost,"
                "duration_minutes) VALUES (:id,:name,'SHOW',100,50,90)"
            ),
            {"id": package, "name": f"Show-{package}"},
        )
        await session.execute(
            text(
                "INSERT INTO inventory_items(id,name,service_category,total_stock) "
                "VALUES (:id,:name,'DECORATION',1)"
            ),
            {"id": inventory, "name": f"Recurso-{inventory}"},
        )
        await session.execute(
            text(
                "INSERT INTO package_inventory_items(package_id,inventory_item_id,quantity) "
                "VALUES (:package,:item,1)"
            ),
            {"package": package, "item": inventory},
        )
        await session.commit()
    payload = {
        "quote_id": str(uuid4()),
        "client_name": "Cliente prueba",
        "phone": f"9{uuid4().int % 10**8:08d}",
        "address": "Av. Principal 123",
        "district": "Lima",
        "event_date": str(date.today() + timedelta(days=365 + next(SEQUENCE))),
        "start_time": "23:30",
        "package_id": str(package),
        "theme_id": None,
        "extra_ids": [],
        "client_provides_transport": True,
        "payment_method": "YAPE",
        "paid_amount": "10.00",
    }
    headers = {}
    for role, actor in users.items():
        token = create_access_token(
            subject=str(actor), role=role, secret_key=get_settings().secret_key
        )
        headers[role] = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        yield client, factory, payload, headers, users


async def register(client, payload, headers, receipt=PNG):
    return await client.post(
        PREFIX,
        data={"payload_json": json.dumps(payload)},
        files={"receipt_file": ("receipt.png", receipt, "image/png")},
        headers=headers,
    )


async def confirm(client, payload, headers, **extra):
    return await client.post(
        f"{PREFIX}/{payload['quote_id']}/confirm",
        json={"receipt_verified": True, **extra},
        headers=headers,
    )


async def test_request_receipt_reservation_contract_atomic_and_replay(scenario):
    client, factory, payload, headers, users = scenario
    first = await register(client, payload, headers["SUPERADMIN"])
    assert first.status_code == 201, first.text
    assert first.json()["payment_status"] == "PENDING_VERIFICATION"
    replay = await register(client, payload, headers["SUPERADMIN"])
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    reserved = await confirm(client, payload, headers["ENCARGADO"])
    assert reserved.status_code == 200, reserved.text
    row = reserved.json()
    assert row["payment_status"] == "VERIFIED" and row["quote_status"] == "CONVERTED"
    repeated = await confirm(client, payload, headers["ENCARGADO"])
    assert repeated.json() == row
    pdf = await client.get(f"{PREFIX}/{payload['quote_id']}/contract", headers=headers["ENCARGADO"])
    assert pdf.status_code == 200, pdf.text
    assert base64.b64decode(pdf.json()["pdf_base64"]).startswith(b"%PDF-")
    evidence = await client.get(
        f"/api/v1/payments/{row['payment_id']}/evidence", headers=headers["ENCARGADO"]
    )
    assert evidence.status_code == 200 and evidence.content == PNG, evidence.text
    async with factory() as session:
        payment = (
            await session.execute(
                text("SELECT registered_by_user_id,verified_by_user_id FROM payments WHERE id=:id"),
                {"id": row["payment_id"]},
            )
        ).one()
        assert payment.registered_by_user_id == users["SUPERADMIN"]
        assert payment.verified_by_user_id == users["ENCARGADO"]
        reservation = (
            await session.execute(
                text("SELECT starts_at,ends_at FROM inventory_reservations WHERE event_id=:id"),
                {"id": row["event_id"]},
            )
        ).one()
        assert reservation.ends_at.date() == reservation.starts_at.date() + timedelta(days=1)
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id IN (:payment,:quote,:contract)"
                ),
                {
                    "payment": row["payment_id"],
                    "quote": payload["quote_id"],
                    "contract": row["contract_id"],
                },
            )
            == 3
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_time", "10:00"),
        ("paid_amount", "11.00"),
        ("district", "Otro distrito"),
        ("event_date", "2099-01-01"),
    ],
)
async def test_changed_payload_cannot_reuse_reference(scenario, field, value):
    client, _, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    changed = {**payload, field: value}
    assert (await register(client, changed, headers["SUPERADMIN"])).status_code == 409


async def test_receipt_changed_cannot_reuse_reference(scenario):
    client, _, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    assert (
        await register(client, payload, headers["SUPERADMIN"], receipt=PNG + b"new")
    ).status_code == 409


async def test_fifteen_concurrent_confirmations_are_idempotent_without_pool_starvation(scenario):
    client, factory, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    responses = await asyncio.wait_for(
        asyncio.gather(*(confirm(client, payload, headers["ENCARGADO"]) for _ in range(15))),
        timeout=30,
    )
    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
    assert len({response.json()["event_id"] for response in responses}) == 1
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM events WHERE quote_id=:quote"),
                {"quote": payload["quote_id"]},
            )
            == 1
        )


async def test_two_competing_quotes_cannot_oversell_stock(scenario):
    client, factory, payload, headers, _ = scenario
    second = {**payload, "quote_id": str(uuid4()), "phone": f"9{uuid4().int % 10**8:08d}"}
    for incoming in [payload, second]:
        result = await register(client, incoming, headers["SUPERADMIN"])
        assert result.status_code == 201, result.text
    results = await asyncio.gather(
        *(confirm(client, incoming, headers["ENCARGADO"]) for incoming in [payload, second])
    )
    assert all(result.status_code == 200 for result in results), [result.text for result in results]
    assert sorted(result.json()["payment_status"] for result in results) == [
        "REQUIRES_MANUAL_APPROVAL",
        "VERIFIED",
    ]
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM events WHERE quote_id IN (:first,:second)"),
                {"first": payload["quote_id"], "second": second["quote_id"]},
            )
            == 1
        )


async def test_storage_rolls_back_when_stage_fails(scenario, monkeypatch):
    client, factory, payload, headers, _ = scenario
    async with factory() as session:
        before = await session.scalar(text("SELECT count(*) FROM booking_documents"))

    async def fail_stage(*args, **kwargs):
        raise RuntimeError("Fallo de persistencia simulado")

    monkeypatch.setattr(SqlAlchemyManualBookingStore, "stage", fail_stage)
    result = await register(client, payload, headers["SUPERADMIN"])
    assert result.status_code == 500, result.text
    async with factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM booking_documents")) == before
        assert (
            await session.scalar(
                text("SELECT count(*) FROM quotes WHERE id=:id"), {"id": payload["quote_id"]}
            )
            == 0
        )


async def test_commit_failure_is_not_reported_as_success(scenario, monkeypatch):
    client, factory, payload, headers, _ = scenario

    async def fail_commit(self):
        raise RuntimeError("Fallo de commit simulado")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    result = await register(client, payload, headers["SUPERADMIN"])
    assert result.status_code == 500, result.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM quotes WHERE id=:id"), {"id": payload["quote_id"]}
            )
            == 0
        )


@pytest.mark.parametrize("role,status", [(None, 401), ("OPERADOR", 403)])
async def test_rbac_denies_manual_flow(scenario, role, status):
    client, _, payload, headers, _ = scenario
    result = await register(client, payload, {} if role is None else headers[role])
    assert result.status_code == status


async def test_self_verification_needs_superadmin_reason(scenario):
    client, _, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    assert (await confirm(client, payload, headers["SUPERADMIN"])).status_code == 422
    result = await confirm(
        client,
        payload,
        headers["SUPERADMIN"],
        override_reason="Excepción supervisada para demostración",
    )
    assert result.status_code == 200, result.text


async def test_expired_quote_cannot_create_reservation(scenario):
    client, factory, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    async with factory() as session:
        await session.execute(
            text("UPDATE quotes SET expires_at=now()-interval '1 minute' WHERE id=:id"),
            {"id": payload["quote_id"]},
        )
        await session.commit()
    assert (await confirm(client, payload, headers["ENCARGADO"])).status_code == 422


@pytest.mark.parametrize(
    "receipt", [b"invalid", PNG + b"0" * (5 * 1024 * 1024)], ids=["invalid", "oversized"]
)
async def test_invalid_receipt_never_creates_quote(scenario, receipt):
    client, factory, payload, headers, _ = scenario
    result = await register(client, payload, headers["SUPERADMIN"], receipt=receipt)
    assert result.status_code == 422, result.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM quotes WHERE id=:id"), {"id": payload["quote_id"]}
            )
            == 0
        )


async def test_duplicate_payload_with_different_reference_is_rejected(scenario):
    client, _, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    duplicate = {**payload, "quote_id": str(uuid4())}
    result = await register(client, duplicate, headers["SUPERADMIN"])
    assert result.status_code == 409, result.text


async def test_budget_reference_can_retrieve_the_persisted_document(scenario):
    client, factory, payload, headers, _ = scenario
    request = {
        key: value
        for key, value in payload.items()
        if key not in {"quote_id", "phone", "district", "payment_method", "paid_amount"}
    }
    prepared = await client.post(
        "/api/v1/budgets/prepare", json=request, headers=headers["SUPERADMIN"]
    )
    assert prepared.status_code == 200, prepared.text
    result = await client.get(
        f"/api/v1/budgets/{prepared.json()['budget_id']}/document", headers=headers["ENCARGADO"]
    )
    assert (
        result.status_code == 200 and result.json()["pdf_base64"] == prepared.json()["pdf_base64"]
    )
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM quotes WHERE id=:id"), {"id": payload["quote_id"]}
            )
            == 0
        )


async def test_overbooked_advance_can_be_rejected_and_refunded(scenario):
    client, _, payload, headers, _ = scenario
    fake = SimpleNamespace(
        check_availability=AsyncMock(
            return_value=AvailabilityResult(AvailabilityStatus.REQUIRES_MANUAL_APPROVAL)
        )
    )
    client._transport.app.dependency_overrides[containers.get_availability_port] = lambda: fake
    result = await register(client, payload, headers["SUPERADMIN"])
    assert (
        result.status_code == 201 and result.json()["payment_status"] == "REQUIRES_MANUAL_APPROVAL"
    ), result.text
    path = f"{PREFIX}/{payload['quote_id']}/refund"
    rejected = await client.post(
        path,
        json={"action": "REQUEST", "reason": "Cliente rechaza cambio de fecha"},
        headers=headers["ENCARGADO"],
    )
    assert rejected.status_code == 200 and rejected.json()["payment_status"] == "REFUND_PENDING", (
        rejected.text
    )
    refunded = await client.post(
        path,
        json={"action": "CONFIRM", "reason": "Transferencia devuelta referencia DEV-001"},
        headers=headers["ENCARGADO"],
    )
    assert refunded.status_code == 200 and refunded.json()["payment_status"] == "REFUNDED", (
        refunded.text
    )
    assert refunded.json()["event_id"] is None
    payment = await client.get(
        f"/api/v1/payments/{result.json()['payment_id']}", headers=headers["ENCARGADO"]
    )
    assert payment.status_code == 200 and payment.json()["validation_status"] == "REFUNDED", (
        payment.text
    )


async def test_overbooked_advance_requires_explicit_approval_and_reason(scenario):
    client, _, payload, headers, _ = scenario
    fake = SimpleNamespace(
        check_availability=AsyncMock(
            return_value=AvailabilityResult(AvailabilityStatus.REQUIRES_MANUAL_APPROVAL)
        )
    )
    client._transport.app.dependency_overrides[containers.get_availability_port] = lambda: fake
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    no_reason = await confirm(client, payload, headers["SUPERADMIN"], approve_overbooking=True)
    assert no_reason.status_code == 422
    approved = await confirm(
        client,
        payload,
        headers["ENCARGADO"],
        approve_overbooking=True,
        override_reason="Se coordinó un elenco adicional para el evento",
    )
    assert approved.status_code == 200 and approved.json()["payment_status"] == "VERIFIED", (
        approved.text
    )


async def test_manual_mobility_is_persisted_and_audited(scenario):
    client, factory, payload, headers, _ = scenario
    incoming = {
        **payload,
        "client_provides_transport": False,
        "manual_mobility_amount": "50.00",
        "mobility_override_reason": "Tarifa acordada por el encargado",
    }
    result = await register(client, incoming, headers["SUPERADMIN"])
    assert result.status_code == 201, result.text
    assert result.json()["total_amount"] == "150.00" and result.json()["advance_amount"] == "10.00"
    reserved = await confirm(client, incoming, headers["ENCARGADO"])
    assert reserved.status_code == 200, reserved.text
    async with factory() as session:
        row = (
            await session.execute(
                text("SELECT total_services_amount,total_mobility_amount FROM events WHERE id=:id"),
                {"id": reserved.json()["event_id"]},
            )
        ).one()
        assert row.total_services_amount == 100 and row.total_mobility_amount == 50
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id=:id "
                    "AND action='OVERRIDE_MOBILITY'"
                ),
                {"id": incoming["quote_id"]},
            )
            == 1
        )
