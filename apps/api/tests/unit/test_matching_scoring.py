from decimal import Decimal

from procurepilot_api.modules.matching.scoring import (
    SCORING_VERSION,
    WEIGHTS,
    WEIGHTS_STUB_EMBEDDING,
    ScoreInputs,
    active_weights,
    score_candidate,
)


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
        ),
        embedding_model="real-embedding-v1",
    ) == Decimal("0.7975")


def test_stub_embedding_weight_is_redistributed_to_lexical_and_versioned() -> None:
    assert SCORING_VERSION == "matching-score-v2"
    assert WEIGHTS_STUB_EMBEDDING == {
        "deterministic": Decimal("0.30"),
        "lexical": Decimal("0.40"),
        "semantic": Decimal("0.00"),
        "brand": Decimal("0.10"),
        "variant": Decimal("0.07"),
        "pack_unit": Decimal("0.06"),
        "pack_size": Decimal("0.04"),
        "price": Decimal("0.03"),
    }
    assert active_weights("stub-hash-v1") == WEIGHTS_STUB_EMBEDDING
    assert active_weights("real-embedding-v1") == WEIGHTS
    assert score_candidate(
        ScoreInputs(
            deterministic_signal=Decimal("1"),
            lexical_similarity=Decimal("0.8"),
            semantic_similarity=Decimal("0.0"),
            brand_match=Decimal("1"),
            variant_match=Decimal("0"),
            pack_unit_match=Decimal("1"),
            pack_size_plausibility=Decimal("0.75"),
            price_plausibility=Decimal("0.25"),
        )
    ) == Decimal("0.8175")


def test_missing_optional_features_are_neutral_not_zero() -> None:
    assert score_candidate(
        ScoreInputs(lexical_similarity=Decimal("1"), semantic_similarity=Decimal("1"))
    ) == Decimal("0.5500")
