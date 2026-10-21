"""Catálogo de motivos de falla (spec 09, sección 9)."""

import pytest

from app.application.use_cases.messaging.failure_catalog import (
    GENERIC_DELIVERY_REASON,
    GENERIC_SEND_REASON,
    MESSAGING_UNAVAILABLE_REASON,
    WINDOW_CLOSED_REASON,
    translate_delivery_failure,
    translate_send_failure,
)

# Texto real que produce Chatwoot, sin código de Meta (captura B2, 2026-10-20).
CHATWOOT_WINDOW_TEXT = (
    "El mensaje no se envió porque la ventana de atención al cliente de WhatsApp de 24 horas "
    "está cerrada y no se proporcionaron parámetros de plantilla."
)


@pytest.mark.parametrize(
    ("external_error", "code", "reason"),
    [
        (CHATWOOT_WINDOW_TEXT, None, WINDOW_CLOSED_REASON),
        ("(#131047) Re-engagement message", 131047, WINDOW_CLOSED_REASON),
        (
            "(#131026) Message undeliverable",
            131026,
            "El cliente no puede recibir el mensaje. "
            "Comprueba que su número tenga WhatsApp activo.",
        ),
        (
            "(#131030) Recipient phone number not in allowed list",
            131030,
            "El número no está entre los destinatarios de prueba.",
        ),
        (
            "(#131031) Account has been locked",
            131031,
            "La cuenta de WhatsApp Business está bloqueada. Contacta al administrador del sistema.",
        ),
        (
            "(#131056) Pair rate limit hit",
            131056,
            "Se enviaron demasiados mensajes a este cliente. Espera unos minutos.",
        ),
        (
            "(#131049) Healthy ecosystem engagement",
            131049,
            "WhatsApp limitó este mensaje. Intenta más tarde.",
        ),
        ("(#999999) Algo nuevo", 999999, GENERIC_DELIVERY_REASON),
        ("Falla sin código ni ventana", None, GENERIC_DELIVERY_REASON),
        ("", None, GENERIC_DELIVERY_REASON),
        (None, None, GENERIC_DELIVERY_REASON),
    ],
)
def test_a_delivery_failure_is_translated_with_its_meta_code(
    external_error: str | None, code: int | None, reason: str
) -> None:
    failure = translate_delivery_failure(external_error)

    assert (failure.code, failure.reason) == (code, reason)


def test_only_the_window_reasons_are_flagged_as_window_closed() -> None:
    assert translate_delivery_failure(CHATWOOT_WINDOW_TEXT).window_closed is True
    assert translate_delivery_failure("(#131047) x").window_closed is True
    assert translate_delivery_failure("(#131030) x").window_closed is False


def test_the_original_text_never_reaches_the_reason() -> None:
    failure = translate_delivery_failure("(#131030) Recipient phone number not in allowed list")

    assert "Recipient" not in failure.reason


@pytest.mark.parametrize(
    ("last_error", "reason"),
    [
        ("ServiceWindowClosedError: fuera de ventana", WINDOW_CLOSED_REASON),
        ("MessagingUnavailableError: Chatwoot no responde", MESSAGING_UNAVAILABLE_REASON),
        ("ValueError: otra cosa", GENERIC_SEND_REASON),
        ("sin tipo de excepción", GENERIC_SEND_REASON),
        (None, GENERIC_SEND_REASON),
    ],
)
def test_an_unsent_outbox_row_is_translated_by_its_exception_type(
    last_error: str | None, reason: str
) -> None:
    assert translate_send_failure(last_error) == reason
