"""Unit tests for ProductMatchingService tie-breaking logic (R3.2, US2, task T018).

Pure unit tests with mocked candidate lists and no database connection:
- Single confident candidate meeting threshold is selected
- Multiple equally-qualifying candidates left unmatched (bundle-vs-component edge case)
- Zero qualifying candidates left unmatched (low confidence or empty list)
- Exact threshold boundary handling (ge=0.9200 vs lt=0.9200)
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from procurepilot_api.config import Settings
from procurepilot_api.modules.matching.search import SimilarityCandidate
from procurepilot_api.modules.pos.matching_service import ProductMatchingService


@pytest.fixture
def matching_service() -> ProductMatchingService:
    # Uses default threshold 0.9200
    return ProductMatchingService()


def _make_candidate(confidence: str | float | Decimal) -> SimilarityCandidate:
    return SimilarityCandidate(
        workspace_product_id=uuid4(),
        confidence=Decimal(str(confidence)),
        reasons={"lexical_similarity": str(confidence)},
    )


def test_single_confident_match_qualifies(matching_service: ProductMatchingService) -> None:
    """A single candidate clearing 0.9200 auto-accept threshold is selected."""
    c1 = _make_candidate("0.9500")
    c2 = _make_candidate("0.8500")
    c3 = _make_candidate("0.7000")

    selected = matching_service.select_candidate([c1, c2, c3])
    assert selected is not None
    assert selected.workspace_product_id == c1.workspace_product_id
    assert selected.confidence == Decimal("0.9500")


def test_multiple_equally_qualifying_candidates_left_unmatched(
    matching_service: ProductMatchingService,
) -> None:
    """When multiple candidates clear the threshold (e.g. bundle vs component), leave unmatched."""
    c1 = _make_candidate("0.9600")
    c2 = _make_candidate("0.9400")  # both >= 0.9200
    c3 = _make_candidate("0.7000")

    selected = matching_service.select_candidate([c1, c2, c3])
    assert selected is None


def test_zero_qualifying_candidates_left_unmatched(
    matching_service: ProductMatchingService,
) -> None:
    """When no candidate clears the threshold, leave unmatched for manual review."""
    c1 = _make_candidate("0.8900")
    c2 = _make_candidate("0.8500")
    c3 = _make_candidate("0.6000")

    selected = matching_service.select_candidate([c1, c2, c3])
    assert selected is None


def test_empty_candidate_list_left_unmatched(
    matching_service: ProductMatchingService,
) -> None:
    """An empty candidate list returns None."""
    selected = matching_service.select_candidate([])
    assert selected is None


def test_exact_threshold_boundary_clears_or_refuses(
    matching_service: ProductMatchingService,
) -> None:
    """A candidate at exactly 0.9200 qualifies; a candidate at 0.9199 does not."""
    c_exact = _make_candidate("0.9200")
    c_below = _make_candidate("0.9199")

    # Single candidate right on threshold
    assert matching_service.select_candidate([c_exact]) is not None

    # Single candidate just below threshold
    assert matching_service.select_candidate([c_below]) is None


def test_custom_threshold_setting() -> None:
    """Custom settings threshold is respected."""
    custom_service = ProductMatchingService(
        Settings(
            MATCHING_AUTO_ACCEPT_THRESHOLD=0.95,
        )
    )
    c1 = _make_candidate("0.9300")  # < 0.95
    assert custom_service.select_candidate([c1]) is None

    c2 = _make_candidate("0.9600")  # >= 0.95
    assert custom_service.select_candidate([c2]) is not None
