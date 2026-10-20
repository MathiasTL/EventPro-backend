"""Plantillas manual-v1; ReportLab, texto escapado y ejecución fuera del event loop."""

from uuid import UUID

from starlette.concurrency import run_in_threadpool

from app.application.dtos.budget_dto import BudgetResult
from app.application.ports.output.manual_booking_port import ManualBooking
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


async def contract_pdf(booking: ManualBooking, number: str) -> bytes:
    return await run_in_threadpool(
        render_document,
        "EventPro - Contrato de servicios",
        [
            f"Contrato N° {number} | Modo manual | Plantilla manual-v1",
            f"Cliente: {booking.client_name} | Contacto: {booking.phone}",
            f"Fecha: {booking.event_date} | Inicio: {booking.start_time:%H:%M} (Lima)",
            f"Dirección: {booking.address} | Distrito: {booking.district}",
            f"Paquete: {booking.package_name} | Duración: {booking.duration_minutes} minutos",
            f"Temática: {booking.theme_name or 'Sin temática'}",
            *[f"Servicio: {line.name} - S/ {line.amount:.2f}" for line in booking.lines],
            f"Total servicios: S/ {booking.total_amount - booking.mobility_amount:.2f}",
            f"Movilidad acordada: S/ {booking.mobility_amount:.2f}.",
            f"Adelanto validado: S/ {booking.advance_amount:.2f}",
            f"Saldo de servicios pendiente: S/ {booking.pending_balance:.2f}. "
            f"Movilidad pendiente: S/ {booking.mobility_amount:.2f}.",
            "El cliente deberá cancelar el saldo antes de iniciar el servicio. "
            "El tiempo adicional requiere acuerdo y registro del cobro correspondiente.",
            "El adelanto validado registra la reserva del evento y del inventario requerido. "
            "El contrato está emitido y pendiente de firma del cliente.",
            "Este documento no contiene una firma electrónica ni un sello PAdES. "
            "La firma y el envío por WhatsApp son etapas posteriores.",
            "Firma del cliente: ____________________   Fecha: ____________________",
            "Firma del representante de EventPro: ____________________",
        ],
    )
