"""Motor del agente conversacional: un modelo de lenguaje con herramientas guía la cotización.

El modelo conversa y decide qué hacer; los datos y los efectos salen solo de las herramientas
(``list_catalog``, ``create_quote``, ``pay_advance``, ``request_handoff``). Cada herramienta con
efectos abre su propia unidad de trabajo: la cotización y su resumen determinista (US-07) se
confirman juntos, y un error de negocio (spec 08, sección 2.3) revierte solo esa herramienta y
vuelve al modelo como resultado estructurado para que reaccione. Las llamadas al modelo ocurren
fuera de toda transacción.

Un turno es acotado: a lo sumo ``MAX_TOOL_ITERATIONS`` llamadas al modelo y un presupuesto de
tiempo que cabe en el trabajo del worker. Si el modelo falla antes de que el turno haya cambiado
algo, se propaga ``LanguageModelError`` y quien llama usa el motor de menús; si ya hubo
cotización o pago en el turno, no se reinicia nada: se deriva a un encargado.
"""

import asyncio
import json
import time as clock_time
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.dtos.gateway_event_dto import IncomingClientMessage
from app.application.dtos.language_model_dto import (
    LlmMessage,
    LlmReply,
    LlmRole,
    LlmToolCall,
)
from app.application.dtos.quote_dto import ClientInput, CreateQuoteInput, QuoteExtraInput
from app.application.ports.output.bot_unit_of_work_port import BotTransaction, BotUnitOfWork
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.language_model_port import ILanguageModelPort, LanguageModelError
from app.application.use_cases.bot import agent_prompt as prompts
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.agent_session import AgentSession, trim_history
from app.application.use_cases.bot.bot_handoff import link_created_quote, quote_details
from app.application.use_cases.bot.bot_session import BotSession, MenuOption
from app.core.logging import get_logger
from app.domain.entities.quote import QuoteSource, QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityRejectedError,
    InvalidQuoteStateError,
    PaymentUnderReviewError,
    QuoteExpiredError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError, ValidationError
from app.domain.value_objects.outbox import MessageType

MAX_TOOL_ITERATIONS = 5
# El trabajo del worker se cancela a los 30 s; el presupuesto deja margen para el respaldo.
TURN_BUDGET_SECONDS = 20.0
DISTRICTS = ("Lima", "Callao")
ATTACHMENT_PLACEHOLDER = "[El cliente envió un archivo o una imagen sin texto.]"
_MAX_USER_TEXT = 1500
_MIN_ADDRESS_LENGTH = 5
_MAX_ADDRESS_LENGTH = 200
_MIN_NAME_LENGTH = 3
_MAX_NAME_LENGTH = 120
_MAX_OBSERVATIONS_LENGTH = 500
_MAX_EXTRA_QUANTITY = 20


@dataclass(frozen=True)
class AgentHandoff:
    """Hay que pasar la conversación a un encargado: ``reply`` es el aviso al cliente."""

    reason: str
    reply: str


@dataclass(frozen=True)
class AgentTurnResult:
    """``handoff`` es ``None`` si el agente respondió y la conversación sigue con el bot."""

    handoff: AgentHandoff | None = None


class _BadArguments(Exception):
    """Los argumentos de una herramienta no son válidos; el mensaje se devuelve al modelo."""


@dataclass(frozen=True)
class _ToolOutcome:
    result: dict[str, Any]
    changed_state: bool = False
    handoff: AgentHandoff | None = None


class ConversationAgent:
    def __init__(
        self,
        *,
        unit_of_work: BotUnitOfWork,
        model: ILanguageModelPort,
        clock: IClockPort,
        turn_budget_seconds: float = TURN_BUDGET_SECONDS,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._model = model
        self._clock = clock
        self._turn_budget_seconds = turn_budget_seconds

    async def run_turn(
        self, session: AgentSession, message: IncomingClientMessage
    ) -> AgentTurnResult:
        """Responde un mensaje del cliente y actualiza ``session`` (historial, cotización).

        Lanza ``LanguageModelError`` solo si el modelo falló y el turno no cambió nada.
        """

        text = message.content.strip()
        if not text and session.payment_started:
            await self._reply(message, texts.RECEIPT_RECEIVED)
            return AgentTurnResult()
        log = get_logger("bot")
        deadline = clock_time.monotonic() + self._turn_budget_seconds
        system_prompt = prompts.build_system_prompt(texts.today_in_lima(self._clock.utcnow()))
        history = [
            *session.history,
            LlmMessage(LlmRole.USER, (text or ATTACHMENT_PLACEHOLDER)[:_MAX_USER_TEXT]),
        ]
        changed_state = False
        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                reply = await self._complete(system_prompt, history, deadline)
            except LanguageModelError as error:
                if not changed_state:
                    raise
                log.warning(
                    "bot_llm_failed_after_action",
                    conversation_id=message.conversation_id,
                    reason=error.reason,
                )
                return AgentTurnResult(AgentHandoff("llm_after_action", texts.HANDOFF_ERROR))
            if not reply.tool_calls:
                history.append(LlmMessage(LlmRole.ASSISTANT, reply.text))
                await self._reply(message, reply.text)
                session.history = trim_history(history)
                return AgentTurnResult()
            history.append(LlmMessage(LlmRole.ASSISTANT, reply.text, reply.tool_calls))
            for call in reply.tool_calls:
                outcome = await self._run_tool(call, session, message)
                changed_state = changed_state or outcome.changed_state
                if outcome.handoff is not None:
                    return AgentTurnResult(outcome.handoff)
                history.append(
                    LlmMessage(
                        LlmRole.TOOL,
                        json.dumps(outcome.result, ensure_ascii=False),
                        tool_call_id=call.id,
                    )
                )
        log.warning("bot_agent_tool_loop_limit", conversation_id=message.conversation_id)
        return AgentTurnResult(
            AgentHandoff("tool_loop_limit", texts.HANDOFF_NOT_UNDERSTOOD),
        )

    async def _complete(
        self, system_prompt: str, history: list[LlmMessage], deadline: float
    ) -> LlmReply:
        remaining = deadline - clock_time.monotonic()
        if remaining <= 0:
            raise LanguageModelError("budget")
        try:
            async with asyncio.timeout(remaining):
                reply = await self._model.complete(
                    system_prompt=system_prompt,
                    messages=trim_history(history),
                    tools=prompts.TOOLS,
                )
        except TimeoutError as error:
            raise LanguageModelError("timeout") from error
        if not reply.tool_calls and not reply.text.strip():
            raise LanguageModelError("bad_response")
        return reply

    # --- Herramientas ---------------------------------------------------------------------

    async def _run_tool(
        self, call: LlmToolCall, session: AgentSession, message: IncomingClientMessage
    ) -> _ToolOutcome:
        log = get_logger("bot")
        try:
            arguments = _parse_arguments(call.arguments)
            outcome = await self._dispatch(call.name, arguments, session, message)
        except _BadArguments as error:
            outcome = _ToolOutcome(
                {"ok": False, "error": "invalid_arguments", "message": str(error)}
            )
        log.info(
            "bot_agent_tool",
            conversation_id=message.conversation_id,
            tool=call.name,
            ok=outcome.result.get("ok", False),
        )
        return outcome

    async def _dispatch(
        self,
        name: str,
        arguments: dict[str, Any],
        session: AgentSession,
        message: IncomingClientMessage,
    ) -> _ToolOutcome:
        if name == prompts.LIST_CATALOG:
            return await self._list_catalog()
        if name == prompts.CREATE_QUOTE:
            return await self._create_quote(arguments, session, message)
        if name == prompts.PAY_ADVANCE:
            return await self._pay_advance(session, message)
        if name == prompts.REQUEST_HANDOFF:
            return _request_handoff(arguments)
        return _ToolOutcome({"ok": False, "error": "unknown_tool"})

    async def _list_catalog(self) -> _ToolOutcome:
        async with self._unit_of_work() as tx:
            packages = await tx.catalog.list_packages()
            extras = await tx.catalog.list_extras()
        return _ToolOutcome(
            {
                "ok": True,
                "currency": "PEN",
                "packages": [
                    {
                        "id": str(package.id),
                        "name": package.name,
                        "category": texts.CATEGORY_LABELS.get(
                            package.service_category.value, package.service_category.value
                        ),
                        "base_price": texts.money(package.base_price),
                        "duration_minutes": package.duration_minutes,
                        "description": package.description,
                        "compatible_themes": [
                            {"id": str(theme.id), "name": theme.name}
                            for theme in package.compatible_themes
                            if theme.is_active
                        ],
                    }
                    for package in packages
                    if package.is_active
                ],
                "extras": [
                    {
                        "id": str(extra.id),
                        "name": extra.name,
                        "price": texts.money(extra.sale_price),
                        "description": extra.description,
                    }
                    for extra in extras
                    if extra.is_active
                ],
            }
        )

    async def _create_quote(
        self, arguments: dict[str, Any], session: AgentSession, message: IncomingClientMessage
    ) -> _ToolOutcome:
        today = texts.today_in_lima(self._clock.utcnow())
        try:
            data = _parse_quote_arguments(arguments, today)
            async with self._unit_of_work() as tx:
                summary_session = await self._check_catalog(tx, data)
                quote = await tx.create_quote.execute(
                    CreateQuoteInput(
                        package_id=data.package_id,
                        event_date=data.event_date,
                        event_time=data.event_time,
                        location_address=data.address,
                        location_district=data.district,
                        client=ClientInput(
                            phone=message.sender_phone.value, full_name=data.full_name
                        ),
                        theme_id=data.theme_id,
                        extras=data.extras,
                        client_provides_mobility=data.provides_mobility,
                        observations=data.observations,
                        source=QuoteSource.WHATSAPP,
                    )
                )
                await link_created_quote(tx, message.conversation_id, quote, self._clock.utcnow())
                await _enqueue(tx, message, texts.quote_summary(summary_session, quote))
        except AvailabilityRejectedError as error:
            return _availability_outcome(error)
        except _BadArguments as error:
            return _ToolOutcome({"ok": False, "error": "validation", "message": str(error)})
        except ValidationError as error:
            return _ToolOutcome({"ok": False, "error": "validation", "message": str(error)})
        session.quote_id = str(quote.quote_id)
        session.quote_details = quote_details(summary_session)
        session.payment_started = False
        return _ToolOutcome(
            {
                "ok": True,
                "quote_id": str(quote.quote_id),
                "services_subtotal": texts.money(quote.services_subtotal),
                "mobility_amount": texts.money(quote.final_mobility_amount),
                "total": texts.money(quote.total_amount),
                "advance": texts.money(quote.advance_amount),
                "expires_at": texts.format_moment(quote.expires_at),
                "summary_sent_to_client": True,
            },
            changed_state=True,
        )

    async def _check_catalog(self, tx: BotTransaction, data: "_QuoteData") -> BotSession:
        """Verifica paquete, temática y extras contra el catálogo y arma los datos del resumen."""

        package = await tx.catalog.get_package(data.package_id)
        if package is None or not package.is_active:
            raise _BadArguments("El paquete no existe o no está disponible.")
        themes = {theme.id: theme for theme in package.compatible_themes if theme.is_active}
        theme_name: str | None = None
        if data.theme_id is not None:
            theme = themes.get(data.theme_id)
            if theme is None:
                raise _BadArguments("La temática no es compatible con el paquete elegido.")
            theme_name = theme.name
        elif themes:
            raise _BadArguments("Falta elegir una temática compatible con el paquete.")
        extras: list[MenuOption] = []
        if data.extras:
            available = {extra.id: extra for extra in await tx.catalog.list_extras()}
            for chosen in data.extras:
                extra = available.get(chosen.extra_id)
                if extra is None or not extra.is_active:
                    raise _BadArguments("Uno de los extras no existe o no está disponible.")
                title = extra.name if chosen.quantity == 1 else f"{extra.name} x{chosen.quantity}"
                extras.append(MenuOption(str(extra.id), title))
        return BotSession(
            package_id=str(package.id),
            package_name=package.name,
            theme_id=str(data.theme_id) if data.theme_id else None,
            theme_name=theme_name,
            extras=extras,
            event_date=data.event_date.isoformat(),
            event_time=data.event_time.strftime("%H:%M"),
            district=data.district,
            address=data.address,
            full_name=data.full_name,
            provides_mobility=data.provides_mobility,
            observations=data.observations,
        )

    async def _pay_advance(
        self, session: AgentSession, message: IncomingClientMessage
    ) -> _ToolOutcome:
        if session.quote_id is None:
            return _ToolOutcome({"ok": False, "error": "no_quote"})
        if session.payment_started:
            return _ToolOutcome({"ok": True, "status": "PAYMENT_STARTED", "already_started": True})
        try:
            async with self._unit_of_work() as tx:
                result = await tx.pay_advance.execute(UUID(session.quote_id))
                if result.status is not QuoteStatus.PAYMENT_STARTED:
                    raise InvalidQuoteStateError("El pago no quedó iniciado.")
                await _enqueue(tx, message, texts.payment_instructions(result))
        except QuoteExpiredError:
            return _ToolOutcome({"ok": False, "error": "quote_expired"})
        except PaymentUnderReviewError:
            return _ToolOutcome({"ok": False, "error": "payment_under_review"})
        except AvailabilityRejectedError as error:
            # Cupo ocupado o aprobación manual al revalidar: la transacción se revirtió, no se
            # encoló nada y el agente puede ofrecer las alternativas.
            return _availability_outcome(error)
        except (InvalidQuoteStateError, ResourceNotFoundError):
            # ``QuoteNotFoundError`` es un ``ResourceNotFoundError``; también cubre el paquete
            # que ya no está disponible.
            return _ToolOutcome({"ok": False, "error": "quote_unavailable"})
        session.payment_started = True
        return _ToolOutcome(
            {
                "ok": True,
                "status": "PAYMENT_STARTED",
                "advance": texts.money(result.advance_amount),
                "payment_deadline": texts.format_moment(result.payment_deadline),
                "instructions_sent_to_client": True,
            },
            changed_state=True,
        )

    # --- Envío ------------------------------------------------------------------------------

    async def _reply(self, message: IncomingClientMessage, text: str) -> None:
        async with self._unit_of_work() as tx:
            await _enqueue(tx, message, text)


# --- Argumentos ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _QuoteData:
    package_id: UUID
    theme_id: UUID | None
    extras: tuple[QuoteExtraInput, ...]
    event_date: date
    event_time: time
    district: str
    address: str
    full_name: str
    provides_mobility: bool
    observations: str | None


async def _enqueue(tx: BotTransaction, message: IncomingClientMessage, text: str) -> None:
    await tx.enqueue_message.execute(
        recipient=message.sender_phone,
        message_type=MessageType.TEXT,
        payload={"body": text},
    )


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError as error:
        raise _BadArguments("Los argumentos no son un JSON válido.") from error
    if not isinstance(parsed, dict):
        raise _BadArguments("Los argumentos deben ser un objeto JSON.")
    return parsed


def _availability_outcome(error: AvailabilityRejectedError) -> _ToolOutcome:
    return _ToolOutcome(
        {
            "ok": False,
            "error": "availability_rejected",
            "message": str(error),
            "alternatives": [
                {
                    "date": alternative.event_date.isoformat(),
                    "time": f"{alternative.event_time:%H:%M}",
                }
                for alternative in error.alternatives
            ],
            "handoff_available": error.handoff_available,
        }
    )


def _request_handoff(arguments: dict[str, Any]) -> _ToolOutcome:
    reason = arguments.get("reason")
    if reason == "BOT_NOT_UNDERSTOOD":
        return _ToolOutcome(
            {"ok": True}, handoff=AgentHandoff("bot_not_understood", texts.HANDOFF_NOT_UNDERSTOOD)
        )
    return _ToolOutcome(
        {"ok": True}, handoff=AgentHandoff("client_request", texts.HANDOFF_REQUESTED)
    )


def _parse_quote_arguments(arguments: dict[str, Any], today: date) -> _QuoteData:
    try:
        package_id = UUID(str(arguments["package_id"]))
        theme = arguments.get("theme_id")
        theme_id = UUID(str(theme)) if theme else None
        extras = tuple(
            QuoteExtraInput(UUID(str(item["extra_id"])), int(item.get("quantity", 1)))
            for item in arguments.get("extras") or []
        )
        event_date = date.fromisoformat(str(arguments["event_date"]))
        event_time = time.fromisoformat(str(arguments["event_time"]))
        district = str(arguments["district"]).strip().title()
        address = " ".join(str(arguments["address"]).split())
        full_name = " ".join(str(arguments["full_name"]).split())
        provides_mobility = arguments["client_provides_mobility"]
        observations = " ".join(str(arguments.get("observations") or "").split()) or None
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise _BadArguments(
            "Faltan datos o tienen un formato inválido (fecha AAAA-MM-DD, hora HH:MM, ids)."
        ) from error
    if not isinstance(provides_mobility, bool):
        raise _BadArguments("client_provides_mobility debe ser verdadero o falso.")
    if event_date <= today:
        raise _BadArguments("La fecha del evento debe ser posterior a hoy.")
    if district not in DISTRICTS:
        raise _BadArguments("El distrito debe ser Lima o Callao.")
    if len(address) < _MIN_ADDRESS_LENGTH:
        raise _BadArguments("La dirección es muy corta.")
    if len(full_name) < _MIN_NAME_LENGTH or not any(char.isalpha() for char in full_name):
        raise _BadArguments("Se necesita el nombre completo del cliente.")
    if any(extra.quantity > _MAX_EXTRA_QUANTITY for extra in extras):
        raise _BadArguments("La cantidad de un extra es demasiado alta.")
    return _QuoteData(
        package_id=package_id,
        theme_id=theme_id,
        extras=extras,
        event_date=event_date,
        event_time=event_time.replace(second=0, microsecond=0, tzinfo=None),
        district=district,
        address=address[:_MAX_ADDRESS_LENGTH],
        full_name=full_name[:_MAX_NAME_LENGTH],
        provides_mobility=provides_mobility,
        observations=observations[:_MAX_OBSERVATIONS_LENGTH] if observations else None,
    )


__all__ = [
    "MAX_TOOL_ITERATIONS",
    "AgentHandoff",
    "AgentTurnResult",
    "ConversationAgent",
    "Decimal",
]
