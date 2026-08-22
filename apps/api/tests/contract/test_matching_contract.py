from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from procurepilot_api.modules.matching.schemas import (
    FeatureScore,
    MatchCandidate,
    MatchDecision,
    MatchReason,
    ProductSummary,
    QuotationLineMatchState,
    QuotationLineSummary,
    QuotationMatches,
)


def test_quotation_matches_contract_shape_requires_candidates_with_structured_reasons() -> None:
    line_id = uuid4()
    product = ProductSummary(
        id=uuid4(),
        tenant_name="Tenant milk",
        brand="Brand",
        canonical_name="Milk",
        variant=None,
        gtin=None,
        base_unit="litre",
        status="active",
    )
    candidate = MatchCandidate(
        id=uuid4(),
        quotation_line_id=line_id,
        candidate_product=product,
        confidence="0.9200",
        reasons=MatchReason(
            alias_hit=True,
            gtin_match=False,
            supplier_code_match=False,
            lexical_similarity="1.0000",
            semantic_similarity="1.0000",
            feature_score=FeatureScore(
                brand_match="1.0000",
                variant_match="0.5000",
                pack_unit_match="1.0000",
                pack_size_plausibility="0.5000",
                price_plausibility="0.5000",
            ),
        ),
        rank=1,
        scoring_version="matching-score-v1",
        embedding_model="stub-hash-v1",
        created_at=datetime.now(UTC),
    )
    decision = MatchDecision(
        id=uuid4(),
        quotation_line_id=line_id,
        matched_product=product,
        selected_match_candidate_id=candidate.id,
        outcome="same_product",
        is_automatic=True,
        decided_at=datetime.now(UTC),
        confidence="0.9200",
    )
    payload = QuotationMatches(
        quotation_id=uuid4(),
        lines=[
            QuotationLineMatchState(
                line=QuotationLineSummary(id=line_id, line_number=1, original_text="Brand milk"),
                candidates=[candidate],
                decision=decision,
            )
        ],
    )
    dumped = payload.model_dump(mode="json")
    assert dumped["lines"][0]["candidates"][0]["reasons"]["alias_hit"] is True
    assert dumped["lines"][0]["decision"]["is_automatic"] is True


def test_match_candidate_contract_rejects_bare_score_without_reason() -> None:
    product = ProductSummary(
        id=uuid4(),
        tenant_name="Tenant milk",
        canonical_name="Milk",
        base_unit="litre",
        status="active",
    )
    try:
        MatchCandidate(
            id=uuid4(),
            quotation_line_id=uuid4(),
            candidate_product=product,
            confidence="0.9200",
            rank=1,
            created_at=datetime.now(UTC),
        )
    except ValidationError as exc:
        assert "reasons" in str(exc)
    else:
        raise AssertionError("MatchCandidate accepted a bare score without structured reasons")
