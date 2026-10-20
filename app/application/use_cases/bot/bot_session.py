"""Estado de la conversación del bot: en qué paso va el cliente y lo que ya respondió.

Es un objeto plano y serializable a JSON: ``IConversationSessionPort`` lo guarda tal cual
(Redis, 24 h). Los menús numerados se guardan con la sesión para que el número que escribe el
cliente siempre signifique lo que se le mostró, aunque el catálogo cambie entre mensajes.
"""

from dataclasses import asdict, dataclass, field, fields
from enum import StrEnum
from typing import Any


class BotStep(StrEnum):
    """Pregunta que el bot espera que el cliente responda."""

    CATEGORY = "CATEGORY"
    PACKAGE = "PACKAGE"
    THEME = "THEME"
    EXTRAS = "EXTRAS"
    DATE = "DATE"
    TIME = "TIME"
    DISTRICT = "DISTRICT"
    ADDRESS = "ADDRESS"
    NAME = "NAME"
    MOBILITY = "MOBILITY"
    OBSERVATIONS = "OBSERVATIONS"
    CONFIRM = "CONFIRM"
    ALTERNATIVES = "ALTERNATIVES"
    PAID = "PAID"


@dataclass
class MenuOption:
    """Opción de un menú numerado: ``title`` es lo que se acepta escrito; ``detail`` solo se ve."""

    key: str
    title: str
    detail: str = ""


@dataclass
class BotSession:
    step: BotStep = BotStep.CATEGORY
    options: list[MenuOption] = field(default_factory=list)
    category: str | None = None
    package_id: str | None = None
    package_name: str | None = None
    theme_id: str | None = None
    theme_name: str | None = None
    extras: list[MenuOption] = field(default_factory=list)
    event_date: str | None = None  # ISO: AAAA-MM-DD
    event_time: str | None = None  # HH:MM
    district: str | None = None
    address: str | None = None
    full_name: str | None = None
    provides_mobility: bool = False
    observations: str | None = None
    quote_id: str | None = None
    # Respuestas seguidas que el bot no entendió: dos seguidas derivan a un encargado.
    misses: int = 0
    # Último mensaje ya procesado: un reintento del trabajo no responde dos veces.
    last_message_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BotSession | None":
        """Reconstruye la sesión; ``None`` si el JSON guardado no tiene la forma esperada."""

        known = {f.name for f in fields(cls)}
        try:
            values = {key: value for key, value in data.items() if key in known}
            values["step"] = BotStep(values["step"])
            values["options"] = [MenuOption(**item) for item in values.get("options", [])]
            values["extras"] = [MenuOption(**item) for item in values.get("extras", [])]
            return cls(**values)
        except (KeyError, TypeError, ValueError):
            return None
