from datetime import timedelta
from uuid import uuid4

import pytest

from app.domain.entities.contract import Contract, ContractStatus, InvalidContractStateError
from app.domain.exceptions.resource_exceptions import ValidationError
from tests.contract_support import NOW


def draft():
    return Contract(contract_number="CTR-2026-0001", event_id=uuid4())


def test_issue_and_rotate_link_reset_otp():
    contract = draft()
    contract.issue("database/contracts/a")
    contract.otp_hash, contract.otp_attempts = "old", 4
    contract.replace_link("hash", NOW + timedelta(days=7))
    assert contract.status is ContractStatus.ISSUED
    assert contract.otp_hash is None and contract.otp_attempts == 0
    assert contract.signature_token_hash == "hash"


@pytest.mark.parametrize("status", [ContractStatus.SIGNED, ContractStatus.VOIDED])
def test_terminal_states_reject_reissue(status):
    contract = draft()
    contract.status = status
    with pytest.raises(InvalidContractStateError):
        contract.issue("new")
    with pytest.raises(InvalidContractStateError):
        contract.replace_link("hash", NOW)


@pytest.mark.parametrize("status", [ContractStatus.DRAFT, ContractStatus.ISSUED])
def test_void_invalidates_link_and_otp(status):
    contract = draft()
    contract.status = status
    contract.signature_token_hash, contract.otp_hash = "link", "otp"
    contract.void(event_status="AWAITING_SIGNATURE", reason="Cambio solicitado")
    assert contract.status is ContractStatus.VOIDED
    assert contract.signature_token_hash is contract.otp_hash is None


def test_signed_contract_can_only_be_voided_for_cancelled_event():
    contract = draft()
    contract.status = ContractStatus.SIGNED
    with pytest.raises(InvalidContractStateError):
        contract.void(event_status="SCHEDULED", reason="Cambio")
    with pytest.raises(InvalidContractStateError):
        contract.void(event_status="CANCELLED", reason="Cambio", event_started=True)
    contract.void(event_status="CANCELLED", reason="Cancelación anterior al evento")
    assert contract.status is ContractStatus.VOIDED


@pytest.mark.parametrize("status", ["IN_PROGRESS", "EXTENDED", "SETTLED"])
def test_cannot_void_during_or_after_event(status):
    with pytest.raises(InvalidContractStateError):
        draft().void(event_status=status, reason="Cambio")


def test_invalid_contract_data_is_rejected():
    with pytest.raises(ValidationError):
        Contract(contract_number="N", event_id=uuid4(), status="INVALID")
    with pytest.raises(ValidationError):
        Contract(contract_number="", event_id=uuid4())
    with pytest.raises(ValidationError):
        Contract(contract_number="N", event_id=uuid4(), status=ContractStatus.ISSUED)
    with pytest.raises(ValidationError):
        Contract(contract_number="N", event_id=uuid4(), otp_attempts=-1)
    with pytest.raises(ValidationError):
        Contract(
            contract_number="N",
            event_id=uuid4(),
            status=ContractStatus.SIGNED,
            pdf_storage_path="path",
        )
    with pytest.raises(ValidationError):
        draft().issue("")
    with pytest.raises(ValidationError):
        draft().void(event_status="AWAITING_SIGNATURE", reason="   ")


def test_link_requires_aware_expiry_and_void_is_terminal():
    contract = draft()
    contract.issue("pdf")
    with pytest.raises(ValidationError):
        contract.replace_link("hash", NOW.replace(tzinfo=None))
    contract.void(event_status="AWAITING_SIGNATURE", reason="Cambio")
    with pytest.raises(InvalidContractStateError):
        contract.void(event_status="AWAITING_SIGNATURE", reason="Cambio")
