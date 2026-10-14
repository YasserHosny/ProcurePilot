import pytest

from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.landed_cost.service import _required_currency, _resolve_currency


def test_landed_cost_currency_precedence_and_missing_branch() -> None:
    assert _resolve_currency("EGP", "USD", "EUR") == "EGP"
    assert _resolve_currency(None, "USD", "EUR") == "USD"
    assert _resolve_currency(None, None, "EGP") == "EGP"
    with pytest.raises(ConflictError) as error:
        _required_currency(_resolve_currency(None, None, None))
    assert error.value.details == {"reason": "currency_missing"}
