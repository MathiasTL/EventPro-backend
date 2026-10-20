"""Textos que el bot envía por WhatsApp, en español neutro (tú), y su armado.

Solo texto plano con menús numerados: el gateway aplana las listas interactivas, así que un
menú escrito funciona igual en WhatsApp y en la bandeja de Chatwoot.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.application.dtos.quote_dto import CreatedQuoteDTO, PayAdvanceResultDTO
from app.application.use_cases.bot.bot_session import BotSession, BotStep, MenuOption

LIMA = timezone(timedelta(hours=-5), "America/Lima")

GREETING = (
    "Hola, te damos la bienvenida a EventPro. Soy el asistente virtual y te ayudaré a cotizar "
    'tu evento. En cualquier momento puedes escribir "menú" para empezar de nuevo o '
    '"asesor" para hablar con un encargado.'
)
NOT_UNDERSTOOD = "No entendí tu respuesta."
HANDOFF_REQUESTED = (
    "Con gusto. Un encargado continuará esta conversación en breve; gracias por tu paciencia."
)
HANDOFF_NOT_UNDERSTOOD = (
    "No logro entender tus respuestas, así que te comunico con un encargado que te ayudará "
    "enseguida."
)
HANDOFF_ERROR = "Tuvimos un problema al procesar tu solicitud. Te comunico con un encargado."
HANDOFF_NO_CATALOG = "En este momento no puedo mostrarte el catálogo. Te comunico con un encargado."
QUOTE_EXPIRED = (
    'Tu cotización venció y ya no admite el pago. Escribe "menú" para crear una nueva o '
    '"asesor" para hablar con un encargado.'
)
QUOTE_UNAVAILABLE = (
    'Esta cotización ya no admite el pago. Escribe "menú" para crear una nueva o '
    '"asesor" para hablar con un encargado.'
)
INVALID_DATA = "Algunos datos de tu solicitud no son válidos. Revisemos la fecha de tu evento."
ALREADY_PAID = (
    "Ya iniciaste el pago de tu adelanto. Cuando lo realices, envía aquí la captura del "
    'comprobante y un encargado lo validará. Escribe "menú" para cotizar otro evento o '
    '"asesor" para hablar con un encargado.'
)
RECEIPT_RECEIVED = (
    "Recibimos tu mensaje. Un encargado validará tu comprobante y te confirmará la reserva."
)
OTHER_DATE = "Elegir otra fecha u horario"
TALK_TO_A_PERSON = "Hablar con un encargado"
PAY_ADVANCE = "Pagar adelanto"

CATEGORY_LABELS = {
    "SHOW": "Shows",
    "DJ": "DJ",
    "DECORATION": "Decoración",
    "TENTS": "Carpas",
}

_QUESTIONS: dict[BotStep, str] = {
    BotStep.CATEGORY: "¿Qué tipo de servicio te interesa?",
    BotStep.PACKAGE: "Estos son nuestros paquetes. ¿Cuál prefieres?",
    BotStep.THEME: "¿Qué temática prefieres?",
    BotStep.EXTRAS: (
        "¿Quieres agregar extras? Responde con los números separados por comas (por ejemplo "
        "1,3) o con 0 para continuar sin extras."
    ),
    BotStep.DATE: (
        "¿Para qué fecha es tu evento? Escríbela con el formato DD/MM/AAAA (por ejemplo "
        "15/11/2026)."
    ),
    BotStep.TIME: (
        "¿A qué hora debe comenzar el servicio? Escríbela con el formato HH:MM (por ejemplo 16:30)."
    ),
    BotStep.DISTRICT: "¿En qué distrito será el evento?",
    BotStep.ADDRESS: "Escribe la dirección exacta del evento (calle, número y una referencia).",
    BotStep.NAME: "¿Cuál es tu nombre completo?",
    BotStep.MOBILITY: "¿Tú proveerás la movilidad para trasladar al equipo?",
    BotStep.OBSERVATIONS: (
        '¿Quieres dejar alguna observación para el equipo? Escríbela o responde "no".'
    ),
    BotStep.CONFIRM: (
        '¿Cómo deseas continuar? También puedes escribir "asesor" para hablar con un encargado.'
    ),
    BotStep.ALTERNATIVES: "Esa fecha y ese horario no están disponibles. Estas son las opciones:",
}


def money(amount: Decimal) -> str:
    return f"S/ {amount:,.2f}"


def format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def format_moment(value: datetime) -> str:
    """Fecha y hora de Lima de un instante con zona."""

    return value.astimezone(LIMA).strftime("%d/%m/%Y %H:%M")


def today_in_lima(now: datetime) -> date:
    return now.astimezone(LIMA).date()


def menu(options: list[MenuOption]) -> str:
    lines = [
        f"{number}. {option.title}{f' - {option.detail}' if option.detail else ''}"
        for number, option in enumerate(options, start=1)
    ]
    return "\n".join(lines)


def prompt(session: BotSession) -> str:
    """Pregunta del paso actual con sus opciones numeradas, tal como se guardaron."""

    parts = [_QUESTIONS.get(session.step, "")]
    if session.step is BotStep.PACKAGE and session.category:
        label = CATEGORY_LABELS.get(session.category, session.category)
        parts[0] = f"Estos son nuestros paquetes de {label}. ¿Cuál prefieres?"
    if session.options:
        parts.append(menu(session.options))
    if session.step is BotStep.EXTRAS:
        parts.append("0. Continuar sin extras")
    return "\n\n".join(part for part in parts if part)


def quote_summary(session: BotSession, quote: CreatedQuoteDTO) -> str:
    """Resumen de la cotización (US-07): desglose, adelanto, plazo y aviso de reserva."""

    event_date = date.fromisoformat(session.event_date or "")
    event_time = time.fromisoformat(session.event_time or "")
    lines = [
        "Este es el resumen de tu cotización:",
        "",
        f"Paquete: {session.package_name}",
    ]
    if session.theme_name:
        lines.append(f"Temática: {session.theme_name}")
    if session.extras:
        lines.append("Extras: " + ", ".join(extra.title for extra in session.extras))
    lines += [
        f"Fecha: {format_date(event_date)} a las {event_time.strftime('%H:%M')}",
        f"Lugar: {session.address}, {session.district}",
        "",
        f"Servicios: {money(quote.services_subtotal)}",
    ]
    if session.provides_mobility:
        lines.append("Movilidad: a tu cargo")
    else:
        lines.append(f"Movilidad: {money(quote.final_mobility_amount)}")
    lines += [
        f"Total: {money(quote.total_amount)}",
        "",
        f"Adelanto para reservar: {money(quote.advance_amount)}",
        f"Saldo de servicios, el día del evento: {money(quote.breakdown.services_balance_due)}",
        f"Saldo de movilidad, el día del evento: {money(quote.breakdown.mobility_due)}",
        "",
        f"Esta cotización es válida hasta el {format_moment(quote.expires_at)} (24 horas).",
        "Importante: tu fecha solo queda reservada cuando validemos el pago del adelanto.",
    ]
    return "\n".join(lines)


def payment_instructions(result: PayAdvanceResultDTO) -> str:
    """Datos para pagar el adelanto; solo se envían después de ``PayAdvance``."""

    info = result.payment_instructions
    return "\n".join(
        [
            f"Para reservar tu fecha, paga el adelanto de {money(result.advance_amount)} "
            f"hasta el {format_moment(result.payment_deadline)}.",
            "",
            f"Yape: {info.yape.phone} a nombre de {info.yape.holder}",
            f"Plin: {info.plin.phone} a nombre de {info.plin.holder}",
            f"Transferencia {info.bank_transfer.bank}: cuenta {info.bank_transfer.account}, "
            f"CCI {info.bank_transfer.cci}, a nombre de {info.bank_transfer.holder}",
            "",
            "Después de pagar, envía aquí la captura del comprobante. Un encargado lo validará "
            "y te confirmará la reserva.",
        ]
    )
