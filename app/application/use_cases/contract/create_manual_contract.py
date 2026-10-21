"""Contingencia autoritativa: registra y verifica el encargado en una transacción."""

from dataclasses import replace
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from app.application.dtos.availability_dto import AvailabilityRequest
from app.application.dtos.budget_dto import BudgetLine
from app.application.dtos.manual_contract_dto import ManualContractInput
from app.application.ports.output.availability_port import IAvailabilityPort
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.contract_port import IContractRepository
from app.application.ports.output.manual_booking_port import IBookingDocuments, ManualBooking
from app.application.ports.output.manual_contract_port import IManualContractStore
from app.application.use_cases.contract.manage_contracts import ManageContracts
from app.application.use_cases.quote.prepare_budget import PrepareBudgetUseCase
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.contract import Contract
from app.domain.exceptions.resource_exceptions import ResourceInUseError, ValidationError
from app.domain.value_objects.money import Money
from app.domain.value_objects.time_window import TimeWindow


class InvalidAdvanceAmount(ValidationError):
    code = "invalid-advance-amount"


class ManualAvailabilityConflict(ResourceInUseError):
    code = "availability-conflict"


class CreateManualContract:
    def __init__(
        self,
        store: IManualContractStore,
        repo: IContractRepository,
        catalog: ICatalogReadPort,
        availability: IAvailabilityPort,
        receipts: IBookingDocuments,
        contracts: ManageContracts,
        clock: IClockPort,
        advance_percent: int = 10,
    ) -> None:
        self._store, self._repo, self._catalog = store, repo, catalog
        self._availability, self._receipts = availability, receipts
        self._contracts, self._clock = contracts, clock
        self._percent = Decimal(advance_percent) / 100

    async def execute(
        self,
        request: ManualContractInput,
        user_id: UUID,
    ) -> tuple[ManualBooking, Contract, bool]:
        await self._store.lock_request(request.quote_id)
        existing = await self._store.get(request.quote_id)
        if existing:
            if existing.request_hash != request.request_hash or not existing.contract_id:
                raise ResourceInUseError("La clave de idempotencia ya pertenece a otra solicitud")
            return existing, await self._contracts.get(existing.contract_id), False
        budget = await PrepareBudgetUseCase(
            self._catalog, self._availability, int(self._percent * 100)
        ).execute(request.budget)
        quantities = dict(request.quantities)
        lines = tuple(
            BudgetLine(line.name, line.amount * (quantities[extra] if extra else 1))
            for line, extra in zip(budget.lines, (None, *request.budget.extra_ids), strict=True)
        )
        catalog_services = sum((line.amount for line in lines), Decimal(0))
        if any(line.amount > Decimal("99999999.99") for line in lines):
            raise ValidationError("Una línea excede el importe máximo permitido")
        services = (
            request.agreed_services if request.agreed_services is not None else catalog_services
        )
        if services <= 0 or (request.agreed_services is not None and not request.agreed_reason):
            raise ValidationError("El importe acordado requiere un motivo y debe ser positivo")
        advance = Money(services * self._percent).amount
        if request.advance != advance:
            raise InvalidAdvanceAmount(
                "El adelanto debe coincidir exactamente con el porcentaje de servicios"
            )
        total = services + budget.mobility_amount
        if total > Decimal("99999999.99"):
            raise ValidationError("El total excede el importe máximo permitido")
        budget = replace(
            budget,
            lines=lines,
            services_subtotal=services,
            total_amount=total,
            advance_amount=advance,
            pending_balance=total - advance,
        )
        path = await self._receipts.store(
            data=request.receipt,
            content_type=request.receipt_type,
            original_filename=request.receipt_name,
        )
        await self._store.stage(
            request.quote_id,
            budget,
            request.phone,
            request.district,
            request.payment_method,
            path,
            user_id,
            request.request_hash,
        )
        # Mismo candado PostgreSQL de disponibilidad usado por las demás confirmaciones.
        booking = await self._store.get(request.quote_id, lock=True)
        if booking is None:
            raise ValidationError("No se pudo recuperar la solicitud")
        capacity = await self._availability.check_availability(
            AvailabilityRequest(
                booking.event_date, booking.start_time, budget.duration_minutes, booking.package_id
            )
        )
        if not capacity.is_available:
            raise ManualAvailabilityConflict(
                "No hay disponibilidad; usa el flujo de aprobación de sobrecupo"
            )
        requirements = tuple(await self._catalog.get_inventory_requirements(booking.package_id))
        event_id = uuid5(NAMESPACE_URL, f"eventpro:manual-event:{request.quote_id}")
        contract_id = uuid5(NAMESPACE_URL, f"eventpro:manual-contract:{request.quote_id}")
        number = await self._repo.next_number(self._clock.utcnow().year)
        booking = await self._store.finalize(
            booking,
            user_id,
            event_id,
            contract_id,
            number,
            None,
            TimeWindow.from_schedule(
                booking.event_date, booking.start_time, budget.duration_minutes
            ),
            requirements,
            "Registro manual autoritativo con evidencia verificada",
            draft=True,
        )
        # Completar cantidades y observaciones tras convertir la cotización mantiene
        # sus datos pactados alineados con la instantánea usada por la emisión.
        await self._store.set_details(request)
        await self._store.set_contract_details(event_id, contract_id, request)
        contract = (
            await self._contracts.issue_for_event(event_id, user_id)
            if request.issue
            else await self._contracts.get(contract_id)
        )
        await self._repo.record_audit(
            AuditLog(
                id=uuid4(),
                user_id=user_id,
                action="MANUAL_CONTRACT",
                entity_name="contracts",
                entity_id=contract_id,
                new_values={
                    "receipt_verified": True,
                    "authoritative_manual": True,
                    "catalog_services": str(catalog_services),
                    "agreed_services": str(services),
                    "agreed_services_reason": request.agreed_reason,
                    "mobility_reason": request.budget.mobility_override_reason,
                    "issue_contract": request.issue,
                },
            )
        )
        return booking, contract, True
