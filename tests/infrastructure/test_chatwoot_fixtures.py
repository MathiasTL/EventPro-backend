"""Guarda de saneamiento de los fixtures de Chatwoot (capturas reales ya saneadas)."""

from typing import Any

import pytest

from tests.chatwoot_fixture_support import (
    FIXTURES_DIR,
    REDACTED,
    fixture_names,
    load_fixture,
    scrub_violations,
)

# Capturas reales saneadas del 2026-10-19 (primeras 12) y del 2026-10-20 (bandeja de E1).
CAPTURED_API_FIXTURES = [
    "api_contact_created",
    "api_contact_search",
    "api_conversation_created",
    "api_conversation_list",
    "api_conversation_reopened",
    "api_inbox_conversation_list",
    "api_inbox_message_list",
    "api_message_created",
    "api_message_created_by_agent",
    "api_message_list",
    "api_message_list_window_failed",
    "api_toggle_status_resolved",
    "api_update_last_seen",
]
CAPTURED_WEBHOOK_FIXTURES = [
    "message_created_incoming",
    "message_created_outgoing",
    "message_updated_delivered",
    "message_updated_failed",
    "message_updated_read",
    "message_updated_sent",
]
# Construidos a mano desde la referencia de Meta: `provisional` es `true`.
CONSTRUCTED_FIXTURES = ["message_updated_failed_131026"]
CAPTURED_FIXTURES = [*CAPTURED_API_FIXTURES, *CAPTURED_WEBHOOK_FIXTURES]
EXPECTED_FIXTURES = sorted([*CAPTURED_FIXTURES, *CONSTRUCTED_FIXTURES])
# Valores inventados que pueden aparecer en nombres, usuarios de WhatsApp y correos.
FAKE_PEOPLE = {
    "Agente Demo",
    "Bandeja WhatsApp Demo",
    "Cliente Demo",
    "Cliente Prueba",
    "Cuenta Demo",
    "Encargado Prueba",
    "EventPro Bot",
    "cliente.demo",
    "cliente.prueba",
    "hello_world",
}
FAKE_PHONES = {"+51999111222", "+51999333444", "51999111222", "51999333444"}
_PEOPLE_KEYS = {"name", "available_name", "social_whatsapp_user_name", "whatsapp"}

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
    assert document["provisional"] is (name in CONSTRUCTED_FIXTURES)
    assert scrub_violations(document) == []


def _values(node: Any, keys: set[str]) -> list[Any]:
    """Valores de todas las claves `keys` en cualquier nivel del documento."""

    found: list[Any] = []
    if isinstance(node, dict):
        for key, child in node.items():
            if key in keys:
                found.append(child)
            found.extend(_values(child, keys))
    elif isinstance(node, list):
        for child in node:
            found.extend(_values(child, keys))
    return found


@pytest.mark.parametrize("name", EXPECTED_FIXTURES)
def test_fixture_carries_only_invented_people_phones_and_emails(name: str) -> None:
    body = load_fixture(name)["body"]

    people = {value for value in _values(body, _PEOPLE_KEYS) if isinstance(value, str)}
    phones = {value for value in _values(body, {"phone_number"}) if isinstance(value, str)}
    assert people - FAKE_PEOPLE - FAKE_PHONES == set()
    assert phones - FAKE_PHONES == set()
    assert all(value is None for value in _values(body, {"email"}))


@pytest.mark.parametrize("name", CAPTURED_API_FIXTURES)
def test_attachment_urls_use_the_fake_public_host_and_token(name: str) -> None:
    urls = [
        value
        for value in _values(load_fixture(name)["body"], {"data_url", "thumb_url"})
        if isinstance(value, str)
    ]

    assert all(url.startswith("https://chat.example.test/rails/active_storage/") for url in urls)
    assert all("FAKETOKEN" in url for url in urls)


def test_the_constructed_meta_failure_fixture_keeps_the_captured_error_format() -> None:
    captured = load_fixture("message_updated_failed")["body"]["content_attributes"]
    constructed = load_fixture("message_updated_failed_131026")["body"]["content_attributes"]

    assert captured["external_error"].startswith("(#131030) ")
    assert constructed["external_error"].startswith("(#131026) ")


@pytest.mark.parametrize("name", CAPTURED_WEBHOOK_FIXTURES + CONSTRUCTED_FIXTURES)
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
