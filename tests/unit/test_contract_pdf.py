from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader

from app.application.dtos.contract_dto import PromoterIdentity
from app.domain.entities.contract import Contract, ContractStatus
from app.infrastructure.adapters.secondary.storage.contract_clauses import (
    build_immutable_clauses,
    service_category_label,
)
from app.infrastructure.adapters.secondary.storage.contract_pdf import ReportLabContractPdf
from tests.contract_support import contract_data


async def test_professional_contract_pdf_renders_multipage_structure_and_immutable_clauses():
    promoter = PromoterIdentity(
        legal_name="Eventos La Tremenda E.I.R.L.",
        commercial_name="La Tremenda",
        ruc="20601234567",
        address="Av. Javier Prado 456, San Borja",
        city="Lima",
        email="legal@latremenda.pe",
        phone="+51987654321",
        clauses_version="1.0",
    )
    data = contract_data(
        event_code="EVT-TEST-001",
        service_category="SHOW",
        duration_minutes=90,
        package_description="Incluye 4 bailarines & animación.",
    )
    contract = Contract(
        contract_number="CTR-2026-0042",
        event_id=data.event_id,
        is_manual_mode=True,
        custom_clauses="Acceso por puerta lateral <ingreso> & estacionamiento reservado.",
        created_at=datetime(2026, 11, 25, 15, 0, tzinfo=UTC),
    )

    pdf_bytes = await ReportLabContractPdf(promoter=promoter).render(contract, data)

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) < 5 * 1024 * 1024
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) >= 2

    full_text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in (
        "CTR-2026-0042",
        "EVT-TEST-001",
        "Eventos La Tremenda E.I.R.L.",
        "20601234567",
        "EL LOCADOR (LA PROMOTORA)",
        "EL COMITENTE (EL CLIENTE)",
        "SECCIÓN I — CONDICIONES PARTICULARES DEL SERVICIO PACTADO",
        "SECCIÓN II — CLÁUSULAS GENERALES INAMOVIBLES",
        "SECCIÓN III — ACEPTACIÓN, CONFORMIDAD Y FIRMAS",
        service_category_label("SHOW"),
        "Incluye 4 bailarines & animación.",
        "Acceso por puerta lateral <ingreso> & estacionamiento reservado.",
        "OBSERVACIONES ESPECIALES DEL CLIENTE",
        "Sorpresa al minuto 45 <especial>",
        f"Página 1 de {len(reader.pages)}",
        f"Página {len(reader.pages)} de {len(reader.pages)}",
    ):
        assert expected in full_text

    for clause in build_immutable_clauses(promoter, data):
        assert clause.ordinal in full_text
        assert clause.title in full_text


async def test_contract_pdf_shows_client_mobility_exemption_and_signed_state():
    data = contract_data(
        mobility=Decimal("0.00"),
        total=Decimal("1000.00"),
        client_provides_mobility=True,
    )
    contract = Contract(
        contract_number="CTR-2026-0099",
        event_id=data.event_id,
        status=ContractStatus.SIGNED,
        pdf_storage_path="database/contracts/orig.pdf",
        sealed_pdf_storage_path="database/contracts/sealed.pdf",
        sealed_pdf_sha256="a" * 64,
        signed_at=datetime(2026, 11, 25, 19, 30, tzinfo=UTC),
        created_at=datetime(2026, 11, 25, 18, 0, tzinfo=UTC),
    )

    pdf_bytes = await ReportLabContractPdf().render(contract, data)
    text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf_bytes)).pages)

    assert "Exonerada (el cliente proporciona transporte ida y vuelta)" in text
    assert "Firmado electrónicamente el 25/11/2026 19:30 UTC." in text
