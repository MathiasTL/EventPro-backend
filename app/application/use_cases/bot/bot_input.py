"""Lectura de lo que escribe el cliente: texto normalizado, menús, fechas y horas."""

import re
import unicodedata
from datetime import date, time

from app.application.use_cases.bot.bot_session import MenuOption

# Palabras que piden hablar con una persona (US-27); se buscan como palabras completas.
HANDOFF_WORDS = frozenset(
    {
        "asesor",
        "asesora",
        "encargado",
        "encargada",
        "humano",
        "humana",
        "operador",
        "operadora",
    }
)
RESTART_WORDS = frozenset({"reiniciar", "menu", "inicio", "empezar"})
SKIP_WORDS = frozenset({"0", "no", "ninguno", "ninguna", "nada", "omitir", "continuar"})
YES_WORDS = frozenset({"si", "s", "yo proveo la movilidad", "yo la proveo"})
NO_WORDS = frozenset({"no", "n"})

_DATE = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})")
_TIME = re.compile(r"(\d{1,2}):(\d{2})")
_PUNCTUATION = ".,;:!?¡¿\"'"


def normalize(text: str) -> str:
    """Minúsculas, sin tildes ni signos en los extremos y con espacios simples."""

    decomposed = unicodedata.normalize("NFD", text.casefold())
    plain = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(plain.strip(_PUNCTUATION + " ").split())


def words(normalized: str) -> set[str]:
    return {word.strip(_PUNCTUATION) for word in normalized.split()}


def asks_for_a_person(normalized: str) -> bool:
    return not HANDOFF_WORDS.isdisjoint(words(normalized))


def asks_to_restart(normalized: str) -> bool:
    return normalized in RESTART_WORDS


def pick_option(normalized: str, options: list[MenuOption]) -> MenuOption | None:
    """Opción por su número (empieza en 1) o por su título completo, sin distinguir tildes."""

    if normalized.isdecimal():
        index = int(normalized)
        return options[index - 1] if 1 <= index <= len(options) else None
    return next((option for option in options if normalize(option.title) == normalized), None)


def pick_many(normalized: str, options: list[MenuOption]) -> list[MenuOption] | None:
    """Varias opciones separadas por coma, ``y`` o espacios; ``None`` si alguna no existe."""

    parts = [part.strip() for part in re.split(r"[,;]|\sy\s", normalized) if part.strip()]
    if len(parts) == 1 and all(token.isdecimal() for token in parts[0].split()):
        parts = parts[0].split()
    chosen: list[MenuOption] = []
    for part in parts:
        option = pick_option(part, options)
        if option is None:
            return None
        if option not in chosen:
            chosen.append(option)
    return chosen or None


def parse_date(text: str) -> date | None:
    """Fecha ``DD/MM/AAAA`` (también con ``-`` o ``.``); ``None`` si no existe en el calendario."""

    match = _DATE.fullmatch(text.strip())
    if match is None:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_time(text: str) -> time | None:
    """Hora ``HH:MM`` de 24 horas; ``None`` si no es una hora válida."""

    match = _TIME.fullmatch(text.strip())
    if match is None:
        return None
    hour, minute = (int(group) for group in match.groups())
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)
