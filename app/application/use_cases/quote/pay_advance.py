"""Pago del adelanto real: revalida disponibilidad y devuelve instrucciones (E1, US-07).

El caso de uso no confirma la transacción: el llamador (router o unidad de trabajo del bot)
es dueño del ``commit``. Toda la operación ocurre bajo el bloqueo de la cotización para que
dos pulsaciones simultáneas del botón «Pagar adelanto» no dupliquen la transición.
"""

from datetime import timedelta
from uuid import UUID

from app.application.dtos.availability_dto import AvailabilityRequest, AvailabilityStatus
from app.application.dtos.quote_dto import PayAdvanceResultDTO, PaymentInstructionsDTO
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.domain.entities.quote import Quote, QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityAlternative,
    AvailabilityConflictError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
    SimultaneousThresholdExceededError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError


class PayAdvanceUseCase:
    """``SENT`` → ``PAYMENT_STARTED`` con instrucciones de Yape, Plin o transferencia."""

    def __init__(
        self,
        quotes: IQuoteRepositoryPort,
        catalog: ICatalogReadPort,
        availability: IAvailabilityPort,
        clock: IClockPort,
        instructions: PaymentInstructionsDTO,
        recheck_minutes: int = 60,
    ) -> None:
        if recheck_minutes <= 0:
            raise ValueError("recheck_minutes debe ser mayor que cero")
        self._quotes = quotes
        self._catalog = catalog
        self._availability = availability
        self._clock = clock
        self._instructions = instructions
        self._recheck_minutes = recheck_minutes

    async def execute(self, quote_id: UUID) -> PayAdvanceResultDTO:
        quote = await self._quotes.get_by_id_for_update(quote_id)
        if quote is None:
            raise QuoteNotFoundError("La cotización solicitada no existe.")
        if quote.status is QuoteStatus.EXPIRED:
            raise QuoteExpiredError("La cotización venció.")
        if quote.status in (QuoteStatus.CONVERTED, QuoteStatus.CANCELLED):
            raise InvalidQuoteStateError(f"La cotización está {quote.status.value}.")
        # Idempotente: la segunda pulsación devuelve las mismas instrucciones y plazo.
        if quote.status is QuoteStatus.PAYMENT_STARTED:
            return self._result(quote, AvailabilityStatus.AVAILABLE, rechecked=False)

        now = self._clock.utcnow()
        # El vencimiento manda sobre la revalidación: no se consulta cupo de una cotización vencida.
        if now >= quote.expires_at:
            raise QuoteExpiredError("La cotización venció.")
        rechecked = now - quote.sent_at > timedelta(minutes=self._recheck_minutes)
        availability = AvailabilityStatus.AVAILABLE
        if rechecked:
            availability = await self._revalidate(quote)
        quote.start_payment(now)
        await self._quotes.save(quote)
        return self._result(quote, availability, rechecked=rechecked)

    async def _revalidate(self, quote: Quote) -> AvailabilityStatus:
        package = await self._catalog.get_package(quote.package_id)
        if package is None or not package.is_active:
            raise ResourceNotFoundError("El paquete de la cotización ya no está disponible.")
        result = await self._availability.check_availability(
            AvailabilityRequest(
                event_date=quote.event_date,
                start_time=quote.event_time,
                duration_minutes=package.duration_minutes,
                package_id=quote.package_id,
            )
        )
        if result.is_available:
            return AvailabilityStatus.AVAILABLE
        alternatives = await self._suggest_alternatives(quote, package.duration_minutes)
        if result.requires_manual_approval:
            raise SimultaneousThresholdExceededError(
                "Se requiere aprobación del encargado para este horario.",
                alternatives=alternatives,
            )
        raise AvailabilityConflictError(
            "No hay disponibilidad para la fecha y el horario solicitados.",
            alternatives=alternatives,
        )

    async def _suggest_alternatives(
        self, quote: Quote, duration_minutes: int
    ) -> tuple[AvailabilityAlternative, ...]:
        """Prueba los tres días siguientes con el mismo horario y duración del paquete."""

        alternatives: list[AvailabilityAlternative] = []
        for days in range(1, 4):
            event_date = quote.event_date + timedelta(days=days)
            result = await self._availability.check_availability(
                AvailabilityRequest(
                    event_date=event_date,
                    start_time=quote.event_time,
                    duration_minutes=duration_minutes,
                    package_id=quote.package_id,
                )
            )
            if result.is_available:
                alternatives.append(
                    AvailabilityAlternative(event_date=event_date, event_time=quote.event_time)
                )
        return tuple(alternatives)

    def _result(
        self, quote: Quote, availability: AvailabilityStatus, *, rechecked: bool
    ) -> PayAdvanceResultDTO:
        return PayAdvanceResultDTO(
            quote_id=quote.id,
            status=quote.status,
            availability=availability,
            rechecked=rechecked,
            advance_amount=quote.liquidation.advance_amount.amount,
            payment_deadline=quote.expires_at,
            payment_instructions=self._instructions,
        )
