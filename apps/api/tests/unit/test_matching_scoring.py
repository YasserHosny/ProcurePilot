from decimal import Decimal

from procurepilot_api.modules.matching.scoring import WEIGHTS, ScoreInputs, score_candidate


def test_matching_scoring_uses_research_r5_weights_exactly() -> None:
    assert WEIGHTS == {
        "deterministic": Decimal("0.30"),
        "lexical": Decimal("0.20"),
        "semantic": Decimal("0.20"),
        "brand": Decimal("0.10"),
        "variant": Decimal("0.07"),
        "pack_unit": Decimal("0.06"),
        "pack_size": Decimal("0.04"),
        "price": Decimal("0.03"),
    }
    assert score_candidate(
        ScoreInputs(
            deterministic_signal=Decimal("1"),
            lexical_similarity=Decimal("0.8"),
            semantic_similarity=Decimal("0.7"),
            brand_match=Decimal("1"),
            variant_match=Decimal("0"),
            pack_unit_match=Decimal("1"),
            pack_size_plausibility=Decimal("0.75"),
            price_plausibility=Decimal("0.25"),
        )
    ) == Decimal("0.7975")


def test_missing_optional_features_are_neutral_not_zero() -> None:
    assert score_candidate(
        ScoreInputs(lexical_similarity=Decimal("1"), semantic_similarity=Decimal("1"))
    ) == Decimal("0.5500")
