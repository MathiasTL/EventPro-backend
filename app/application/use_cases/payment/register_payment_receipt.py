"""Comprobante recibido por WhatsApp: registra el adelanto del bot en la transacción del turno."""

from uuid import UUID

from app.application.dtos.payment_dto import CreateAdvancePaymentInput
from app.application.ports.output.quote_repository_port import IQuoteRepositoryPort
from app.application.use_cases.payment.register_advance_payment import RegisterAdvancePaymentUseCase
from app.domain.entities.payment import PaymentMethod
from app.domain.entities.quote import QuoteStatus
from app.domain.exceptions.quote_exceptions import InvalidQuoteStateError, QuoteNotFoundError


class RegisterPaymentReceiptUseCase:
    def __init__(
        self, quotes: IQuoteRepositoryPort, register_advance: RegisterAdvancePaymentUseCase
    ) -> None:
        self._quotes = quotes
        self._register_advance = register_advance

    async def execute(self, quote_id: UUID, evidence_path: str) -> None:
        quote = await self._quotes.get_by_id(quote_id)
        if quote is None:
            raise QuoteNotFoundError("La cotización no existe.")
        if quote.status is not QuoteStatus.PAYMENT_STARTED:
            raise InvalidQuoteStateError("La cotización no espera un pago.")
        await self._register_advance.execute(
            CreateAdvancePaymentInput(
                quote_id=quote_id,
                payment_method=PaymentMethod.UNSPECIFIED,
                amount=quote.liquidation.advance_amount.amount,
                evidence_path=evidence_path,
            )
        )
