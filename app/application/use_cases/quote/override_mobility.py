"""RF-21 / US-19: sobrescritura manual del costo de movilidad de una cotización.

El encargado ajusta el monto de movilidad sugerido (peajes atípicos, zonas de acceso
complejo) antes de que se emita el contrato. ``FinancialEngine.liquidate`` recalcula el
total y el saldo a partir del nuevo monto; el adelanto del 10% de los servicios no cambia
porque ``services_subtotal`` permanece igual. Cada ajuste se registra en la bitácora.
"""

from __future__ import annotations

from app.application.dtos.override_dto import OverrideMobilityDTO, OverrideMobilityInput
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.application.services.audit_service import AuditService
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.services.financial_engine import FinancialEngine
from app.domain.value_objects.liquidation import ExtraCharge
from app.domain.value_objects.money import Money

_BLOCKED_STATUSES = (QuoteStatus.CONVERTED, QuoteStatus.CANCELLED)


class OverrideQuoteMobilityUseCase:
    """Recalcula el total y el saldo de la cotización al sobrescribir la movilidad."""

    def __init__(
        self, quotes: IQuoteRepositoryPort, engine: FinancialEngine, audit: AuditService
    ) -> None:
        self._quotes = quotes
        self._engine = engine
        self._audit = audit

    async def execute(self, dto: OverrideMobilityInput) -> OverrideMobilityDTO:
        quote = await self._quotes.get_by_id(dto.quote_id)
        if quote is None:
            raise ResourceNotFoundError("Cotización no encontrada")
        if quote.status in _BLOCKED_STATUSES:
            raise InvalidQuoteStateError(f"La cotización está {quote.status.value}.")

        extras_total = Money.zero()
        for line in quote.extras:
            extras_total = extras_total + line.subtotal
        package_price = quote.liquidation.services_subtotal - extras_total
        extras = [ExtraCharge(line.unit_price, line.quantity) for line in quote.extras]
        new_liquidation = self._engine.liquidate(
            package_price=package_price,
            extras=extras,
            mobility_amount=Money(dto.manual_mobility_amount),
        )

        old_values = {
            "mobility_amount": str(quote.liquidation.mobility_amount.amount),
            "total_amount": str(quote.liquidation.total_amount.amount),
            "pending_balance": str(quote.liquidation.pending_balance.amount),
            "mobility_overridden": quote.mobility_overridden,
        }

        quote.override_mobility(liquidation=new_liquidation, reason=dto.reason)
        await self._quotes.save(quote)

        await self._audit.record(
            action="OVERRIDE_MOBILITY",
            entity_name="quotes",
            entity_id=quote.id,
            user_id=dto.decided_by_user_id,
            old_values=old_values,
            new_values={
                "mobility_amount": str(quote.liquidation.mobility_amount.amount),
                "total_amount": str(quote.liquidation.total_amount.amount),
                "pending_balance": str(quote.liquidation.pending_balance.amount),
                "mobility_overridden": quote.mobility_overridden,
                "reason": quote.mobility_override_reason,
            },
        )

        return OverrideMobilityDTO(
            quote_id=quote.id,
            mobility_amount=quote.liquidation.mobility_amount.amount,
            total_amount=quote.liquidation.total_amount.amount,
            advance_amount=quote.liquidation.advance_amount.amount,
            pending_balance=quote.liquidation.pending_balance.amount,
            mobility_overridden=quote.mobility_overridden,
        )
