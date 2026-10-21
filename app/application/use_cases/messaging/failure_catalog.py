"""Catálogo de motivos de falla de un mensaje saliente (spec 09, sección 9, D5).

Funciones puras: traducen el motivo crudo que informa Chatwoot (``external_error``) o el que
guarda el despachador (``last_error``) a un texto en español para el navegador. El texto
original nunca sale del backend.
"""

import re
from dataclasses import dataclass

WINDOW_CLOSED_REASON = "Han pasado más de 24 horas; el cliente debe escribir primero."
GENERIC_DELIVERY_REASON = "No se pudo entregar el mensaje."
GENERIC_SEND_REASON = "No se pudo enviar el mensaje."
MESSAGING_UNAVAILABLE_REASON = "La mensajería no estuvo disponible. Reintenta el envío."

WINDOW_CLOSED_META_CODE = 131047

_META_REASONS: dict[int, str] = {
    WINDOW_CLOSED_META_CODE: WINDOW_CLOSED_REASON,
    131026: (
        "El cliente no puede recibir el mensaje. Comprueba que su número tenga WhatsApp activo."
    ),
    131030: "El número no está entre los destinatarios de prueba.",
    131031: "La cuenta de WhatsApp Business está bloqueada. Contacta al administrador del sistema.",
    131056: "Se enviaron demasiados mensajes a este cliente. Espera unos minutos.",
    131049: "WhatsApp limitó este mensaje. Intenta más tarde.",
}
# Chatwoot antepone el código de Meta así: "(#131030) Recipient phone number not in allowed list".
_META_CODE = re.compile(r"\(#(\d{3,7})\)")
# Chatwoot rechaza por su cuenta (sin código de Meta) cuando la ventana de 24 h está cerrada.
_WINDOW_TEXT = re.compile(r"ventana.*24\s*horas|24\s*horas.*ventana", re.IGNORECASE | re.DOTALL)
_SEND_REASONS: dict[str, str] = {
    "ServiceWindowClosedError": WINDOW_CLOSED_REASON,
    "MessagingUnavailableError": MESSAGING_UNAVAILABLE_REASON,
}


@dataclass(frozen=True)
class DeliveryFailure:
    """``code`` es el código numérico de Meta si existe; ``reason`` es el texto en español."""

    code: int | None
    reason: str

    @property
    def window_closed(self) -> bool:
        """La causa es la ventana de 24 h: el reintento se rechaza mientras siga cerrada."""

        return self.reason == WINDOW_CLOSED_REASON


def translate_delivery_failure(external_error: str | None) -> DeliveryFailure:
    """Traduce el ``external_error`` de un mensaje que WhatsApp o Chatwoot rechazaron."""

    text = external_error or ""
    match = _META_CODE.search(text)
    if match is not None:
        code = int(match.group(1))
        return DeliveryFailure(code=code, reason=_META_REASONS.get(code, GENERIC_DELIVERY_REASON))
    if _WINDOW_TEXT.search(text):
        return DeliveryFailure(code=None, reason=WINDOW_CLOSED_REASON)
    return DeliveryFailure(code=None, reason=GENERIC_DELIVERY_REASON)


def translate_send_failure(last_error: str | None) -> str:
    """Traduce el ``last_error`` del outbox, que empieza con el tipo de la excepción."""

    error_type = (last_error or "").partition(":")[0].strip()
    return _SEND_REASONS.get(error_type, GENERIC_SEND_REASON)
