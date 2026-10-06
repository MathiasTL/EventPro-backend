"""Datos de eventos para pruebas; nunca se siembran en la base de desarrollo."""

from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.domain.entities.event import Event
from app.domain.value_objects.money import Money


def make_event(**changes: Any) -> Event:
    values: dict[str, Any] = {
        "event_code": f"EVT-2026-{uuid4().hex[:8]}",
        "quote_id": uuid4(),
        "event_date": date(2026, 10, 15),
        "start_time": time(21, 30),
        "end_time": time(22, 30),
        "address": "Av. Benavides 2150",
        "district": "Miraflores",
        "total_services_amount": Money(Decimal("980.00")),
        "total_mobility_amount": Money(Decimal("100.50")),
        "final_total_amount": Money(Decimal("1080.50")),
        "advance_paid": Money(Decimal("100.00")),
    }
    values.update(changes)
    return Event(**values)
