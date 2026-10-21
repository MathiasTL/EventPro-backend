from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort


class ExpireDueQuotesUseCase:
    def __init__(self, quotes: IQuoteRepositoryPort, clock: IClockPort) -> None:
        self._quotes = quotes
        self._clock = clock

    async def execute(self) -> int:
        now = self._clock.utcnow()
        count = 0
        for quote in await self._quotes.find_due(now):
            # Nueva lectura después de bloquear la cotización: protege también pagos
            # confirmados mientras la consulta inicial esperaba una transacción concurrente.
            if await self._quotes.has_payment_in_review(quote.id):
                continue
            quote.expire(now)
            await self._quotes.save(quote)
            count += 1
        return count
