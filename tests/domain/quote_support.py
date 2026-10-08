"""Fábricas de Quote compartidas por las pruebas de dominio y de persistencia."""

from datetime import UTC, date, datetime, time
from uuid import UUID, uuid4

from app.domain.entities.quote import Quote, QuoteExtraLine, QuoteSource
from app.domain.value_objects.liquidation import ExtraCharge
from app.domain.value_objects.mobility import MobilityZone, RouteEstimate

from .financial_support import default_engine, pen

NOW = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


def make_quote(
    *,
    now: datetime = NOW,
    deadline_hours: int = 24,
    source: QuoteSource = QuoteSource.WHATSAPP,
    client_provides_mobility: bool = False,
    estimate: RouteEstimate | None = None,
    extra_id: UUID | None = None,
    **overrides: object,
) -> Quote:
    engine = default_engine()
    mobility = engine.resolve_mobility(
        client_provides_mobility=client_provides_mobility,
        estimate=estimate,
        zone=MobilityZone.ZONE_2,
    )
    extra = ExtraCharge(pen("50.25"), 3)
    liquidation = engine.liquidate(
        package_price=pen("1000.00"), extras=[extra], mobility_amount=mobility.final_amount
    )
    lines = [QuoteExtraLine(extra_id or uuid4(), 3, extra.unit_price, extra.subtotal)]
    values: dict[str, object] = {
        "client_id": uuid4(),
        "source": source,
        "event_date": date(2026, 10, 25),
        "event_time": time(21, 30),
        "location_address": "Av. Benavides 1234",
        "location_district": "Miraflores",
        "package_id": uuid4(),
        "client_provides_mobility": client_provides_mobility,
        "mobility": mobility,
        "liquidation": liquidation,
        "extras": lines,
        "now": now,
        "deadline_hours": deadline_hours,
    }
    values.update(overrides)
    return Quote.create(**values)  # type: ignore[arg-type]
