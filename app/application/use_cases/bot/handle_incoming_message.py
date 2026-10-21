"""Caso de uso HandleIncomingMessage: el bot de WhatsApp que guía la cotización (E1).

Responde solo cuando la conversación está en manos del bot (``pending``, RF-01). El motor
principal es el agente conversacional con OpenAI (``ConversationAgent``); si no está configurado,
o si OpenAI falla o agota el tiempo (``bot_llm_fallback``), responde el motor de menús: el cliente
avanza por pasos lineales con menús numerados (US-01 a US-03, US-05); al terminar se crea la
cotización y se encola su resumen en la misma transacción (US-07, spec 08 sección 2.4). Ante
un error de negocio reacciona según la spec 08 sección 2.3, y deriva a un encargado cuando el
cliente lo pide, no se le entiende dos veces seguidas o algo falla (US-27).

No confirma por su cuenta: cada turno abre una unidad de trabajo que confirma al salir sin
error. Los logs llevan identificadores y pasos, nunca el texto del cliente, nombres ni teléfonos.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, time
from typing import Any
from uuid import UUID

from app.application.dtos.gateway_event_dto import GatewayEventOutcome, IncomingClientMessage
from app.application.dtos.messaging_dto import ConversationStatus
from app.application.dtos.quote_dto import ClientInput, CreateQuoteInput, QuoteExtraInput
from app.application.ports.output.bot_unit_of_work_port import BotTransaction, BotUnitOfWork
from app.application.ports.output.cache_lock_port import ICacheLockPort
from app.application.ports.output.clock_port import IClockPort
from app.application.ports.output.conversation_session_port import IConversationSessionPort
from app.application.ports.output.language_model_port import LanguageModelError
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.use_cases.bot import bot_messages as texts
from app.application.use_cases.bot.agent_engine import ConversationAgent
from app.application.use_cases.bot.agent_session import AgentSession
from app.application.use_cases.bot.bot_handoff import (
    BotHandoffRecorder,
    agent_summary,
    link_created_quote,
    menu_summary,
    stored_session_summary,
)
from app.application.use_cases.bot.bot_input import (
    NO_WORDS,
    SKIP_WORDS,
    YES_WORDS,
    asks_for_a_person,
    asks_to_restart,
    normalize,
    parse_date,
    parse_time,
    pick_many,
    pick_option,
)
from app.application.use_cases.bot.bot_session import BotSession, BotStep, MenuOption
from app.core.logging import get_logger
from app.domain.entities.quote import QuoteSource, QuoteStatus
from app.domain.exceptions.quote_exceptions import (
    AvailabilityRejectedError,
    InvalidQuoteStateError,
    QuoteExpiredError,
    QuoteNotFoundError,
)
from app.domain.exceptions.resource_exceptions import ValidationError
from app.domain.value_objects.outbox import MessageType

# Respuestas seguidas sin entender antes de pasar la conversación a un encargado.
MAX_MISSES = 2
# Un turno es corto: el cerrojo evita que dos mensajes seguidos del mismo cliente se pisen.
LOCK_TTL_SECONDS = 30
LOCK_WAIT_SECONDS = 10.0
DISTRICTS = ("Lima", "Callao")
_MIN_ADDRESS_LENGTH = 5
_MIN_NAME_LENGTH = 3
_MAX_ADDRESS_LENGTH = 200
_MAX_NAME_LENGTH = 120
_MAX_OBSERVATIONS_LENGTH = 500
_PAY_WORDS = frozenset({"pagar", "pagar adelanto"})


class _NotUnderstood(Exception):
    """La respuesta no corresponde al paso; ``hint`` explica qué se esperaba."""

    def __init__(self, hint: str = "") -> None:
        super().__init__(hint)
        self.hint = hint


class _NoCatalog(Exception):
    """El catálogo no tiene nada que ofrecer: se deriva a un encargado."""


class _HandoffChosen(Exception):
    """El cliente eligió hablar con un encargado en un menú."""


@dataclass
class _Turn:
    tx: BotTransaction
    session: BotSession
    message: IncomingClientMessage
    text: str
    normalized: str


_Action = Callable[[_Turn], Awaitable[str]]


class HandleIncomingMessage:
    def __init__(
        self,
        *,
        unit_of_work: BotUnitOfWork,
        sessions: IConversationSessionPort,
        messaging: IMessagingPort,
        clock: IClockPort,
        lock: ICacheLockPort | None = None,
        agent: ConversationAgent | None = None,
        handoffs: BotHandoffRecorder | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._sessions = sessions
        self._messaging = messaging
        self._clock = clock
        self._lock = lock
        self._agent = agent
        self._handoffs = handoffs

    async def execute(self, message: IncomingClientMessage) -> GatewayEventOutcome:
        """``APPLIED`` si el bot respondió; ``IGNORED`` si no le tocaba o ya lo había hecho."""

        log = get_logger("bot")
        if message.is_private or message.conversation_status is not ConversationStatus.BOT:
            log.info(
                "bot_message_skipped",
                conversation_id=message.conversation_id,
                reason="private" if message.is_private else "not_pending",
            )
            return GatewayEventOutcome.IGNORED
        if self._lock is None:
            return await self._handle(message)
        key = f"eventpro:bot:lock:{message.conversation_id}"
        if not await self._lock.acquire(
            key, ttl_seconds=LOCK_TTL_SECONDS, wait_seconds=LOCK_WAIT_SECONDS
        ):
            log.warning("bot_conversation_busy", conversation_id=message.conversation_id)
            return GatewayEventOutcome.IGNORED
        try:
            return await self._handle(message)
        finally:
            await self._lock.release(key)

    async def _handle(self, message: IncomingClientMessage) -> GatewayEventOutcome:
        stored = await self._sessions.get(message.conversation_id)
        if stored is not None and stored.get("last_message_id") == message.external_message_id:
            get_logger("bot").info("bot_message_duplicate", conversation_id=message.conversation_id)
            return GatewayEventOutcome.IGNORED
        text = message.content.strip()
        normalized = normalize(text)
        if asks_for_a_person(normalized):
            await self._handoff(
                message,
                texts.HANDOFF_REQUESTED,
                reason="requested",
                summary=stored_session_summary(stored),
            )
            return GatewayEventOutcome.APPLIED
        session = BotSession.from_dict(stored) if stored is not None else None
        # Una conversación que cayó al motor de menús sigue en él hasta que termine o el
        # cliente escriba "menú"; ahí vuelve al agente.
        if self._agent is not None and (session is None or asks_to_restart(normalized)):
            agent_session = AgentSession()
            if session is None and stored is not None:
                agent_session = AgentSession.from_dict(stored) or agent_session
            outcome = await self._run_agent(message, agent_session)
            if outcome is not None:
                return outcome
            # Respaldo: el motor de menús empieza desde el principio para esta conversación.
            return await self._run(message, BotSession(), self._begin, text, normalized)
        if session is None or asks_to_restart(normalized):
            return await self._run(message, BotSession(), self._begin, text, normalized)
        return await self._run(message, session, self._advance, text, normalized)

    async def _run_agent(
        self, message: IncomingClientMessage, session: AgentSession
    ) -> GatewayEventOutcome | None:
        """Turno del agente; ``None`` si el modelo falló sin cambiar nada y toca el respaldo."""

        log = get_logger("bot")
        agent = self._agent
        if agent is None:
            return None
        try:
            result = await agent.run_turn(session, message)
        except LanguageModelError as error:
            log.warning(
                "bot_llm_fallback", conversation_id=message.conversation_id, reason=error.reason
            )
            return None
        except Exception as error:
            log.error(
                "bot_turn_failed",
                conversation_id=message.conversation_id,
                step="agent",
                error_type=type(error).__name__,
            )
            await self._handoff(
                message, texts.HANDOFF_ERROR, reason="error", summary=agent_summary(session)
            )
            return GatewayEventOutcome.APPLIED
        if result.handoff is not None:
            await self._handoff(
                message,
                result.handoff.reply,
                reason=result.handoff.reason,
                summary=agent_summary(session),
            )
            return GatewayEventOutcome.APPLIED
        session.last_message_id = message.external_message_id
        await self._sessions.save(message.conversation_id, session.to_dict())
        return GatewayEventOutcome.APPLIED

    # --- Un turno: ejecuta, responde y guarda --------------------------------------------

    async def _run(
        self,
        message: IncomingClientMessage,
        session: BotSession,
        action: _Action,
        text: str,
        normalized: str,
    ) -> GatewayEventOutcome:
        snapshot = session.to_dict()
        log = get_logger("bot")
        try:
            async with self._unit_of_work() as tx:
                reply = await action(_Turn(tx, session, message, text, normalized))
                await self._send(tx, message, reply)
        except _NotUnderstood as miss:
            return await self._on_miss(message, snapshot, miss.hint)
        except _HandoffChosen:
            await self._handoff(
                message,
                texts.HANDOFF_REQUESTED,
                reason="chosen",
                summary=menu_summary(_restore(snapshot)),
            )
            return GatewayEventOutcome.APPLIED
        except _NoCatalog:
            await self._handoff(
                message,
                texts.HANDOFF_NO_CATALOG,
                reason="no_catalog",
                summary=menu_summary(_restore(snapshot)),
            )
            return GatewayEventOutcome.APPLIED
        except AvailabilityRejectedError as error:
            restored = _restore(snapshot)
            reply = self._offer_alternatives(restored, error)
        except QuoteExpiredError:
            restored, reply = _restore(snapshot), texts.QUOTE_EXPIRED
        except (InvalidQuoteStateError, QuoteNotFoundError):
            restored, reply = _restore(snapshot), texts.QUOTE_UNAVAILABLE
        except ValidationError:
            restored = _restore(snapshot)
            restored.step, restored.options = BotStep.DATE, []
            reply = f"{texts.INVALID_DATA}\n\n{texts.prompt(restored)}"
        except Exception as error:
            log.error(
                "bot_turn_failed",
                conversation_id=message.conversation_id,
                step=snapshot["step"],
                error_type=type(error).__name__,
            )
            await self._handoff(
                message,
                texts.HANDOFF_ERROR,
                reason="error",
                summary=menu_summary(_restore(snapshot)),
            )
            return GatewayEventOutcome.APPLIED
        else:
            session.misses = 0
            await self._save(message, session)
            return GatewayEventOutcome.APPLIED
        # Reacción a un error de negocio: el turno se revirtió, la respuesta va en otro.
        restored.misses = 0
        await self._reply_alone(message, reply)
        await self._save(message, restored)
        return GatewayEventOutcome.APPLIED

    async def _on_miss(
        self, message: IncomingClientMessage, snapshot: dict[str, Any], hint: str
    ) -> GatewayEventOutcome:
        session = _restore(snapshot)
        session.misses += 1
        if session.misses >= MAX_MISSES:
            await self._handoff(
                message,
                texts.HANDOFF_NOT_UNDERSTOOD,
                reason="not_understood",
                summary=menu_summary(session),
            )
            return GatewayEventOutcome.APPLIED
        lead = f"{texts.NOT_UNDERSTOOD} {hint}".strip()
        await self._reply_alone(message, f"{lead}\n\n{texts.prompt(session)}")
        await self._save(message, session)
        return GatewayEventOutcome.APPLIED

    async def _handoff(
        self, message: IncomingClientMessage, reply: str, *, reason: str, summary: str | None
    ) -> None:
        """US-27: avisa al cliente, olvida la sesión y deja la conversación a un encargado.

        Solo si Chatwoot aceptó el cambio se registra la derivación y se avisa a la bandeja
        (spec 09, 6.2); ``summary`` se arma antes porque la sesión se borra aquí.
        """

        log = get_logger("bot")
        log.info("bot_handoff", conversation_id=message.conversation_id, reason=reason)
        try:
            await self._reply_alone(message, reply)
        except Exception as error:
            log.error(
                "bot_handoff_reply_failed",
                conversation_id=message.conversation_id,
                error_type=type(error).__name__,
            )
        await self._sessions.clear(message.conversation_id)
        try:
            await self._messaging.set_conversation_status(
                message.conversation_id, ConversationStatus.HUMAN
            )
        except Exception as error:
            log.error(
                "bot_handoff_status_failed",
                conversation_id=message.conversation_id,
                error_type=type(error).__name__,
            )
            return
        if self._handoffs is not None:
            await self._handoffs.record(
                message.conversation_id, message.sender_phone, reason=reason, summary=summary
            )

    async def _send(self, tx: BotTransaction, message: IncomingClientMessage, text: str) -> None:
        await tx.enqueue_message.execute(
            recipient=message.sender_phone,
            message_type=MessageType.TEXT,
            payload={"body": text},
        )

    async def _reply_alone(self, message: IncomingClientMessage, text: str) -> None:
        async with self._unit_of_work() as tx:
            await self._send(tx, message, text)

    async def _save(self, message: IncomingClientMessage, session: BotSession) -> None:
        session.last_message_id = message.external_message_id
        await self._sessions.save(message.conversation_id, session.to_dict())

    # --- Pasos ----------------------------------------------------------------------------

    async def _begin(self, turn: _Turn) -> str:
        """Saludo y menú de categorías, con las que tienen paquetes activos."""

        packages = await turn.tx.catalog.list_packages()
        present = {package.service_category.value for package in packages}
        categories = [key for key in texts.CATEGORY_LABELS if key in present]
        if not categories:
            raise _NoCatalog
        turn.session.step = BotStep.CATEGORY
        turn.session.options = [MenuOption(key, texts.CATEGORY_LABELS[key]) for key in categories]
        return f"{texts.GREETING}\n\n{texts.prompt(turn.session)}"

    async def _advance(self, turn: _Turn) -> str:
        handlers: dict[BotStep, _Action] = {
            BotStep.CATEGORY: self._on_category,
            BotStep.PACKAGE: self._on_package,
            BotStep.THEME: self._on_theme,
            BotStep.EXTRAS: self._on_extras,
            BotStep.DATE: self._on_date,
            BotStep.TIME: self._on_time,
            BotStep.DISTRICT: self._on_district,
            BotStep.ADDRESS: self._on_address,
            BotStep.NAME: self._on_name,
            BotStep.MOBILITY: self._on_mobility,
            BotStep.OBSERVATIONS: self._on_observations,
            BotStep.CONFIRM: self._on_confirm,
            BotStep.ALTERNATIVES: self._on_alternatives,
            BotStep.PAID: self._on_paid,
        }
        return await handlers[turn.session.step](turn)

    async def _on_category(self, turn: _Turn) -> str:
        option = _require(pick_option(turn.normalized, turn.session.options))
        packages = [
            package
            for package in await turn.tx.catalog.list_packages()
            if package.service_category.value == option.key
        ]
        if not packages:
            raise _NoCatalog
        session = turn.session
        session.category = option.key
        session.options = [
            MenuOption(str(package.id), package.name, texts.money(package.base_price))
            for package in packages
        ]
        session.step = BotStep.PACKAGE
        return texts.prompt(session)

    async def _on_package(self, turn: _Turn) -> str:
        option = _require(pick_option(turn.normalized, turn.session.options))
        package = await turn.tx.catalog.get_package(UUID(option.key))
        if package is None:
            raise _NotUnderstood("Ese paquete ya no está disponible.")
        session = turn.session
        session.package_id, session.package_name = option.key, package.name
        themes = [theme for theme in package.compatible_themes if theme.is_active]
        if not themes:
            return await self._ask_extras(turn)
        session.options = [MenuOption(str(theme.id), theme.name) for theme in themes]
        session.step = BotStep.THEME
        return texts.prompt(session)

    async def _on_theme(self, turn: _Turn) -> str:
        option = _require(pick_option(turn.normalized, turn.session.options))
        turn.session.theme_id, turn.session.theme_name = option.key, option.title
        return await self._ask_extras(turn)

    async def _ask_extras(self, turn: _Turn) -> str:
        extras = await turn.tx.catalog.list_extras()
        session = turn.session
        if not extras:
            session.extras = []
            return self._ask_date(session)
        session.options = [
            MenuOption(str(extra.id), extra.name, texts.money(extra.sale_price)) for extra in extras
        ]
        session.step = BotStep.EXTRAS
        return texts.prompt(session)

    async def _on_extras(self, turn: _Turn) -> str:
        session = turn.session
        if turn.normalized in SKIP_WORDS:
            session.extras = []
        else:
            session.extras = _require(pick_many(turn.normalized, session.options))
        return self._ask_date(session)

    def _ask_date(self, session: BotSession) -> str:
        session.options = []
        session.step = BotStep.DATE
        return texts.prompt(session)

    async def _on_date(self, turn: _Turn) -> str:
        event_date = parse_date(turn.text)
        if event_date is None:
            raise _NotUnderstood("La fecha debe tener el formato DD/MM/AAAA.")
        if event_date <= texts.today_in_lima(self._clock.utcnow()):
            raise _NotUnderstood("La fecha debe ser posterior a hoy.")
        turn.session.event_date = event_date.isoformat()
        turn.session.step = BotStep.TIME
        return texts.prompt(turn.session)

    async def _on_time(self, turn: _Turn) -> str:
        event_time = parse_time(turn.text)
        if event_time is None:
            raise _NotUnderstood("La hora debe tener el formato HH:MM, por ejemplo 16:30.")
        session = turn.session
        session.event_time = event_time.strftime("%H:%M")
        if session.address and session.district and session.full_name:
            # Se cambió solo la fecha (alternativa o corrección): el resto ya está respondido.
            return await self._create_quote(turn)
        session.options = [MenuOption(district.lower(), district) for district in DISTRICTS]
        session.step = BotStep.DISTRICT
        return texts.prompt(session)

    async def _on_district(self, turn: _Turn) -> str:
        option = _require(pick_option(turn.normalized, turn.session.options))
        turn.session.district = option.title
        turn.session.options = []
        turn.session.step = BotStep.ADDRESS
        return texts.prompt(turn.session)

    async def _on_address(self, turn: _Turn) -> str:
        if len(turn.text) < _MIN_ADDRESS_LENGTH:
            raise _NotUnderstood("La dirección es muy corta.")
        turn.session.address = turn.text[:_MAX_ADDRESS_LENGTH]
        turn.session.step = BotStep.NAME
        return texts.prompt(turn.session)

    async def _on_name(self, turn: _Turn) -> str:
        name = " ".join(turn.text.split())
        if len(name) < _MIN_NAME_LENGTH or not any(char.isalpha() for char in name):
            raise _NotUnderstood("Necesito tu nombre completo.")
        session = turn.session
        session.full_name = name[:_MAX_NAME_LENGTH]
        session.options = [
            MenuOption("yes", "Yo proveo la movilidad"),
            MenuOption("no", "Necesito que cotice la movilidad"),
        ]
        session.step = BotStep.MOBILITY
        return texts.prompt(session)

    async def _on_mobility(self, turn: _Turn) -> str:
        option = pick_option(turn.normalized, turn.session.options)
        if option is not None:
            provides = option.key == "yes"
        elif turn.normalized in YES_WORDS:
            provides = True
        elif turn.normalized in NO_WORDS:
            provides = False
        else:
            raise _NotUnderstood
        turn.session.provides_mobility = provides
        turn.session.options = []
        turn.session.step = BotStep.OBSERVATIONS
        return texts.prompt(turn.session)

    async def _on_observations(self, turn: _Turn) -> str:
        if not turn.text:
            raise _NotUnderstood
        skipped = turn.normalized in SKIP_WORDS
        turn.session.observations = None if skipped else turn.text[:_MAX_OBSERVATIONS_LENGTH]
        return await self._create_quote(turn)

    async def _create_quote(self, turn: _Turn) -> str:
        """Crea la cotización; el resumen se encola en esta misma transacción (US-07)."""

        session = turn.session
        quote = await turn.tx.create_quote.execute(
            CreateQuoteInput(
                package_id=UUID(_text(session.package_id)),
                event_date=date.fromisoformat(_text(session.event_date)),
                event_time=time.fromisoformat(_text(session.event_time)),
                location_address=_text(session.address),
                location_district=_text(session.district),
                client=ClientInput(
                    phone=turn.message.sender_phone.value, full_name=_text(session.full_name)
                ),
                theme_id=UUID(session.theme_id) if session.theme_id else None,
                extras=tuple(QuoteExtraInput(UUID(extra.key), 1) for extra in session.extras),
                client_provides_mobility=session.provides_mobility,
                observations=session.observations,
                source=QuoteSource.WHATSAPP,
            )
        )
        await link_created_quote(turn.tx, turn.message.conversation_id, quote, self._clock.utcnow())
        session.quote_id = str(quote.quote_id)
        session.options = [MenuOption("pay", texts.PAY_ADVANCE)]
        session.step = BotStep.CONFIRM
        return f"{texts.quote_summary(session, quote)}\n\n{texts.prompt(session)}"

    async def _on_confirm(self, turn: _Turn) -> str:
        session = turn.session
        option = pick_option(turn.normalized, session.options)
        if option is None and turn.normalized not in _PAY_WORDS:
            raise _NotUnderstood
        result = await turn.tx.pay_advance.execute(UUID(_text(session.quote_id)))
        if result.status is not QuoteStatus.PAYMENT_STARTED:
            raise InvalidQuoteStateError("El pago no quedó iniciado.")
        session.options = []
        session.step = BotStep.PAID
        return texts.payment_instructions(result)

    async def _on_alternatives(self, turn: _Turn) -> str:
        session = turn.session
        option = _require(pick_option(turn.normalized, session.options))
        if option.key == "handoff":
            raise _HandoffChosen
        if option.key == "other":
            return self._ask_date(session)
        moment = option.key.removeprefix("alt:")
        session.event_date, session.event_time = moment.split("T")
        return await self._create_quote(turn)

    async def _on_paid(self, turn: _Turn) -> str:
        return texts.ALREADY_PAID if turn.text else texts.RECEIPT_RECEIVED

    def _offer_alternatives(self, session: BotSession, error: AvailabilityRejectedError) -> str:
        options = [
            MenuOption(
                f"alt:{alternative.event_date.isoformat()}T{alternative.event_time:%H:%M}",
                f"{texts.format_date(alternative.event_date)} a las {alternative.event_time:%H:%M}",
            )
            for alternative in error.alternatives
        ]
        options.append(MenuOption("other", texts.OTHER_DATE))
        if error.handoff_available:
            options.append(MenuOption("handoff", texts.TALK_TO_A_PERSON))
        session.options = options
        session.step = BotStep.ALTERNATIVES
        return texts.prompt(session)


def _restore(snapshot: dict[str, Any]) -> BotSession:
    """Sesión tal como estaba antes del turno que falló."""

    session = BotSession.from_dict(dict(snapshot))
    if session is None:
        raise ValueError("La instantánea de la sesión no es válida")
    return session


def _require[T](value: T | None) -> T:
    """La respuesta del cliente o, si no corresponde a ninguna opción, ``_NotUnderstood``."""

    if value is None:
        raise _NotUnderstood
    return value


def _text(value: str | None) -> str:
    if value is None:
        raise ValueError("Falta un dato de la sesión")
    return value
