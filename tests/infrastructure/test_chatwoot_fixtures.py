"""Guarda de saneamiento de los fixtures de Chatwoot (solo datos inventados)."""

from typing import Any

import pytest

from tests.chatwoot_fixture_support import (
    FIXTURES_DIR,
    REDACTED,
    fixture_names,
    load_fixture,
    scrub_violations,
)

EXPECTED_FIXTURES = [
    "api_contact_created",
    "api_contact_search",
    "api_conversation_created",
    "api_conversation_list",
    "api_message_created",
    "api_message_list",
    "message_created_incoming",
    "message_created_outgoing",
    "message_updated_delivered",
    "message_updated_failed",
    "message_updated_read",
    "message_updated_sent",
]

_SAFE = {
    "provisional": True,
    "headers": {"X-Chatwoot-Signature": REDACTED},
    "body": {"phone_number": "+51999111222", "url": "https://files.example.org/a.pdf"},
}


def _with_body(**body: Any) -> dict[str, Any]:
    return {**_SAFE, "body": body}


def test_all_expected_fixtures_exist() -> None:
    assert fixture_names() == EXPECTED_FIXTURES


def test_readme_documents_capture_steps_and_scrub_checklist() -> None:
    readme = (FIXTURES_DIR / "README.md").read_text(encoding="utf-8")

    assert "Lista de saneamiento" in readme
    assert "Pasos de captura" in readme


@pytest.mark.parametrize("name", EXPECTED_FIXTURES)
def test_fixture_is_scrubbed_and_has_the_expected_envelope(name: str) -> None:
    document = load_fixture(name)

    assert set(document) == {"provisional", "headers", "body"}
    assert document["provisional"] is True
    assert scrub_violations(document) == []


@pytest.mark.parametrize("name", EXPECTED_FIXTURES[6:])
def test_webhook_fixtures_never_carry_a_real_signature(name: str) -> None:
    headers = {key.lower(): value for key, value in load_fixture(name)["headers"].items()}

    assert headers["x-chatwoot-signature"] == REDACTED
    assert "x-chatwoot-delivery" in headers


def test_guard_accepts_a_document_made_of_fake_data() -> None:
    assert scrub_violations(_SAFE) == []


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        (_with_body(phone="+51987654321"), "$.body.phone: digit-run"),
        (_with_body(contact="ana@gmail.com"), "$.body.contact: email"),
        (
            _with_body(blob="Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWo"),
            "$.body.blob: long-token",
        ),
        (_with_body(api_access_token="abc123"), "$.body.api_access_token: secret-key"),
        (_with_body(file="https://cdn.real-host.net/a.pdf"), "$.body.file: real-host"),
        (
            _with_body(file="https://files.example.org/a.pdf?X-Amz-Signature=abc"),
            "$.body.file: signed-url",
        ),
        (
            {**_SAFE, "headers": {"x-chatwoot-signature": "sha256=" + "a" * 64}},
            "$.headers.x-chatwoot-signature: real-signature",
        ),
        ({"headers": {}, "body": {}}, "$.provisional: missing-key"),
        (_with_body(numbers=["51987654321"]), "$.body.numbers[0]: digit-run"),
    ],
)
def test_guard_flags_real_looking_data(document: dict[str, Any], expected: str) -> None:
    assert expected in scrub_violations(document)


def test_guard_accepts_epoch_timestamps_but_not_other_long_digit_runs() -> None:
    assert scrub_violations(_with_body(sent_at="1791813660")) == []
    assert scrub_violations(_with_body(sent_at="9991112221")) == ["$.body.sent_at: digit-run"]


def test_guard_accepts_long_snake_case_error_codes() -> None:
    document = _with_body(external_error="message_outside_messaging_window")

    assert scrub_violations(document) == []


def test_guard_never_echoes_the_offending_value() -> None:
    problems = scrub_violations(_with_body(phone="+51987654321", contact="ana@gmail.com"))

    assert problems
    assert all("987654321" not in problem and "gmail" not in problem for problem in problems)
