"""Estado serializable de la sesión del bot y lectura de lo que escribe el cliente."""

import json
from datetime import date, time

import pytest

from app.application.use_cases.bot.bot_input import (
    asks_for_a_person,
    asks_to_restart,
    normalize,
    parse_date,
    parse_time,
    pick_many,
    pick_option,
)
from app.application.use_cases.bot.bot_session import BotSession, BotStep, MenuOption

OPTIONS = [MenuOption("a", "Decoración"), MenuOption("b", "DJ", "desde S/ 500.00")]


def test_a_session_survives_a_json_round_trip() -> None:
    session = BotSession(
        step=BotStep.EXTRAS,
        options=OPTIONS,
        extras=[MenuOption("x", "Globos", "S/ 80.00")],
        event_date="2026-11-15",
        provides_mobility=True,
        misses=1,
    )

    restored = BotSession.from_dict(json.loads(json.dumps(session.to_dict())))

    assert restored == session


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"step": "NOPE"},
        {"step": "DATE", "options": [{"bogus": 1}]},
        {"step": "DATE", "options": 3},
    ],
)
def test_an_unreadable_session_is_none(data: dict[str, object]) -> None:
    assert BotSession.from_dict(data) is None


def test_unknown_stored_fields_are_ignored() -> None:
    session = BotSession.from_dict({"step": "DATE", "removed_field": 1})

    assert session is not None and session.step is BotStep.DATE


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  ¡Menú!  ", "menu"), ("DECORACIÓN", "decoracion"), ("a   b", "a b"), ("", "")],
)
def test_normalize_ignores_case_accents_and_edge_punctuation(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1", "a"),
        ("2", "b"),
        ("dj", "b"),
        ("decoracion", "a"),
        ("3", None),
        ("0", None),
        ("x", None),
    ],
)
def test_pick_option_by_number_or_title(text: str, expected: str | None) -> None:
    option = pick_option(text, OPTIONS)

    assert (option.key if option else None) == expected


def test_pick_many_rejects_the_whole_answer_if_one_choice_is_unknown() -> None:
    assert pick_many("1,3", OPTIONS) is None
    assert pick_many("", OPTIONS) is None
    chosen = pick_many("1 y dj", OPTIONS)
    assert chosen is not None and [o.key for o in chosen] == ["a", "b"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15/11/2026", date(2026, 11, 15)),
        ("1-2-2027", date(2027, 2, 1)),
        ("31/04/2026", None),
        ("15/11/26", None),
    ],
)
def test_parse_date(text: str, expected: date | None) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("16:30", time(16, 30)), ("7:05", time(7, 5)), ("24:00", None), ("16.30", None)],
)
def test_parse_time(text: str, expected: time | None) -> None:
    assert parse_time(text) == expected


def test_person_and_restart_words() -> None:
    assert asks_for_a_person(normalize("Quiero hablar con un Encargado."))
    assert not asks_for_a_person(normalize("hola, buenas tardes"))
    assert asks_to_restart("menu")
    assert not asks_to_restart("quiero el menu del paquete")
