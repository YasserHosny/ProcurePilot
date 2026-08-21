# Phase 0 Research: Matching and Normalisation

**Feature**: 004-matching-normalisation | **Date**: 2026-08-21

Chunks 4.1-4.3 settled tenancy, catalogue normalisation, quotation extraction, review state and
the first real background worker. This document resolves only what matching, alias learning and
landed-cost computation add. Offer comparison, historical price aggregation and savings ledger work
remain out of scope.

---

## R1 - Matching lives inside `apps/api`

**Decision**: implement matching and landed-cost logic as two new FastAPI modules inside the
existing modular monolith: `apps/api/src/procurepilot_api/modules/matching/` and
`apps/api/src/procurepilot_api/modules/landed_cost/`. Do not create `services/matching-worker`.

**Rationale**: `docs/architecture/engineering-spec.md` §2.3 describes a future
`services/matching-worker`, but the constitution permits new services only for measured scaling or
isolation reasons, and pre-authorises only the extraction worker and optimiser when load justifies
them. Matching in this chunk is database-local computation: deterministic lookups, `pg_trgm`,
`pgvector` and scoring over already-reviewed quotation rows. It makes no third-party network call
and has none of chunk 4.3 extraction's provider-latency or provider-availability isolation needs.

Keeping the logic in `apps/api` also keeps match decisions, alias writes and landed-cost computation
inside one transaction boundary where RLS, RBAC and idempotency are already established.

**Alternatives considered**:
- *Create `services/matching-worker` as the engineering spec names* - rejected for this chunk. The
  algorithm content in that section is still used, but the deployable shape conflicts with the
  constitution and the approved plan.
- *Run matching only from the web client* - rejected. Tenant scope, database indexes, alias writes
  and landed-cost replay must be server-side.
- *Defer all matching until a queue exists* - rejected. Reviewed quotations need immediate
  downstream matching, and pilot-scale computation can run in the existing API process.

---

## R2 - Deterministic keys before similarity

**Decision**: the matching pipeline checks deterministic keys in this exact order:

1. GTIN exact match against `canonical_product.gtin`, scoped through this tenant's
   `workspace_product`.
2. Supplier product code exact match, if extraction supplies one for the line and an existing
   tenant-scoped supplier-code alias/source field has recorded it for a product.
3. Alias exact match using `lower(product_alias.alias_text) = lower(quotation_line.original_text)`,
   because the existing unique index is `(tenant_id, lower(alias_text))`.
4. Only if no deterministic key resolves the line, fall through to similarity candidate generation.

**Rationale**: deterministic keys are stronger evidence than lexical or semantic similarity and
must short-circuit the expensive stages. GTIN is the strongest product identity. Supplier product
code is exact but supplier-specific, so it remains tenant/supplier scoped. Alias exact match is the
learning loop from human decisions: once a wording has been confirmed, identical wording must not
go through similarity again.

Each deterministic candidate still creates a `match_candidate` row with confidence and structured
reason, because Principle I requires evidence even for obvious matches.

**Alternatives considered**:
- *Run similarity first and let exact keys boost the score* - slower and less explainable. A GTIN
  match should not have to compete with a fuzzy text score.
- *Alias before GTIN* - tempting for "seen before" wording, but GTIN is globally stronger product
  evidence and catches a supplier wording that changed while the barcode stayed stable.
- *Case-sensitive alias matching* - contradicts the existing catalogue uniqueness rule and would
  make `Gloves Large` and `gloves large` behave differently.

---

## R3 - `pg_trgm` lexical pass

**Decision**: use `pg_trgm` as the first similarity pass over normalised text. Compare
`quotation_line.original_text` with catalogue text from two boundary-safe sources:
`canonical_product.brand/name/variant` and `workspace_product.tenant_name`. Use Postgres
`similarity(left, right)` for scoring and the `%` operator for index-assisted prefiltering, with an
environment-backed threshold initially planned as `MATCHING_TRIGRAM_THRESHOLD=0.30`.

The search is indexable through expression trigram indexes, not a stored cross-table search column:

- `canonical_product`: GIN trigram expression index over
  `lower(concat_ws(' ', brand, name, variant))`.
- `workspace_product`: GIN trigram expression index over `lower(tenant_name)`.

Candidate generation can prefilter on either expression and combine the two lexical similarities at
query time. A stored column that mixes canonical and workspace text would have to live on a
tenant-scoped table to be safe; expression indexes avoid that extra denormalisation for this chunk.

**Rationale**: trigram similarity is fast, deterministic and works with the existing `pg_trgm`
extension and GIN/GiST index shape. It handles misspellings, reordered words and supplier prose
better than exact text search, while remaining cheap enough to narrow candidates before vector
search. It is also explainable: a candidate can say it matched because wording was similar.

The trigram stage is a recall-oriented prefilter, not a final decision. Low trigram scores can still
be rescued by deterministic keys; otherwise semantic and feature scoring decide whether a candidate
belongs in the review band.

**Alternatives considered**:
- *Full-text search only* - good for token presence, weaker for short product names, misspellings
  and supplier abbreviations.
- *Vector search over the full catalogue first* - more expensive and less transparent as a first
  pass.
- *Hard-code the trigram threshold* - rejected. Real catalogue text will tune this value over time.

---

## R4 - `pgvector` semantic pass and stub embeddings

**Decision**: store two embeddings, preserving the chunk 4.2 shared-spine boundary:

- `canonical_product.canonical_embedding vector(256)` from only
  `brand + canonical_product.name + variant`.
- `workspace_product.tenant_name_embedding vector(256)` from only `tenant_name`.

Both use the same deterministic stub dimension for this chunk: 256 components. Use cosine distance
for each vector and combine semantic similarity at query time, initially
`0.70 * canonical_similarity + 0.30 * tenant_name_similarity` when both are present, or the present
similarity alone when one side is absent. Use HNSW indexes when implementation reaches
production-like data volumes; for the first pilot implementation, exact vector scans are acceptable
until benchmark volume proves the indexes are needed.

Use a stub embedding provider in this chunk, behind the same provider interface planned for real
embeddings. The stub must be deterministic, versioned and labelled, for example
`embedding_model = stub-hash-v1`. Real embedding credentials and provider selection are not
available yet, exactly like chunk 4.3's honest treatment of extraction providers pending real
credentials.

**Rationale**: semantic similarity is useful for equivalent wording that trigrams miss:
abbreviations, translated supplier phrasing and reordered descriptions. But unlabelled or fake
semantic confidence is dangerous. A deterministic stub lets the schema, pipeline, persistence and
evaluation hooks land without pretending the quality gate has been met. The matching benchmark must
record that semantic scores came from `stub-hash-v1` and treat precision claims as unvalidated
until a real model and held-out dataset exist.

Splitting the embeddings matters for tenant isolation. `canonical_product` is deliberately the one
shared product table and must not contain workspace-specific names. A single full-text embedding on
`canonical_product` would leak `workspace_product.tenant_name` into the shared spine. A single
tenant-scoped full-text embedding on `workspace_product` would be safe but wasteful once real
embedding calls cost money, because every workspace would recompute the same canonical
brand/name/variant signal. Two embeddings keep the boundary intact and let the canonical vector be
computed once per canonical product.

Cosine distance is the default because product text embeddings are compared by direction, not
vector magnitude. HNSW is the planned index because it is the standard `pgvector` ANN index for
low-latency nearest-neighbour retrieval once catalogue size demands it.

**Alternatives considered**:
- *Skip pgvector until credentials exist* - would leave a large part of the intended pipeline
  untested and defer schema risk.
- *One tenant-scoped embedding on `workspace_product` from the full product string* - safe for
  isolation, but recomputes canonical brand/name/variant text once per tenant and becomes wasteful
  with real embedding credentials.
- *Call an external embedding API directly from matching code* - violates the no-secrets/no-real
  credentials reality of this planning phase and would add a hidden network dependency.
- *Use Euclidean distance* - less natural for text embeddings and harder to interpret consistently
  across model changes.

---

## R5 - Feature scoring and calibrated confidence

**Decision**: use a simple weighted scoring pipeline, not a trained ML model, for this chunk. Each
candidate gets component scores in `[0, 1]`, then:

```text
raw_score = 0.30 * deterministic_signal
          + 0.20 * lexical_similarity
          + 0.20 * semantic_similarity
          + 0.10 * brand_match
          + 0.07 * variant_match
          + 0.06 * pack_unit_match
          + 0.04 * pack_size_plausibility
          + 0.03 * price_plausibility
```

Deterministic candidates set `deterministic_signal = 1` and receive a deterministic reason
(`gtin_match`, `supplier_code_match` or `alias_hit`). Similarity-only candidates set it to `0`.
Missing brand, variant, pack or price data contributes neutral `0.5` for that component rather than
zero, so absence of optional data does not look like negative evidence. The final confidence is a
calibrated mapping of `raw_score`, initially identity-clamped and later adjusted by the matching
evaluation harness when labelled data exists.

**Rationale**: the constitution asks for confidence and reasons, not an opaque model. A weighted
sum is transparent, testable and easy to tune after the 500+ labelled benchmark exists. The weights
make lexical and semantic evidence the core for fuzzy candidates while keeping product attributes
as plausibility checks. Price plausibility is intentionally light because this chunk has no
historical price aggregation; it can compare only against available current quotation context or
tenant product hints, not a full price-history model.

**Alternatives considered**:
- *Train a classifier now* - premature without a labelled benchmark and likely to overfit pilot
  data.
- *Use only the maximum of lexical and semantic similarity* - loses the catalogue attributes that
  make two similar names meaningfully different products.
- *Treat missing feature data as zero* - punishes sparse but legitimate catalogue records and would
  inflate review volume for the wrong reason.

---

## R6 - Routing thresholds and close-call handling

**Decision**: configure matching routing thresholds through environment-backed settings, following
chunk 4.3's extraction threshold pattern:

| Setting | Initial planned value | Meaning |
|---|---:|---|
| `MATCHING_AUTO_ACCEPT_THRESHOLD` | `0.9200` | top candidate can be automatically accepted |
| `MATCHING_AUTO_REJECT_THRESHOLD` | `0.2500` | no useful candidate was found; still opens a no-match task |
| `MATCHING_REVIEW_MARGIN` | `0.0500` | if top two candidates differ by less than this, route to review |

Auto-accept happens only when the top candidate meets the threshold and is not a close call. Below
auto-accept, the line routes to the match queue, including lines with no candidate at all. The
auto-reject threshold is therefore a reason for queue presentation (`no_candidate`), not a silent
drop.

**Rationale**: thresholds are routing controls that must be tuned from real data. They are not
schema constants. The initial auto-accept value mirrors the product quality gate: at least 92%
precision at auto-accept. Close-call handling prevents a high absolute score from hiding an
ambiguous choice.

**Alternatives considered**:
- *Only one threshold* - cannot distinguish "review plausible candidates" from "review no-match
  and create product".
- *Auto-create products when all scores are low* - violates Human Authority Over Automation.
- *Allow automatic acceptance of close top-two candidates* - turns ambiguity into a hidden guess.

---

## R7 - Landed-cost rule versioning and replay

**Decision**: the landed-cost module exposes pure rule functions keyed by a version string, starting
with `landed-cost-v1`. Every `landed_cost` row stores:

- the `rule_version`
- every raw input as amount+currency pairs or decimal strings
- the computed total amount+currency
- valid-time (`valid_from`, `valid_to`) and record-time (`recorded_at`)

`landed-cost-v1` computes:

```text
vat_amount = unit_price_amount * quantity * vat_rate
landed_cost = (unit_price_amount * quantity)
            + vat_amount
            + delivery_fee_amount
            - discount_amount
            + 0 other_charges
```

All arithmetic uses exact decimal values. Recompute uses only the stored raw inputs and the stored
rule version, never live quotation, supplier or catalogue state.

**Rationale**: this is the first product feature that exercises Constitution Principle II. A later
rule change must not alter historical numbers. Version strings are simple, readable and enough for
the first rule set; the implementation can add a registry table later if rules become
data-configurable.

`quotation_line` stores `vat_rate`, not `vat_amount`, so `vat_amount` is derived. It has no
`other_charges` field; this chunk treats other charges as zero and records that raw input as zero,
consistent with the spec assumptions.

**Alternatives considered**:
- *Store only the total and recompute from current quotation_line on demand* - not replayable after
  corrections, schema changes or rule changes.
- *Store a JSON formula blob per row* - more flexible than needed and harder to test.
- *Model other charges now* - explicitly out of scope; a future rule can add new inputs under a new
  rule version.

---

## R8 - Alias creation and duplicate wording

**Decision**: human decisions create or reuse `product_alias` with the exact
`quotation_line.original_text`, the quotation's `supplier_id` when present, and the chosen
`workspace_product_id`.

Upsert behavior is deliberately narrow:

- If `(tenant_id, lower(alias_text))` does not exist, insert it.
- If it exists for the same `workspace_product_id`, reuse it and do not create a duplicate.
- If it exists for a different `workspace_product_id`, refuse the alias write with a conflict and
  leave the existing alias unchanged.

Correcting or retiring a previously confirmed alias is out of scope for this chunk, so this chunk
must not overwrite a different product's alias on duplicate-key collision.

**Rationale**: `product_alias` already defines one meaning per wording per workspace. Silently
moving the wording to another product would rewrite history and contradict the explicit out-of-scope
boundary. Refusing the conflicting alias makes the edge state visible without implementing alias
correction.

Automatic deterministic alias hits do not need to create another alias; they reuse the existing one.

**Alternatives considered**:
- *Overwrite on conflict* - rejected; it implements alias correction without the necessary review
  model.
- *Allow duplicate aliases per supplier* - contradicts the existing unique index and weakens the
  "same wording never needs review again" requirement.
- *Do not learn aliases from human decisions* - misses FR-010 and SC-005.

---

## R9 - Match-resolution queue table

**Decision**: create a dedicated `match_task` table, analogous to chunk 4.3's `review_task`, rather
than deriving the queue from `match_candidate` and `match_decision` rows alone.

**Rationale**: FR-011 requires match-resolution work as its own queue, independent of a single
quotation page. Constitution Principle III also says human review is an architectural concept with
its own state, not merely a screen. `match_task` gives the queue status, priority, reason,
timestamps and uniqueness independent of candidate regeneration. It can still show full context by
joining to the source `quotation_line`, its parent `quotation`, ranked `match_candidate` rows, any
`match_decision`, and the landed-cost result after resolution.

This also keeps append-only match decisions clean: tasks can move from `open` to `resolved` while
decisions remain immutable outcome facts.

**Alternatives considered**:
- *Queue as "lines without a decision"* - loses priority, reason, SLA state and in-progress
  ownership.
- *Use `review_task` for matching too* - mixes extraction review with product matching, which have
  different resources, reasons and UI.
- *Put queue state on `match_candidate`* - wrong cardinality; there can be several candidates for
  one line but only one piece of human work.

---

## R10 - Matching evaluation and calibration

**Decision**: implement evaluation hooks consistent with `docs/quality/test-strategy.md` §4:
500+ labelled product-match pairs including hard negatives, precision at auto-accept, recall,
review-band size, alias hit rate, and Expected Calibration Error with confidence within 5% per
bucket. The benchmark lives under `ml/benchmarks/` and the harness under `ml/evals/` at
implementation time.

**Rationale**: the success criteria cannot be claimed honestly before the labelled set exists.
The pipeline can be built and measured, but precision and review-band targets remain unvalidated
until the held-out benchmark is available. The evaluation output must include the scoring version,
thresholds, embedding model identifier and calibration version so runs are comparable.

**Alternatives considered**:
- *Use production corrections as the only benchmark* - useful telemetry, but not a held-out set and
  biased by whatever the current model routes to humans.
- *Tune and evaluate on the same examples* - rejected by the test strategy and the constitution.
- *Omit calibration until after real embeddings* - rejected. Even stubbed pipelines need the ECE
  reporting surface so it is not bolted on later.

---

## Summary of decisions

| # | Question | Decision |
|---|---|---|
| R1 | Deployable shape | `matching` and `landed_cost` modules inside `apps/api`; no new service |
| R2 | Exact match order | GTIN -> supplier code -> lower(alias_text) -> similarity |
| R3 | Lexical search | `pg_trgm` over line text vs product name/brand/variant, threshold from env |
| R4 | Semantic search | `pgvector` cosine over product text embeddings; deterministic stub first |
| R5 | Confidence | Weighted rules/scoring pipeline, not trained ML in this chunk |
| R6 | Routing | Env-backed auto-accept/reject/margin thresholds; close calls go to review |
| R7 | Landed cost | Pure versioned function, raw inputs stored, VAT derived, other charges zero |
| R8 | Alias learning | Insert/reuse exact wording; conflicting alias is refused, not overwritten |
| R9 | Queue | Dedicated `match_task` table |
| R10 | Evaluation | 500+ labelled pairs, hard negatives, precision/recall/review/ECE metrics |

**No NEEDS CLARIFICATION items remain.**
