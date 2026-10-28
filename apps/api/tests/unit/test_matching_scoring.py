from decimal import Decimal

import pytest

from procurepilot_api.modules.matching.scoring import (
    SCORING_VERSION,
    STUB_EMBEDDING_MODEL,
    WEIGHTS,
    WEIGHTS_STUB_EMBEDDING,
    ScoreInputs,
    active_weights,
    reason_payload,
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


@pytest.mark.parametrize(
    ("embedding_model", "semantic"),
    [(STUB_EMBEDDING_MODEL, {}), ("real-embedding-v1", {"semantic_similarity": "0.7123"})],
)
def test_reasons_include_only_measured_signals_and_preserve_legacy_fields(
    embedding_model: str, semantic: dict[str, str]
) -> None:
    reasons = reason_payload(
        inputs=ScoreInputs(
            lexical_similarity=Decimal("0.81234"),
            semantic_similarity=Decimal("0.71234"),
            brand_match=None,
            variant_match=Decimal("0"),
            pack_unit_match=Decimal("1"),
            pack_size_plausibility=None,
            price_plausibility=Decimal("0.34567"),
        ),
        embedding_model=embedding_model,
    )
    assert reasons.pop("measured") == {
        "lexical_similarity": "0.8123",
        **semantic,
        "variant_match": "0.0000",
        "pack_unit_match": "1.0000",
        "price_plausibility": "0.3457",
    }
    assert reasons == {
        "alias_hit": False,
        "gtin_match": False,
        "supplier_code_match": False,
        "lexical_similarity": "0.8123",
        "semantic_similarity": "0.7123",
        "feature_score": {
            "brand_match": "0.5000",
            "variant_match": "0.0000",
            "pack_unit_match": "1.0000",
            "pack_size_plausibility": "0.5000",
            "price_plausibility": "0.3457",
        },
    }


@pytest.mark.parametrize(
    "feature",
    [
        "brand_match",
        "variant_match",
        "pack_unit_match",
        "pack_size_plausibility",
        "price_plausibility",
    ],
)
@pytest.mark.parametrize("value", [None, Decimal("0"), Decimal("0.5"), Decimal("1")])
def test_each_optional_feature_is_measured_exactly_when_supplied(
    feature: str, value: Decimal | None
) -> None:
    reasons = reason_payload(inputs=ScoreInputs(**{feature: value}))
    expected = {"lexical_similarity": "0.0000"}
    if value is not None:
        expected[feature] = format(value, ".4f")
    assert reasons["measured"] == expected


@pytest.mark.parametrize(
    ("embedding_model", "expected"),
    [(STUB_EMBEDDING_MODEL, b"0.8175"), ("real-embedding-v1", b"0.7975")],
)
def test_explanation_does_not_change_fixed_confidence_bytes(
    embedding_model: str, expected: bytes
) -> None:
    inputs = ScoreInputs(
        deterministic_signal=Decimal("1"),
        lexical_similarity=Decimal("0.8"),
        semantic_similarity=Decimal("0.7"),
        brand_match=Decimal("1"),
        variant_match=Decimal("0"),
        pack_unit_match=Decimal("1"),
        pack_size_plausibility=Decimal("0.75"),
        price_plausibility=Decimal("0.25"),
    )
    before = str(score_candidate(inputs, embedding_model=embedding_model)).encode("ascii")
    assert before == expected
    reason_payload(inputs=inputs)
    assert str(score_candidate(inputs, embedding_model=embedding_model)).encode("ascii") == before
