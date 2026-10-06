"""Estados operativos de Event según RN, sección 3.3."""

from enum import StrEnum


class EventStatus(StrEnum):
    AWAITING_SIGNATURE = "AWAITING_SIGNATURE"
    SCHEDULED = "SCHEDULED"
    AWAITING_BALANCE = "AWAITING_BALANCE"
    IN_PROGRESS = "IN_PROGRESS"
    EXTENDED = "EXTENDED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"
