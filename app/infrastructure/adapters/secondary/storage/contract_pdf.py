"""Plantilla profesional de contratos RF-13 en ReportLab portable (sin GTK)."""

from dataclasses import dataclass
from functools import partial
from html import escape
from io import BytesIO
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.application.dtos.contract_dto import ContractData, PromoterIdentity
from app.domain.entities.contract import Contract, ContractStatus
from app.infrastructure.adapters.secondary.storage.contract_clauses import (
    build_immutable_clauses,
    service_category_label,
)

_INK_HEX = "#14111B"
_MAGENTA_HEX = "#B81D74"
_BODY_HEX = "#27272A"
_MUTED_HEX = "#52525B"
_BORDER_HEX = "#D4D4D8"
_SURFACE_HEX = "#F8F7FA"
_ACCENT_SOFT_HEX = "#FDF2F8"


def _html_lines(value: str) -> str:
    """Escapa texto no confiable para XML de ReportLab preservando saltos de línea."""
    lines = value.splitlines()
    if not lines:
        return "—"
    return "<br/>".join(escape(line) if line else "&nbsp;" for line in lines)


@dataclass(frozen=True)
class _PdfStyles:
    title: Any
    subtitle: Any
    meta: Any
    section: Any
    subsection: Any
    clause_title: Any
    body: Any
    body_small: Any
    table_header: Any
    table_cell: Any
    table_cell_bold: Any
    table_cell_right: Any
    table_cell_right_bold: Any
    note: Any


def _build_styles() -> _PdfStyles:
    from reportlab.lib import colors  # type: ignore[import-untyped]
    from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT  # type: ignore[import-untyped]
    from reportlab.lib.styles import (  # type: ignore[import-untyped]
        ParagraphStyle,
        getSampleStyleSheet,
    )

    base = getSampleStyleSheet()
    ink = colors.HexColor(_INK_HEX)
    body_color = colors.HexColor(_BODY_HEX)
    muted = colors.HexColor(_MUTED_HEX)

    return _PdfStyles(
        title=ParagraphStyle(
            "ContractTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.white,
            spaceAfter=2,
        ),
        subtitle=ParagraphStyle(
            "ContractSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#E4E4E7"),
        ),
        meta=ParagraphStyle(
            "ContractMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=muted,
        ),
        section=ParagraphStyle(
            "ContractSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=ink,
            spaceBefore=8,
            spaceAfter=4,
        ),
        subsection=ParagraphStyle(
            "ContractSubsection",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.2,
            leading=12.5,
            textColor=ink,
            spaceBefore=6,
            spaceAfter=3,
        ),
        clause_title=ParagraphStyle(
            "ClauseTitle",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=9.0,
            leading=12,
            textColor=ink,
            spaceBefore=6,
            spaceAfter=2,
        ),
        body=ParagraphStyle(
            "ContractBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.8,
            leading=12.5,
            textColor=body_color,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        ),
        body_small=ParagraphStyle(
            "ContractBodySmall",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=11.5,
            textColor=body_color,
            spaceAfter=3,
        ),
        table_header=ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=11,
            textColor=ink,
        ),
        table_cell=ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=body_color,
        ),
        table_cell_bold=ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.6,
            leading=11.5,
            textColor=ink,
        ),
        table_cell_right=ParagraphStyle(
            "TableCellRight",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=body_color,
            alignment=TA_RIGHT,
        ),
        table_cell_right_bold=ParagraphStyle(
            "TableCellRightBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.8,
            leading=11.5,
            textColor=ink,
            alignment=TA_RIGHT,
        ),
        note=ParagraphStyle(
            "ContractNote",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8.1,
            leading=11,
            textColor=muted,
            spaceAfter=3,
        ),
    )


def _make_numbered_canvas(
    contract_number: str,
    commercial_name: str,
    clauses_version: str,
) -> type[Any]:
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

    class _NumberedCanvas(canvas.Canvas):  # type: ignore[misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict[str, Any]] = []

        def showPage(self) -> None:
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_chrome(total_pages)
                super().showPage()
            super().save()

        def _draw_chrome(self, total_pages: int) -> None:
            page_num = self._pageNumber
            width, height = self._pagesize
            left = 46
            right = width - 46
            self.saveState()
            if page_num > 1:
                self.setStrokeColor(colors.HexColor(_BORDER_HEX))
                self.setLineWidth(0.5)
                self.line(left, height - 38, right, height - 38)
                self.setFont("Helvetica-Bold", 7.5)
                self.setFillColor(colors.HexColor(_INK_HEX))
                self.drawString(left, height - 32, commercial_name.upper())
                self.setFont("Helvetica", 7.5)
                self.setFillColor(colors.HexColor(_MUTED_HEX))
                self.drawRightString(
                    right,
                    height - 32,
                    f"Contrato N° {contract_number} · Cláusulas v{clauses_version}",
                )

            self.setStrokeColor(colors.HexColor(_BORDER_HEX))
            self.setLineWidth(0.5)
            self.line(left, 36, right, 36)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor(_MUTED_HEX))
            self.drawString(
                left,
                25,
                f"EventPro · Contrato N° {contract_number} (v{clauses_version})",
            )
            self.drawRightString(right, 25, f"Página {page_num} de {total_pages}")
            self.restoreState()

    return _NumberedCanvas


def _render_contract_bytes(
    contract: Contract,
    data: ContractData,
    promoter: PromoterIdentity,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
    from reportlab.platypus import (  # type: ignore[import-untyped]
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = _build_styles()
    ink = colors.HexColor(_INK_HEX)
    magenta = colors.HexColor(_MAGENTA_HEX)
    border = colors.HexColor(_BORDER_HEX)
    surface = colors.HexColor(_SURFACE_HEX)
    accent_soft = colors.HexColor(_ACCENT_SOFT_HEX)

    page_width = A4[0] - 92  # 46 pt de margen a cada lado
    mode_label = "Contingencia Manual" if contract.is_manual_mode else "Emisión Estándar"
    event_ref = data.event_code or str(data.event_id)
    issued_date = contract.created_at.strftime("%d/%m/%Y")

    story: list[Any] = []

    # --- Encabezado institucional ---
    banner_rows = [
        [
            Paragraph(
                f"{escape(promoter.commercial_name.upper())} · {escape(promoter.legal_name)}",
                styles.subtitle,
            ),
            Paragraph(
                f"<b>Contrato N° {escape(contract.contract_number)}</b>",
                _banner_right_style(styles.subtitle),
            ),
        ],
        [
            Paragraph(
                "CONTRATO DE LOCACIÓN DE SERVICIOS DE ENTRETENIMIENTO Y EVENTOS",
                styles.title,
            ),
            "",
        ],
    ]
    banner = Table(banner_rows, colWidths=[page_width * 0.68, page_width * 0.32])
    banner.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 1), (1, 1)),
                ("BACKGROUND", (0, 0), (-1, -1), ink),
                ("LINEBELOW", (0, 1), (-1, 1), 2.5, magenta),
                ("TOPPADDING", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(banner)
    story.append(Spacer(1, 6))

    meta_text = (
        f"<b>Evento:</b> {escape(event_ref)} &nbsp;|&nbsp; "
        f"<b>Modalidad:</b> {escape(mode_label)} &nbsp;|&nbsp; "
        f"<b>Fecha de emisión:</b> {issued_date} ({escape(promoter.city)}, Perú) &nbsp;|&nbsp; "
        f"<b>Cláusulas generales:</b> v{escape(promoter.clauses_version)}"
    )
    story.append(Paragraph(meta_text, styles.meta))
    story.append(Spacer(1, 8))

    # --- Comparecencia ---
    story.append(
        Paragraph(
            "Conste por el presente documento, el <b>Contrato de Prestación de Servicios de "
            "Entretenimiento</b> que celebran, al amparo del artículo 1764 y siguientes del "
            "Código Civil peruano, las partes identificadas a continuación:",
            styles.body,
        )
    )
    parties_table = Table(
        [
            [
                Paragraph("EL LOCADOR (LA PROMOTORA)", styles.table_header),
                Paragraph("EL COMITENTE (EL CLIENTE)", styles.table_header),
            ],
            [
                Paragraph(
                    f"<b>Razón / Titular:</b> {escape(promoter.legal_name)}<br/>"
                    f"<b>Nombre comercial:</b> {escape(promoter.commercial_name)}<br/>"
                    f"<b>RUC:</b> {escape(promoter.ruc)}<br/>"
                    f"<b>Domicilio:</b> {escape(promoter.address)}<br/>"
                    f"<b>Contacto:</b> {escape(promoter.email)} · {escape(promoter.phone)}",
                    styles.table_cell,
                ),
                Paragraph(
                    f"<b>Nombre / Razón social:</b> {escape(data.client_name)}<br/>"
                    f"<b>DNI:</b> {escape(data.dni or '—')} &nbsp;|&nbsp; "
                    f"<b>RUC:</b> {escape(data.ruc or '—')}<br/>"
                    f"<b>Teléfono WhatsApp:</b> {escape(data.phone)}<br/>"
                    f"<b>Domicilio / Lugar del evento:</b> {escape(data.address)}<br/>"
                    f"<b>Distrito:</b> {escape(data.district)}",
                    styles.table_cell,
                ),
            ],
        ],
        colWidths=[page_width * 0.5, page_width * 0.5],
    )
    parties_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(parties_table)
    story.append(Spacer(1, 10))

    # --- SECCIÓN I: CONDICIONES PARTICULARES PACTADAS (VARIABLES) ---
    story.append(
        Paragraph(
            "SECCIÓN I — CONDICIONES PARTICULARES DEL SERVICIO PACTADO",
            styles.section,
        )
    )
    story.append(
        Paragraph(
            "Esta sección recoge los términos variables acordados específicamente para la "
            "presente solicitud de servicio. Todo aspecto operativo no modificado expresamente "
            "aquí se rige por las Cláusulas Generales Inamovibles de la Sección II.",
            styles.note,
        )
    )

    duration_text = f"{data.duration_minutes} minutos" if data.duration_minutes else "Según paquete"
    schedule_table = Table(
        [
            [
                Paragraph("I.1 Cronograma y locación del evento", styles.table_header),
                "",
            ],
            [
                Paragraph(
                    f"<b>Fecha del evento:</b> {data.event_date:%d/%m/%Y}",
                    styles.table_cell,
                ),
                Paragraph(
                    f"<b>Horario (Lima):</b> {data.start_time:%H:%M} a {data.end_time:%H:%M} "
                    f"({escape(duration_text)})",
                    styles.table_cell,
                ),
            ],
            [
                Paragraph(f"<b>Dirección exacta:</b> {escape(data.address)}", styles.table_cell),
                Paragraph(f"<b>Distrito:</b> {escape(data.district)}", styles.table_cell),
            ],
        ],
        colWidths=[page_width * 0.55, page_width * 0.45],
    )
    schedule_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (1, 0), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(schedule_table)
    story.append(Spacer(1, 8))

    # I.2 Alcance del servicio y extras
    category_desc = service_category_label(data.service_category)
    service_rows: list[list[Any]] = [
        [Paragraph("I.2 Alcance del servicio contratado", styles.table_header), ""],
        [
            Paragraph("Categoría de servicio", styles.table_cell_bold),
            Paragraph(escape(category_desc), styles.table_cell),
        ],
        [
            Paragraph("Paquete principal", styles.table_cell_bold),
            Paragraph(escape(data.package_name), styles.table_cell),
        ],
        [
            Paragraph("Temática", styles.table_cell_bold),
            Paragraph(escape(data.theme_name or "Sin temática"), styles.table_cell),
        ],
    ]
    if data.package_description:
        service_rows.append(
            [
                Paragraph("Descripción del paquete", styles.table_cell_bold),
                Paragraph(_html_lines(data.package_description), styles.table_cell),
            ]
        )
    extras_html = (
        "<br/>".join(f"- {escape(item)}" for item in data.extras)
        if data.extras
        else "Sin extras adicionales contratados"
    )
    service_rows.append(
        [
            Paragraph("Extras contratados", styles.table_cell_bold),
            Paragraph(extras_html, styles.table_cell),
        ]
    )
    service_table = Table(service_rows, colWidths=[page_width * 0.30, page_width * 0.70])
    service_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (1, 0), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(service_table)
    story.append(Spacer(1, 8))

    # I.3 Liquidación económica (conservando las cadenas literales verificadas por pruebas)
    mobility_note = (
        "Exonerada (el cliente proporciona transporte ida y vuelta)"
        if data.client_provides_mobility and data.mobility == 0
        else "Traslado ida y vuelta desde base operativa"
    )
    money_rows = [
        [Paragraph("I.3 Liquidación económica y forma de pago", styles.table_header), ""],
        [
            Paragraph("Subtotal de servicios:", styles.table_cell),
            Paragraph(f"S/ {data.services:.2f}", styles.table_cell_right),
        ],
        [
            Paragraph(f"Movilidad: ({escape(mobility_note)})", styles.table_cell),
            Paragraph(f"S/ {data.mobility:.2f}", styles.table_cell_right),
        ],
        [
            Paragraph("Total:", styles.table_cell_bold),
            Paragraph(f"S/ {data.total:.2f}", styles.table_cell_right_bold),
        ],
        [
            Paragraph("Adelanto cobrado:", styles.table_cell),
            Paragraph(f"S/ {data.advance:.2f}", styles.table_cell_right),
        ],
        [
            Paragraph("Saldo de servicios:", styles.table_cell),
            Paragraph(f"S/ {data.pending_services:.2f}", styles.table_cell_right),
        ],
        [
            Paragraph("Movilidad pendiente:", styles.table_cell),
            Paragraph(f"S/ {data.pending_mobility:.2f}", styles.table_cell_right),
        ],
        [
            Paragraph("Saldo total pendiente:", styles.table_cell_bold),
            Paragraph(f"S/ {data.pending_balance:.2f}", styles.table_cell_right_bold),
        ],
        [
            Paragraph(
                f"Resumen pactado — Total: S/ {data.total:.2f} · "
                f"Adelanto cobrado: S/ {data.advance:.2f} · "
                f"Saldo de servicios: S/ {data.pending_services:.2f} · "
                f"Movilidad pendiente: S/ {data.pending_mobility:.2f} · "
                f"Saldo total pendiente: S/ {data.pending_balance:.2f}",
                styles.note,
            ),
            "",
        ],
    ]
    money_table = Table(money_rows, colWidths=[page_width * 0.72, page_width * 0.28])
    money_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("SPAN", (0, 8), (1, 8)),
                ("BACKGROUND", (0, 0), (1, 0), surface),
                ("BACKGROUND", (0, 7), (1, 7), accent_soft),
                ("BACKGROUND", (0, 8), (1, 8), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(money_table)
    story.append(Spacer(1, 8))

    # I.4 Observaciones especiales del cliente (texto literal, PC-10)
    obs_text = _html_lines(data.observations) if data.observations else "Sin observaciones"
    obs_table = Table(
        [
            [Paragraph("I.4 OBSERVACIONES ESPECIALES DEL CLIENTE", styles.table_header)],
            [Paragraph(obs_text, styles.table_cell)],
        ],
        colWidths=[page_width],
    )
    obs_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("LINEBELOW", (0, 0), (0, 0), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(obs_table)
    story.append(Spacer(1, 8))

    # I.5 Acuerdos particulares opcionales
    custom_text = (
        _html_lines(contract.custom_clauses)
        if contract.custom_clauses
        else (
            "Sin acuerdos particulares adicionales. Rigen íntegramente las Condiciones "
            "Particulares precedentes y las Cláusulas Generales Inamovibles de la Sección II."
        )
    )
    custom_table = Table(
        [
            [Paragraph("I.5 ACUERDOS Y CLÁUSULAS PARTICULARES", styles.table_header)],
            [Paragraph(custom_text, styles.table_cell)],
        ],
        colWidths=[page_width],
    )
    custom_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("LINEBELOW", (0, 0), (0, 0), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(custom_table)
    story.append(Spacer(1, 10))

    # --- SECCIÓN II: CLÁUSULAS GENERALES INAMOVIBLES ---
    story.append(
        Paragraph(
            "SECCIÓN II — CLÁUSULAS GENERALES INAMOVIBLES "
            f"(VERSIÓN {escape(promoter.clauses_version)})",
            styles.section,
        )
    )
    story.append(
        Paragraph(
            "Las siguientes cláusulas constituyen el marco jurídico estándar e inamovible de "
            "contratación para servicios de entretenimiento y eventos de EL LOCADOR.",
            styles.note,
        )
    )

    for clause in build_immutable_clauses(promoter, data):
        heading = Paragraph(
            f"{escape(clause.ordinal)}: {escape(clause.title)}", styles.clause_title
        )
        first_body = Paragraph(escape(clause.paragraphs[0]), styles.body)
        story.append(KeepTogether([heading, first_body]))
        for extra_paragraph in clause.paragraphs[1:]:
            story.append(Paragraph(escape(extra_paragraph), styles.body))

    story.append(Spacer(1, 8))

    # --- SECCIÓN III: CONFORMIDAD Y FIRMAS ---
    story.append(
        KeepTogether(
            [
                Paragraph("SECCIÓN III — ACEPTACIÓN, CONFORMIDAD Y FIRMAS", styles.section),
                Paragraph(
                    f"Leído íntegramente el presente documento y plenamente informadas de sus "
                    f"alcances legales y condiciones económicas, las partes manifiestan su "
                    f"conformidad en {escape(promoter.city)}, Perú, el {issued_date}.",
                    styles.body,
                ),
            ]
        )
    )

    if contract.status is ContractStatus.SIGNED and contract.signed_at is not None:
        client_sign_state = (
            f"Firmado electrónicamente el {contract.signed_at:%d/%m/%Y %H:%M} UTC.<br/>"
            "Ver hoja final: Constancia de Firma Electrónica y sello PAdES."
        )
    else:
        client_sign_state = (
            "Documento emitido; pendiente de firma electrónica del cliente.<br/>"
            "La aceptación con OTP y firma manuscrita anexará la Constancia PAdES."
        )

    signatures = Table(
        [
            [
                Paragraph("POR EL LOCADOR", styles.table_header),
                Paragraph("POR EL COMITENTE", styles.table_header),
            ],
            [
                Paragraph(
                    f"<b>{escape(promoter.legal_name)}</b><br/>"
                    f"Nombre comercial: {escape(promoter.commercial_name)}<br/>"
                    f"RUC: {escape(promoter.ruc)}<br/>"
                    "Representación autorizada para emisión electrónica.",
                    styles.table_cell,
                ),
                Paragraph(
                    f"<b>{escape(data.client_name)}</b><br/>"
                    f"DNI: {escape(data.dni or '—')} | RUC: {escape(data.ruc or '—')}<br/>"
                    f"FIRMA DEL CLIENTE: ____________________<br/>"
                    f"{client_sign_state}",
                    styles.table_cell,
                ),
            ],
        ],
        colWidths=[page_width * 0.5, page_width * 0.5],
    )
    signatures.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), surface),
                ("BOX", (0, 0), (-1, -1), 0.6, border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(KeepTogether([signatures]))

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=46,
        rightMargin=46,
        topMargin=56,
        bottomMargin=50,
        title=f"Contrato N° {contract.contract_number}",
        author=promoter.legal_name,
    )
    numbered_canvas = _make_numbered_canvas(
        contract.contract_number,
        promoter.commercial_name,
        promoter.clauses_version,
    )
    doc.build(story, canvasmaker=numbered_canvas)
    return output.getvalue()


def _banner_right_style(base_style: Any) -> Any:
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle(
        "BannerRight",
        parent=base_style,
        alignment=TA_RIGHT,
    )


class ReportLabContractPdf:
    """Generador portable de contratos PDF en ReportLab."""

    def __init__(self, promoter: PromoterIdentity | None = None) -> None:
        self._promoter = promoter or PromoterIdentity()

    async def render(self, contract: Contract, data: ContractData) -> bytes:
        return await run_in_threadpool(
            partial(_render_contract_bytes, contract, data, self._promoter)
        )
