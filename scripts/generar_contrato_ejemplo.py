r"""Genera una muestra ficticia con el renderer real; no conecta a BD ni envía mensajes.

Desde la raíz: .\.venv\Scripts\python.exe scripts/generar_contrato_ejemplo.py
"""

import asyncio
import sys
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.application.dtos.contract_dto import ContractData  # noqa: E402
from app.domain.entities.contract import Contract  # noqa: E402
from app.infrastructure.adapters.secondary.storage.contract_pdf import (  # noqa: E402
    ReportLabContractPdf,
)


async def main() -> None:
    event_id = UUID("00000000-0000-4000-8000-000000000001")
    contract = Contract(
        contract_number="DEMO-2026-0001",
        event_id=event_id,
        is_manual_mode=True,
        custom_clauses=(
            "MUESTRA DE PRUEBA: todos los datos son ficticios. Sin validez contractual.\n"
            "El cliente facilita un punto de energía y acceso al local 30 minutos antes.\n"
            "El saldo se completa antes del inicio del servicio."
        ),
    )
    data = ContractData(
        event_id=event_id,
        event_status="AWAITING_SIGNATURE",
        quote_id=UUID("00000000-0000-4000-8000-000000000002"),
        source="MANUAL",
        client_name="CLIENTE FICTICIO - DEMOSTRACIÓN",
        phone="+51000000000",
        dni="00000000",
        ruc=None,
        event_date=date(2026, 12, 15),
        start_time=time(20, 0),
        end_time=time(21, 30),
        address="Av. de Ejemplo 123 (dirección ficticia)",
        district="Miraflores",
        package_name="Hora Loca Premium - S/ 900.00",
        theme_name="Fiesta tropical",
        extras=("Máquina de burbujas x 1: S/ 100.00", "Cotillón adicional x 2: S/ 100.00"),
        services=Decimal("1100.00"),
        mobility=Decimal("70.00"),
        total=Decimal("1170.00"),
        advance=Decimal("110.00"),
        required_advance=Decimal("110.00"),
        observations=(
            "DOCUMENTO DE DEMOSTRACIÓN. No representa una reserva ni un pago real.\n"
            "No reproducir reggaetón. Coordinar el ingreso sorpresa al minuto 45."
        ),
    )
    output = ROOT / "output" / "pdf" / "contrato-ejemplo-diego.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(await ReportLabContractPdf().render(contract, data))
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
