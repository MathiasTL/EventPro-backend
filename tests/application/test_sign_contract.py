import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.contract.sign_contract import SignatureError, SignContract
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.domain.entities.contract import ContractStatus
from tests.contract_support import setup_contracts


async def signing():
    manager, repo, documents, outbox, _ = setup_contracts()
    issued = await manager.issue_for_event(repo.data.event_id)
    token = outbox.add.call_args.args[0].payload["body"].rsplit("/", 1)[-1]
    clock = type("Clock", (), {"utcnow": lambda self: self.now})()
    clock.now = datetime.now(UTC)
    issued.signature_token_expires_at = clock.now + timedelta(hours=1)
    await repo.save(issued)
    seal = AsyncMock()
    seal.seal.return_value = (b"%PDF sealed", False)
    service = SignContract(
        repo, documents, documents, seal, EnqueueMessage(outbox, clock), clock, secret="secret" * 8
    )
    return service, manager, repo, documents, outbox, seal, clock, token, issued


def otp_code(outbox):
    return re.search(r"\b[0-9]{6}\b", outbox.add.call_args.args[0].payload["body"])[0]


async def test_sign_consumes_link_schedules_and_queues_private_document():
    service, _, repo, files, outbox, seal, _, token, issued = await signing()
    await service.request_otp(token)
    proof = await service.verify_otp(token, otp_code(outbox))
    result = await service.sign(
        token, proof["otp_proof"], b"png", "Cliente", ip="127.0.0.1", user_agent="Browser"
    )
    assert result.status is ContractStatus.SIGNED
    assert result.signature_token_hash is None and result.otp_hash is None
    assert repo.data.event_status == "SCHEDULED"
    assert await files.open(result.sealed_pdf_storage_path) == b"%PDF sealed"
    assert repo.audits[-1].action == "CONTRACT_SIGNED"
    assert repo.audits[-1].new_values["otp_verified"] is True
    assert outbox.add.call_args.args[0].payload["path"] == result.sealed_pdf_storage_path
    seal.seal.assert_awaited_once()
    with pytest.raises(SignatureError, match="Enlace no disponible"):
        await service.resolve(token)


async def test_five_failed_attempts_block_proof_and_persist_counter():
    service, _, repo, _, outbox, _, _, token, issued = await signing()
    await service.request_otp(token)
    correct = otp_code(outbox)
    wrong = "000000" if correct != "000000" else "111111"
    for attempt in range(1, 6):
        result = await service.verify_otp(token, wrong)
        assert isinstance(result, SignatureError)
        assert result.status == (422 if attempt < 5 else 429)
        assert (await repo.get(issued.id)).otp_attempts == attempt
    assert (await service.verify_otp(token, correct)).status == 429
    assert (await repo.get(issued.id)).otp_hash is None


async def test_resend_cooldown_window_and_old_proof_revocation():
    service, _, _, _, outbox, _, clock, token, _ = await signing()
    await service.request_otp(token)
    proof = await service.verify_otp(token, otp_code(outbox))
    with pytest.raises(SignatureError) as exc:
        await service.request_otp(token)
    assert exc.value.status == 429
    clock.now += timedelta(seconds=61)
    await service.request_otp(token)
    with pytest.raises(SignatureError) as exc:
        await service.sign(
            token, proof["otp_proof"], b"png", "Cliente", ip="127.0.0.1", user_agent=""
        )
    assert exc.value.status == 401
    clock.now += timedelta(seconds=61)
    await service.request_otp(token)
    clock.now += timedelta(seconds=61)
    with pytest.raises(SignatureError) as exc:
        await service.request_otp(token)
    assert exc.value.status == 429


async def test_expired_otp_and_expired_link_and_rotation():
    service, manager, repo, _, outbox, _, clock, token, issued = await signing()
    await service.request_otp(token)
    code = otp_code(outbox)
    clock.now += timedelta(minutes=11)
    assert (await service.verify_otp(token, code)).status == 410
    contract = await repo.get(issued.id)
    contract.signature_token_expires_at = clock.now - timedelta(seconds=1)
    await repo.save(contract)
    with pytest.raises(SignatureError) as exc:
        await service.resolve(token)
    assert exc.value.status == 410
    await manager.resend(issued.id, issued.event_id)
    with pytest.raises(SignatureError) as exc:
        await service.resolve(token)
    assert exc.value.status == 404


async def test_invalid_proof_never_calls_seal():
    service, _, _, _, _, seal, _, token, _ = await signing()
    with pytest.raises(SignatureError) as exc:
        await service.sign(token, "invalid", b"png", "Cliente", ip="127.0.0.1", user_agent="")
    assert exc.value.status == 401
    seal.seal.assert_not_awaited()


async def test_verified_otp_expiring_before_signing_rejects_valid_proof():
    service, _, repo, _, outbox, seal, clock, token, issued = await signing()
    await service.request_otp(token)
    proof = await service.verify_otp(token, otp_code(outbox))
    before = outbox.add.await_count
    clock.now += timedelta(minutes=10)
    with pytest.raises(SignatureError) as error:
        await service.sign(
            token, proof["otp_proof"], b"png", "Cliente", ip="127.0.0.1", user_agent=""
        )
    assert error.value.status == 410 and error.value.code == "otp-expired"
    seal.seal.assert_not_awaited()
    assert outbox.add.await_count == before
    assert (await repo.get(issued.id)).status is ContractStatus.ISSUED
    assert (await repo.get(issued.id)).signature_token_hash is not None
    assert repo.data.event_status == "AWAITING_SIGNATURE"
