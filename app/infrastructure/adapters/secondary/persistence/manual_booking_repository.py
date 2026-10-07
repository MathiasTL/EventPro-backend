"""Unidad transaccional del proceso manual en PostgreSQL/Supabase.

Quotes/clients/contracts todavía no tienen modelos ORM del equipo E1/E4.
El adaptador usa SQL parametrizado sobre el baseline existente.
"""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos.catalog_dto import InventoryRequirementDTO
from app.application.ports.output.manual_booking_port import ManualBooking
from app.application.use_cases.quote.prepare_budget import BudgetLine, BudgetResult
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.time_window import TimeWindow


class SqlAlchemyManualBookingStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, quote_id: UUID, *, lock: bool = False) -> ManualBooking | None:
        if lock:
            # Un único candado transaccional evita carreras entre reservas manuales,
            # incluso para eventos que cruzan medianoche y paquetes diferentes.
            await self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('eventpro:manual-reservation'))")
            )
            await self._session.execute(
                text("SELECT id FROM quotes WHERE id=:id FOR UPDATE"), {"id": quote_id}
            )
        row = (
            (
                await self._session.execute(
                    text("""
            SELECT q.*, c.full_name, c.phone, p.name AS package_name, p.duration_minutes,
              t.name AS theme_name, pay.id AS payment_id, pay.validation_status,
              pay.evidence_path, pay.amount AS paid_amount, e.id AS event_id, co.id AS contract_id,
              co.contract_number, co.pdf_storage_path
            FROM quotes q JOIN clients c ON c.id=q.client_id
            JOIN packages p ON p.id=q.package_id
            LEFT JOIN themes t ON t.id=q.theme_id
            JOIN payments pay ON pay.quote_id=q.id AND pay.concept='ADVANCE'
            LEFT JOIN events e ON e.quote_id=q.id
            LEFT JOIN contracts co ON co.event_id=e.id AND co.status <> 'VOIDED'
            WHERE q.id=:id AND q.source='MANUAL'
            ORDER BY pay.created_at DESC LIMIT 1
        """),
                    {"id": quote_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        extras = (
            (
                await self._session.execute(
                    text("""
            SELECT x.name, qe.subtotal FROM quote_extras qe
            JOIN extras x ON x.id=qe.extra_id WHERE qe.quote_id=:id ORDER BY qe.id
        """),
                    {"id": quote_id},
                )
            )
            .mappings()
            .all()
        )
        extra_total = sum((entry["subtotal"] for entry in extras), Decimal("0"))
        return ManualBooking(
            quote_id=quote_id,
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
            event_id=row["event_id"],
            contract_id=row["contract_id"],
            contract_number=row["contract_number"],
            pdf_path=row["pdf_storage_path"],
        )

    async def stage(
        self,
        quote_id: UUID,
        budget: BudgetResult,
        phone: str,
        district: str,
        payment_method: str,
        evidence_path: str,
    ) -> ManualBooking:
        client = (
            (
                await self._session.execute(
                    text("SELECT id, full_name FROM clients WHERE phone=:phone"), {"phone": phone}
                )
            )
            .mappings()
            .first()
        )
        if (
            client is not None
            and client["full_name"].casefold() != budget.request.client_name.casefold()
        ):
            raise ValidationError("El teléfono ya pertenece a otro nombre de cliente")
        if client is None:
            client_id = uuid4()
            await self._session.execute(
                text("INSERT INTO clients (id, phone, full_name) VALUES (:id,:phone,:name)"),
                {"id": client_id, "phone": phone, "name": budget.request.client_name},
            )
        else:
            client_id = client["id"]
        await self._session.execute(
            text("""
            INSERT INTO quotes (id,client_id,source,event_date,event_time,location_address,
              location_district,package_id,theme_id,client_provides_mobility,
              services_subtotal,total_amount,advance_amount,pending_balance,status,sent_at,expires_at)
            VALUES (:id,:client,'MANUAL',:date,:time,:address,:district,:package,:theme,true,
              :total,:total,:advance,:balance,'PAYMENT_STARTED',now(),now()+interval '24 hours')
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
                "advance": budget.advance_amount,
                "balance": budget.pending_balance,
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
        await self._session.execute(
            text("""
            INSERT INTO payments (quote_id,concept,payment_method,amount,evidence_path)
            VALUES (:quote,'ADVANCE',:method,:amount,:path)
        """),
            {
                "quote": quote_id,
                "method": payment_method,
                "amount": budget.advance_amount,
                "path": evidence_path,
            },
        )
        result = await self.get(quote_id)
        assert result is not None
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
    ) -> ManualBooking:
        await self._session.execute(
            text("""
            INSERT INTO events (id,event_code,quote_id,event_date,start_time,end_time,
              address,district,total_services_amount,total_mobility_amount,
              final_total_amount,advance_paid,status)
            VALUES (:id,:code,:quote,:date,:start,:end,:address,:district,:total,0,
              :total,:advance,'AWAITING_SIGNATURE')
        """),
            {
                "id": event_id,
                "code": "EVT-" + event_id.hex[:20].upper(),
                "quote": booking.quote_id,
                "date": booking.event_date,
                "start": booking.start_time,
                "end": window.end.time(),
                "address": booking.address,
                "district": booking.district,
                "total": booking.total_amount,
                "advance": booking.advance_amount,
            },
        )
        for requirement in requirements:
            await self._session.execute(
                text("""
                INSERT INTO inventory_reservations
                  (event_id,inventory_item_id,quantity,starts_at,ends_at)
                VALUES (:event,:item,:quantity,:start,:end)
            """),
                {
                    "event": event_id,
                    "item": requirement.inventory_item_id,
                    "quantity": requirement.quantity,
                    "start": window.start,
                    "end": window.end,
                },
            )
        await self._session.execute(
            text("""
            UPDATE payments SET validation_status='VERIFIED',event_id=:event,
              verified_by_user_id=:user,verified_at=now() WHERE id=:payment
        """),
            {"event": event_id, "user": user_id, "payment": booking.payment_id},
        )
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
        assert result is not None
        await self._session.commit()
        return result

    async def list_recent(self) -> tuple[ManualBooking, ...]:
        ids = (
            (
                await self._session.execute(
                    text("""
            SELECT q.id FROM quotes q WHERE q.source='MANUAL'
              AND EXISTS (SELECT 1 FROM payments p WHERE p.quote_id=q.id)
            ORDER BY q.created_at DESC LIMIT 20
        """)
                )
            )
            .scalars()
            .all()
        )
        rows = []
        for quote_id in ids:
            row = await self.get(quote_id)
            if row is not None:
                rows.append(row)
        return tuple(rows)
