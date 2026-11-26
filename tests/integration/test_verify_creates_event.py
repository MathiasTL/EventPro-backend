"""Verificar un adelanto sin event_id crea el evento de la cotización conversacional."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.application.dtos.availability_dto import AvailabilityResult, AvailabilityStatus
from app.infrastructure.di import containers

from .test_contract_management import registered_event
from .test_contract_management import scenario as contract_scenario
from .test_manual_booking_flow import register

scenario = contract_scenario
pytestmark = pytest.mark.integration


async def conversational_payment(scenario, observations="Sin reggaetón"):
    client, factory, payload, headers, _ = scenario
    payload = {**payload, "observations": observations}
    registered = await register(client, payload, headers["SUPERADMIN"])
    assert registered.status_code == 201, registered.text
    async with factory() as session:
        await session.execute(
            text("UPDATE quotes SET source='WHATSAPP' WHERE id=:id"), {"id": payload["quote_id"]}
        )
        await session.commit()
    return payload, registered.json()["payment_id"]


async def verify(scenario, payment_id, **body):
    client, _, _, headers, _ = scenario
    return await client.patch(
        f"/api/v1/payments/{payment_id}/verify",
        json={"status": "VERIFIED", **body},
        headers=headers["ENCARGADO"],
    )


async def scalar(scenario, sql, **params):
    async with scenario[1]() as session:
        return await session.scalar(text(sql), params)


async def test_verify_without_event_creates_event_converts_quote_and_issues_contract(scenario):
    payload, payment_id = await conversational_payment(scenario)
    result = await verify(scenario, payment_id)
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["validation_status"] == "VERIFIED" and body["event_id"]
    async with scenario[1]() as session:
        event = (
            await session.execute(
                text(
                    "SELECT status, client_observations, district, final_total_amount, "
                    "advance_paid FROM events WHERE id=:id"
                ),
                {"id": body["event_id"]},
            )
        ).one()
    assert event.status == "AWAITING_SIGNATURE"
    assert event.client_observations == "Sin reggaetón"
    assert event.district == "Lima" and event.advance_paid > 0
    quote = payload["quote_id"]
    assert await scalar(scenario, "SELECT status FROM quotes WHERE id=:q", q=quote) == "CONVERTED"
    assert (
        await scalar(scenario, "SELECT event_id FROM payments WHERE id=:p", p=payment_id)
    ) is not None
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM inventory_reservations WHERE event_id=:e",
            e=body["event_id"],
        )
        == 1
    )
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM contracts WHERE event_id=:e AND status='ISSUED'",
            e=body["event_id"],
        )
        == 1
    )
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM outbox_messages WHERE payload->>'contract_id' IN "
            "(SELECT c.id::text FROM contracts c WHERE c.event_id=:e)",
            e=body["event_id"],
        )
        == 1
    )


async def test_retrying_verification_does_not_duplicate_event_or_contract(scenario):
    payload, payment_id = await conversational_payment(scenario)
    assert (await verify(scenario, payment_id)).status_code == 200
    retry = await verify(scenario, payment_id)
    assert retry.status_code == 409, retry.text
    quote = payload["quote_id"]
    assert await scalar(scenario, "SELECT count(*) FROM events WHERE quote_id=:q", q=quote) == 1
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM contracts c JOIN events e ON e.id=c.event_id WHERE e.quote_id=:q",
            q=quote,
        )
        == 1
    )


async def test_verify_without_event_id_reuses_existing_awaiting_signature_event(scenario):
    event_id, payment_id = await registered_event(scenario)
    result = await verify(scenario, payment_id)
    assert result.status_code == 200, result.text
    assert result.json()["event_id"] == str(event_id)
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM events "
            "WHERE quote_id=(SELECT quote_id FROM payments WHERE id=:p)",
            p=payment_id,
        )
        == 1
    )
    assert (
        await scalar(
            scenario,
            "SELECT status FROM quotes WHERE id=(SELECT quote_id FROM payments WHERE id=:p)",
            p=payment_id,
        )
        == "CONVERTED"
    )


async def test_provided_event_id_keeps_current_behavior(scenario):
    event_id, payment_id = await registered_event(scenario)
    result = await verify(scenario, payment_id, event_id=str(event_id))
    assert result.status_code == 200, result.text
    assert result.json()["event_id"] == str(event_id)
    assert (
        await scalar(
            scenario,
            "SELECT status FROM quotes WHERE id=(SELECT quote_id FROM payments WHERE id=:p)",
            p=payment_id,
        )
        == "PAYMENT_STARTED"
    )


async def test_availability_conflict_requires_manual_approval_and_creates_nothing(scenario):
    client = scenario[0]
    payload, payment_id = await conversational_payment(scenario)
    fake = SimpleNamespace(
        check_availability=AsyncMock(return_value=AvailabilityResult(AvailabilityStatus.CONFLICT))
    )
    client._transport.app.dependency_overrides[containers.get_availability_port] = lambda: fake
    result = await verify(scenario, payment_id)
    assert result.status_code == 200, result.text
    assert result.json()["validation_status"] == "REQUIRES_MANUAL_APPROVAL"
    assert result.json()["event_id"] is None
    quote = payload["quote_id"]
    assert await scalar(scenario, "SELECT count(*) FROM events WHERE quote_id=:q", q=quote) == 0
    assert (
        await scalar(scenario, "SELECT status FROM quotes WHERE id=:q", q=quote)
        == "PAYMENT_STARTED"
    )
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM contracts c JOIN events e ON e.id=c.event_id WHERE e.quote_id=:q",
            q=quote,
        )
        == 0
    )


async def test_overbooked_bot_advance_approved_without_event_id_creates_event(scenario):
    client, _, _, headers, _ = scenario
    payload, payment_id = await conversational_payment(scenario)
    async with scenario[1]() as session:
        await session.execute(
            text("UPDATE payments SET validation_status='REQUIRES_MANUAL_APPROVAL' WHERE id=:p"),
            {"p": payment_id},
        )
        await session.commit()
    # Aun sin cupo, la aprobación es el sobrecupo autorizado y crea el evento.
    fake = SimpleNamespace(
        check_availability=AsyncMock(return_value=AvailabilityResult(AvailabilityStatus.CONFLICT))
    )
    client._transport.app.dependency_overrides[containers.get_availability_port] = lambda: fake
    path = f"/api/v1/overrides/payments/{payment_id}/approve-simultaneous"
    result = await client.post(
        path, json={"action": "APPROVE", "notes": "Elenco extra"}, headers=headers["ENCARGADO"]
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["validation_status"] == "VERIFIED" and body["event_created_id"]
    quote, event = payload["quote_id"], body["event_created_id"]
    assert await scalar(scenario, "SELECT status FROM quotes WHERE id=:q", q=quote) == "CONVERTED"
    assert (
        await scalar(scenario, "SELECT status FROM events WHERE id=:e", e=event)
        == "AWAITING_SIGNATURE"
    )
    assert (
        await scalar(
            scenario, "SELECT count(*) FROM inventory_reservations WHERE event_id=:e", e=event
        )
        == 1
    )
    assert (
        await scalar(
            scenario,
            "SELECT count(*) FROM contracts WHERE event_id=:e AND status='ISSUED'",
            e=event,
        )
        == 1
    )
    retry = await client.post(
        path, json={"action": "APPROVE", "notes": "Elenco extra"}, headers=headers["ENCARGADO"]
    )
    assert retry.status_code == 409, retry.text
    assert await scalar(scenario, "SELECT count(*) FROM events WHERE quote_id=:q", q=quote) == 1
    assert await scalar(scenario, "SELECT count(*) FROM contracts WHERE event_id=:e", e=event) == 1
