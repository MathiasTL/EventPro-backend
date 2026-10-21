import logging

import pytest
from pydantic import ValidationError

from app.core.logging import SignatureTokenFilter
from app.infrastructure.adapters.primary.web.v1.contract_signing_router import SignRequest


def test_access_log_redacts_token_and_keeps_uvicorn_arguments():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "POST", "/api/v1/contracts/sign/secret-token/otp", "1.1", 200),
        None,
    )
    SignatureTokenFilter().filter(record)
    assert len(record.args) == 5
    assert "secret-token" not in record.getMessage()
    assert "/contracts/sign/[redacted]/otp" in record.getMessage()


@pytest.mark.parametrize("acceptance", [False, 1, "true", None])
def test_signature_requires_explicit_boolean_acceptance(acceptance):
    with pytest.raises(ValidationError):
        SignRequest(
            otp_proof="x" * 20,
            signature_base64="anything",
            signer_full_name="Cliente",
            accept_terms=acceptance,
        )
