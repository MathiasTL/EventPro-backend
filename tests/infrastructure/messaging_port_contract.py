"""Suite de contrato de ``IMessagingPort``.

La ejecuta el adaptador falso hoy y deberá pasarla el adaptador real de Chatwoot: una
subclase concreta (``Test...``) implementa ``make_adapter``, ``close_service_window`` y
``make_unavailable``. Esta clase no empieza por ``Test``, así que pytest no la recolecta.
"""

from collections.abc import Sequence

import pytest

from app.application.dtos.messaging_dto import (
    ConversationStatus,
    ListRow,
    ListSection,
    MessageDirection,
    MessageReceipt,
)
from app.application.ports.output.messaging_port import IMessagingPort
from app.domain.exceptions.messaging_exceptions import (
    MessagingUnavailableError,
    ServiceWindowClosedError,
)
from app.domain.exceptions.resource_exceptions import ResourceNotFoundError
from app.domain.value_objects.phone_number import PhoneNumber

PHONE = PhoneNumber.parse("999111222")
OTHER_PHONE = PhoneNumber.parse("999333444")
SECTIONS: Sequence[ListSection] = (
    ListSection("Paquetes", (ListRow("pkg-1", "Show infantil", "Duración 2 h"),)),
)


class MessagingPortContract:
    def make_adapter(self) -> IMessagingPort:
        raise NotImplementedError

    def close_service_window(self, adapter: IMessagingPort) -> None:
        raise NotImplementedError

    def make_unavailable(self, adapter: IMessagingPort) -> None:
        raise NotImplementedError

    @pytest.fixture
    def adapter(self) -> IMessagingPort:
        return self.make_adapter()

    @staticmethod
    def _assert_receipt(receipt: MessageReceipt) -> None:
        assert receipt.message_id
        assert receipt.conversation_id > 0
        assert receipt.sent_at.tzinfo is not None

    async def test_send_text_returns_a_receipt(self, adapter: IMessagingPort) -> None:
        self._assert_receipt(await adapter.send_text(PHONE, "Hola"))

    async def test_send_interactive_list_returns_a_receipt(self, adapter: IMessagingPort) -> None:
        self._assert_receipt(await adapter.send_interactive_list(PHONE, "Elige", SECTIONS))

    async def test_send_template_returns_a_receipt(self, adapter: IMessagingPort) -> None:
        receipt = await adapter.send_template(PHONE, "otp_firma", {"code": "123456"})
        self._assert_receipt(receipt)

    async def test_send_attachment_returns_a_receipt(self, adapter: IMessagingPort) -> None:
        receipt = await adapter.send_attachment(
            PHONE, b"%PDF-1.7", "cotizacion.pdf", "application/pdf", "Tu cotización"
        )
        self._assert_receipt(receipt)

    async def test_messages_to_the_same_phone_share_a_conversation(
        self, adapter: IMessagingPort
    ) -> None:
        first = await adapter.send_text(PHONE, "Uno")
        second = await adapter.send_text(PHONE, "Dos")
        other = await adapter.send_text(OTHER_PHONE, "Tres")
        assert first.conversation_id == second.conversation_id
        assert other.conversation_id != first.conversation_id
        assert first.message_id != second.message_id

    async def test_closed_window_rejects_free_form_messages(self, adapter: IMessagingPort) -> None:
        self.close_service_window(adapter)
        with pytest.raises(ServiceWindowClosedError) as text_error:
            await adapter.send_text(PHONE, "Hola")
        assert text_error.value.code == "service-window-closed"
        with pytest.raises(ServiceWindowClosedError):
            await adapter.send_interactive_list(PHONE, "Elige", SECTIONS)
        with pytest.raises(ServiceWindowClosedError):
            await adapter.send_attachment(PHONE, b"x", "a.png", "image/png", None)

    async def test_closed_window_still_accepts_templates(self, adapter: IMessagingPort) -> None:
        self.close_service_window(adapter)
        self._assert_receipt(await adapter.send_template(PHONE, "otp_firma", {"code": "1"}))

    async def test_unavailable_gateway_raises_messaging_unavailable(
        self, adapter: IMessagingPort
    ) -> None:
        self.make_unavailable(adapter)
        with pytest.raises(MessagingUnavailableError):
            await adapter.send_text(PHONE, "Hola")
        with pytest.raises(MessagingUnavailableError):
            await adapter.send_template(PHONE, "otp_firma", {})
        with pytest.raises(MessagingUnavailableError):
            await adapter.list_conversations()

    async def test_conversation_status_round_trip(self, adapter: IMessagingPort) -> None:
        receipt = await adapter.send_text(PHONE, "Hola")
        conversations = await adapter.list_conversations()
        assert [item.status for item in conversations] == [ConversationStatus.BOT]
        await adapter.set_conversation_status(receipt.conversation_id, ConversationStatus.HUMAN)
        humans = await adapter.list_conversations(status=ConversationStatus.HUMAN)
        assert [item.conversation_id for item in humans] == [receipt.conversation_id]
        assert await adapter.list_conversations(status=ConversationStatus.BOT) == ()

    async def test_set_status_of_unknown_conversation_raises_not_found(
        self, adapter: IMessagingPort
    ) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.set_conversation_status(999_999, ConversationStatus.HUMAN)

    async def test_list_conversations_reports_phone_window_and_paging(
        self, adapter: IMessagingPort
    ) -> None:
        await adapter.send_text(PHONE, "Hola")
        newest = await adapter.send_text(OTHER_PHONE, "Buenas")
        conversations = await adapter.list_conversations()
        assert [item.phone for item in conversations] == [OTHER_PHONE, PHONE]
        assert conversations[0].conversation_id == newest.conversation_id
        assert conversations[0].service_window_open is True
        assert conversations[0].last_message_at == newest.sent_at
        second_page = await adapter.list_conversations(page=2, page_size=1)
        assert [item.phone for item in second_page] == [PHONE]
        self.close_service_window(adapter)
        assert (await adapter.list_conversations())[0].service_window_open is False

    async def test_list_messages_is_chronological_and_limited(
        self, adapter: IMessagingPort
    ) -> None:
        first = await adapter.send_text(PHONE, "Uno")
        await adapter.send_text(PHONE, "Dos")
        last = await adapter.send_text(PHONE, "Tres")
        messages = await adapter.list_messages(first.conversation_id)
        assert [message.body for message in messages] == ["Uno", "Dos", "Tres"]
        assert all(message.direction is MessageDirection.OUTGOING for message in messages)
        assert [message.sent_at for message in messages] == sorted(
            message.sent_at for message in messages
        )
        newest_two = await adapter.list_messages(first.conversation_id, limit=2)
        assert [message.body for message in newest_two] == ["Dos", "Tres"]
        older = await adapter.list_messages(first.conversation_id, before=last.sent_at)
        assert [message.body for message in older] == ["Uno", "Dos"]

    async def test_list_messages_of_unknown_conversation_raises_not_found(
        self, adapter: IMessagingPort
    ) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.list_messages(999_999)
