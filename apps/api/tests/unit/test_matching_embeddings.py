import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from procurepilot_api.modules.matching.embeddings import (
    DEFAULT_BEDROCK_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    BedrockEmbeddingProvider,
    StubEmbeddingProvider,
    get_embedding_provider,
)
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
    assert semantic_threshold_for_model(DEFAULT_BEDROCK_EMBEDDING_MODEL) == SEMANTIC_THRESHOLD


def test_embedding_provider_factory_selects_mode_and_titan_model() -> None:
    stub = get_embedding_provider(
        SimpleNamespace(
            matching_embedding_provider_mode="stub", matching_embedding_model="stub-hash-v1"
        )
    )
    bedrock = get_embedding_provider(
        SimpleNamespace(
            matching_embedding_provider_mode="bedrock", matching_embedding_model="stub-hash-v1"
        )
    )
    assert isinstance(stub, StubEmbeddingProvider)
    assert isinstance(bedrock, BedrockEmbeddingProvider)
    assert bedrock.model == DEFAULT_BEDROCK_EMBEDDING_MODEL


def test_matching_service_default_settings_keep_stub_embedding_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.modules.matching.service import MatchingService

    default_settings = SimpleNamespace(
        matching_embedding_provider_mode="stub", matching_embedding_model="stub-hash-v1"
    )
    monkeypatch.setattr(
        "procurepilot_api.modules.matching.service.get_settings", lambda: default_settings
    )
    service = MatchingService()
    assert isinstance(service._embeddings, StubEmbeddingProvider)
    assert service._embeddings.embed("Brand product variant") == StubEmbeddingProvider().embed(
        "Brand product variant"
    )


def test_bedrock_embedding_provider_invokes_titan_v2_and_parses_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding = [float(i) for i in range(EMBEDDING_DIMENSION)]
    client = Mock()
    client.invoke_model.return_value = {
        "body": BytesIO(json.dumps({"embedding": embedding}).encode())
    }
    session = Mock()
    session.client.return_value = client
    boto3 = Mock(Session=Mock(return_value=session))
    monkeypatch.setitem(__import__("sys").modules, "boto3", boto3)

    result = BedrockEmbeddingProvider().embed("sample product text")

    kwargs = client.invoke_model.call_args.kwargs
    assert kwargs["modelId"] == DEFAULT_BEDROCK_EMBEDDING_MODEL
    assert json.loads(kwargs["body"]) == {
        "inputText": "sample product text",
        "dimensions": 256,
        "normalize": True,
    }
    assert result == embedding
    assert len(result) == EMBEDDING_DIMENSION


def test_stub_embedding_candidate_search_passes_unreachable_semantic_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, float] = {}

    def fake_search_rows(**kwargs: object) -> list[dict[str, object]]:
        seen["semantic_threshold"] = float(kwargs["semantic_threshold"])
        return []

    monkeypatch.setattr("procurepilot_api.modules.matching.search._search_rows", fake_search_rows)

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
