from app.domain.value_objects.financial_reporting import EventFinancialSnapshot
from app.infrastructure.adapters.secondary.persistence.models.event_financial_snapshot_model import (  # noqa: E501
    EventFinancialSnapshotModel,
)


def snapshot_to_model(snapshot: EventFinancialSnapshot) -> EventFinancialSnapshotModel:
    return EventFinancialSnapshotModel(
        event_id=snapshot.event_id,
        gross_revenue=snapshot.gross_revenue.amount,
        fixed_packages_cost=snapshot.costs.package_cost.amount,
        fixed_extras_cost=snapshot.fixed_extras_cost.amount,
        mobility_operational_cost=snapshot.costs.mobility_cost.amount,
        recorded_at=snapshot.recorded_at,
        origin="SETTLEMENT",
        details={
            "package": {
                "id": str(snapshot.costs.package_id),
                "unit_cost": str(snapshot.costs.package_cost.amount),
            },
            "extras": [
                {
                    "id": str(line.extra_id),
                    "quantity": line.quantity,
                    "unit_cost": str(line.unit_cost.amount),
                    "subtotal": str((line.unit_cost * line.quantity).amount),
                }
                for line in snapshot.costs.extras
            ],
            "mobility": {
                "source": "QUOTE_BASE",
                "amount": str(snapshot.costs.mobility_cost.amount),
            },
            "revenue": {
                "advance_paid": str(snapshot.advance_paid.amount),
                "pre_show_balance_paid": str(snapshot.pre_show_balance_paid.amount),
                "legacy_extra_hours_amount": str(snapshot.legacy_extra_hours_amount.amount),
                "verified_extension_amount": str(snapshot.verified_extension_amount.amount),
            },
        },
    )
