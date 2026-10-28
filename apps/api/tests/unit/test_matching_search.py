from unittest.mock import Mock
from uuid import uuid4

import pytest

from procurepilot_api.modules.matching import search
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider
from procurepilot_api.modules.matching.scoring import STUB_EMBEDDING_MODEL
from procurepilot_api.modules.matching.service import MatchingService


@pytest.mark.parametrize("embedding_model", [STUB_EMBEDDING_MODEL, "real-embedding-v1"])
@pytest.mark.parametrize(
    ("product", "features", "stub_confidence", "real_confidence"),
    [
        ({"brand": None, "variant": "", "base_unit": None}, {}, b"0.4700", b"0.4500"),
        (
            {"brand": "Brand", "variant": "missing", "base_unit": "litre"},
            {"brand_match": "1.0000", "variant_match": "0.0000", "pack_unit_match": "1.0000"},
            b"0.5150",
            b"0.4950",
        ),
        (
            {"brand": "missing", "variant": "missing", "base_unit": "kilogram"},
            {"brand_match": "0.0000", "variant_match": "0.0000", "pack_unit_match": "0.0000"},
            b"0.3550",
            b"0.3350",
        ),
    ],
)
def test_similarity_candidates_report_only_computed_signals_without_changing_confidence(
    monkeypatch: pytest.MonkeyPatch,
    embedding_model: str,
    product: dict[str, object],
    features: dict[str, str],
    stub_confidence: bytes,
    real_confidence: bytes,
) -> None:
    product_id = uuid4()
    monkeypatch.setattr(
        search,
        "_search_rows",
        lambda **_: [
            {
                "workspace_product_id": str(product_id),
                "lexical_similarity": "0.8",
                "semantic_similarity": "0.7",
            }
        ],
    )
    monkeypatch.setattr(search, "_products_by_id", lambda *_: {str(product_id): product})
    provider = Mock(spec=StubEmbeddingProvider, model=embedding_model)
    provider.embed.return_value = [0.0] * 256

    (candidate,) = search.build_similarity_candidates(
        client=object(),
        line={"original_text": "Brand product", "pack": {"unit": "litre"}},
        embedding_provider=provider,
        trigram_threshold=0.3,
    )

    expected = {"lexical_similarity": "0.8000", **features}
    if embedding_model != STUB_EMBEDDING_MODEL:
        expected["semantic_similarity"] = "0.7000"
    assert candidate.reasons["measured"] == expected
    assert str(candidate.confidence).encode("ascii") == (
        stub_confidence if embedding_model == STUB_EMBEDDING_MODEL else real_confidence
    )
    client = Mock()
    client.table.return_value.insert.return_value.execute.return_value.data = []
    service = MatchingService()
    service._persist_candidates(  # noqa: SLF001
        client,
        Mock(tenant_id=uuid4()),
        {"id": uuid4()},
        [
            {
                "workspace_product_id": product_id,
                "confidence": candidate.confidence,
                "reasons": candidate.reasons,
            }
        ],
    )
    (stored,) = client.table.return_value.insert.call_args.args[0]
    assert stored["confidence"].encode("ascii") == (
        stub_confidence if embedding_model == STUB_EMBEDDING_MODEL else real_confidence
    )
    assert stored["reasons"]["measured"] == expected


@pytest.mark.parametrize("missing", [None, ""])
def test_missing_product_attributes_are_not_measured(missing: object) -> None:
    assert search._contains("Brand product", missing) is None  # noqa: SLF001
    assert search._unit_match({"pack": {"unit": "litre"}}, {"base_unit": missing}) is None  # noqa: SLF001
    assert search._unit_match({}, {"base_unit": "litre"}) is None  # noqa: SLF001
