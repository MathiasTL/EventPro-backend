import hashlib
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfReader

from app.application.dtos.contract_dto import ContractFilters
from app.domain.entities.contract import Contract, ContractStatus, InvalidContractStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from tests.contract_support import NOW, contract_data, setup_contracts


async def test_issue_is_idempotent_and_secrets_are_hashed():
    service, repo, documents, outbox, _ = setup_contracts()
    first = await service.issue_for_event(repo.data.event_id)
    second = await service.issue_for_event(repo.data.event_id)
    assert first.id == second.id
    assert len(documents.files) == len(repo.contracts) == 1
    outbox.add.assert_awaited_once()
    message = outbox.add.call_args.args[0]
    token = message.payload["body"].rsplit("/", 1)[1]
    assert hashlib.sha256(token.encode()).hexdigest() == first.signature_token_hash
    assert token not in str(repo.audits)
    assert message.redact_after_send
    assert first.signature_token_expires_at == NOW + timedelta(hours=168)


@pytest.mark.parametrize(
    "changes",
    [
        {"advance": 0},
        {"advance": 99},
        {"advance": 1081},
        {"total": 999},
        {"event_status": "CANCELLED"},
        {"event_status": "IN_PROGRESS"},
    ],
)
async def test_unverified_or_invalid_event_does_not_issue(changes):
    service, repo, documents, outbox, _ = setup_contracts(contract_data(**changes))
    with pytest.raises(InvalidContractStateError):
        await service.issue_for_event(repo.data.event_id)
    assert not documents.files and not repo.contracts
    outbox.add.assert_not_awaited()


async def test_resend_rotates_link_and_clears_otp():
    service, repo, _, outbox, _ = setup_contracts()
    contract = await service.issue_for_event(repo.data.event_id)
    old_hash = contract.signature_token_hash
    contract.otp_hash, contract.otp_attempts = "old", 4
    await repo.save(contract)
    resent = await service.resend(contract.id, uuid4())
    assert resent.signature_token_hash != old_hash
    assert resent.otp_hash is None and resent.otp_attempts == 0
    assert outbox.add.await_count == 2
    assert repo.audits[-1].action == "CONTRACT_LINK_RESENT"


async def test_observations_regenerate_pdf_and_rotate_link_with_audit():
    service, repo, documents, outbox, pdf = setup_contracts()
    contract = await service.issue_for_event(repo.data.event_id)
    updated = await service.update_observations(contract.id, "Nueva nota literal", uuid4())
    assert updated.pdf_storage_path != contract.pdf_storage_path
    assert updated.signature_token_hash != contract.signature_token_hash
    assert repo.data.observations == "Nueva nota literal"
    assert pdf.render.call_args.args[1].observations == "Nueva nota literal"
    assert repo.audits[-1].old_values["client_observations"] == contract_data().observations
    assert repo.audits[-1].new_values["client_observations"] == "Nueva nota literal"
    assert len(documents.files) == outbox.add.await_count == 2
    await service.update_observations(contract.id, "Nueva nota literal", uuid4())
    assert len(documents.files) == 2  # Cambio idéntico no envía ni regenera.


async def test_draft_observations_remain_draft_without_sending_link():
    service, repo, _, outbox, _ = setup_contracts()
    contract = Contract(contract_number="CTR-2026-0010", event_id=repo.data.event_id)
    await repo.save(contract)
    updated = await service.update_observations(contract.id, "Borrador", uuid4())
    assert updated.status is ContractStatus.DRAFT
    outbox.add.assert_not_awaited()
    with pytest.raises(ResourceNotFoundError):
        await service.pdf(contract.id)


async def test_void_allows_new_contract_but_keeps_previous_document():
    service, repo, _, _, _ = setup_contracts()
    first = await service.issue_for_event(repo.data.event_id)
    voided = await service.void(first.id, "Cambio de cláusulas", uuid4())
    assert voided.signature_token_hash is None
    assert await service.pdf(first.id) == b"%PDF-1.4 prueba"
    second = await service.issue_for_event(repo.data.event_id)
    assert first.id != second.id and first.contract_number != second.contract_number
    page = await service.list(ContractFilters(status=ContractStatus.VOIDED))
    assert page.total == 1


async def test_signed_is_immutable_and_serves_sealed_document():
    service, repo, documents, _, _ = setup_contracts()
    contract = await service.issue_for_event(repo.data.event_id)
    path = await documents.store(
        data=b"sealed", content_type="application/pdf", original_filename="s"
    )
    contract.status = ContractStatus.SIGNED
    contract.signed_at = NOW
    contract.sealed_pdf_storage_path, contract.sealed_pdf_sha256 = path, "a" * 64
    await repo.save(contract)
    assert await service.pdf(contract.id) == b"sealed"
    with pytest.raises(InvalidContractStateError):
        await service.update_observations(contract.id, "No permitido", uuid4())
    with pytest.raises(InvalidContractStateError):
        await service.resend(contract.id, uuid4())


async def test_rejects_unknown_contract_invalid_pagination_and_payment_event():
    service, repo, _, _, _ = setup_contracts()
    with pytest.raises(ResourceNotFoundError):
        await service.get(uuid4())
    with pytest.raises(ValidationError):
        await service.list(ContractFilters(page=0))
    with pytest.raises(ValidationError):
        await service.prepare_payment_event(repo.data.event_id, uuid4())
    await service.prepare_payment_event(repo.data.event_id, repo.data.quote_id)
    repo.data = replace(repo.data, event_status="CANCELLED")
    with pytest.raises(InvalidContractStateError):
        await service.prepare_payment_event(repo.data.event_id, repo.data.quote_id)


async def test_real_pdf_has_amounts_extras_and_literal_observations():
    service, repo, _, _, _ = setup_contracts(real_pdf=True)
    contract = await service.issue_for_event(repo.data.event_id)
    content = await service.pdf(contract.id)
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)
    for expected in [
        "CTR-2026-0001",
        "José Pérez",
        "1080.00",
        "980.00",
        "Burbujas",
        "Sin reggaetón",
        "Sorpresa al minuto 45 <especial>",
    ]:
        assert expected in text


async def test_failed_render_or_queue_does_not_silently_succeed():
    service, repo, _, outbox, pdf = setup_contracts()
    pdf.render.side_effect = RuntimeError("render failed")
    with pytest.raises(RuntimeError):
        await service.issue_for_event(repo.data.event_id)
    assert not repo.contracts
    pdf.render.side_effect = None
    outbox.add.side_effect = RuntimeError("outbox failed")
    with pytest.raises(RuntimeError):
        await service.issue_for_event(repo.data.event_id)
    assert not repo.contracts
