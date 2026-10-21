"""Transacciones de contingencia y firma sobre PostgreSQL/Redis efímeros."""

import asyncio
import base64
import json
import re
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.application.use_cases.contract.sign_contract import SignatureError
from app.infrastructure.adapters.secondary.signature.pades_signature_adapter import (
    PadesSignatureAdapter,
)
from app.infrastructure.adapters.secondary.storage.contract_pdf import ReportLabContractPdf
from tests.unit.test_pades_signature import signature_png

from .test_manual_booking_flow import PNG
from .test_manual_booking_flow import scenario as scenario_fixture

scenario = scenario_fixture
pytestmark = pytest.mark.integration


def manual_payload(legacy, **changes):
    return {
        "client": {"phone": legacy["phone"], "full_name": "Cliente manual", "dni": "12345678"},
        "event_date": legacy["event_date"],
        "event_time": legacy["start_time"],
        "location_address": legacy["address"],
        "location_district": legacy["district"],
        "package_id": legacy["package_id"],
        "client_provides_mobility": True,
        "advance": {"payment_method": "CASH", "amount": "10.00"},
        "client_observations": "Nota literal especial",
        "custom_clauses": "Cláusula especial",
        **changes,
    }


async def create(client, payload, headers, key=None):
    return await client.post(
        "/api/v1/contracts/manual",
        data={"payload": json.dumps(payload)},
        files={"advance_evidence_file": ("receipt.png", PNG, "image/png")},
        headers={**headers, "Idempotency-Key": str(key or uuid4())},
    )


async def signing_link(factory, contract_id):
    async with factory() as session:
        body = await session.scalar(
            text(
                "SELECT payload->>'body' FROM outbox_messages WHERE payload->>'contract_id'=:id "
                "AND status='PENDING' ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": contract_id},
        )
    return body.rsplit("/", 1)[-1]


async def otp(client, factory, token, contract_id):
    requested = await client.post(f"/api/v1/contracts/sign/{token}/otp")
    assert requested.status_code == 200, requested.text
    async with factory() as session:
        body = await session.scalar(
            text(
                "SELECT payload->>'body' FROM outbox_messages WHERE payload->>'contract_id'=:id "
                "AND status='PENDING' ORDER BY created_at DESC LIMIT 1"
            ),
            {"id": contract_id},
        )
    code = re.search(r"\b[0-9]{6}\b", body)[0]
    verified = await client.post(
        f"/api/v1/contracts/sign/{token}/otp/verify", json={"otp_code": code}
    )
    assert verified.status_code == 200, verified.text
    return verified.json()["otp_proof"]


async def test_manual_draft_replay_and_conflict_are_atomic(scenario):
    client, factory, legacy, headers, _ = scenario
    payload = manual_payload(legacy, issue_contract=False)
    key = uuid4()
    first = await create(client, payload, headers["ENCARGADO"], key)
    assert first.status_code == 201, first.text
    assert first.json()["contract_status"] == "DRAFT"
    replay = await create(client, payload, headers["ENCARGADO"], key)
    assert replay.status_code == 200 and replay.json() == first.json()
    changed = await create(
        client, {**payload, "custom_clauses": "Otro texto"}, headers["ENCARGADO"], key
    )
    assert changed.status_code == 409
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM events WHERE quote_id=:id"), {"id": key}
            )
            == 1
        )
        assert (
            await session.scalar(
                text("SELECT validation_status FROM payments WHERE quote_id=:id"), {"id": key}
            )
            == "VERIFIED"
        )
        assert (
            await session.scalar(
                text("SELECT client_observations FROM events WHERE quote_id=:id"), {"id": key}
            )
            == "Nota literal especial"
        )
    issued = await client.post(
        "/api/v1/contracts",
        json={"event_id": first.json()["event_id"]},
        headers=headers["ENCARGADO"],
    )
    assert issued.status_code == 200 and issued.json()["status"] == "ISSUED"


async def test_manual_keeps_quantities_and_quote_notes_with_real_quote_repository(
    scenario, monkeypatch
):
    client, factory, legacy, headers, _ = scenario
    # Este caso espera éxito: conservar la excepción original facilita diagnosticar
    # errores de persistencia sin convertirlos en un 500 genérico del transporte.
    monkeypatch.setattr(client._transport, "raise_app_exceptions", True)
    extra_id = uuid4()
    async with factory() as session:
        await session.execute(
            text("INSERT INTO extras(id,name,sale_price,direct_cost) VALUES (:id,:name,25,5)"),
            {"id": extra_id, "name": f"Extra-{extra_id}"},
        )
        await session.commit()
    payload = manual_payload(
        legacy,
        extras=[{"extra_id": str(extra_id), "quantity": 3}],
        advance={"payment_method": "CASH", "amount": "17.50"},
    )
    key = uuid4()
    result = await create(client, payload, headers["ENCARGADO"], key)
    assert result.status_code == 201, result.text
    assert Decimal(str(result.json()["total_amount"])) == Decimal("175.00")
    async with factory() as session:
        row = (
            await session.execute(
                text("SELECT quantity,unit_price,subtotal FROM quote_extras WHERE quote_id=:id"),
                {"id": key},
            )
        ).one()
        assert row == (3, Decimal("25.00"), Decimal("75.00"))
        assert (
            await session.scalar(
                text("SELECT observations FROM quotes WHERE id=:id"),
                {"id": key},
            )
            == payload["client_observations"]
        )


async def test_manual_pdf_failure_rolls_back_all_new_rows(scenario, monkeypatch):
    client, factory, legacy, headers, _ = scenario

    async def fail(*args):
        raise RuntimeError("render failure")

    monkeypatch.setattr(ReportLabContractPdf, "render", fail)
    key = uuid4()
    result = await create(client, manual_payload(legacy), headers["ENCARGADO"], key)
    assert result.status_code == 500
    async with factory() as session:
        assert (
            await session.scalar(text("SELECT count(*) FROM quotes WHERE id=:id"), {"id": key}) == 0
        )
        assert (
            await session.scalar(
                text("SELECT count(*) FROM payments WHERE quote_id=:id"), {"id": key}
            )
            == 0
        )


async def test_manual_permissions_and_invalid_advance_do_not_create_quote(scenario):
    client, factory, legacy, headers, _ = scenario
    payload = manual_payload(legacy, advance={"payment_method": "CASH", "amount": "11.00"})
    key = uuid4()
    assert (await create(client, payload, {}, key)).status_code == 401
    assert (await create(client, payload, headers["OPERADOR"], key)).status_code == 403
    result = await create(client, payload, headers["ENCARGADO"], key)
    assert result.status_code == 400, result.text
    async with factory() as session:
        assert (
            await session.scalar(text("SELECT count(*) FROM quotes WHERE id=:id"), {"id": key}) == 0
        )


async def test_wrong_otp_attempts_survive_error_responses(scenario):
    client, factory, legacy, headers, _ = scenario
    created = await create(client, manual_payload(legacy), headers["ENCARGADO"])
    assert created.status_code == 201, created.text
    key = created.json()["contract_id"]
    token = await signing_link(factory, key)
    assert (await client.post(f"/api/v1/contracts/sign/{token}/otp")).status_code == 200
    # Garantizar un código incorrecto sin depender del azar del generador.
    async with factory() as session:
        await session.execute(
            text("UPDATE contracts SET otp_hash=:hash WHERE id=:id"),
            {"id": UUID(key), "hash": "0" * 64},
        )
        await session.commit()
    for attempt in range(5):
        result = await client.post(
            f"/api/v1/contracts/sign/{token}/otp/verify", json={"otp_code": "123456"}
        )
        assert result.status_code == (422 if attempt < 4 else 429), result.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT otp_attempts FROM contracts WHERE id=:id"), {"id": UUID(key)}
            )
            == 5
        )


async def test_signing_failure_rolls_back_and_parallel_retry_signs_once(scenario, monkeypatch):
    client, factory, legacy, headers, _ = scenario
    created = await create(client, manual_payload(legacy), headers["ENCARGADO"])
    assert created.status_code == 201, created.text
    key = created.json()["contract_id"]
    token = await signing_link(factory, key)
    summary = await client.get(f"/api/v1/contracts/sign/{token}")
    assert summary.status_code == 200, summary.text
    assert summary.headers["cache-control"] == "private, no-store"
    assert "otp_hash" not in summary.text
    proof = await otp(client, factory, token, key)
    payload = {
        "otp_proof": proof,
        "signature_base64": base64.b64encode(signature_png()).decode(),
        "signer_full_name": "Cliente manual",
        "accept_terms": True,
    }

    async def fail(*args):
        raise SignatureError(503, "signature-unavailable", "Unavailable")

    monkeypatch.setattr(PadesSignatureAdapter, "seal", fail)
    failed = await client.post(f"/api/v1/contracts/sign/{token}", json=payload)
    assert failed.status_code == 503
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT status FROM contracts WHERE id=:id"), {"id": UUID(key)}
            )
            == "ISSUED"
        )

    async def seal(self, pdf, image, name):
        return pdf, False

    monkeypatch.setattr(PadesSignatureAdapter, "seal", seal)
    responses = await asyncio.gather(
        *[client.post(f"/api/v1/contracts/sign/{token}", json=payload) for _ in range(2)]
    )
    assert sorted(result.status_code for result in responses) == [200, 404]
    async with factory() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id=:id "
                    "AND action='CONTRACT_SIGNED'"
                ),
                {"id": UUID(key)},
            )
            == 1
        )
        assert (
            await session.scalar(
                text("SELECT status FROM events WHERE id=:id"),
                {"id": UUID(created.json()["event_id"])},
            )
            == "SCHEDULED"
        )
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM outbox_messages WHERE message_type='DOCUMENT' "
                    "AND payload->>'filename'=:name"
                ),
                {"name": f"{created.json()['contract_number']}-signed.pdf"},
            )
            == 1
        )
