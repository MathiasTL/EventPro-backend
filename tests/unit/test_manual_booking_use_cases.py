"""Reglas del proceso nuevo, usando puertos falsos y sin conectar a Supabase."""

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dtos.availability_dto import AvailabilityResult, AvailabilityStatus
from app.application.dtos.budget_dto import BudgetInput, BudgetLine
from app.application.ports.output.manual_booking_port import ManualBooking
from app.application.use_cases.quote.confirm_manual_booking import ConfirmManualBookingUseCase
from app.application.use_cases.quote.prepare_budget import PrepareBudgetUseCase
from app.application.use_cases.quote.register_manual_booking import (
    RegisterManualBookingInput,
    RegisterManualBookingUseCase,
)
from app.domain.exceptions.resource_exceptions import (
    ResourceInUseError,
    ResourceNotFoundError,
    ValidationError,
)
from app.infrastructure.adapters.primary.web.schemas.manual_booking_schemas import ManualRequest
from app.infrastructure.adapters.secondary.storage.booking_pdf import contract_pdf, render_pdf


def budget_setup():
    package_id, theme_id, extra_id = uuid4(), uuid4(), uuid4()
    catalog = SimpleNamespace(
        get_package=AsyncMock(
            return_value=SimpleNamespace(
                id=package_id,
                name="Show <especial>",
                base_price=Decimal("100.05"),
                duration_minutes=90,
                is_active=True,
            )
        ),
        get_theme=AsyncMock(return_value=SimpleNamespace(id=theme_id, name="Tema", is_active=True)),
        are_themes_compatible=AsyncMock(return_value=True),
        get_extra=AsyncMock(
            return_value=SimpleNamespace(name="Extra", sale_price=Decimal("10.00"), is_active=True)
        ),
        get_inventory_requirements=AsyncMock(return_value=()),
    )
    availability = SimpleNamespace(
        check_availability=AsyncMock(return_value=AvailabilityResult(AvailabilityStatus.AVAILABLE))
    )
    request = BudgetInput(
        "Cliente & <nombre>",
        date.today() + timedelta(days=30),
        time(23, 30),
        "Av. Principal 123",
        package_id,
        theme_id,
        (extra_id,),
    )
    return catalog, availability, request


async def test_budget_prices_rounding_and_configurable_advance():
    catalog, availability, request = budget_setup()
    result = await PrepareBudgetUseCase(catalog, availability, 15).execute(request)
    assert result.total_amount == Decimal("110.05")
    assert result.advance_amount == Decimal("16.51")
    assert result.pending_balance == Decimal("93.54")
    assert availability.check_availability.await_args.args[0].duration_minutes == 90


async def test_manual_mobility_does_not_increase_advance():
    catalog, availability, request = budget_setup()
    result = await PrepareBudgetUseCase(catalog, availability).execute(
        replace(
            request,
            client_provides_transport=False,
            manual_mobility_amount=Decimal("50"),
            mobility_override_reason="Tarifa acordada por distrito",
        )
    )
    assert result.total_amount == Decimal("160.05")
    assert result.advance_amount == Decimal("11.01")
    assert result.pending_balance == Decimal("99.04")


@pytest.mark.parametrize(
    "failure", ["past", "duplicate", "package", "theme", "incompatible", "extra", "mobility"]
)
async def test_budget_rejects_invalid_requests(failure):
    catalog, availability, request = budget_setup()
    if failure == "past":
        request = replace(request, event_date=date.today() - timedelta(days=1))
    elif failure == "duplicate":
        request = replace(request, extra_ids=request.extra_ids * 2)
    elif failure == "package":
        catalog.get_package.return_value = None
    elif failure == "theme":
        catalog.get_theme.return_value = None
    elif failure == "incompatible":
        catalog.are_themes_compatible.return_value = False
    elif failure == "extra":
        catalog.get_extra.return_value = None
    else:
        request = replace(request, client_provides_transport=False)
    with pytest.raises((ValidationError, ResourceNotFoundError)):
        await PrepareBudgetUseCase(catalog, availability).execute(request)


def booking(**changes):
    values = dict(
        quote_id=uuid4(),
        client_name="Cliente <&>",
        phone="+51999999999",
        address="Av. Principal 123",
        district="Lima",
        event_date=date.today() + timedelta(days=30),
        start_time=time(23, 30),
        package_id=uuid4(),
        package_name="Show",
        theme_name=None,
        duration_minutes=90,
        lines=(BudgetLine("Show", Decimal("100")),),
        total_amount=Decimal("100"),
        advance_amount=Decimal("10"),
        pending_balance=Decimal("90"),
        payment_id=uuid4(),
        payment_status="PENDING_VERIFICATION",
        paid_amount=Decimal("10"),
        evidence_path="receipt",
        quote_status="PAYMENT_STARTED",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    values.update(changes)
    return ManualBooking(**values)


def confirmation_setup(row):
    store = SimpleNamespace(
        get=AsyncMock(return_value=row),
        finalize=AsyncMock(return_value=row),
        require_approval=AsyncMock(
            return_value=replace(row, payment_status="REQUIRES_MANUAL_APPROVAL")
        ),
    )
    catalog, availability, _ = budget_setup()
    documents = SimpleNamespace(
        store=AsyncMock(return_value="database/contracts/pdf"), delete=AsyncMock()
    )
    renderer = AsyncMock(return_value=b"%PDF-1.4")
    return (
        ConfirmManualBookingUseCase(store, catalog, availability, documents, renderer),
        store,
        availability,
        documents,
        renderer,
    )


async def test_confirmation_validates_window_and_renders_before_lock():
    row = booking()
    use_case, store, _, documents, renderer = confirmation_setup(row)
    await use_case.execute(row.quote_id, uuid4())
    window = store.finalize.await_args.args[6]
    assert window.end.date() == window.start.date() + timedelta(days=1)
    renderer.assert_awaited_once()
    documents.store.assert_awaited_once()
    assert store.get.await_args_list[0].kwargs == {}
    assert store.get.await_args_list[1].kwargs == {"lock": True}


@pytest.mark.parametrize(
    "changes",
    [
        {"quote_status": "CANCELLED"},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        {"payment_status": "REFUND_PENDING"},
        {"paid_amount": Decimal("9")},
        {"event_date": date.today() - timedelta(days=1)},
    ],
)
async def test_confirmation_rejects_invalid_states(changes):
    row = booking(**changes)
    use_case, store, _, documents, _ = confirmation_setup(row)
    with pytest.raises(ValidationError):
        await use_case.execute(row.quote_id, uuid4())
    store.finalize.assert_not_awaited()
    documents.store.assert_not_awaited()


async def test_confirmation_overcapacity_preserves_receipt_for_review():
    row = booking()
    use_case, store, availability, documents, _ = confirmation_setup(row)
    availability.check_availability.return_value = AvailabilityResult(AvailabilityStatus.CONFLICT)
    result = await use_case.execute(row.quote_id, uuid4())
    assert result.payment_status == "REQUIRES_MANUAL_APPROVAL"
    store.finalize.assert_not_awaited()
    documents.store.assert_not_awaited()


async def test_confirmation_replay_uses_same_event_and_contract():
    row = booking(
        event_id=uuid4(), contract_id=uuid4(), payment_status="VERIFIED", quote_status="CONVERTED"
    )
    use_case, store, _, documents, renderer = confirmation_setup(row)
    assert await use_case.execute(row.quote_id, uuid4()) == row
    renderer.assert_not_awaited()
    store.finalize.assert_not_awaited()
    documents.store.assert_not_awaited()


async def test_commit_error_does_not_delete_durable_contract():
    row = booking()
    use_case, store, _, documents, _ = confirmation_setup(row)
    store.finalize.side_effect = ConnectionError("Resultado de commit incierto")
    with pytest.raises(ConnectionError):
        await use_case.execute(row.quote_id, uuid4())
    documents.delete.assert_not_awaited()


async def test_self_verification_requires_supervised_reason():
    actor = uuid4()
    row = booking(registered_by_user_id=actor)
    use_case, store, _, _, _ = confirmation_setup(row)
    with pytest.raises(ValidationError):
        await use_case.execute(row.quote_id, actor)
    await use_case.execute(
        row.quote_id,
        actor,
        self_verification_reason="Verificación supervisada para entrega",
        may_verify_own_receipt=True,
    )
    assert store.finalize.await_args.args[-1] == "Verificación supervisada para entrega"


@pytest.mark.parametrize("same", [True, False])
async def test_registration_idempotency_compares_full_payload(same):
    row = booking(request_hash="same")
    store = SimpleNamespace(
        lock_request=AsyncMock(), get=AsyncMock(return_value=row), stage=AsyncMock()
    )
    catalog, availability, request = budget_setup()
    receipts = SimpleNamespace(store=AsyncMock())
    use_case = RegisterManualBookingUseCase(
        store, PrepareBudgetUseCase(catalog, availability), receipts
    )
    incoming = RegisterManualBookingInput(
        row.quote_id,
        request,
        row.phone,
        row.district,
        "YAPE",
        "10",
        "same" if same else "changed",
        b"image",
        "image/png",
        "receipt.png",
    )
    if same:
        assert await use_case.execute(incoming, uuid4()) == (row, False)
    else:
        with pytest.raises(ResourceInUseError):
            await use_case.execute(incoming, uuid4())
    receipts.store.assert_not_awaited()
    store.stage.assert_not_awaited()


async def test_pdf_generation_accepts_untrusted_text_and_produces_pdf():
    catalog, availability, request = budget_setup()
    result = await PrepareBudgetUseCase(catalog, availability).execute(request)
    for data in [render_pdf(result, uuid4()), await contract_pdf(booking(), "CTR-TEST")]:
        assert data.startswith(b"%PDF-")
        assert b"%%EOF" in data
        assert len(data) > 1000


@pytest.mark.parametrize("phone", ["999999999", "51999999999", "+51999999999"])
def test_phone_normalization(phone):
    _, _, request = budget_setup()
    payload = ManualRequest(
        client_name=request.client_name,
        event_date=request.event_date,
        start_time=request.start_time,
        address=request.address,
        package_id=request.package_id,
        phone=phone,
        district="Lima",
        payment_method="YAPE",
        paid_amount="10",
        quote_id=uuid4(),
        client_provides_transport=True,
    )
    assert payload.phone == "+51999999999"
