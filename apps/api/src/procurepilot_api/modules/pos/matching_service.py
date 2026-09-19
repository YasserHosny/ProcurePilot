"""Product matching service for POS and inventory integration (R3.2, task T017).

Matches synced_product_signal rows to workspace_product rows by reusing:
- modules/matching/search.py: build_similarity_candidates
- modules/matching/embeddings.py: StubEmbeddingProvider
- config.py: pos_matching_auto_accept_threshold (default 0.9000)

Enforces FR-006:
Only creates an automatic match when EXACTLY ONE candidate clears the auto-accept
confidence threshold. Zero or multiple qualifying candidates are left unmatched
for manual review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider
from procurepilot_api.modules.matching.search import (
    SimilarityCandidate,
    build_similarity_candidates,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _QueryResponse:
    """Mimics the small slice of the supabase-py response shape build_similarity_candidates
    actually reads (`.data`), so it can run unmodified against a raw psycopg connection."""

    data: list[dict[str, object]] = field(default_factory=list)


class _RpcQuery:
    def __init__(
        self, conn: psycopg.Connection, fn_name: str, params: dict[str, object]
    ) -> None:
        self._conn = conn
        self._fn_name = fn_name
        self._params = params

    def execute(self) -> _QueryResponse:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select workspace_product_id, lexical_similarity, semantic_similarity
                from match_candidate_search(
                    %(p_line_text)s::text,
                    %(p_line_embedding)s::vector,
                    %(p_trigram_threshold)s::real,
                    %(p_semantic_threshold)s::real,
                    %(p_limit)s::integer
                )
                """,
                self._params,
            )
            rows = [dict(r) for r in cur.fetchall()]
        return _QueryResponse(data=rows)


class _TableQuery:
    def __init__(self, conn: psycopg.Connection, table_name: str) -> None:
        self._conn = conn
        self._table_name = table_name
        self._columns = "*"
        self._in_col: str | None = None
        self._in_vals: list[str] = []

    def select(self, columns: str) -> _TableQuery:
        self._columns = columns
        return self

    def in_(self, col: str, vals: list[str]) -> _TableQuery:
        self._in_col = col
        self._in_vals = vals
        return self

    def execute(self) -> _QueryResponse:
        if not self._in_vals:
            return _QueryResponse(data=[])
        with self._conn.cursor(row_factory=dict_row) as cur:
            query = (
                f"select {self._columns} from {self._table_name} "
                f"where {self._in_col} = any(%(vals)s)"
            )
            cur.execute(query, {"vals": self._in_vals})
            rows = [dict(r) for r in cur.fetchall()]
        return _QueryResponse(data=rows)


class PsycopgSearchClient:
    """Adapter allowing build_similarity_candidates to run directly against Postgres via psycopg."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def rpc(self, fn_name: str, params: dict[str, object]) -> _RpcQuery:
        return _RpcQuery(self._conn, fn_name, params)

    def table(self, table_name: str) -> _TableQuery:
        return _TableQuery(self._conn, table_name)


class ProductMatchingService:
    """T017: Matches POS signals to workspace products using similarity search."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._embeddings = StubEmbeddingProvider(self._settings.matching_embedding_model)

    @property
    def auto_accept_threshold(self) -> Decimal:
        return Decimal(str(self._settings.pos_matching_auto_accept_threshold))

    @staticmethod
    def name_similarity(candidate: SimilarityCandidate) -> Decimal:
        """The raw lexical/semantic similarity a bare item name actually carries.

        candidate.confidence is quotation-line matching's composite score, weighted 30% on a
        deterministic (GTIN) signal that a bare POS item name never has — that composite score
        cannot clear a meaningful auto-accept bar even for a perfect name match (see
        config.py's pos_matching_auto_accept_threshold comment). Use the two signals a name
        search actually produces instead.
        """
        lexical = Decimal(str(candidate.reasons.get("lexical_similarity", "0")))
        semantic = Decimal(str(candidate.reasons.get("semantic_similarity", "0")))
        return max(lexical, semantic)

    def select_candidate(
        self,
        candidates: list[SimilarityCandidate],
    ) -> SimilarityCandidate | None:
        """Tie-breaking logic for candidate selection (FR-006, T017).

        Returns candidate only if EXACTLY ONE candidate clears auto_accept_threshold.
        Zero candidates or multiple qualifying candidates return None (left unmatched).
        """
        threshold = self.auto_accept_threshold
        qualifying = [c for c in candidates if self.name_similarity(c) >= threshold]
        if len(qualifying) == 1:
            return qualifying[0]
        return None

    def match_signal(
        self,
        signal: dict[str, object] | object,
        *,
        conn: psycopg.Connection,
        client: object | None = None,
    ) -> UUID | None:
        """Attempt to match a synced product signal to a workspace product.

        If exactly one candidate meets or exceeds matching_auto_accept_threshold,
        inserts a pos_product_match row (match_method='automatic') and returns its id.
        Otherwise leaves unmatched for manual review and returns None.
        """
        tenant_id = (
            signal["tenant_id"] if isinstance(signal, dict) else signal.tenant_id
        )
        signal_id = signal["id"] if isinstance(signal, dict) else signal.id
        external_item_name = (
            signal["external_item_name"]
            if isinstance(signal, dict)
            else signal.external_item_name
        )

        with conn.cursor(row_factory=dict_row) as cur:
            # Check if this signal already has a match
            cur.execute(
                """
                select id from pos_product_match
                where tenant_id = %(tenant_id)s and synced_product_signal_id = %(signal_id)s
                """,
                {"tenant_id": tenant_id, "signal_id": signal_id},
            )
            if cur.fetchone() is not None:
                return None

        search_client = client or PsycopgSearchClient(conn)
        candidates = build_similarity_candidates(
            client=search_client,
            line={"original_text": external_item_name},
            embedding_provider=self._embeddings,
            trigram_threshold=self._settings.matching_trigram_threshold,
        )

        selected = self.select_candidate(candidates)
        if selected is None:
            return None

        with conn.cursor(row_factory=dict_row) as cur:
            # Check if candidate workspace_product is already matched elsewhere (1:1 constraint)
            cur.execute(
                """
                select id from pos_product_match
                where tenant_id = %(tenant_id)s and workspace_product_id = %(wp_id)s
                """,
                {"tenant_id": tenant_id, "wp_id": selected.workspace_product_id},
            )
            if cur.fetchone() is not None:
                logger.info(
                    "Candidate workspace_product %s already matched; leaving signal %s unmatched",
                    selected.workspace_product_id,
                    signal_id,
                )
                return None

            cur.execute(
                """
                insert into pos_product_match (
                    tenant_id,
                    synced_product_signal_id,
                    workspace_product_id,
                    match_method,
                    matched_by,
                    matched_at,
                    confidence
                ) values (
                    %(tenant_id)s,
                    %(synced_product_signal_id)s,
                    %(workspace_product_id)s,
                    'automatic',
                    null,
                    now(),
                    %(confidence)s
                )
                returning id
                """,
                {
                    "tenant_id": tenant_id,
                    "synced_product_signal_id": signal_id,
                    "workspace_product_id": selected.workspace_product_id,
                    "confidence": self.name_similarity(selected),
                },
            )
            match_row = cur.fetchone()
            return UUID(str(match_row["id"])) if match_row else None
