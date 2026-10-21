"""Contratos con PostgreSQL/Redis efímeros; ninguna llamada externa ni base compartida."""

import asyncio
import base64
from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import text

from app.infrastructure.adapters.secondary.persistence.repositories.sqlalchemy_outbox_repository import (  # noqa: E501
    SqlAlchemyOutboxRepository,
)
from app.infrastructure.adapters.secondary.storage.contract_pdf import ReportLabContractPdf

from .test_manual_booking_flow import confirm, register
from .test_manual_booking_flow import scenario as scenario_fixture

scenario = scenario_fixture
pytestmark = pytest.mark.integration


async def registered_event(scenario, *, verified=False):
    client, factory, payload, headers, _ = scenario
    registered = await register(client, payload, headers["SUPERADMIN"])
    assert registered.status_code == 201, registered.text
    payment_id = registered.json()["payment_id"]
    event_id = uuid4()
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO events(id,event_code,quote_id,event_date,start_time,end_time,address,"
                "district,status,total_services_amount,total_mobility_amount,final_total_amount,"
                "client_observations) VALUES (:id,:code,:quote,:day,'22:00','23:00','Lugar','Lima',"
                "'AWAITING_SIGNATURE',100,0,100,'Nota literal del cliente')"
            ),
            {
                "id": event_id,
                "code": f"EVT-{event_id.hex[:20]}",
                "quote": payload["quote_id"],
                "day": date.fromisoformat(payload["event_date"]),
            },
        )
        await session.execute(
            text("UPDATE payments SET event_id=:event, validation_status=:status WHERE id=:id"),
            {
                "event": event_id if verified else None,
                "id": payment_id,
                "status": "VERIFIED" if verified else "PENDING_VERIFICATION",
            },
        )
        await session.commit()
    return event_id, payment_id


async def test_verified_payment_automatically_issues_and_queues_once(scenario):
    client, factory, _, headers, _ = scenario
    event_id, payment_id = await registered_event(scenario)
    result = await client.patch(
        f"/api/v1/payments/{payment_id}/verify",
        json={"status": "VERIFIED", "event_id": str(event_id)},
        headers=headers["ENCARGADO"],
    )
    assert result.status_code == 200, result.text
    contracts = await client.get(
        f"/api/v1/contracts?event_id={event_id}", headers=headers["ENCARGADO"]
    )
    assert contracts.json()["total"] == 1
    contract = contracts.json()["items"][0]
    assert contract["status"] == "ISSUED"
    pdf = await client.get(
        f"/api/v1/contracts/{contract['contract_id']}/pdf", headers=headers["ENCARGADO"]
    )
    content = "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert "Nota literal del cliente" in content
    async with factory() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM audit_logs WHERE entity_id=:id "
                    "AND action='CONTRACT_ISSUED'"
                ),
                {"id": contract["contract_id"]},
            )
            == 1
        )
        row = (
            await session.execute(
                text(
                    "SELECT signature_token_hash, signature_token_expires_at "
                    "FROM contracts WHERE id=:id"
                ),
                {"id": contract["contract_id"]},
            )
        ).one()
        assert len(row[0]) == 64 and row[1] is not None
        assert (
            await session.scalar(
                text("SELECT count(*) FROM outbox_messages WHERE payload->>'body' LIKE :pattern"),
                {"pattern": f"%{contract['contract_number']}%"},
            )
            == 1
        )


async def test_concurrent_issue_is_one_contract_and_one_message(scenario):
    client, factory, _, headers, _ = scenario
    event_id, _ = await registered_event(scenario, verified=True)

    async def issue():
        return await client.post(
            "/api/v1/contracts", json={"event_id": str(event_id)}, headers=headers["ENCARGADO"]
        )

    results = await asyncio.gather(issue(), issue())
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json()["contract_id"] == results[1].json()["contract_id"]
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM contracts WHERE event_id=:id"), {"id": event_id}
            )
            == 1
        )


async def test_pdf_failure_rolls_back_payment_and_documents(scenario, monkeypatch):
    client, factory, _, headers, _ = scenario
    event_id, payment_id = await registered_event(scenario)

    async def fail(*args):
        raise RuntimeError("PDF unavailable")

    monkeypatch.setattr(ReportLabContractPdf, "render", fail)
    result = await client.patch(
        f"/api/v1/payments/{payment_id}/verify",
        json={"status": "VERIFIED", "event_id": str(event_id)},
        headers=headers["ENCARGADO"],
    )
    assert result.status_code == 500, result.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT validation_status FROM payments WHERE id=:id"), {"id": payment_id}
            )
            == "PENDING_VERIFICATION"
        )
        assert (
            await session.scalar(
                text("SELECT count(*) FROM contracts WHERE event_id=:id"), {"id": event_id}
            )
            == 0
        )


async def test_manual_confirmation_uses_same_contract_lifecycle(scenario):
    client, factory, payload, headers, _ = scenario
    notes = "  Entrada por puerta lateral\nConservar esta nota  "
    extra_id = uuid4()
    async with factory() as session:
        await session.execute(
            text("INSERT INTO extras(id,name,sale_price,direct_cost) VALUES (:id,'Globos',20,5)"),
            {"id": extra_id},
        )
        await session.commit()
    payload = {
        **payload,
        "observations": notes,
        "extra_ids": [str(extra_id)],
        "paid_amount": "12.00",
        "client_provides_transport": False,
        "manual_mobility_amount": "50.00",
        "mobility_override_reason": "Tarifa acordada por el encargado",
    }
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 200
    changed = {**payload, "observations": notes.strip()}
    assert (await register(client, changed, headers["SUPERADMIN"])).status_code == 409
    async with factory() as session:
        await session.execute(
            text(
                "UPDATE clients SET dni='12345678',ruc='20123456789' "
                "WHERE id=(SELECT client_id FROM quotes WHERE id=:id)"
            ),
            {"id": payload["quote_id"]},
        )
        await session.commit()
    result = await confirm(client, payload, headers["ENCARGADO"])
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["contract_number"].startswith("CTR-")
    fetched = await client.get(
        f"/api/v1/contracts/{data['contract_id']}", headers=headers["ENCARGADO"]
    )
    assert fetched.status_code == 200 and fetched.json()["is_manual_mode"]
    downloaded = await client.get(
        f"/api/v1/contracts/{data['contract_id']}/pdf", headers=headers["ENCARGADO"]
    )
    assert downloaded.status_code == 200, downloaded.text
    content = "\n".join(p.extract_text() for p in PdfReader(BytesIO(downloaded.content)).pages)
    assert "12345678" in content and "20123456789" in content
    assert "OBSERVACIONES ESPECIALES DEL CLIENTE" in content
    assert "Entrada por puerta lateral" in content and "Conservar esta nota" in content
    assert "Globos x 1: S/ 20.00" in content
    assert "158.00" in content  # Total 170 menos adelanto 12, incluida movilidad.
    legacy_pdf = await client.get(
        f"/api/v1/manual-bookings/{payload['quote_id']}/contract", headers=headers["ENCARGADO"]
    )
    assert legacy_pdf.status_code == 200, legacy_pdf.text
    assert base64.b64decode(legacy_pdf.json()["pdf_base64"]) == downloaded.content
    replay = await confirm(client, payload, headers["ENCARGADO"])
    assert replay.status_code == 200 and replay.json() == data
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT client_observations FROM events WHERE id=:id"),
                {"id": data["event_id"]},
            )
            == notes
        )
        assert (
            await session.scalar(
                text("SELECT signature_token_hash FROM contracts WHERE id=:id"),
                {"id": data["contract_id"]},
            )
            is not None
        )
        assert (
            await session.scalar(
                text("SELECT count(*) FROM outbox_messages WHERE payload->>'contract_id'=:id"),
                {"id": data["contract_id"]},
            )
            == 1
        )


@pytest.mark.parametrize("failure", ["pdf", "outbox"])
async def test_manual_e2_failure_rolls_back_confirmation(scenario, monkeypatch, failure):
    client, factory, payload, headers, _ = scenario
    assert (await register(client, payload, headers["SUPERADMIN"])).status_code == 201
    async with factory() as session:
        before = await session.scalar(text("SELECT count(*) FROM booking_documents"))

    async def fail(*args):
        raise RuntimeError("Fallo simulado de integración E2")

    target = ReportLabContractPdf if failure == "pdf" else SqlAlchemyOutboxRepository
    with monkeypatch.context() as patch:
        patch.setattr(target, "render" if failure == "pdf" else "add", fail)
        result = await confirm(client, payload, headers["ENCARGADO"])
    assert result.status_code == 500, result.text
    async with factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM booking_documents")) == before
        assert (
            await session.scalar(
                text("SELECT status FROM quotes WHERE id=:id"), {"id": payload["quote_id"]}
            )
            == "PAYMENT_STARTED"
        )
        assert (
            await session.scalar(
                text("SELECT validation_status FROM payments WHERE quote_id=:id"),
                {"id": payload["quote_id"]},
            )
            == "PENDING_VERIFICATION"
        )
        assert (
            await session.scalar(
                text("SELECT count(*) FROM events WHERE quote_id=:id"),
                {"id": payload["quote_id"]},
            )
            == 0
        )
    # El mismo registro se puede confirmar al recuperarse E2.
    recovered = await confirm(client, payload, headers["ENCARGADO"])
    assert recovered.status_code == 200, recovered.text


async def test_regeneration_updates_schedule_and_void_allows_reissue(scenario):
    client, factory, _, headers, _ = scenario
    event_id, _ = await registered_event(scenario, verified=True)
    issued = await client.post(
        "/api/v1/contracts", json={"event_id": str(event_id)}, headers=headers["ENCARGADO"]
    )
    key = issued.json()["contract_id"]
    changed = await client.patch(
        f"/api/v1/contracts/{key}/observations",
        json={"client_observations": "Nuevo texto <literal>"},
        headers=headers["ENCARGADO"],
    )
    assert changed.status_code == 200, changed.text
    async with factory() as session:
        assert (
            await session.scalar(
                text("SELECT client_observations FROM events WHERE id=:id"), {"id": event_id}
            )
            == "Nuevo texto <literal>"
        )
    assert (
        await client.post(
            f"/api/v1/contracts/{key}/void",
            json={"reason": "Cambios"},
            headers=headers["ENCARGADO"],
        )
    ).status_code == 200
    second = await client.post(
        "/api/v1/contracts", json={"event_id": str(event_id)}, headers=headers["ENCARGADO"]
    )
    assert second.status_code == 200 and second.json()["contract_id"] != key


async def test_failed_queue_rolls_back_document_and_contract(scenario, monkeypatch):
    client, factory, _, headers, _ = scenario
    event_id, _ = await registered_event(scenario, verified=True)
    async with factory() as session:
        before = await session.scalar(text("SELECT count(*) FROM booking_documents"))

    async def fail(*args):
        raise RuntimeError("Queue unavailable")

    monkeypatch.setattr(SqlAlchemyOutboxRepository, "add", fail)
    result = await client.post(
        "/api/v1/contracts", json={"event_id": str(event_id)}, headers=headers["ENCARGADO"]
    )
    assert result.status_code == 500, result.text
    async with factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM booking_documents")) == before
        assert (
            await session.scalar(
                text("SELECT count(*) FROM contracts WHERE event_id=:id"), {"id": event_id}
            )
            == 0
        )


async def test_resend_and_void_redact_pending_obsolete_links(scenario):
    client, factory, _, headers, _ = scenario
    event_id, _ = await registered_event(scenario, verified=True)
    issued = await client.post(
        "/api/v1/contracts", json={"event_id": str(event_id)}, headers=headers["ENCARGADO"]
    )
    key = issued.json()["contract_id"]
    async with factory() as session:
        message_id = await session.scalar(
            text("SELECT id FROM outbox_messages WHERE payload->>'contract_id'=:id"), {"id": key}
        )
    assert (
        await client.post(f"/api/v1/contracts/{key}/resend-link", headers=headers["ENCARGADO"])
    ).status_code == 200
    async with factory() as session:
        row = (
            await session.execute(
                text("SELECT status,payload FROM outbox_messages WHERE id=:id"), {"id": message_id}
            )
        ).one()
        assert row == ("FAILED", None)
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM outbox_messages "
                    "WHERE status='PENDING' AND payload->>'contract_id'=:id"
                ),
                {"id": key},
            )
            == 1
        )
    assert (
        await client.post(
            f"/api/v1/contracts/{key}/void", json={"reason": "Cambio"}, headers=headers["ENCARGADO"]
        )
    ).status_code == 200
    async with factory() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM outbox_messages "
                    "WHERE status='PENDING' AND payload->>'contract_id'=:id"
                ),
                {"id": key},
            )
            == 0
        )
