"""Tabla de estado comercial derivado (spec 09, 4.2)."""

import pytest

from app.application.dtos.inbox_dto import LeadStatus
from app.application.use_cases.messaging.lead_status import derive_lead_status
from app.domain.entities.quote import QuoteStatus


@pytest.mark.parametrize(
    ("quote_status", "expected"),
    [
        (None, LeadStatus.QUOTING),
        (QuoteStatus.SENT, LeadStatus.QUOTE_SENT),
        (QuoteStatus.PAYMENT_STARTED, LeadStatus.PAYMENT_STARTED),
        (QuoteStatus.CONVERTED, LeadStatus.CONVERTED),
        (QuoteStatus.EXPIRED, LeadStatus.QUOTE_CLOSED),
        (QuoteStatus.CANCELLED, LeadStatus.QUOTE_CLOSED),
    ],
)
def test_it_maps_every_quote_status(quote_status: QuoteStatus | None, expected: LeadStatus) -> None:
    assert derive_lead_status(quote_status) == expected


def test_event_done_only_applies_to_converted_quotes() -> None:
    assert derive_lead_status(QuoteStatus.CONVERTED, event_done=True) is LeadStatus.EVENT_DONE
    assert derive_lead_status(QuoteStatus.SENT, event_done=True) is LeadStatus.QUOTE_SENT
    assert derive_lead_status(None, event_done=True) is LeadStatus.QUOTING
