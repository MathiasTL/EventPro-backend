from copy import deepcopy
from decimal import Decimal

from app.application.dtos.event_extension_dto import RegisterEventExtensionInput
from app.domain.value_objects.money import Money
from tests.start_event_support import FakeStartEventRepository

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def extension_input(event_id, **changes):
    values = dict(
        event_id=event_id,
        extra_minutes=30,
        agreed_rate=Decimal("100"),
        payment_method="YAPE",
        evidence_data=PNG_BYTES,
        evidence_content_type="image/png",
        evidence_filename="receipt.png",
    )
    from app.domain.entities.payment import PaymentMethod

    values["payment_method"] = PaymentMethod.YAPE
    values.update(changes)
    return RegisterEventExtensionInput(**values)


class FakeExtensionRepository(FakeStartEventRepository):
    def __init__(self, events=()):
        super().__init__(events)
        self.extensions = []
        self.payments = []
        self.total_reads = []
        self.locks = 0

    async def lock_availability(self):
        self.locks += 1

    async def load_occupancy(self, event, added_minutes):
        from app.application.dtos.event_occupancy_dto import EventOccupancy

        return EventOccupancy()

    async def rollback_operation(self):
        pass

    async def save_extension(self, event, extension, payment):
        if self.fail_save:
            raise RuntimeError("No se pudo persistir")
        self.extensions.append(deepcopy(extension))
        self.payments.append(deepcopy(payment))
        self.saves.append(deepcopy(event))
        self.events[event.id] = deepcopy(event)

    async def get_verified_extension_totals(self, event_id):
        from app.application.dtos.event_extension_dto import VerifiedExtensionTotals

        self.total_reads.append(event_id)
        rows = [row for row in self.extensions if row.event_id == event_id]
        return VerifiedExtensionTotals(
            sum((row.agreed_rate for row in rows), Money.zero()),
            sum(row.extra_minutes for row in rows),
        )

    async def save_settlement(self, event):
        await self.save_start(event)

    async def can_discard_extension_evidence(self, payment_id):
        return all(payment.id != payment_id for payment in self.payments)


class RecordingEvidenceStorage:
    def __init__(self):
        self.paths = []
        self.deleted = []
        self.fail_store = False
        self.fail_delete = False

    def max_bytes(self):
        return 5 * 1024 * 1024

    async def store(self, **kwargs):
        if self.fail_store:
            raise ValueError("storage failed")
        self.paths.append("evidence/test.png")
        return self.paths[-1]

    async def delete(self, path):
        self.deleted.append(path)
        if self.fail_delete:
            raise ValueError("cleanup failed")

    async def open(self, path):
        return PNG_BYTES
