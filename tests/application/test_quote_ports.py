import inspect
from typing import Any, get_type_hints
from uuid import UUID

import pytest

from app.application.dtos.client_dto import ClientDetailDTO, ClientDTO, FindClientsFilter
from app.application.dtos.page_dto import PageDTO
from app.application.dtos.quote_dto import (
    CancelledQuoteDTO,
    CreatedQuoteDTO,
    CreateQuoteInput,
    ListQuotesFilter,
    PayAdvanceResultDTO,
    QuoteDetailDTO,
    QuoteListItemDTO,
)
from app.application.ports.input.client_read_port import IFindClientsPort, IGetClientPort
from app.application.ports.input.quote_create_port import ICreateQuotePort
from app.application.ports.input.quote_expiry_port import IExpireDueQuotesPort
from app.application.ports.input.quote_lifecycle_port import ICancelQuotePort, IPayAdvancePort
from app.application.ports.input.quote_read_port import IGetQuotePort, IListQuotesPort

# Puerto -> (parámetros de ``execute`` con su anotación, anotación de retorno).
CONTRACT: dict[type, tuple[dict[str, Any], Any]] = {
    ICreateQuotePort: ({"dto": CreateQuoteInput}, CreatedQuoteDTO),
    IGetQuotePort: ({"quote_id": UUID}, QuoteDetailDTO),
    IListQuotesPort: ({"filters": ListQuotesFilter}, PageDTO[QuoteListItemDTO]),
    IPayAdvancePort: ({"quote_id": UUID}, PayAdvanceResultDTO),
    ICancelQuotePort: ({"quote_id": UUID, "reason": str | None}, CancelledQuoteDTO),
    IExpireDueQuotesPort: ({}, int),
    IFindClientsPort: ({"filters": FindClientsFilter}, PageDTO[ClientDTO]),
    IGetClientPort: ({"client_id": UUID}, ClientDetailDTO),
}
PORTS = list(CONTRACT)


def _public_members(port: type) -> list[str]:
    return [name for name in vars(port) if not name.startswith("_")]


def test_all_eight_ports_are_protocols_named_by_convention() -> None:
    assert len(PORTS) == 8
    for port in PORTS:
        assert port.__name__.startswith("I")
        assert port.__name__.endswith("Port")
        assert getattr(port, "_is_protocol", False) is True, port.__name__


@pytest.mark.parametrize("port", PORTS, ids=lambda port: port.__name__)
def test_each_port_declares_one_async_execute(port: type) -> None:
    assert _public_members(port) == ["execute"]
    assert inspect.iscoroutinefunction(port.execute)  # type: ignore[attr-defined]


@pytest.mark.parametrize("port", PORTS, ids=lambda port: port.__name__)
def test_execute_signatures_match_the_contract(port: type) -> None:
    expected_params, expected_return = CONTRACT[port]
    execute = port.execute  # type: ignore[attr-defined]
    signature = inspect.signature(execute)
    parameters = [name for name in signature.parameters if name != "self"]
    assert parameters == list(expected_params)
    hints = get_type_hints(execute)
    assert hints.pop("return") == expected_return
    assert hints == expected_params


def test_cancel_reason_defaults_to_none() -> None:
    reason = inspect.signature(ICancelQuotePort.execute).parameters["reason"]
    assert reason.default is None


@pytest.mark.parametrize("port", PORTS, ids=lambda port: port.__name__)
def test_each_port_has_a_docstring_on_execute(port: type) -> None:
    assert (port.execute.__doc__ or "").strip()  # type: ignore[attr-defined]
