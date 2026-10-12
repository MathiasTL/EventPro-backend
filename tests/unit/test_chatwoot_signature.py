"""Verificación de la firma del webhook de Chatwoot: pura, sobre bytes y con reloj fijo."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from app.infrastructure.adapters.primary.webhooks.chatwoot_signature import (
    SignatureCheck,
    verify_chatwoot_signature,
)

SECRET = "secreto-de-prueba"
NOW = datetime(2026, 10, 12, 14, 1, 0, tzinfo=UTC)
BODY = json.dumps({"event": "message_updated", "id": 4821}, separators=(",", ":")).encode()


def sign(body: bytes, *, secret: str = SECRET, timestamp: str) -> str:
    message = timestamp.encode() + b"." + body
    return "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def stamp(offset_seconds: int = 0) -> str:
    return str(int((NOW + timedelta(seconds=offset_seconds)).timestamp()))


def check(
    *,
    body: bytes = BODY,
    secret: str = SECRET,
    timestamp: str | None = None,
    signature: str | None = None,
    signing_secret: str = SECRET,
    now: datetime = NOW,
) -> SignatureCheck:
    """Firma con ``signing_secret`` y verifica con ``secret``, salvo que se pase otra firma."""

    if timestamp is None:
        timestamp = stamp()
    if signature is None:
        signature = sign(body, secret=signing_secret, timestamp=timestamp)
    return verify_chatwoot_signature(secret, timestamp, body, signature, now)


def test_a_correctly_signed_current_request_is_valid() -> None:
    assert check() is SignatureCheck.VALID


def test_a_different_body_with_its_own_signature_is_also_valid() -> None:
    other = b'{"event":"message_created"}'

    assert check(body=other) is SignatureCheck.VALID


def test_one_altered_byte_breaks_the_signature() -> None:
    timestamp = stamp()
    signature = sign(BODY, timestamp=timestamp)
    altered = BODY.replace(b"4821", b"4822")

    assert (
        verify_chatwoot_signature(SECRET, timestamp, altered, signature, NOW)
        is SignatureCheck.MISMATCH
    )


def test_a_pretty_printed_body_does_not_match_the_compact_signature() -> None:
    timestamp = stamp()
    signature = sign(BODY, timestamp=timestamp)
    pretty = json.dumps(json.loads(BODY), indent=2).encode()

    assert pretty != BODY
    assert (
        verify_chatwoot_signature(SECRET, timestamp, pretty, signature, NOW)
        is SignatureCheck.MISMATCH
    )


def test_a_signature_made_with_another_secret_is_a_mismatch() -> None:
    assert check(signing_secret="otro-secreto") is SignatureCheck.MISMATCH


def test_the_timestamp_is_part_of_the_signed_message() -> None:
    signature = sign(BODY, timestamp=stamp(-10))

    assert check(timestamp=stamp(), signature=signature) is SignatureCheck.MISMATCH


@pytest.mark.parametrize(
    ("timestamp", "signature"),
    [
        (None, "sha256=" + "0" * 64),
        ("1791813660", None),
        ("", "sha256=" + "0" * 64),
        ("1791813660", ""),
    ],
    ids=["no-timestamp", "no-signature", "empty-timestamp", "empty-signature"],
)
def test_a_missing_header_is_reported_before_anything_else(
    timestamp: str | None, signature: str | None
) -> None:
    result = verify_chatwoot_signature(SECRET, timestamp, BODY, signature, NOW)

    assert result is SignatureCheck.MISSING_HEADER


@pytest.mark.parametrize("timestamp", ["abc", "17918x3660", "-1791813660", "1791813660.5", " 17 "])
def test_a_timestamp_that_is_not_only_digits_is_rejected(timestamp: str) -> None:
    signature = sign(BODY, timestamp=timestamp)

    assert check(timestamp=timestamp, signature=signature) is SignatureCheck.BAD_TIMESTAMP


def test_a_non_ascii_digit_timestamp_is_rejected() -> None:
    timestamp = "١٧٩١٨١٣٦٦٠"
    signature = sign(BODY, timestamp=timestamp)

    assert check(timestamp=timestamp, signature=signature) is SignatureCheck.BAD_TIMESTAMP


def test_a_signature_without_the_sha256_prefix_is_a_mismatch() -> None:
    timestamp = stamp()
    bare = sign(BODY, timestamp=timestamp).removeprefix("sha256=")

    assert check(timestamp=timestamp, signature=bare) is SignatureCheck.MISMATCH


def test_an_upper_case_hex_signature_is_a_mismatch() -> None:
    timestamp = stamp()
    digest = sign(BODY, timestamp=timestamp).removeprefix("sha256=")

    assert check(timestamp=timestamp, signature="sha256=" + digest.upper()) is (
        SignatureCheck.MISMATCH
    )


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (-299, SignatureCheck.VALID),
        (-300, SignatureCheck.VALID),
        (-301, SignatureCheck.STALE_TIMESTAMP),
        (300, SignatureCheck.VALID),
        (301, SignatureCheck.STALE_TIMESTAMP),
    ],
)
def test_the_timestamp_window_is_symmetric_and_300_seconds_is_accepted(
    offset: int, expected: SignatureCheck
) -> None:
    assert check(timestamp=stamp(offset)) is expected


def test_a_stale_timestamp_is_reported_even_with_a_wrong_signature() -> None:
    result = check(timestamp=stamp(-301), signing_secret="otro-secreto")

    assert result is SignatureCheck.STALE_TIMESTAMP


def test_an_empty_secret_rejects_even_a_signature_made_with_the_empty_secret() -> None:
    result = check(secret="", signing_secret="")

    assert result is SignatureCheck.SECRET_NOT_CONFIGURED


def test_the_secret_check_comes_before_the_header_check() -> None:
    result = verify_chatwoot_signature("", None, BODY, None, NOW)

    assert result is SignatureCheck.SECRET_NOT_CONFIGURED


def test_a_non_ascii_signature_is_a_mismatch_and_does_not_raise() -> None:
    assert check(signature="sha256=ñ") is SignatureCheck.MISMATCH


def test_signatures_of_equal_length_that_differ_in_the_last_character_are_rejected() -> None:
    timestamp = stamp()
    valid = sign(BODY, timestamp=timestamp)
    flipped = valid[:-1] + ("0" if valid[-1] != "0" else "1")

    assert len(flipped) == len(valid)
    assert check(timestamp=timestamp, signature=flipped) is SignatureCheck.MISMATCH


def test_the_comparison_is_made_with_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return real(left, right)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    timestamp = stamp()
    signature = sign(BODY, timestamp=timestamp)

    assert check(timestamp=timestamp, signature=signature) is SignatureCheck.VALID
    assert calls == [(signature.encode(), signature.encode())]
