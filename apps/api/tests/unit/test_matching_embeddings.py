from procurepilot_api.modules.matching.embeddings import EMBEDDING_DIMENSION, StubEmbeddingProvider


def test_stub_embedding_provider_is_versioned_deterministic_and_256_dimensional() -> None:
    provider = StubEmbeddingProvider("stub-hash-v1")
    first = provider.embed("Brand product variant")
    second = provider.embed("Brand product variant")
    assert provider.model == "stub-hash-v1"
    assert EMBEDDING_DIMENSION == 256
    assert len(first) == 256
    assert first == second
