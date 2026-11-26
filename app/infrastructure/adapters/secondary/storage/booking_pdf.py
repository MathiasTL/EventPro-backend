"""Presupuestos y adaptación del flujo manual al generador de contratos E2."""

from uuid import NAMESPACE_URL, UUID, uuid5

from app.application.dtos.budget_dto import BudgetResult
from app.application.dtos.contract_dto import ContractData, PromoterIdentity
from app.application.ports.output.manual_booking_port import ManualBooking
from app.domain.entities.contract import Contract
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.storage.contract_pdf import ReportLabContractPdf
from app.infrastructure.adapters.secondary.storage.document_pdf import render_document


def render_pdf(result: BudgetResult, budget_id: UUID) -> bytes:
    return render_document(
        "EventPro - Presupuesto",
        [
            f"Referencia: {budget_id}",
            f"Cliente: {result.request.client_name}",
            f"Evento: {result.request.event_date} {result.request.start_time:%H:%M} (Lima), "
            f"{result.duration_minutes} minutos",
            f"Dirección: {result.request.address}",
            f"Temática: {result.theme_name or 'Sin temática'}",
            *[f"{line.name}: S/ {line.amount:.2f}" for line in result.lines],
            f"Servicios: S/ {result.services_subtotal:.2f} | "
            f"Movilidad: S/ {result.mobility_amount:.2f}",
            f"Total: S/ {result.total_amount:.2f}",
            f"Adelanto requerido: S/ {result.advance_amount:.2f} | "
            f"Saldo: S/ {result.pending_balance:.2f}",
            f"Disponibilidad: {result.availability.status.value}",
            "Presupuesto previo. No acredita pago ni reserva fecha o recursos. "
            "La disponibilidad se revalida al confirmar el adelanto. No es un contrato.",
        ],
    )


async def contract_pdf(
    booking: ManualBooking, number: str, *, promoter: PromoterIdentity | None = None
) -> bytes:
    """Adapta el flujo previo a E2; sigue renderizando antes del candado de capacidad.

    ``promoter`` lleva la identidad configurada; sin ella se usan los valores por defecto.
    """
    event_id = uuid5(NAMESPACE_URL, f"eventpro:manual-event:{booking.quote_id}")
    window = TimeWindow.from_schedule(
        booking.event_date, booking.start_time, booking.duration_minutes
    )
    contract = Contract(contract_number=number, event_id=event_id, is_manual_mode=True)
    data = ContractData(
        event_id=event_id,
        event_status="AWAITING_SIGNATURE",
        quote_id=booking.quote_id,
        source="MANUAL",
        client_name=booking.client_name,
        phone=booking.phone,
        dni=booking.dni,
        ruc=booking.ruc,
        event_date=booking.event_date,
        start_time=booking.start_time,
        end_time=window.end.time(),
        address=booking.address,
        district=booking.district,
        package_name=booking.package_name,
        theme_name=booking.theme_name,
        extras=booking.extras,
        services=booking.total_amount - booking.mobility_amount,
        mobility=booking.mobility_amount,
        total=booking.total_amount,
        advance=booking.paid_amount,
        required_advance=booking.advance_amount,
        observations=booking.observations,
        event_code="EVT-" + event_id.hex[:20].upper(),
        duration_minutes=booking.duration_minutes,
        service_category=booking.service_category,
        package_description=booking.package_description,
        client_provides_mobility=booking.client_provides_mobility,
    )
    return await ReportLabContractPdf(promoter=promoter).render(contract, data)
