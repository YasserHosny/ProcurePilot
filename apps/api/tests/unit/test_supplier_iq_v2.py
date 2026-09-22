from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from uuid import UUID

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.offers.supplier_iq_v2 import (
    Alternative,
    OrderLine,
    Price,
    PurchaseOrder,
    ReceiptLine,
    SupplierRiskInput,
    calculate_supplier_risk,
    source_fingerprint,
)

S = UUID(int=1)
OTHER = UUID(int=2)
END = date(2026, 9, 20)
START = END - timedelta(days=180)
SPLIT = END - timedelta(days=90)


def stamp(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), UTC)


def fixture(n: int = 3, price: str = "110") -> SupplierRiskInput:
    orders, receipts, prices = [], [], []
    for i in range(n):
        product = UUID(int=100 + i)
        for period, day in enumerate((START, SPLIT)):
            ident = 1000 + i * 10 + period
            line = OrderLine(UUID(int=ident), product, "kg", D(10))
            orders.append(
                PurchaseOrder(UUID(int=ident), S, day, day, "received", D(100), "USD", (line,))
            )
            receipts.append(
                ReceiptLine(UUID(int=ident + 10000), UUID(int=ident), line.id, D(10), stamp(day))
            )
            prices.append(
                Price(
                    UUID(int=ident + 20000),
                    S,
                    product,
                    "kg",
                    "USD",
                    D("100" if period == 0 else price),
                    stamp(day),
                )
            )
    return SupplierRiskInput(
        supplier_id=S,
        window_end=END,
        purchase_orders=tuple(orders),
        receipts=tuple(receipts),
        prices=tuple(prices),
    )


def test_public_shape_and_defaults() -> None:
    p = fixture()
    r = calculate_supplier_risk(p)
    assert (p.window_start, p.split_date) == (START, SPLIT)
    assert r.components["price_drift"].risk == D(".5")
    assert r.score == D(".625")
    assert r.release_posture == "g3_unmet"
    assert r.state == "provisional"
    assert r.model_dump(mode="json")["score"] == "0.6250"
    with pytest.raises(FrozenInstanceError):
        p.window_end = START


@pytest.mark.parametrize(
    ("price", "risk"), [("80", "0"), ("100", "0"), ("110", ".5"), ("120", "1"), ("150", "1")]
)
def test_price_formula(price: str, risk: str) -> None:
    assert calculate_supplier_risk(fixture(price=price)).components["price_drift"].risk == D(risk)


@pytest.mark.parametrize(
    ("n", "confidence", "state"),
    [
        (0, "low", "insufficient_data"),
        (2, "low", "insufficient_data"),
        (3, "medium", "provisional"),
        (9, "medium", "provisional"),
        (10, "high", "ready"),
    ],
)
def test_confidence_and_state(n: int, confidence: str, state: str) -> None:
    r = calculate_supplier_risk(fixture(n))
    assert r.components["single_source"].confidence == confidence
    assert r.state == state


def test_zero_baseline_and_three_weight_renormalization() -> None:
    p = fixture()
    p = replace(
        p,
        prices=tuple(
            replace(x, unit_price=D(0)) if x.recorded_at.date() < SPLIT else x for x in p.prices
        ),
    )
    r = calculate_supplier_risk(p)
    assert r.components["price_drift"].excluded_counts["zero_baseline"] == 3
    assert r.components["price_drift"].risk is None
    assert r.score == D(".50") / D(".75")
    assert r.weights["concentration"] == D(".30") / D(".75")
    assert calculate_supplier_risk(replace(p, receipts=(), purchase_orders=())).score is None


@pytest.mark.parametrize(
    "status", ["submitted", "confirmed", "partially_received", "received", "closed"]
)
def test_concentration_currencies(status: str) -> None:
    p = fixture()
    own = tuple(replace(x, status=status) for x in p.purchase_orders)
    other = tuple(
        replace(x, id=UUID(int=x.id.int + 50000), supplier_id=OTHER, amount=D(300)) for x in own
    )
    eur = tuple(replace(x, id=UUID(int=x.id.int + 60000), currency="EUR", amount=D(1)) for x in own)
    r = calculate_supplier_risk(replace(p, purchase_orders=own + other + eur))
    c = r.components["concentration"]
    assert c.risk == 1
    assert {b.currency: b.share for b in c.currency_buckets} == {"EUR": D(1), "USD": D(".25")}


def test_concentration_requires_three_tenant_orders_and_one_supplier_order() -> None:
    p = fixture()
    own = p.purchase_orders[0]
    tenant_peers = tuple(
        replace(
            own,
            id=UUID(int=own.id.int + 70000 + i),
            supplier_id=OTHER,
            amount=D(100),
        )
        for i in range(2)
    )
    c = calculate_supplier_risk(replace(p, purchase_orders=(own,) + tenant_peers)).components[
        "concentration"
    ]
    assert c.risk == D(1) / D(3)
    assert c.sample_count == 3


@pytest.mark.parametrize("status", ["draft", "cancelled"])
def test_excluded_orders(status: str) -> None:
    p = fixture()
    r = calculate_supplier_risk(
        replace(p, purchase_orders=tuple(replace(x, status=status) for x in p.purchase_orders))
    )
    assert r.components["concentration"].risk is None
    assert r.components["reliability"].risk is None


@pytest.mark.parametrize("status", ["open", "in_progress"])
def test_due_open_orders_count_for_reliability(status: str) -> None:
    p = fixture()
    expected = calculate_supplier_risk(p).components["reliability"]
    actual = calculate_supplier_risk(
        replace(p, purchase_orders=tuple(replace(x, status=status) for x in p.purchase_orders))
    ).components["reliability"]
    assert actual.sample_count == expected.sample_count
    assert actual.baseline_count == expected.baseline_count
    assert actual.current_count == expected.current_count
    assert actual.risk == expected.risk


def test_cumulative_receipts_and_expected_date_assignment() -> None:
    p = fixture()
    receipts = tuple(replace(x, quantity=D(4)) for x in p.receipts) + tuple(
        replace(x, id=UUID(int=x.id.int + 30000), quantity=D(6)) for x in p.receipts
    )
    p = replace(
        p,
        receipts=receipts,
        purchase_orders=tuple(replace(x, ordered_on=START) for x in p.purchase_orders),
    )
    assert calculate_supplier_risk(p).components["reliability"].risk == 0
    late = tuple(
        replace(x, received_at=stamp(END)) if x.received_at.date() >= SPLIT else x for x in receipts
    )
    assert calculate_supplier_risk(replace(p, receipts=late)).components["reliability"].risk == 1


@pytest.mark.parametrize(("failed", "risk"), [(0, "0"), (1, ".4"), (2, ".8"), (3, "1")])
def test_reliability_decay(failed: int, risk: str) -> None:
    p = fixture(10)
    removed = {x.id for x in p.receipts if x.received_at.date() == SPLIT}
    removed = set(sorted(removed)[:failed])
    r = calculate_supplier_risk(
        replace(p, receipts=tuple(x for x in p.receipts if x.id not in removed))
    )
    assert r.components["reliability"].risk == D(risk)


@pytest.mark.parametrize(
    ("active", "currency", "unit", "valid", "risk"),
    [
        (True, "USD", "kg", True, "0"),
        (False, "USD", "kg", True, "1"),
        (True, "EUR", "kg", True, "1"),
        (True, "USD", "g", True, "1"),
        (True, "USD", "kg", False, "1"),
    ],
)
def test_alternatives(active: bool, currency: str, unit: str, valid: bool, risk: str) -> None:
    p = fixture()
    alternatives = tuple(
        Alternative(
            UUID(int=40000 + i),
            OTHER,
            UUID(int=100 + i),
            unit,
            currency,
            D(90),
            stamp(START),
            START,
            END + timedelta(days=1) if valid else END,
            active,
        )
        for i in range(3)
    )
    r = calculate_supplier_risk(replace(p, alternatives=alternatives))
    assert r.components["single_source"].risk == D(risk)


def test_single_source_uses_product_level_alternative_coverage() -> None:
    p = fixture()
    alternatives = tuple(
        Alternative(
            UUID(int=50000 + i),
            OTHER,
            UUID(int=100 + i),
            "kg",
            "USD",
            D(90),
            stamp(SPLIT),
            SPLIT,
            END + timedelta(days=1),
            True,
        )
        for i in range(3)
    )
    orders = tuple(
        replace(order, currency="USD" if order.expected_delivery_date == START else "EUR")
        for order in p.purchase_orders
    )
    component = calculate_supplier_risk(
        replace(p, purchase_orders=orders, alternatives=alternatives)
    ).components["single_source"]
    assert component.risk == 0


def test_single_source_includes_due_open_orders() -> None:
    p = fixture()
    expected = calculate_supplier_risk(p).components["single_source"]
    actual = calculate_supplier_risk(
        replace(p, purchase_orders=tuple(replace(x, status="open") for x in p.purchase_orders))
    ).components["single_source"]
    assert actual.denominator == expected.denominator
    assert actual.numerator == expected.numerator


def test_fingerprint_canonical_and_sensitive() -> None:
    p = fixture()
    reverse = replace(
        p,
        purchase_orders=tuple(reversed(p.purchase_orders)),
        receipts=tuple(reversed(p.receipts)),
        prices=tuple(reversed(p.prices)),
    )
    assert source_fingerprint(p) == source_fingerprint(reverse)
    assert calculate_supplier_risk(p) == calculate_supplier_risk(reverse)
    assert source_fingerprint(p) != source_fingerprint(replace(p, receipts=()))
    equivalent = replace(
        p, prices=tuple(replace(x, unit_price=x.unit_price.quantize(D(".00"))) for x in p.prices)
    )
    assert source_fingerprint(p) == source_fingerprint(equivalent)


@pytest.mark.parametrize(
    ("score", "level"),
    [
        ("0", "low"),
        (".349999", "low"),
        (".35", "medium"),
        (".649999", "medium"),
        (".65", "high"),
        ("1", "high"),
    ],
)
def test_risk_level_boundaries(score: str, level: str) -> None:
    from procurepilot_api.modules.offers.supplier_iq_v2 import _level

    assert _level(D(score)) == level


@pytest.mark.parametrize(
    "missing", ["concentration", "price_drift", "reliability", "single_source"]
)
def test_each_missing_component_renormalizes(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.offers import supplier_iq_v2 as module

    p = fixture()
    full = calculate_supplier_risk(p)
    function = {
        "concentration": "_concentration",
        "price_drift": "_prices",
        "reliability": "_reliability",
        "single_source": "_single_source",
    }[missing]
    absent = full.components[missing].model_copy(update={"risk": None})
    monkeypatch.setattr(module, function, lambda _: absent)
    result = calculate_supplier_risk(p)
    expected = sum(
        (full.components[k].risk * w for k, w in module.WEIGHTS.items() if k != missing), D(0)
    ) / (1 - module.WEIGHTS[missing])
    assert result.score == expected
    assert result.state == "provisional"
    assert missing not in result.weights


def test_median_not_mean_and_product_coverage() -> None:
    p = fixture()
    extra = tuple(
        replace(x, id=UUID(int=x.id.int + 50000), unit_price=D(10000))
        for x in p.prices
        if x.recorded_at.date() == SPLIT
    )
    extra += tuple(
        replace(x, id=UUID(int=x.id.int + 60000)) for x in p.prices if x.recorded_at.date() == SPLIT
    )
    r = calculate_supplier_risk(replace(p, prices=p.prices + extra))
    assert r.components["price_drift"].risk == D(".5")
    one = tuple(
        replace(x, product_id=UUID(int=100), base_unit=str(i // 2)) for i, x in enumerate(p.prices)
    )
    assert calculate_supplier_risk(replace(p, prices=one)).components["price_drift"].risk is None


@pytest.mark.parametrize(
    ("due", "reason"),
    [
        (None, "no_expected_date"),
        (END, "not_yet_due"),
        (START - timedelta(days=1), "outside_window"),
    ],
)
def test_reliability_date_exclusions(due: date | None, reason: str) -> None:
    p = fixture()
    p = replace(
        p, purchase_orders=tuple(replace(o, expected_delivery_date=due) for o in p.purchase_orders)
    )
    c = calculate_supplier_risk(p).components["reliability"]
    assert c.risk is None
    assert c.excluded_counts[reason] == 6


def test_overdelivery_cannot_complete_another_line() -> None:
    p = fixture()
    orders = tuple(
        replace(o, lines=o.lines + (replace(o.lines[0], id=UUID(int=o.id.int + 90000)),))
        for o in p.purchase_orders
    )
    receipts = tuple(replace(r, quantity=D(20)) for r in p.receipts)
    assert (
        calculate_supplier_risk(replace(p, purchase_orders=orders, receipts=receipts))
        .components["reliability"]
        .risk
        == 1
    )


def test_history_maturity_and_window_edges() -> None:
    p = fixture(10)
    p = replace(
        p,
        purchase_orders=tuple(
            replace(o, ordered_on=max(o.ordered_on, START + timedelta(days=1)))
            for o in p.purchase_orders
        ),
        prices=tuple(
            replace(x, recorded_at=max(x.recorded_at, stamp(START + timedelta(days=1))))
            for x in p.prices
        ),
    )
    r = calculate_supplier_risk(p)
    assert r.observed_history_days == 179
    assert r.state == "provisional"
    outside = tuple(replace(x, recorded_at=stamp(END)) for x in p.prices)
    c = calculate_supplier_risk(replace(p, prices=outside)).components["price_drift"]
    assert c.risk is None
    assert c.excluded_counts["outside_window"] == 20


def test_excluded_price_does_not_extend_history_maturity() -> None:
    p = fixture(10)
    p = replace(
        p,
        purchase_orders=tuple(
            replace(o, ordered_on=max(o.ordered_on, START + timedelta(days=1)))
            for o in p.purchase_orders
        ),
        prices=tuple(
            replace(x, recorded_at=max(x.recorded_at, stamp(START + timedelta(days=1))))
            for x in p.prices
        ),
    )
    excluded = replace(p.prices[0], id=UUID(int=999999), recorded_at=stamp(START), unit_price=D(-1))
    assert calculate_supplier_risk(replace(p, prices=p.prices + (excluded,))).state == "provisional"


def test_older_valid_history_can_establish_maturity() -> None:
    p = fixture(10)
    older = replace(
        p.prices[0],
        id=UUID(int=999998),
        recorded_at=stamp(START - timedelta(days=30)),
        unit_price=D(100),
    )
    result = calculate_supplier_risk(replace(p, prices=p.prices + (older,)))
    assert result.observed_history_days == 210
    assert result.state == "ready"


def test_currency_samples_cannot_be_pooled() -> None:
    p = fixture()
    orders = tuple(
        replace(o, currency="USD" if i < 2 else "EUR" if i < 4 else "GBP")
        for i, o in enumerate(p.purchase_orders)
    )
    assert (
        calculate_supplier_risk(replace(p, purchase_orders=orders)).components["concentration"].risk
        is None
    )


@pytest.mark.parametrize("change", ["unit", "currency", "supplier", "unpaired"])
def test_price_groups_never_cross_match(change: str) -> None:
    p = fixture()
    changes = {
        "unit": {"base_unit": "g"},
        "currency": {"currency": "EUR"},
        "supplier": {"supplier_id": OTHER},
        "unpaired": {"recorded_at": stamp(START)},
    }
    prices = tuple(
        replace(x, **changes[change]) if x.recorded_at.date() == SPLIT else x for x in p.prices
    )
    assert calculate_supplier_risk(replace(p, prices=prices)).components["price_drift"].risk is None


def test_precision_only_changes_at_serialization() -> None:
    p = fixture(price="101")
    orders = p.purchase_orders + tuple(
        replace(o, supplier_id=OTHER, id=UUID(int=o.id.int + 90000), amount=D(200))
        for o in p.purchase_orders
    )
    r = calculate_supplier_risk(replace(p, purchase_orders=orders))
    assert r.components["concentration"].risk == D(1) / D(3)
    assert r.model_dump(mode="json")["components"]["concentration"]["risk"] == "0.3333"
    assert r.components["concentration"].risk == D(1) / D(3)


def test_invalid_windows_and_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="equal"):
        SupplierRiskInput(supplier_id=S, window_end=END, split_date=START)
    p = fixture()
    with pytest.raises(ValueError, match="Duplicate"):
        replace(p, receipts=p.receipts + p.receipts)


def test_source_projection_rejects_non_decimal_and_duplicate_lines() -> None:
    with pytest.raises(ValueError, match="quantity"):
        OrderLine(UUID(int=900), UUID(int=901), "kg", 1.0)
    line = OrderLine(UUID(int=900), UUID(int=901), "kg", D(1))
    with pytest.raises(ValueError, match="amount"):
        PurchaseOrder(UUID(int=902), S, START, START, "received", 1.0, "USD", (line,))
    with pytest.raises(ValueError, match="Duplicate order line IDs"):
        PurchaseOrder(UUID(int=902), S, START, START, "received", D(1), "USD", (line, line))


def test_v2_results_are_immutable_and_large_decimals_serialize() -> None:
    result = calculate_supplier_risk(fixture())
    with pytest.raises(ValidationError):
        result.score = D("99")
    with pytest.raises(ValidationError):
        result.components["price_drift"].risk = D("99")
    with pytest.raises(TypeError):
        result.components["price_drift"] = result.components["concentration"]
    with pytest.raises(TypeError):
        result.weights["concentration"] = D("99")
    with pytest.raises(TypeError):
        result.components["concentration"].source_ids[0] = UUID(int=999999)
    with pytest.raises(TypeError):
        result.components["concentration"].currency_buckets[0] = result.components[
            "concentration"
        ].currency_buckets[0]
    large = replace(
        fixture(),
        purchase_orders=tuple(
            replace(order, amount=D("1e25")) for order in fixture().purchase_orders
        ),
    )
    concentration = calculate_supplier_risk(large).model_dump(mode="json")["components"][
        "concentration"
    ]
    assert concentration["currency_buckets"][0]["tenant_spend"].startswith(
        "60000000000000000000000000"
    )


def test_plan_public_score_example() -> None:
    p = fixture(4)
    other = tuple(
        replace(o, supplier_id=OTHER, id=UUID(int=o.id.int + 50000), amount=D(60))
        for o in p.purchase_orders
    )
    alternatives = tuple(
        Alternative(
            UUID(int=40000 + i), OTHER, UUID(int=100 + i), "kg", "USD", D(90), stamp(START), START
        )
        for i in range(2)
    )
    p = replace(p, purchase_orders=p.purchase_orders + other, alternatives=alternatives)
    result = calculate_supplier_risk(
        SupplierRiskInput(
            supplier_id=S,
            window_start=START,
            split_date=SPLIT,
            window_end=END,
            purchase_orders=p.purchase_orders,
            receipts=p.receipts,
            prices=p.prices,
            alternatives=p.alternatives,
        )
    )
    assert result.components["price_drift"].risk == D(".5000")
    assert result.score == D(".4125")
    assert result.release_posture == "g3_unmet"


@pytest.mark.parametrize("baseline", [False, True])
def test_failure_rate_without_positive_decay(baseline: bool) -> None:
    p = fixture(4)
    # Current 3/4 success; baseline 0/4 success (or no observations).
    receipts = tuple(r for r in p.receipts if r.received_at.date() == SPLIT)[1:]
    orders = (
        p.purchase_orders
        if baseline
        else tuple(o for o in p.purchase_orders if o.expected_delivery_date == SPLIT)
    )
    c = calculate_supplier_risk(replace(p, purchase_orders=orders, receipts=receipts)).components[
        "reliability"
    ]
    assert c.risk == D(".25")


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("same", "inactive_or_same_supplier"),
        ("future_record", "invalid_observation"),
        ("future_valid", "invalid_observation"),
        ("negative", "negative_price"),
    ],
)
def test_alternative_exclusions(kind: str, reason: str) -> None:
    p = fixture()
    row = Alternative(
        UUID(int=40000), OTHER, UUID(int=100), "kg", "USD", D(10), stamp(START), START
    )
    changes = {
        "same": {"supplier_id": S},
        "future_record": {"recorded_at": stamp(END)},
        "future_valid": {"valid_from": END + timedelta(days=1)},
        "negative": {"unit_price": D(-1)},
    }
    c = calculate_supplier_risk(
        replace(p, alternatives=(replace(row, **changes[kind]),))
    ).components["single_source"]
    assert c.risk == 1
    assert c.excluded_counts[reason] == 1


def test_fingerprint_timezone_line_order_and_versions() -> None:
    from datetime import timezone

    from procurepilot_api.modules.offers import supplier_iq_v2 as module

    p = fixture()
    first = p.purchase_orders[0]
    second_line = OrderLine(UUID(int=999997), first.lines[0].product_id, "kg", D(1))
    nested = replace(first, lines=(first.lines[0], second_line))
    nested_reversed = replace(first, lines=(second_line, first.lines[0]))
    assert source_fingerprint(
        replace(p, purchase_orders=(nested,) + p.purchase_orders[1:])
    ) == source_fingerprint(replace(p, purchase_orders=(nested_reversed,) + p.purchase_orders[1:]))
    changed = replace(
        p,
        receipts=tuple(
            replace(r, received_at=r.received_at.astimezone(timezone(timedelta(hours=2))))
            for r in p.receipts
        ),
    )
    assert source_fingerprint(p) == source_fingerprint(changed)
    assert module.__all__ == [
        "RISK_VERSION",
        "SCORECARD_VERSION",
        "SupplierRiskInput",
        "SupplierRiskResult",
        "calculate_supplier_risk",
        "source_fingerprint",
    ]
    r = calculate_supplier_risk(p)
    assert r.risk_version == "supplier-risk-v2"
    assert r.scorecard_version == "supplier-scorecard-v2"
    for c in r.components.values():
        assert c.source_ids == tuple(sorted(set(c.source_ids)))
        assert (c.window_start, c.split_date, c.window_end) == (START, SPLIT, END)
        assert c.calculation_version == r.risk_version
