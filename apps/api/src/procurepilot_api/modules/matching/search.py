from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from postgrest.exceptions import APIError

from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider, vector_literal
from procurepilot_api.modules.matching.scoring import ScoreInputs, reason_payload, score_candidate

PRODUCT_COLUMNS = (
    "id,tenant_id,canonical_product_id,tenant_name,preferred_supplier_id,status,created_at"
)
CANONICAL_COLUMNS = "id,brand,name,variant,gtin,base_unit,created_at"
SEMANTIC_THRESHOLD = 0.10


@dataclass(frozen=True)
class SimilarityCandidate:
    workspace_product_id: UUID
    confidence: Decimal
    reasons: dict[str, object]


def build_similarity_candidates(
    *,
    client: object,
    line: dict[str, object],
    embedding_provider: StubEmbeddingProvider,
    trigram_threshold: float,
    limit: int = 5,
) -> list[SimilarityCandidate]:
    line_text = str(line.get("original_text") or "")
    rows = _search_rows(
        client=client,
        line_text=line_text,
        line_embedding=vector_literal(embedding_provider.embed(line_text)),
        trigram_threshold=trigram_threshold,
        semantic_threshold=SEMANTIC_THRESHOLD,
        limit=limit,
    )
    products = _products_by_id(
        client,
        [UUID(str(row["workspace_product_id"])) for row in rows],
    )
    candidates: list[SimilarityCandidate] = []
    for row in rows:
        product = products.get(str(row["workspace_product_id"]))
        if product is None:
            continue
        inputs = ScoreInputs(
            lexical_similarity=Decimal(str(row["lexical_similarity"])),
            semantic_similarity=Decimal(str(row["semantic_similarity"])),
            brand_match=_contains(line_text, product.get("brand")),
            variant_match=_contains(line_text, product.get("variant")),
            pack_unit_match=_unit_match(line, product),
            pack_size_plausibility=None,
            price_plausibility=None,
        )
        candidates.append(
            SimilarityCandidate(
                workspace_product_id=UUID(str(row["workspace_product_id"])),
                confidence=score_candidate(inputs),
                reasons=reason_payload(inputs=inputs),
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)[:limit]


def _search_rows(
    *,
    client: object,
    line_text: str,
    line_embedding: str,
    trigram_threshold: float,
    semantic_threshold: float,
    limit: int,
) -> list[dict[str, object]]:
    try:
        response = client.rpc(
            "match_candidate_search",
            {
                "p_line_text": line_text,
                "p_line_embedding": line_embedding,
                "p_trigram_threshold": trigram_threshold,
                "p_semantic_threshold": semantic_threshold,
                "p_limit": limit,
            },
        ).execute()
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return _rows(response.data)


def _products_by_id(
    client: object,
    product_ids: list[UUID],
) -> dict[str, dict[str, object]]:
    if not product_ids:
        return {}
    try:
        product_rows = _rows(
            client.table("workspace_product")
            .select(PRODUCT_COLUMNS)
            .in_("id", [str(product_id) for product_id in product_ids])
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    canonical = _canonical_by_id(
        client,
        [UUID(str(row["canonical_product_id"])) for row in product_rows],
    )
    hydrated: dict[str, dict[str, object]] = {}
    for row in product_rows:
        canonical_row = canonical.get(str(row["canonical_product_id"]))
        if canonical_row is None:
            continue
        hydrated[str(row["id"])] = {
            "id": row["id"],
            "tenant_name": row["tenant_name"],
            "status": row["status"],
            "brand": canonical_row.get("brand"),
            "canonical_name": canonical_row["name"],
            "variant": canonical_row.get("variant"),
            "gtin": canonical_row.get("gtin"),
            "base_unit": canonical_row["base_unit"],
        }
    return hydrated


def _canonical_by_id(
    client: object,
    canonical_ids: list[UUID],
) -> dict[str, dict[str, object]]:
    if not canonical_ids:
        return {}
    try:
        rows = _rows(
            client.table("canonical_product")
            .select(CANONICAL_COLUMNS)
            .in_("id", [str(canonical_id) for canonical_id in canonical_ids])
            .execute()
            .data
        )
    except APIError as exc:
        raise ServiceUnavailableError(details={"dependency": "database"}) from exc
    return {str(row["id"]): row for row in rows}


def _contains(text: str, value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal("1") if str(value).casefold() in text.casefold() else Decimal("0")


def _unit_match(line: dict[str, object], product: dict[str, object]) -> Decimal | None:
    pack = line.get("pack")
    if isinstance(pack, dict) and pack.get("unit") and product.get("base_unit"):
        return Decimal("1") if str(pack["unit"]) == str(product["base_unit"]) else Decimal("0")
    return None


def _rows(data: object) -> list[dict[str, object]]:
    if isinstance(data, list) and all(isinstance(row, dict) for row in data):
        return data
    raise ServiceUnavailableError(details={"reason": "invalid_database_response"})
