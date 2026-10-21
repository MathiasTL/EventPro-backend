"""Suite de contrato de ``IMessagingPort``.

La ejecutan el adaptador falso y el adaptador real de Chatwoot (sobre un servidor simulado):
una subclase concreta (``Test...``) implementa los ganchos ``make_adapter``,
``close_service_window``, ``make_unavailable`` y los del lado del cliente (``receive_text``,
``receive_attachment``, ``add_activity``, ``resolve``). Esta clase no empieza por ``Test``, así
que pytest no la recolecta.
"""

from collections.abc import Sequence

import pytest

from app.application.dtos.messaging_dto import (
    ConversationLifecycle,
    ConversationStatus,
    ListRow,
    ListSection,
    MessageDirection,
    MessageReceipt,
    MessageSender,
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

    def receive_text(self, adapter: IMessagingPort, sender: PhoneNumber, body: str) -> None:
        """Mensaje entrante del cliente (reabre una resuelta como pendiente)."""
        raise NotImplementedError

    def receive_attachment(
        self, adapter: IMessagingPort, sender: PhoneNumber, data: bytes, name: str, kind: str
    ) -> None:
        raise NotImplementedError

    def add_activity(self, adapter: IMessagingPort, conversation_id: int, text: str) -> None:
        raise NotImplementedError

    def resolve(self, adapter: IMessagingPort, conversation_id: int) -> None:
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
        with pytest.raises(MessagingUnavailableError):
            await adapter.get_conversation(1)
        with pytest.raises(MessagingUnavailableError):
            await adapter.list_messages(1)
        with pytest.raises(MessagingUnavailableError):
            await adapter.mark_conversation_read(1)
        with pytest.raises(MessagingUnavailableError):
            await adapter.get_attachment(1, 1)

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

    async def test_list_messages_is_chronological_limited_and_paged_by_id(
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
        older = await adapter.list_messages(
            first.conversation_id, before_id=int(last.message_id), limit=50
        )
        assert [message.body for message in older] == ["Uno", "Dos"]
        oldest = await adapter.list_messages(
            first.conversation_id, before_id=int(older[0].message_id)
        )
        assert oldest == ()

    async def test_messages_report_sender_status_and_activity(
        self, adapter: IMessagingPort
    ) -> None:
        sent = await adapter.send_text(PHONE, "Hola")
        self.receive_text(adapter, PHONE, "Quiero cotizar")
        self.add_activity(adapter, sent.conversation_id, "La conversación fue reabierta")
        sent_message, incoming, activity = await adapter.list_messages(sent.conversation_id)
        assert (sent_message.direction, sent_message.sender) == (
            MessageDirection.OUTGOING,
            MessageSender.AGENT_BOT,
        )
        assert sent_message.status == "sent"
        assert (incoming.direction, incoming.sender) == (
            MessageDirection.INCOMING,
            MessageSender.CONTACT,
        )
        assert incoming.body == "Quiero cotizar"
        assert (activity.direction, activity.sender) == (MessageDirection.ACTIVITY, None)
        assert activity.body == "La conversación fue reabierta"

    async def test_summary_reports_unread_preview_and_lifecycle(
        self, adapter: IMessagingPort
    ) -> None:
        sent = await adapter.send_text(PHONE, "Hola")
        self.receive_text(adapter, PHONE, "Quiero cotizar")
        self.receive_text(adapter, PHONE, "x" * 300)
        self.add_activity(adapter, sent.conversation_id, "Aviso del sistema")
        summary = await adapter.get_conversation(sent.conversation_id)
        assert summary.conversation_id == sent.conversation_id
        assert summary.phone == PHONE
        assert summary.unread_count == 2
        assert summary.lifecycle is ConversationLifecycle.PENDING
        assert summary.status is ConversationStatus.BOT
        # La actividad no cambia la vista previa ni la hora del último mensaje.
        assert summary.last_message_preview == "x" * 120
        messages = await adapter.list_messages(sent.conversation_id)
        assert summary.last_message_at == messages[-2].sent_at
        await adapter.set_conversation_status(sent.conversation_id, ConversationStatus.HUMAN)
        reopened = await adapter.get_conversation(sent.conversation_id)
        assert (reopened.lifecycle, reopened.status) == (
            ConversationLifecycle.OPEN,
            ConversationStatus.HUMAN,
        )
        assert (await adapter.list_conversations())[0].unread_count == 2

    async def test_get_conversation_of_unknown_id_raises_not_found(
        self, adapter: IMessagingPort
    ) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.get_conversation(999_999)

    async def test_mark_conversation_read_resets_unread_count(
        self, adapter: IMessagingPort
    ) -> None:
        sent = await adapter.send_text(PHONE, "Hola")
        self.receive_text(adapter, PHONE, "Uno")
        self.receive_text(adapter, PHONE, "Dos")
        assert (await adapter.get_conversation(sent.conversation_id)).unread_count == 2
        await adapter.mark_conversation_read(sent.conversation_id)
        assert (await adapter.get_conversation(sent.conversation_id)).unread_count == 0
        with pytest.raises(ResourceNotFoundError):
            await adapter.mark_conversation_read(999_999)

    async def test_resolved_conversations_are_listed_only_on_request(
        self, adapter: IMessagingPort
    ) -> None:
        resolved = await adapter.send_text(PHONE, "Hola")
        await adapter.send_text(OTHER_PHONE, "Buenas")
        self.resolve(adapter, resolved.conversation_id)
        assert [item.phone for item in await adapter.list_conversations()] == [OTHER_PHONE]
        everything = await adapter.list_conversations(include_resolved=True)
        assert {item.phone: item.lifecycle for item in everything} == {
            PHONE: ConversationLifecycle.RESOLVED,
            OTHER_PHONE: ConversationLifecycle.PENDING,
        }
        assert [
            item.phone
            for item in await adapter.list_conversations(
                status=ConversationStatus.BOT, include_resolved=True
            )
        ] == [OTHER_PHONE, PHONE]
        assert (
            await adapter.list_conversations(status=ConversationStatus.HUMAN, include_resolved=True)
            == ()
        )
        assert (await adapter.get_conversation(resolved.conversation_id)).lifecycle is (
            ConversationLifecycle.RESOLVED
        )

    async def test_client_message_reopens_a_resolved_conversation_as_pending(
        self, adapter: IMessagingPort
    ) -> None:
        sent = await adapter.send_text(PHONE, "Hola")
        await adapter.set_conversation_status(sent.conversation_id, ConversationStatus.HUMAN)
        self.resolve(adapter, sent.conversation_id)
        self.receive_text(adapter, PHONE, "Hola de nuevo")
        summary = await adapter.get_conversation(sent.conversation_id)
        assert (summary.lifecycle, summary.status) == (
            ConversationLifecycle.PENDING,
            ConversationStatus.BOT,
        )

    async def test_incoming_attachment_is_listed_and_downloadable(
        self, adapter: IMessagingPort
    ) -> None:
        sent = await adapter.send_text(PHONE, "Hola")
        self.receive_attachment(adapter, PHONE, b"\xff\xd8jpeg", "File.jpg", "image/jpeg")
        message = (await adapter.list_messages(sent.conversation_id))[-1]
        assert message.body is None
        (attachment,) = message.attachments
        assert (attachment.file_type, attachment.content_type) == ("image", "image/jpeg")
        assert (attachment.extension, attachment.file_size) == ("jpg", 6)
        assert (await adapter.get_conversation(sent.conversation_id)).last_message_preview == (
            "[Adjunto]"
        )
        content = await adapter.get_attachment(sent.conversation_id, attachment.attachment_id)
        assert (content.data, content.content_type, content.filename) == (
            b"\xff\xd8jpeg",
            "image/jpeg",
            "File.jpg",
        )

    async def test_sent_attachment_can_be_downloaded_back(self, adapter: IMessagingPort) -> None:
        receipt = await adapter.send_attachment(
            PHONE, b"%PDF-1.7", "cotizacion.pdf", "application/pdf", "Tu cotización"
        )
        (message,) = await adapter.list_messages(receipt.conversation_id)
        (attachment,) = message.attachments
        assert attachment.file_type == "file"
        content = await adapter.get_attachment(receipt.conversation_id, attachment.attachment_id)
        assert (content.data, content.filename) == (b"%PDF-1.7", "cotizacion.pdf")

    async def test_attachment_of_another_conversation_or_unknown_is_not_found(
        self, adapter: IMessagingPort
    ) -> None:
        mine = await adapter.send_text(PHONE, "Hola")
        other = await adapter.send_attachment(OTHER_PHONE, b"x", "a.png", "image/png", None)
        (other_message,) = await adapter.list_messages(other.conversation_id)
        foreign_id = other_message.attachments[0].attachment_id
        with pytest.raises(ResourceNotFoundError):
            await adapter.get_attachment(mine.conversation_id, foreign_id)
        with pytest.raises(ResourceNotFoundError):
            await adapter.get_attachment(other.conversation_id, 999_999)
        with pytest.raises(ResourceNotFoundError):
            await adapter.get_attachment(999_999, foreign_id)

    async def test_list_messages_of_unknown_conversation_raises_not_found(
        self, adapter: IMessagingPort
    ) -> None:
        with pytest.raises(ResourceNotFoundError):
            await adapter.list_messages(999_999)
