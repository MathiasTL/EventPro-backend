from collections.abc import Iterator, Sequence
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.dtos.payment_dto import PaymentFilters
from app.application.use_cases.payment.audit_payment import AuditPaymentUseCase
from app.application.use_cases.payment.get_payment import GetPaymentUseCase
from app.application.use_cases.payment.get_payment_evidence import GetPaymentEvidenceUseCase
from app.application.use_cases.payment.list_payments import ListPaymentsUseCase
from app.application.use_cases.payment.refund_payment import RefundPaymentUseCase
from app.application.use_cases.payment.register_advance_payment import (
    RegisterAdvancePaymentUseCase,
)
from app.application.use_cases.payment.verify_payment import VerifyPaymentUseCase
from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.payment import (
    Payment,
    PaymentAuditStatus,
    PaymentConcept,
    PaymentMethod,
    PaymentValidationStatus,
)
from app.domain.value_objects.role import Role
from app.infrastructure.di import containers
from app.main import create_app

PATH = "/api/v1/payments"
ADVANCE_PATH = f"{PATH}/advance"
USER_ID = uuid4()
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
QUOTE_ID = str(uuid4())


class FakePaymentRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, Payment] = {}

    async def save(self, payment: Payment) -> Payment:
        self._items[payment.id] = payment
        return payment

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        return self._items.get(payment_id)

    async def list_for_payment(self, filters: PaymentFilters) -> Sequence[Payment]:
        start = (max(1, filters.page) - 1) * max(1, filters.page_size)
        return tuple(self._items.values())[start : start + filters.page_size]

    async def count_for_payment(self, filters: PaymentFilters) -> int:
        return len(self._items)

    async def find_active_advance(self, quote_id: UUID) -> Payment | None:
        for item in self._items.values():
            if (
                item.concept is PaymentConcept.ADVANCE
                and item.quote_id == quote_id
                and item.validation_status
                in (
                    PaymentValidationStatus.PENDING_VERIFICATION,
                    PaymentValidationStatus.REQUIRES_MANUAL_APPROVAL,
                    PaymentValidationStatus.REFUND_PENDING,
                )
            ):
                return item
        return None


class FakeEvidenceStorage:
    def __init__(self) -> None:
        self.stored: dict[str, bytes] = {}

    def max_bytes(self) -> int:
        return 5 * 1024 * 1024

    async def store(self, *, data: bytes, content_type: str, original_filename: str) -> str:
        path = "evidence/fake.png"
        self.stored[path] = data
        return path

    async def open(self, evidence_path: str) -> bytes:
        return self.stored[evidence_path]


class FakeAuditService:
    def __init__(self) -> None:
        self.records: list[AuditLog] = []

    async def record(self, **kwargs) -> AuditLog:
        entry = AuditLog(id=uuid4(), **kwargs)
        self.records.append(entry)
        return entry


def authorization(role: Role = Role.ENCARGADO) -> dict[str, str]:
    token = create_access_token(
        subject=str(USER_ID), role=role.value, secret_key=get_settings().secret_key
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def web_app() -> Iterator[FastAPI]:
    app = create_app()
    repo = FakePaymentRepository()
    storage = FakeEvidenceStorage()
    audits = FakeAuditService()
    app.dependency_overrides[containers.get_register_advance_payment_use_case] = (
        lambda: RegisterAdvancePaymentUseCase(repo)
    )
    app.dependency_overrides[containers.get_list_payments_use_case] = (
        lambda: ListPaymentsUseCase(repo)
    )
    app.dependency_overrides[containers.get_get_payment_use_case] = lambda: GetPaymentUseCase(repo)
    app.dependency_overrides[containers.get_get_payment_evidence_use_case] = (
        lambda: GetPaymentEvidenceUseCase(repo, storage)
    )
    app.dependency_overrides[containers.get_verify_payment_use_case] = (
        lambda: VerifyPaymentUseCase(repo)
    )
    app.dependency_overrides[containers.get_audit_payment_use_case] = (
        lambda: AuditPaymentUseCase(repo, audits)
    )
    app.dependency_overrides[containers.get_refund_payment_use_case] = (
        lambda: RefundPaymentUseCase(repo)
    )
    app.dependency_overrides[containers.get_evidence_storage] = lambda: storage
    yield app
    app.dependency_overrides.clear()


def _multipart(*, quote_id: str = QUOTE_ID, filename: str = "receipt.png") -> tuple[dict, dict]:
    data = {
        "quote_id": quote_id,
        "payment_method": PaymentMethod.YAPE.value,
        "amount": "100.00",
    }
    files = {"receipt_file": (filename, PNG_BYTES, "image/png")}
    return data, files


async def test_register_advance_payment_returns_201(
    web_app: FastAPI,
) -> None:
    data, files = _multipart()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.post(ADVANCE_PATH, headers=authorization(), data=data, files=files)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["concept"] == "ADVANCE"
    assert body["validation_status"] == "PENDING_VERIFICATION"
    assert body["message"] == "Comprobante recibido con éxito. En cola de validación."


async def test_register_advance_payment_rejects_invalid_file(
    web_app: FastAPI,
) -> None:
    class RejectingStorage(FakeEvidenceStorage):
        async def store(
            self, *, data: bytes, content_type: str, original_filename: str
        ) -> str:
            from app.domain.exceptions.resource_exceptions import ValidationError

            raise ValidationError("Tipo de archivo no permitido")

    web_app.dependency_overrides[containers.get_evidence_storage] = lambda: RejectingStorage()
    data, files = _multipart()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.post(ADVANCE_PATH, headers=authorization(), data=data, files=files)
    assert response.status_code == 422
    assert response.json()["type"].endswith("validation-error")


async def test_register_duplicate_active_advance_conflicts(web_app: FastAPI) -> None:
    data, files = _multipart()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        first = await client.post(ADVANCE_PATH, headers=authorization(), data=data, files=files)
        assert first.status_code == 201
        data2, files2 = _multipart()
        second = await client.post(
            ADVANCE_PATH, headers=authorization(), data=data2, files=files2
        )
    assert second.status_code == 409


async def test_verify_reject_and_read_back(web_app: FastAPI) -> None:
    data, files = _multipart()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        created = await client.post(ADVANCE_PATH, headers=authorization(), data=data, files=files)
        payment_id = created.json()["payment_id"]
        verify = await client.patch(
            f"{PATH}/{payment_id}/verify",
            headers=authorization(),
            json={"status": "REJECTED", "rejection_reason": "Monto incompleto"},
        )
        assert verify.status_code == 200
        assert verify.json()["validation_status"] == "REJECTED"
        detail = await client.get(f"{PATH}/{payment_id}", headers=authorization())
        assert detail.status_code == 200
        assert detail.json()["rejection_reason"] == "Monto incompleto"
        evidence = await client.get(f"{PATH}/{payment_id}/evidence", headers=authorization())
        assert evidence.status_code == 200
        assert evidence.content == PNG_BYTES


async def test_verify_reject_requires_reason(web_app: FastAPI) -> None:
    data, files = _multipart()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        created = await client.post(ADVANCE_PATH, headers=authorization(), data=data, files=files)
        payment_id = created.json()["payment_id"]
        response = await client.patch(
            f"{PATH}/{payment_id}/verify", headers=authorization(), json={"status": "REJECTED"}
        )
    assert response.status_code == 422


async def test_unknown_payment_returns_404(web_app: FastAPI) -> None:
    missing = str(uuid4())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.get(f"{PATH}/{missing}", headers=authorization())
    assert response.status_code == 404


@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer invalid"}])
async def test_payments_require_authentication(
    web_app: FastAPI, headers: dict[str, str] | None
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.get(PATH, headers=headers)
    assert response.status_code == 401


async def test_operator_cannot_register_advance(web_app: FastAPI) -> None:
    data, files = _multipart()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.post(
            ADVANCE_PATH, headers=authorization(Role.OPERADOR), data=data, files=files
        )
    assert response.status_code == 403


async def test_list_payments_paginates(web_app: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        for _ in range(2):
            data, files = _multipart(quote_id=str(uuid4()))
            created = await client.post(
                ADVANCE_PATH, headers=authorization(), data=data, files=files
            )
            assert created.status_code == 201
        response = await client.get(
            PATH, headers=authorization(), params={"page": 1, "page_size": 1}
        )
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1


async def test_audit_balance_payment_records_audit_log(web_app: FastAPI) -> None:
    from decimal import Decimal

    from app.domain.value_objects.money import Money

    repo = FakePaymentRepository()
    payment = Payment(
        quote_id=uuid4(),
        event_id=uuid4(),
        concept=PaymentConcept.BALANCE,
        payment_method=PaymentMethod.CASH,
        amount=Money(Decimal("980.50")),
        evidence_path="evidence/screen.png",
        validation_status=PaymentValidationStatus.VERIFIED,
        registered_by_user_id=uuid4(),
        audit_status=PaymentAuditStatus.UNREVIEWED,
    )
    await repo.save(payment)
    audits = FakeAuditService()
    web_app.dependency_overrides[containers.get_audit_payment_use_case] = (
        lambda: AuditPaymentUseCase(repo, audits)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=web_app), base_url="http://test"
    ) as client:
        response = await client.patch(
            f"{PATH}/{payment.id}/audit",
            headers=authorization(),
            json={"audit_status": "REVIEWED"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["audit_status"] == "REVIEWED"
    assert len(audits.records) == 1
    assert audits.records[0].action == "AUDIT_PAYMENT"
