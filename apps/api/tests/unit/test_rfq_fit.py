from decimal import Decimal
from uuid import uuid4

import pytest

from procurepilot_api.modules.matching.rfq_fit import (
    RfqFit,
    fit_against_rfq,
    normalise_text,
    trigram_similarity,
)
from procurepilot_api.modules.rfq.read_api import RfqContext, RfqLineContext

TEXTS = ("أرز بسمتي", "زيت دوار الشمس", "سكر أبيض", "دقيق")
NAMES = (
    "أرز بسمتي (كيس 10 كجم)",
    "زيت دوار الشمس (تنكة 18 لتر)",
    "سكر أبيض (كيس 10 كجم)",
    "دقيق (كيس 45 كجم)",
)


def context(names: tuple[str, ...] = NAMES) -> RfqContext:
    return RfqContext(
        uuid4(),
        tuple(
            RfqLineContext(
                uuid4(), i * 10, uuid4(), name, Decimal("8"), "kilogram", Decimal("10"), ()
            )
            for i, name in enumerate(names)
        ),
    )


def fit(
    text: str,
    rfq: RfqContext,
    *,
    rank: int = 1,
    pack: str | None = None,
    floor: str = "0.30",
    margin: str = "0.15",
) -> RfqFit:
    return fit_against_rfq(
        original_text=text,
        pack_count=Decimal("1") if pack else None,
        unit_size=Decimal(pack) if pack else None,
        pack_unit="kilogram",
        rank=rank,
        context=rfq,
        floor=Decimal(floor),
        margin=Decimal(margin),
    )


@pytest.mark.parametrize(("rank", "text"), enumerate(TEXTS, start=1))
def test_round_one_missing_pack_matches_only_its_own_stem(rank: int, text: str) -> None:
    rfq = context()
    result = fit(text, rfq, rank=rank)
    assert result.matched_rfq_line == rfq.lines[rank - 1]
    assert result.fitting_lines == (rfq.lines[rank - 1],)
    assert result.pack_check == "unknown"
    assert result.reasons["rfq"]["rule_version"] == "rfq-fit-v1"
    assert result.reasons["rfq"]["wording_score"] == "1.0000"
    assert result.reasons["measured"] == {"lexical_similarity": "1.0000"}


@pytest.mark.parametrize(
    ("rank", "text"),
    [(1, "أرز بسمتي هندي"), (3, "سكر أبيض ناعم"), (4, "دقيق فاخر")],
)
def test_a_supplier_adding_a_word_still_matches_through_the_stem(rank: int, text: str) -> None:
    """The bracketed pack is not part of the wording: «دقيق فاخر» answers «دقيق (كيس 45 كجم)».
    Without the stem, neither containment nor raw trigrams reach the floor (review finding)."""
    rfq = context()
    result = fit(text, rfq, rank=rank)
    assert result.matched_rfq_line == rfq.lines[rank - 1]


def test_two_oils_are_ambiguous_even_with_position_bonus() -> None:
    rfq = context(("زيت دوار الشمس", "زيت ذرة"))
    result = fit("زيت", rfq)
    assert result.matched_rfq_line is None
    assert len(result.fitting_lines) == 2


def test_conflicting_pack_is_evidence_but_never_a_fit() -> None:
    rfq = context((NAMES[0],))
    result = fit(TEXTS[0], rfq, pack="5")
    assert result.matched_rfq_line is None
    assert not result.fitting_lines
    score = result.scores[0]
    assert score.pack_check == "conflict"
    assert score.reasons["rfq"]["quoted_pack_base_quantity"] == "5.000000"
    assert score.reasons["rfq"]["rfq_pack_base_quantity"] == "10.000000"


def test_unrequested_product_has_no_fitting_line() -> None:
    result = fit("طماطم", context())
    assert result.matched_rfq_line is None
    assert not result.fitting_lines


def test_position_cannot_create_a_fit_below_floor() -> None:
    result = fit("abcd", context(("abce",)), floor="0.45")
    assert result.scores[0].wording_score == Decimal("0.4286")
    assert result.scores[0].score == Decimal("0.4286")
    assert not result.fitting_lines


def test_missing_pack_requires_double_margin() -> None:
    rfq = context(("abcd", "abce"))
    assert fit("abcd", rfq, floor="0.9", margin="0.4", pack="10").matched_rfq_line
    assert fit("abcd", rfq, floor="0.9", margin="0.4").matched_rfq_line is None


def test_normalisation_and_pg_trgm_word_padding() -> None:
    assert normalise_text("  أَرْز ـ إآٱ ى ئ ة ١٢٣ ۴۵۶ ABC  ") == "ارز ااا ي ي ه 123 456 abc"
    assert trigram_similarity("abcd", "abce") == Decimal("0.4286")
    assert trigram_similarity("cat-cat", "cat") == Decimal("1.0000")
    assert trigram_similarity("", "") == Decimal("0.0000")


@pytest.mark.parametrize("name", ("Rice [10 kg]", "Rice （10 kg）", "Rice (bag [10 kg])"))
def test_bracket_forms_are_stripped(name: str) -> None:
    assert fit("Rice", context((name,))).matched_rfq_line is not None


def test_alias_is_a_wording_signal_and_quantity_does_not_block() -> None:
    rfq = context(("Unrelated product",))
    line = rfq.lines[0]
    from dataclasses import replace

    rfq = replace(rfq, lines=(replace(line, aliases=("أرز بسمتي",)),))
    assert fit(TEXTS[0], rfq).matched_rfq_line is not None


@pytest.mark.parametrize(
    ("size", "unit", "expected"),
    (
        ("10000", "g", "equal"),
        ("10.05", "kg", "equal"),
        ("10.051", "kg", "conflict"),
        ("10", "litre", "conflict"),
    ),
)
def test_pack_conversion_and_tolerance(size: str, unit: str, expected: str) -> None:
    rfq = context(("Rice",))
    result = fit_against_rfq(
        original_text="Rice",
        pack_count=Decimal("1"),
        unit_size=Decimal(size),
        pack_unit=unit,
        rank=1,
        context=rfq,
        floor=Decimal(".3"),
        margin=Decimal(".15"),
    )
    assert result.scores[0].pack_check == expected


def test_repeated_product_lines_never_auto_match() -> None:
    rfq = context(("Rice", "Rice"))
    assert fit("Rice", rfq).matched_rfq_line is None


def test_reordered_reply_matches_by_wording_not_position() -> None:
    rfq = context()
    assert fit(TEXTS[3], rfq, rank=1).matched_rfq_line == rfq.lines[3]


def test_excluding_an_archived_product_preserves_original_rfq_rank() -> None:
    rfq = context(("Old rice", "Flour"))
    result = fit_against_rfq(
        original_text="Flour",
        pack_count=None,
        unit_size=None,
        pack_unit=None,
        rank=1,
        context=rfq,
        floor=Decimal(".3"),
        margin=Decimal(".15"),
        excluded_products=frozenset({rfq.lines[0].workspace_product_id}),
    )
    assert result.matched_rfq_line == rfq.lines[1]
    assert result.reasons["rfq"]["position"] == 2


@pytest.mark.parametrize(
    ("field", "env", "default"),
    (
        ("matching_rfq_fit_floor", "MATCHING_RFQ_FIT_FLOOR", 0.30),
        ("matching_rfq_fit_margin", "MATCHING_RFQ_FIT_MARGIN", 0.15),
    ),
)
def test_rfq_settings_defaults_env_and_bounds(
    field: str,
    env: str,
    default: float,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic import ValidationError

    from procurepilot_api.config import Settings

    monkeypatch.delenv(env, raising=False)
    assert getattr(Settings(), field) == default
    monkeypatch.setenv(env, ".42")
    assert getattr(Settings(), field) == 0.42
    for value in ("-.01", "1.01"):
        monkeypatch.setenv(env, value)
        with pytest.raises(ValidationError):
            Settings()
