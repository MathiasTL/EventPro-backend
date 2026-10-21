"""Plantilla de contratos RF-13; ReportLab portable, ejecutado fuera del event loop."""

from functools import partial

from starlette.concurrency import run_in_threadpool

from app.application.dtos.contract_dto import ContractData
from app.domain.entities.contract import Contract
from app.infrastructure.adapters.secondary.storage.document_pdf import render_document


class ReportLabContractPdf:
    async def render(self, contract: Contract, data: ContractData) -> bytes:
        paragraphs = [
            "CONTRATO DE PRESTACIÓN DE SERVICIOS — EventPro",
            f"Cliente: {data.client_name}",
            f"DNI: {data.dni or '—'} | RUC: {data.ruc or '—'} | Teléfono: {data.phone}",
            f"Fecha: {data.event_date:%d/%m/%Y} | Horario: {data.start_time:%H:%M} a "
            f"{data.end_time:%H:%M}",
            f"Dirección: {data.address} | Distrito: {data.district}",
            f"Paquete: {data.package_name} | Temática: {data.theme_name or 'Sin temática'}",
            "Extras contratados:",
            *data.extras,
            f"Subtotal de servicios: S/ {data.services:.2f}",
            f"Movilidad: S/ {data.mobility:.2f}",
            f"Total: S/ {data.total:.2f} | Adelanto verificado: S/ {data.advance:.2f}",
            f"Saldo pendiente (incluye movilidad): S/ {max(data.total - data.advance, 0):.2f}",
            "OBSERVACIONES ESPECIALES DEL CLIENTE",
            *(data.observations.splitlines() if data.observations else ["Sin observaciones"]),
            "CLÁUSULAS PARTICULARES",
            *(
                contract.custom_clauses.splitlines()
                if contract.custom_clauses
                else [
                    "El servicio comprende los elementos y horarios indicados en este documento.",
                    "El saldo deberá completarse antes del inicio del servicio.",
                ]
            ),
            "FIRMA DEL CLIENTE: ____________________",
            "Documento emitido; pendiente de firma electrónica del cliente.",
        ]
        return await run_in_threadpool(
            partial(render_document, f"Contrato N° {contract.contract_number}", paragraphs)
        )
