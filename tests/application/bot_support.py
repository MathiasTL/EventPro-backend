"""Dobles y un cliente simulado para probar el bot de WhatsApp sin infraestructura."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from app.application.dtos.catalog_dto import (
    ExtraDTO,
    InventoryRequirementDTO,
    PackageReadDTO,
    ThemeDTO,
)
from app.application.dtos.gateway_event_dto import GatewayEventOutcome, IncomingClientMessage
from app.application.dtos.messaging_dto import ConversationStatus
from app.application.ports.output.bot_unit_of_work_port import BotTransaction
from app.application.ports.output.catalog_read_port import ICatalogReadPort
from app.application.ports.output.language_model_port import ILanguageModelPort
from app.application.ports.output.messaging_port import IMessagingPort
from app.application.use_cases.bot.agent_engine import ConversationAgent
from app.application.use_cases.bot.handle_incoming_message import HandleIncomingMessage
from app.application.use_cases.messaging.enqueue_message import EnqueueMessage
from app.domain.value_objects.phone_number import PhoneNumber
from app.domain.value_objects.service_category import ServiceCategory
from app.infrastructure.adapters.secondary.cache.in_memory_conversation_session_adapter import (
    InMemoryConversationSessionAdapter,
)
from app.infrastructure.adapters.secondary.external_services.fake_quote_use_cases import (
    FakeCreateQuote,
    FakePayAdvance,
    FakeQuoteStore,
)
from tests.application.outbox_support import FixedClock, InMemoryOutboxStore

CONVERSATION_ID = 7
PHONE = PhoneNumber("+51999111222")


def _id(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"eventpro:test-catalog:{name}")


SELVA = ThemeDTO(id=_id("selva"), name="Selva")
SAFARI = ThemeDTO(id=_id("safari"), name="Safari")
OLD_THEME = ThemeDTO(id=_id("old"), name="Retirada", is_active=False)
BASIC = PackageReadDTO(
    id=_id("basic"),
    name="Decoración Básica",
    service_category=ServiceCategory.DECORATION,
    base_price=Decimal("400.00"),
    duration_minutes=120,
    compatible_themes=(SELVA,),
)
PREMIUM = PackageReadDTO(
    id=_id("premium"),
    name="Decoración Premium",
    service_category=ServiceCategory.DECORATION,
    base_price=Decimal("900.00"),
    duration_minutes=180,
    compatible_themes=(SELVA, SAFARI, OLD_THEME),
)
HORA_LOCA = PackageReadDTO(
    id=_id("hora-loca"),
    name="Hora Loca",
    service_category=ServiceCategory.SHOW,
    base_price=Decimal("750.00"),
    duration_minutes=60,
    compatible_themes=(SELVA,),
)
DJ_SET = PackageReadDTO(
    id=_id("dj"),
    name="DJ Fiesta",
    service_category=ServiceCategory.DJ,
    base_price=Decimal("500.00"),
    duration_minutes=240,
)
PHOTOS = ExtraDTO(id=_id("photos"), name="Fotografía", sale_price=Decimal("150.00"))
BALLOONS = ExtraDTO(id=_id("balloons"), name="Globos", sale_price=Decimal("80.00"))


class FakeCatalog(ICatalogReadPort):
    """Catálogo en memoria; solo implementa lo que lee el bot."""

    def __init__(
        self,
        packages: Sequence[PackageReadDTO] = (BASIC, PREMIUM, HORA_LOCA, DJ_SET),
        extras: Sequence[ExtraDTO] = (PHOTOS, BALLOONS),
    ) -> None:
        self.packages = list(packages)
        self.extras = list(extras)

    async def list_packages(self, *, include_inactive: bool = False) -> Sequence[PackageReadDTO]:
        return self.packages

    async def get_package(self, package_id: UUID) -> PackageReadDTO | None:
        return next((p for p in self.packages if p.id == package_id), None)

    async def list_themes(self, *, include_inactive: bool = False) -> Sequence[ThemeDTO]:
        raise NotImplementedError

    async def get_theme(self, theme_id: UUID) -> ThemeDTO | None:
        raise NotImplementedError

    async def list_extras(self, *, include_inactive: bool = False) -> Sequence[ExtraDTO]:
        return self.extras

    async def get_extra(self, extra_id: UUID) -> ExtraDTO | None:
        raise NotImplementedError

    async def get_inventory_requirements(
        self, package_id: UUID
    ) -> Sequence[InventoryRequirementDTO]:
        raise NotImplementedError

    async def are_themes_compatible(self, package_id: UUID, theme_id: UUID) -> bool:
        raise NotImplementedError


class RecordingMessaging:
    """Doble de ``IMessagingPort`` que registra los cambios de estado de conversación."""

    def __init__(self, *, fail: bool = False) -> None:
        self.statuses: list[tuple[int, ConversationStatus]] = []
        self.fail = fail

    async def set_conversation_status(
        self, conversation_id: int, status: ConversationStatus
    ) -> None:
        if self.fail:
            raise RuntimeError("gateway caido")
        self.statuses.append((conversation_id, status))


class FakeLock:
    """Doble de ``ICacheLockPort``: registra el uso y puede negar el cerrojo."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.events: list[str] = []

    async def acquire(self, key: str, *, ttl_seconds: int, wait_seconds: float = 0.0) -> bool:
        self.events.append("acquire" if self.available else "denied")
        return self.available

    async def release(self, key: str) -> None:
        self.events.append("release")


class BotHarness:
    """Arma el caso de uso sobre fakes y expone un cliente que escribe por turnos."""

    def __init__(
        self,
        *,
        catalog: FakeCatalog | None = None,
        lock: FakeLock | None = None,
        model: ILanguageModelPort | None = None,
        turn_budget_seconds: float = 20.0,
    ) -> None:
        self.outbox = InMemoryOutboxStore()
        self.quotes = FakeQuoteStore()
        self.create_quote = FakeCreateQuote(self.quotes)
        self.pay_advance = FakePayAdvance(self.quotes)
        self.catalog = catalog or FakeCatalog()
        self.sessions = InMemoryConversationSessionAdapter()
        self.messaging = RecordingMessaging()
        self.clock = FixedClock()
        self.create_quote_override: Any = None
        self._counter = 0
        self.use_case = HandleIncomingMessage(
            unit_of_work=self._unit_of_work,
            sessions=self.sessions,
            messaging=cast("IMessagingPort", self.messaging),
            clock=self.clock,
            lock=lock,
            agent=ConversationAgent(
                unit_of_work=self._unit_of_work,
                model=model,
                clock=self.clock,
                turn_budget_seconds=turn_budget_seconds,
            )
            if model is not None
            else None,
        )

    @asynccontextmanager
    async def _unit_of_work(self) -> AsyncIterator[BotTransaction]:
        async with self.outbox.transaction() as repository:
            yield BotTransaction(
                create_quote=self.create_quote_override or self.create_quote,
                pay_advance=self.pay_advance,
                enqueue_message=EnqueueMessage(repository, self.clock),
                catalog=self.catalog,
            )

    @property
    def sent(self) -> list[str]:
        """Cuerpos de todos los mensajes encolados, en orden."""

        return [str((m.payload or {})["body"]) for m in self.outbox.messages.values()]

    async def say(
        self,
        text: str,
        *,
        status: ConversationStatus = ConversationStatus.BOT,
        private: bool = False,
        message_id: str | None = None,
    ) -> str:
        """Envía un mensaje del cliente y devuelve lo que el bot respondió (``""`` si nada)."""

        self._counter += 1
        before = len(self.sent)
        event = IncomingClientMessage(
            external_message_id=message_id or f"m{self._counter}",
            conversation_id=CONVERSATION_ID,
            conversation_status=status,
            sender_phone=PHONE,
            content=text,
            is_private=private,
        )
        self.last_outcome: GatewayEventOutcome = await self.use_case.execute(event)
        return "\n".join(self.sent[before:])

    async def run(self, *answers: str) -> str:
        """Responde en orden y devuelve la última respuesta del bot."""

        reply = ""
        for answer in answers:
            reply = await self.say(answer)
        return reply


# Respuestas de un cliente que cotiza Decoración Premium con temática Selva y dos extras.
HAPPY_PATH = (
    "hola",  # saludo y categorías
    "3",  # Decoración (orden fijo: Shows, DJ, Decoración, Carpas)
    "2",  # Decoración Premium
    "1",  # Selva
    "1,2",  # extras
    "15/11/2026",
    "16:30",
    "1",  # Lima
    "Av. Larco 123, frente al parque",
    "Ana Torres Quispe",
    "2",  # que cotice la movilidad
    "no",  # sin observaciones
)
