import pytest

from procurepilot_api.modules.matching.embeddings import EMBEDDING_DIMENSION, StubEmbeddingProvider
from procurepilot_api.modules.matching.search import (
    SEMANTIC_THRESHOLD,
    UNREACHABLE_SEMANTIC_THRESHOLD,
    build_similarity_candidates,
    semantic_threshold_for_model,
)


def test_stub_embedding_provider_is_versioned_deterministic_and_256_dimensional() -> None:
    provider = StubEmbeddingProvider("stub-hash-v1")
    first = provider.embed("Brand product variant")
    second = provider.embed("Brand product variant")
    assert provider.model == "stub-hash-v1"
    assert EMBEDDING_DIMENSION == 256
    assert len(first) == 256
    assert first == second


def test_stub_embedding_model_uses_unreachable_semantic_threshold() -> None:
    assert semantic_threshold_for_model("stub-hash-v1") == UNREACHABLE_SEMANTIC_THRESHOLD
    assert semantic_threshold_for_model("real-embedding-v1") == SEMANTIC_THRESHOLD


def test_stub_embedding_candidate_search_passes_unreachable_semantic_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, float] = {}

    def fake_search_rows(**kwargs: object) -> list[dict[str, object]]:
        seen["semantic_threshold"] = float(kwargs["semantic_threshold"])
        return []

    monkeypatch.setattr(
        "procurepilot_api.modules.matching.search._search_rows", fake_search_rows
    )

    assert (
        build_similarity_candidates(
            client=object(),
            line={"original_text": "same supplier wording"},
            embedding_provider=StubEmbeddingProvider("stub-hash-v1"),
            trigram_threshold=0.30,
        )
        == []
    )
    assert seen["semantic_threshold"] == UNREACHABLE_SEMANTIC_THRESHOLD
