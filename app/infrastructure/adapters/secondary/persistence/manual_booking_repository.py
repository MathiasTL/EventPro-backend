"""Unidad transaccional del proceso manual en PostgreSQL/Supabase.

Quotes/clients/contracts todavía no tienen modelos ORM del equipo E1/E4.
El adaptador usa SQL parametrizado sobre el baseline existente.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.budget_dto import BudgetLine, BudgetResult
from app.application.dtos.catalog_dto import InventoryRequirementDTO
from app.application.ports.output.manual_booking_port import ManualBooking
from app.domain.entities.payment import (
    Payment,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.domain.value_objects.money import Money
from app.domain.value_objects.time_window import TimeWindow
from app.infrastructure.adapters.secondary.persistence.mappers.payment_mapper import (
    payment_to_domain,
    payment_to_model,
)
from app.infrastructure.adapters.secondary.persistence.models.audit_log import AuditLog
from app.infrastructure.adapters.secondary.persistence.models.event_model import EventModel
from app.infrastructure.adapters.secondary.persistence.models.event_resource_models import (
    InventoryReservationModel,
)
from app.infrastructure.adapters.secondary.persistence.models.payment_model import PaymentModel
from app.infrastructure.adapters.secondary.persistence.repositories import (
    sqlalchemy_event_occupancy,
)


class SqlAlchemyManualBookingStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def stage(
        self,
        quote_id: UUID,
        budget: BudgetResult,
        phone: str,
        district: str,
        payment_method: str,
        evidence_path: str,
        user_id: UUID,
        request_hash: str,
    ) -> ManualBooking:
        try:
            return await self._stage(
                quote_id,
                budget,
                phone,
                district,
                payment_method,
                evidence_path,
                user_id,
                request_hash,
            )
        except IntegrityError as exc:
            await self._session.rollback()
            if "uq_quotes_manual_request_hash" in str(exc.orig):
                raise ResourceInUseError(
                    "Estos datos ya tienen una solicitud activa; reutiliza su referencia"
                ) from exc
            raise

    async def get(self, quote_id: UUID, *, lock: bool = False) -> ManualBooking | None:
        if lock:
            # Un único candado transaccional evita carreras entre reservas manuales,
            # incluso para eventos que cruzan medianoche y paquetes diferentes.
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": sqlalchemy_event_occupancy.AVAILABILITY_LOCK_KEY},
            )
            await self._session.execute(
                text("SELECT id FROM quotes WHERE id=:id FOR UPDATE"), {"id": quote_id}
            )
        rows = await self._load(quote_id=quote_id)
        return rows[0] if rows else None

    async def lock_request(self, quote_id: UUID) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 22))"), {"id": str(quote_id)}
        )

    async def _load(
        self, *, quote_id: UUID | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[ManualBooking, ...]:
        rows = (
            (
                await self._session.execute(
                    text("""
            SELECT q.id, q.location_address, q.location_district, q.event_date, q.event_time,
              q.package_id, q.services_subtotal, q.total_amount, q.advance_amount,
              q.pending_balance, q.final_mobility_amount, q.status,
              q.manual_request_hash, q.expires_at,
              c.full_name, c.phone, p.name AS package_name, p.duration_minutes,
              t.name AS theme_name, pay.id AS payment_id, pay.validation_status,
              pay.evidence_path, pay.amount AS paid_amount, pay.registered_by_user_id,
              e.id AS event_id, co.id AS contract_id, co.contract_number, co.pdf_storage_path
            FROM quotes q JOIN clients c ON c.id=q.client_id
            JOIN packages p ON p.id=q.package_id
            LEFT JOIN themes t ON t.id=q.theme_id
            JOIN LATERAL (SELECT * FROM payments WHERE quote_id=q.id AND concept='ADVANCE'
              ORDER BY created_at DESC LIMIT 1) pay ON true
            LEFT JOIN events e ON e.quote_id=q.id
            LEFT JOIN contracts co ON co.event_id=e.id AND co.status <> 'VOIDED'
            WHERE q.source='MANUAL' AND (cast(:id AS uuid) IS NULL OR q.id=:id)
            ORDER BY q.created_at DESC, q.id LIMIT :limit OFFSET :offset
        """),
                    {"id": quote_id, "limit": page_size, "offset": (page - 1) * page_size},
                )
            )
            .mappings()
            .all()
        )
        if not rows:
            return ()
        entries = (
            (
                await self._session.execute(
                    text("""
            SELECT qe.quote_id, x.name, qe.subtotal FROM quote_extras qe
            JOIN extras x ON x.id=qe.extra_id WHERE qe.quote_id=ANY(:ids) ORDER BY qe.id
        """),
                    {"ids": [row["id"] for row in rows]},
                )
            )
            .mappings()
            .all()
        )
        return tuple(
            self._to_booking(row, [entry for entry in entries if entry["quote_id"] == row["id"]])
            for row in rows
        )

    @staticmethod
    def _to_booking(row: RowMapping, extras: list[RowMapping]) -> ManualBooking:
        extra_total = sum((entry["subtotal"] for entry in extras), Decimal("0"))
        return ManualBooking(
            quote_id=row["id"],
            client_name=row["full_name"],
            phone=row["phone"],
            address=row["location_address"],
            district=row["location_district"],
            event_date=row["event_date"],
            start_time=row["event_time"],
            package_id=row["package_id"],
            package_name=row["package_name"],
            theme_name=row["theme_name"],
            duration_minutes=row["duration_minutes"],
            lines=(
                BudgetLine(row["package_name"], row["services_subtotal"] - extra_total),
                *(BudgetLine(entry["name"], entry["subtotal"]) for entry in extras),
            ),
            total_amount=row["total_amount"],
            advance_amount=row["advance_amount"],
            pending_balance=row["pending_balance"],
            payment_id=row["payment_id"],
            payment_status=row["validation_status"],
            paid_amount=row["paid_amount"],
            evidence_path=row["evidence_path"],
            quote_status=row["status"],
            request_hash=row["manual_request_hash"],
            expires_at=row["expires_at"],
            registered_by_user_id=row["registered_by_user_id"],
            mobility_amount=row["final_mobility_amount"],
            event_id=row["event_id"],
            contract_id=row["contract_id"],
            contract_number=row["contract_number"],
            pdf_path=row["pdf_storage_path"],
        )

    async def _stage(
        self,
        quote_id: UUID,
        budget: BudgetResult,
        phone: str,
        district: str,
        payment_method: str,
        evidence_path: str,
        user_id: UUID,
        request_hash: str,
    ) -> ManualBooking:
        client = (
            (
                await self._session.execute(
                    text(
                        "SELECT id, full_name FROM clients WHERE phone IN (:phone,:digits,:local) "
                        "ORDER BY (phone=:phone) DESC LIMIT 1"
                    ),
                    {
                        "phone": phone,
                        "digits": phone.lstrip("+"),
                        "local": phone.removeprefix("+51"),
                    },
                )
            )
            .mappings()
            .first()
        )
        if client is None:
            client_id = await self._session.scalar(
                text(
                    "INSERT INTO clients (id,phone,full_name) VALUES (:id,:phone,:name) "
                    "ON CONFLICT (phone) DO UPDATE SET phone=EXCLUDED.phone RETURNING id"
                ),
                {"id": uuid4(), "phone": phone, "name": budget.request.client_name},
            )
        else:
            # El teléfono es la identidad; no modifica nombres de clientes compartidos.
            client_id = client["id"]
        await self._session.execute(
            text("""
            INSERT INTO quotes (id,client_id,source,event_date,event_time,location_address,
              location_district,package_id,theme_id,client_provides_mobility,
              services_subtotal,total_amount,advance_amount,pending_balance,status,sent_at,
              expires_at,manual_request_hash,base_mobility_amount,final_mobility_amount,
              mobility_overridden,mobility_override_reason)
            VALUES (:id,:client,'MANUAL',:date,:time,:address,:district,:package,:theme,:transport,
              :services,:total,:advance,:balance,'PAYMENT_STARTED',now(),
              now()+interval '24 hours',:hash,:mobility,:mobility,:overridden,:mobility_reason)
        """),
            {
                "id": quote_id,
                "client": client_id,
                "date": budget.request.event_date,
                "time": budget.request.start_time,
                "address": budget.request.address,
                "district": district,
                "package": budget.request.package_id,
                "theme": budget.request.theme_id,
                "total": budget.total_amount,
                "services": budget.services_subtotal,
                "transport": budget.request.client_provides_transport,
                "mobility": budget.mobility_amount,
                "overridden": not budget.request.client_provides_transport,
                "mobility_reason": budget.request.mobility_override_reason,
                "advance": budget.advance_amount,
                "balance": budget.pending_balance,
                "hash": request_hash,
            },
        )
        for extra_id, line in zip(budget.request.extra_ids, budget.lines[1:], strict=True):
            await self._session.execute(
                text("""
                INSERT INTO quote_extras (quote_id,extra_id,quantity,unit_price,subtotal)
                VALUES (:quote,:extra,1,:amount,:amount)
            """),
                {"quote": quote_id, "extra": extra_id, "amount": line.amount},
            )
        payment = Payment(
            quote_id=quote_id,
            concept=PaymentConcept.ADVANCE,
            payment_method=PaymentMethod(payment_method),
            amount=Money(budget.advance_amount),
            evidence_path=evidence_path,
            registered_by_user_id=user_id,
            validation_status=(
                PaymentValidationStatus.PENDING_VERIFICATION
                if budget.availability.is_available
                else PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL
            ),
        )
        self._session.add(payment_to_model(payment))
        if not budget.request.client_provides_transport:
            self._session.add(
                AuditLog(
                    user_id=user_id,
                    action="OVERRIDE_MOBILITY",
                    entity_name="quotes",
                    entity_id=quote_id,
                    old_values={"mobility_amount": "0.00"},
                    new_values={
                        "mobility_amount": str(budget.mobility_amount),
                        "reason": budget.request.mobility_override_reason,
                    },
                )
            )
        await self._session.flush()
        result = await self.get(quote_id)
        if result is None:
            raise ValidationError("La solicitud no se pudo recuperar antes de confirmar")
        await self._session.commit()
        return result

    async def finalize(
        self,
        booking: ManualBooking,
        user_id: UUID,
        event_id: UUID,
        contract_id: UUID,
        contract_number: str,
        pdf_path: str,
        window: TimeWindow,
        requirements: tuple[InventoryRequirementDTO, ...],
        override_reason: str | None = None,
    ) -> ManualBooking:
        self._session.add(
            EventModel(
                id=event_id,
                event_code="EVT-" + event_id.hex[:20].upper(),
                quote_id=booking.quote_id,
                event_date=booking.event_date,
                start_time=booking.start_time,
                end_time=window.end.time(),
                address=booking.address,
                district=booking.district,
                total_services_amount=booking.total_amount - booking.mobility_amount,
                total_mobility_amount=booking.mobility_amount,
                final_total_amount=booking.total_amount,
                advance_paid=booking.advance_amount,
                status="AWAITING_SIGNATURE",
            )
        )
        await self._session.flush()
        for requirement in requirements:
            self._session.add(
                InventoryReservationModel(
                    event_id=event_id,
                    inventory_item_id=requirement.inventory_item_id,
                    quantity=requirement.quantity,
                    starts_at=window.start,
                    ends_at=window.end,
                )
            )
        model = await self._session.scalar(
            select(PaymentModel).where(PaymentModel.id == booking.payment_id).with_for_update()
        )
        if model is None:
            raise ValidationError("Pago no encontrado")
        payment = payment_to_domain(model)
        if payment.validation_status is PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL:
            payment.approve_overbooked(
                verified_by_user_id=user_id, event_id=event_id, approved_at=datetime.now(UTC)
            )
        else:
            payment.verify(
                verified_by_user_id=user_id, event_id=event_id, verified_at=datetime.now(UTC)
            )
        model.validation_status = payment.validation_status.value
        model.event_id = payment.event_id
        model.verified_by_user_id = payment.verified_by_user_id
        model.verified_at = payment.verified_at
        self._session.add(
            AuditLog(
                user_id=user_id,
                action="APPROVE_OVERBOOKED_PAYMENT"
                if booking.payment_status == "REQUIRES_MANUAL_APPROVAL"
                else "AUDIT_PAYMENT",
                entity_name="payments",
                entity_id=payment.id,
                old_values={"validation_status": booking.payment_status},
                new_values={
                    "validation_status": payment.validation_status.value,
                    "event_id": str(event_id),
                    "override_reason": override_reason,
                },
            )
        )
        self._session.add(
            AuditLog(
                user_id=user_id,
                action="MANUAL_CONTRACT",
                entity_name="quotes",
                entity_id=booking.quote_id,
                old_values={"status": booking.quote_status},
                new_values={"status": "CONVERTED", "event_id": str(event_id)},
            )
        )
        await self._session.flush()
        await self._session.execute(
            text("UPDATE quotes SET status='CONVERTED' WHERE id=:id"), {"id": booking.quote_id}
        )
        await self._session.execute(
            text("""
            INSERT INTO contracts
              (id,contract_number,event_id,pdf_storage_path,status,is_manual_mode)
            VALUES (:id,:number,:event,:path,'ISSUED',true)
        """),
            {"id": contract_id, "number": contract_number, "event": event_id, "path": pdf_path},
        )
        await self._session.execute(
            text("""
            INSERT INTO audit_logs (user_id,action,entity_name,entity_id,new_values)
            VALUES (:user,'MANUAL_CONTRACT','contracts',:id,
              jsonb_build_object('quote_id',cast(:quote as text),'event_id',cast(:event as text)))
        """),
            {
                "user": user_id,
                "id": contract_id,
                "quote": str(booking.quote_id),
                "event": str(event_id),
            },
        )
        result = await self.get(booking.quote_id)
        if result is None:
            raise ValidationError("La solicitud no se pudo recuperar antes de confirmar")
        await self._session.commit()
        return result

    async def require_approval(self, booking: ManualBooking, user_id: UUID) -> ManualBooking:
        model = await self._session.scalar(
            select(PaymentModel).where(PaymentModel.id == booking.payment_id).with_for_update()
        )
        if model is None:
            raise ResourceNotFoundError("Pago no encontrado")
        payment = payment_to_domain(model)
        payment.require_manual_approval()
        model.validation_status = payment.validation_status.value
        self._session.add(
            AuditLog(
                user_id=user_id,
                action="AUDIT_PAYMENT",
                entity_name="payments",
                entity_id=booking.payment_id,
                old_values={"validation_status": booking.payment_status},
                new_values={"validation_status": "REQUIRES_MANUAL_APPROVAL"},
            )
        )
        await self._session.flush()
        result = await self.get(booking.quote_id)
        if result is None:
            raise ValidationError("Solicitud no encontrada")
        await self._session.commit()
        return result

    async def refund(
        self, quote_id: UUID, user_id: UUID, *, confirm: bool, reason: str
    ) -> ManualBooking:
        booking = await self.get(quote_id, lock=True)
        if booking is None:
            raise ResourceNotFoundError("Solicitud no encontrada")
        if booking.event_id is not None:
            raise ValidationError("Una reserva existente requiere el proceso de cancelación")
        if booking.payment_status == ("REFUNDED" if confirm else "REFUND_PENDING"):
            return booking
        model = await self._session.scalar(
            select(PaymentModel).where(PaymentModel.id == booking.payment_id).with_for_update()
        )
        if model is None:
            raise ResourceNotFoundError("Pago no encontrado")
        payment = payment_to_domain(model)
        if confirm:
            payment.confirm_refund()
            action = "AUDIT_PAYMENT"
        else:
            payment.mark_refund_pending()
            action = "REJECT_OVERBOOKED_PAYMENT"
        model.validation_status = payment.validation_status.value
        model.verified_by_user_id = user_id
        model.verified_at = datetime.now(UTC)
        self._session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                entity_name="payments",
                entity_id=payment.id,
                old_values={"validation_status": booking.payment_status},
                new_values={"validation_status": payment.validation_status.value, "reason": reason},
            )
        )
        await self._session.execute(
            text("UPDATE quotes SET status='CANCELLED' WHERE id=:id"), {"id": quote_id}
        )
        await self._session.flush()
        result = await self.get(quote_id)
        if result is None:
            raise ValidationError("Solicitud no encontrada")
        await self._session.commit()
        return result

    async def list_recent(self, *, page: int = 1, page_size: int = 20) -> tuple[ManualBooking, ...]:
        return await self._load(page=page, page_size=page_size)
