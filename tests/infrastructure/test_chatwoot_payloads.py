"""Constructores y lectores de payloads de Chatwoot, contrastados con los fixtures."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.application.dtos.messaging_dto import (
    ConversationMessage,
    ConversationStatus,
    ConversationSummary,
    ListRow,
    ListSection,
    MessageDirection,
    MessageReceipt,
)
from app.domain.exceptions.messaging_exceptions import MessagingUnavailableError
from app.domain.value_objects.phone_number import PhoneNumber
from app.infrastructure.adapters.secondary.external_services.chatwoot import chatwoot_payloads
from app.infrastructure.adapters.secondary.external_services.chatwoot.chatwoot_payloads import (
    ConversationRef,
    build_attachment_files,
    build_attachment_form,
    build_contact_request,
    build_contact_search_params,
    build_conversation_request,
    build_list_message,
    build_template_message,
    build_template_params,
    build_text_message,
    conversation_items,
    decode_direction,
    find_contact_id,
    flatten_sections,
    instant,
    message_items,
    parse_contact_id,
    parse_conversation_message,
    parse_conversation_ref,
    parse_conversation_summary,
    parse_message_receipt,
)
from tests.chatwoot_fixture_support import load_fixture

PHONE = PhoneNumber("+51999111222")
OTHER_PHONE = PhoneNumber("+51999333444")
T0 = datetime(2026, 10, 12, 14, 0, 0, tzinfo=UTC)
T0_EPOCH = 1791813600


def _body(name: str) -> dict[str, Any]:
    body = load_fixture(name)["body"]
    assert isinstance(body, dict)
    return body


# ---------------------------------------------------------------------------
# instant
# ---------------------------------------------------------------------------


def test_instant_from_epoch_adds_the_id_tie_break_in_microseconds() -> None:
    assert instant(T0_EPOCH, 4821) == T0 + timedelta(microseconds=4821)


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-10-12T14:00:00.000Z",
        "2026-10-12T14:00:00Z",
        "2026-10-12T09:00:00-05:00",
        "2026-10-12T14:00:00.987654Z",
        str(T0_EPOCH),
        float(T0_EPOCH),
    ],
)
def test_instant_accepts_epoch_and_iso_forms_and_returns_the_same_second(
    created_at: int | float | str,
) -> None:
    assert instant(created_at, 7) == T0 + timedelta(microseconds=7)


def test_instant_orders_messages_created_in_the_same_second_by_id() -> None:
    first, second = instant(T0_EPOCH, 4821), instant(T0_EPOCH, 4822)

    assert first < second
    assert instant(T0_EPOCH + 1, 1) > second


def test_instant_keeps_only_the_low_digits_of_large_ids() -> None:
    assert instant(T0_EPOCH, 1_000_004821) == T0 + timedelta(microseconds=4821)


def test_instant_is_timezone_aware_utc() -> None:
    assert instant("2026-10-12T09:00:00-05:00", 1).utcoffset() == timedelta(0)
    assert instant(T0_EPOCH, 1).utcoffset() == timedelta(0)


@pytest.mark.parametrize("created_at", ["ayer", None, True, "", 1.5e300])
def test_instant_rejects_unusable_values(created_at: Any) -> None:
    with pytest.raises(MessagingUnavailableError):
        instant(created_at, 1)


# ---------------------------------------------------------------------------
# dirección y filtrado de mensajes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, MessageDirection.INCOMING),
        ("incoming", MessageDirection.INCOMING),
        (1, MessageDirection.OUTGOING),
        ("outgoing", MessageDirection.OUTGOING),
        (2, None),
        ("activity", None),
        (3, None),
        ("template", None),
        ("otra-cosa", None),
        (None, None),
    ],
)
def test_decode_direction(raw: Any, expected: MessageDirection | None) -> None:
    assert decode_direction(raw) is expected


# ---------------------------------------------------------------------------
# contactos
# ---------------------------------------------------------------------------


def test_find_contact_id_picks_the_exact_phone_among_several_results() -> None:
    body = _body("api_contact_search")

    assert find_contact_id(body, PHONE) == 11
    assert find_contact_id(body, OTHER_PHONE) == 12


def test_find_contact_id_rejects_a_superstring_match() -> None:
    body = {"payload": [{"id": 20, "phone_number": "+519991112223"}]}

    assert find_contact_id(body, PHONE) is None


def test_find_contact_id_rejects_a_substring_match() -> None:
    body = {"payload": [{"id": 21, "phone_number": "+5199911122"}]}

    assert find_contact_id(body, PHONE) is None


def test_find_contact_id_normalizes_the_plus_prefix() -> None:
    body = {"payload": [{"id": 22, "phone_number": "51999111222"}]}

    assert find_contact_id(body, PHONE) == 22


def test_find_contact_id_skips_contacts_without_phone_and_empty_results() -> None:
    body = {"payload": [{"id": 23, "phone_number": None}, {"id": 24}]}

    assert find_contact_id(body, PHONE) is None
    assert find_contact_id({"payload": []}, PHONE) is None


def test_find_contact_id_requires_the_payload_list() -> None:
    with pytest.raises(MessagingUnavailableError):
        find_contact_id({"meta": {}}, PHONE)


def test_find_contact_id_rejects_entries_that_are_not_objects() -> None:
    with pytest.raises(MessagingUnavailableError):
        find_contact_id({"payload": ["+51999111222"]}, PHONE)


def test_parse_contact_id_reads_the_created_contact() -> None:
    assert parse_contact_id(_body("api_contact_created")) == 11


def test_parse_contact_id_fails_when_the_contact_is_missing() -> None:
    with pytest.raises(MessagingUnavailableError):
        parse_contact_id({"payload": {}})


def test_contact_builders() -> None:
    assert build_contact_search_params(PHONE) == {"q": "51999111222"}
    assert build_contact_request(2, PHONE) == {
        "inbox_id": 2,
        "name": "+51999111222",
        "phone_number": "+51999111222",
    }


# ---------------------------------------------------------------------------
# conversaciones
# ---------------------------------------------------------------------------


def test_conversation_request_carries_only_inbox_and_contact() -> None:
    assert build_conversation_request(2, 11) == {"inbox_id": 2, "contact_id": 11}


def test_parse_conversation_ref_reads_id_and_can_reply() -> None:
    assert parse_conversation_ref(_body("api_conversation_created")) == ConversationRef(
        conversation_id=57, can_reply=True
    )


def test_parse_conversation_ref_reports_an_absent_can_reply_as_unknown() -> None:
    assert parse_conversation_ref({"id": 57}) == ConversationRef(conversation_id=57, can_reply=None)
    assert parse_conversation_ref({"id": 57, "can_reply": False}).can_reply is False


def test_parse_conversation_ref_requires_the_id() -> None:
    with pytest.raises(MessagingUnavailableError):
        parse_conversation_ref({"can_reply": True})


def test_conversation_items_reads_the_nested_payload() -> None:
    items = conversation_items(_body("api_conversation_list"))

    assert [item["id"] for item in items] == [57, 58, 59, 60]


def test_conversation_items_requires_the_payload_list() -> None:
    with pytest.raises(MessagingUnavailableError):
        conversation_items({"data": {}})


def test_summary_of_a_pending_conversation_maps_to_bot() -> None:
    item = conversation_items(_body("api_conversation_list"))[0]

    assert parse_conversation_summary(item) == ConversationSummary(
        conversation_id=57,
        phone=PHONE,
        status=ConversationStatus.BOT,
        service_window_open=True,
        last_message_at=instant(T0_EPOCH + 100, 4831),
    )


def test_summary_of_an_open_conversation_maps_to_human_with_a_closed_window() -> None:
    item = conversation_items(_body("api_conversation_list"))[1]

    summary = parse_conversation_summary(item)

    assert summary is not None
    assert summary.status is ConversationStatus.HUMAN
    assert summary.phone == OTHER_PHONE
    assert summary.service_window_open is False
    assert summary.last_message_at == instant(T0_EPOCH + 50, 4825)


def test_summary_skips_resolved_conversations_and_missing_phones() -> None:
    items = conversation_items(_body("api_conversation_list"))

    assert parse_conversation_summary(items[2]) is None
    assert parse_conversation_summary(items[3]) is None


def test_summary_falls_back_to_last_activity_when_there_is_no_embedded_message() -> None:
    item = {
        "id": 61,
        "status": "open",
        "can_reply": True,
        "last_activity_at": T0_EPOCH + 5,
        "messages": [],
        "meta": {"sender": {"phone_number": "+51999111222"}},
    }

    summary = parse_conversation_summary(item)

    assert summary is not None
    assert summary.last_message_at == T0 + timedelta(seconds=5)


def test_summary_without_any_time_has_no_last_message_at() -> None:
    item = {
        "id": 62,
        "status": "pending",
        "can_reply": False,
        "meta": {"sender": {"phone_number": "+51999111222"}},
    }

    summary = parse_conversation_summary(item)

    assert summary is not None
    assert summary.last_message_at is None


def test_summary_skips_a_phone_that_cannot_be_parsed() -> None:
    item = {"id": 63, "status": "open", "meta": {"sender": {"phone_number": "no-es-telefono"}}}

    assert parse_conversation_summary(item) is None


# ---------------------------------------------------------------------------
# mensajes: envío
# ---------------------------------------------------------------------------


def test_text_message_is_public_and_outgoing() -> None:
    assert build_text_message("Hola") == {
        "content": "Hola",
        "message_type": "outgoing",
        "private": False,
    }


SECTIONS = (
    ListSection(
        title="Servicios",
        rows=(ListRow("dj", "DJ", "Musica en vivo"), ListRow("foto", "Fotografia")),
    ),
    ListSection(title="Extras", rows=(ListRow("luces", "Luces", "Iluminacion"),)),
)


def test_flatten_sections_keeps_all_rows_in_order_and_drops_descriptions() -> None:
    assert flatten_sections(SECTIONS) == [
        {"title": "DJ", "value": "dj"},
        {"title": "Fotografia", "value": "foto"},
        {"title": "Luces", "value": "luces"},
    ]


def test_flatten_sections_of_nothing_is_empty() -> None:
    assert flatten_sections(()) == []
    assert flatten_sections((ListSection(title="Vacia", rows=()),)) == []


def test_list_message_uses_input_select_items() -> None:
    message = build_list_message("Elige un servicio", SECTIONS)

    assert message["content"] == "Elige un servicio"
    assert message["content_type"] == "input_select"
    assert message["message_type"] == "outgoing"
    assert message["private"] is False
    assert message["content_attributes"] == {"items": flatten_sections(SECTIONS)}


def test_template_params_wrap_the_parameters_as_body() -> None:
    params = {"1": "Ana", "2": "EVT-1"}

    built = build_template_params("cotizacion_lista", params, category="UTILITY", language="es")

    assert built == {
        "name": "cotizacion_lista",
        "category": "UTILITY",
        "language": "es",
        "processed_params": {"body": {"1": "Ana", "2": "EVT-1"}},
    }
    params["1"] = "otro"
    assert built["processed_params"]["body"]["1"] == "Ana"


def test_template_message_has_a_placeholder_content_and_the_template_params() -> None:
    message = build_template_message("otp_firma", {"1": "x"}, category="UTILITY", language="es")

    assert message["content"] == "[plantilla:otp_firma]"
    assert message["message_type"] == "outgoing"
    assert message["private"] is False
    assert message["template_params"] == build_template_params(
        "otp_firma", {"1": "x"}, category="UTILITY", language="es"
    )


def test_attachment_form_carries_the_caption_only_when_present() -> None:
    assert build_attachment_form("Tu cotizacion") == {
        "message_type": "outgoing",
        "content": "Tu cotizacion",
    }
    assert build_attachment_form(None) == {"message_type": "outgoing"}


def test_attachment_files_use_the_multipart_field_of_attachments() -> None:
    assert build_attachment_files("cotizacion.pdf", b"%PDF", "application/pdf") == [
        ("attachments[]", ("cotizacion.pdf", b"%PDF", "application/pdf"))
    ]


# ---------------------------------------------------------------------------
# mensajes: respuestas
# ---------------------------------------------------------------------------


def test_receipt_from_the_created_message_response() -> None:
    assert parse_message_receipt(_body("api_message_created")) == MessageReceipt(
        message_id="4821", conversation_id=57, sent_at=instant(T0_EPOCH, 4821)
    )


def test_receipt_accepts_an_iso_created_at() -> None:
    body = {**_body("api_message_created"), "created_at": "2026-10-12T14:00:00.000Z"}

    assert parse_message_receipt(body).sent_at == instant(T0_EPOCH, 4821)


def test_receipt_never_uses_the_wamid_and_fits_the_column() -> None:
    body = {**_body("api_message_created"), "source_id": "wamid.FAKEMESSAGEID0001"}

    receipt = parse_message_receipt(body)

    assert receipt.message_id == "4821"
    assert len(receipt.message_id) <= 64


@pytest.mark.parametrize("missing", ["id", "conversation_id", "created_at"])
def test_receipt_requires_id_conversation_and_creation_time(missing: str) -> None:
    body = {key: value for key, value in _body("api_message_created").items() if key != missing}

    with pytest.raises(MessagingUnavailableError):
        parse_message_receipt(body)


def test_message_items_reads_the_payload_list() -> None:
    assert [item["id"] for item in message_items(_body("api_message_list"))] == [
        4821,
        4822,
        4823,
        4824,
        4825,
    ]


def test_message_items_requires_the_payload_list() -> None:
    with pytest.raises(MessagingUnavailableError):
        message_items({"meta": {}})


def test_listed_outgoing_and_incoming_messages() -> None:
    items = message_items(_body("api_message_list"))

    assert parse_conversation_message(items[0]) == ConversationMessage(
        message_id="4821",
        conversation_id=57,
        direction=MessageDirection.OUTGOING,
        body="Hola",
        sent_at=instant(T0_EPOCH, 4821),
        attachment_filename=None,
    )
    incoming = parse_conversation_message(items[1])
    assert incoming is not None
    assert incoming.direction is MessageDirection.INCOMING
    assert incoming.body == "Gracias"


def test_listed_activity_and_private_messages_are_excluded() -> None:
    items = message_items(_body("api_message_list"))

    assert parse_conversation_message(items[2]) is None
    assert parse_conversation_message(items[3]) is None


def test_listed_attachment_exposes_the_decoded_file_name() -> None:
    message = parse_conversation_message(message_items(_body("api_message_list"))[4])

    assert message is not None
    assert message.attachment_filename == "cotizacion final.pdf"
    assert message.body == "Tu cotizacion"


def test_listed_message_accepts_the_string_direction_and_a_missing_body() -> None:
    item = {
        "id": 9,
        "conversation_id": 57,
        "message_type": "incoming",
        "private": False,
        "content": None,
        "created_at": T0_EPOCH,
    }

    message = parse_conversation_message(item)

    assert message is not None
    assert message.direction is MessageDirection.INCOMING
    assert message.body is None
    assert message.attachment_filename is None


def test_attachment_name_ignores_the_query_string() -> None:
    item = {
        "id": 10,
        "conversation_id": 57,
        "message_type": 1,
        "private": False,
        "content": None,
        "created_at": T0_EPOCH,
        "attachments": [{"data_url": "https://files.example.org/a/foto.png?v=1"}],
    }

    message = parse_conversation_message(item)

    assert message is not None
    assert message.attachment_filename == "foto.png"


def test_listed_message_without_required_fields_fails() -> None:
    with pytest.raises(MessagingUnavailableError):
        parse_conversation_message({"message_type": 1, "private": False, "content": "x"})


# ---------------------------------------------------------------------------
# nombres de campo aislados en constantes
# ---------------------------------------------------------------------------


def test_every_chatwoot_field_name_is_a_module_constant() -> None:
    constants = {
        name: value
        for name, value in vars(chatwoot_payloads).items()
        if name.endswith(("_KEY", "_PARAM", "_FIELD")) and name.isupper()
    }

    assert constants["ID_KEY"] == "id"
    assert constants["CAN_REPLY_KEY"] == "can_reply"
    assert constants["ATTACHMENT_FILE_FIELD"] == "attachments[]"
    assert all(isinstance(value, str) and value for value in constants.values())
