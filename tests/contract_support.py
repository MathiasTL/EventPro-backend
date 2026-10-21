"""Dobles de puertos para probar contratos sin base de datos ni mensajería real."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

from app.application.dtos.contract_dto import ContractData, ContractPage
from app.application.use_cases.contract.manage_contracts import ManageContracts
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.infrastructure.adapters.secondary.storage.contract_pdf import ReportLabContractPdf

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def contract_data(**changes):
    data = ContractData(
        event_id=uuid4(),
        event_status="AWAITING_SIGNATURE",
        quote_id=uuid4(),
        source="WHATSAPP",
        client_name="José Pérez",
        phone="+51999999999",
        dni="12345678",
        ruc=None,
        event_date=date(2027, 1, 10),
        start_time=time(22),
        end_time=time(23),
        address="Av. Principal 123",
        district="Lima",
        package_name="Hora Loca",
        theme_name="Selva",
        extras=("Burbujas x 2: S/ 50.00",),
        services=Decimal("1000"),
        mobility=Decimal("80"),
        total=Decimal("1080"),
        advance=Decimal("100"),
        required_advance=Decimal("100"),
        observations="Sin reggaetón\nSorpresa al minuto 45 <especial>",
    )
    return replace(data, **changes)


class MemoryContracts:
    def __init__(self, data=None):
        self.data = data or contract_data()
        self.contracts = {}
        self.audits = []
        self.counter = 0

    async def get(self, key):
        return deepcopy(self.contracts.get(key))

    async def find_token(self, token_hash):
        return next(
            (deepcopy(c) for c in self.contracts.values() if c.signature_token_hash == token_hash),
            None,
        )

    async def schedule_event(self, event_id):
        assert event_id == self.data.event_id
        self.data = replace(self.data, event_status="SCHEDULED")

    async def active_for_event(self, event_id):
        for contract in self.contracts.values():
            if contract.event_id == event_id and contract.status != "VOIDED":
                return deepcopy(contract)
        return None

    async def event_data(self, event_id, *, lock=False):
        assert event_id == self.data.event_id
        return self.data

    async def next_number(self, year):
        self.counter += 1
        return f"CTR-{year}-{self.counter:04d}"

    async def save(self, contract):
        self.contracts[contract.id] = deepcopy(contract)

    async def list(self, filters):
        items = [
            c
            for c in self.contracts.values()
            if (filters.status is None or c.status == filters.status)
            and (filters.event_id is None or c.event_id == filters.event_id)
            and (filters.is_manual_mode is None or c.is_manual_mode == filters.is_manual_mode)
        ]
        return ContractPage(items, filters.page, filters.page_size, len(items))

    async def set_observations(self, event_id, text):
        self.data = replace(self.data, observations=text)

    async def record_audit(self, entry):
        self.audits.append(entry)

    async def invalidate_pending_links(self, contract_id):
        pass


class MemoryDocuments:
    def __init__(self):
        self.files = {}

    async def store(self, *, data, content_type, original_filename):
        path = f"database/contracts/{uuid4()}"
        self.files[path] = data
        return path

    async def open(self, path):
        return self.files[path]

    async def delete(self, evidence_path):
        self.files.pop(evidence_path, None)

    def max_bytes(self):
        return 5 * 1024 * 1024


def setup_contracts(data=None, *, real_pdf=False):
    repository = MemoryContracts(data)
    documents = MemoryDocuments()
    outbox = AsyncMock()
    outbox.add.side_effect = lambda message: message
    clock = type("Clock", (), {"utcnow": lambda self: NOW})()
    pdf = ReportLabContractPdf() if real_pdf else AsyncMock()
    if not real_pdf:
        pdf.render.return_value = b"%PDF-1.4 prueba"
    service = ManageContracts(
        repository,
        documents,
        pdf,
        EnqueueMessage(outbox, clock),
        clock,
        frontend_url="https://app.eventpro.pe",
    )
    return service, repository, documents, outbox, pdf
