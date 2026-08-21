---
description: "Task list for Matching and Normalisation implementation"
---

# Tasks: Matching and Normalisation

**Input**: Design documents from `/specs/004-matching-normalisation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/matching.openapi.yaml, quickstart.md

**Tests**: Included. The spec makes automatic matching precision, human resolution, landed-cost replay, tenant isolation, RBAC, auditability and accessibility release conditions.

**Organization**: grouped by setup, blocking foundation, then user stories so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable - different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md; setup, foundational and cross-cutting tasks have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: repo-level scaffolding for matching i18n, matching evaluation assets and environment-backed thresholds.

- [ ] T001 Add the `matching.*` i18n namespace to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping English and Arabic keys at parity before the match-resolution screens ship per plan.md Principle VII
- [ ] T002 [P] Create the versioned product-matching benchmark skeleton in `ml/benchmarks/product_matching/README.md` and `ml/benchmarks/product_matching/.gitkeep`, mirroring the chunk 4.3 quotation benchmark shape for research R10
- [ ] T003 [P] Create the product-matching eval skeleton in `ml/evals/product_matching/README.md`, `ml/evals/product_matching/.gitkeep` and `ml/evals/product_matching/run_eval.py`, mirroring the chunk 4.3 quotation eval shape for docs/quality/test-strategy.md section 4
- [ ] T004 Add matching settings to `.env.example`: `MATCHING_AUTO_ACCEPT_THRESHOLD=0.9200`, `MATCHING_AUTO_REJECT_THRESHOLD=0.2500`, `MATCHING_REVIEW_MARGIN=0.0500`, `MATCHING_TRIGRAM_THRESHOLD=0.30` and `MATCHING_EMBEDDING_MODEL=stub-hash-v1` per research R4 and R6

**Checkpoint**: i18n parity, evaluation directories and local configuration are ready; no new service or docker-compose entry exists for this chunk.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: database shape, RLS boundary and API module boundaries that all user stories depend on.

⚠️ **Everything else depends on this phase.** Migrations stay ordered, and RLS is last for review.

- [ ] T005 Write migration `supabase/migrations/20260819000022_matching_reference.sql` creating only the match reference enums from data-model.md: match task `status`, `priority`, `reason` and match decision `outcome`
- [ ] T006 Write migration `supabase/migrations/20260819000023_match_candidates_tasks.sql` creating `match_candidate` and `match_task` with exactly the data-model.md fields, FKs to `quotation_line` and `workspace_product`, confidence/rank checks, candidate uniqueness and the outstanding-task partial unique index
- [ ] T007 Write migration `supabase/migrations/20260819000024_match_decisions.sql` creating `match_decision` with exactly the data-model.md fields, FKs to `quotation_line`, `workspace_product`, `match_candidate`, `membership` and `product_alias`, one-decision-per-line uniqueness and human/automatic consistency checks
- [ ] T008 Write migration `supabase/migrations/20260819000025_landed_cost.sql` creating `landed_cost` with exactly the data-model.md fields, money amount+currency pairs, `raw_inputs`, `rule_version`, `valid_from`, `valid_to`, `recorded_at`, same-currency checks and one computation per decision/rule version
- [ ] T009 Write migration `supabase/migrations/20260819000026_matching_indexes.sql` adding `canonical_product.canonical_embedding vector(256)`, `canonical_product.canonical_embedding_model`, `workspace_product.tenant_name_embedding vector(256)`, `workspace_product.tenant_name_embedding_model`, expression GIN trigram indexes over canonical brand/name/variant text and workspace `tenant_name`, and vector cosine indexes only as warranted by implementation volume per research R3 and corrected R4
- [ ] T010 Write migration `supabase/migrations/20260819000027_matching_rls.sql` applying ENABLE + FORCE row level security plus USING and WITH CHECK tenant policies to `match_candidate`, `match_task`, `match_decision` and `landed_cost`
- [ ] T011 Create the matching module skeleton in `apps/api/src/procurepilot_api/modules/matching/__init__.py`, `apps/api/src/procurepilot_api/modules/matching/schemas.py`, `apps/api/src/procurepilot_api/modules/matching/service.py` and `apps/api/src/procurepilot_api/modules/matching/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py` following the catalogue/quotations module pattern
- [ ] T012 Create the landed-cost module skeleton in `apps/api/src/procurepilot_api/modules/landed_cost/__init__.py`, `apps/api/src/procurepilot_api/modules/landed_cost/schemas.py`, `apps/api/src/procurepilot_api/modules/landed_cost/service.py` and `apps/api/src/procurepilot_api/modules/landed_cost/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py` following the catalogue/quotations module pattern

**Checkpoint**: migrations apply from scratch; the API imports the two new modules; no user story code starts before this passes.

---

## Phase 3: User Story 1 - Automatic matching (P1) MVP

**Goal**: reviewed quotation lines are matched automatically where evidence is strong, with persisted candidates, confidence and structured reasons.

**Independent Test**: take a reviewed quotation line whose wording exactly matches a confirmed alias and confirm it produces a candidate, an automatic decision and a reason without human action.

### Tests for User Story 1

- [ ] T013 [P] [US1] Write contract tests for `GET /quotations/{quotation_id}/matches` in `apps/api/tests/contract/test_matching_contract.py`, covering the OpenAPI `QuotationMatches`, `MatchCandidate`, `MatchDecision` and not-reviewed 409 shapes
- [ ] T014 [P] [US1] Write unit tests in `apps/api/tests/unit/test_matching_deterministic.py` proving exact GTIN, supplier-code and alias-hit matches run in research R2 order and short-circuit lexical/semantic scoring
- [ ] T015 [P] [US1] Write unit tests in `apps/api/tests/unit/test_matching_scoring.py` proving the research R5 weighted formula exactly: 0.30 deterministic, 0.20 lexical, 0.20 semantic, 0.10 brand, 0.07 variant, 0.06 pack-unit, 0.04 pack-size and 0.03 price plausibility, with missing optional features treated as neutral 0.5
- [ ] T016 [P] [US1] Write integration tests in `apps/api/tests/integration/test_matching_pipeline.py` proving a reviewed line with no deterministic key still gets ranked `match_candidate` rows from pg_trgm/pgvector similarity and structured reasons per FR-003 through FR-005
- [ ] T017 [P] [US1] Write routing integration tests in `apps/api/tests/integration/test_matching_routing.py` proving auto-accept creates `match_decision` only when the top confidence meets `MATCHING_AUTO_ACCEPT_THRESHOLD` and the top two candidates are outside `MATCHING_REVIEW_MARGIN` per research R6
- [ ] T018 [P] [US1] Write match-candidate tenant isolation tests in `apps/api/tests/integration/test_matching_isolation.py` proving cross-tenant `match_candidate` reads return not found rather than forbidden per FR-020

### Implementation for User Story 1

- [ ] T019 [P] [US1] Create matching Pydantic schemas in `apps/api/src/procurepilot_api/modules/matching/schemas.py` for `MatchReason`, `MatchCandidate`, `MatchDecision`, `MatchTask`, `QuotationLineMatchState` and `QuotationMatches`, matching `specs/004-matching-normalisation/contracts/matching.openapi.yaml`
- [ ] T020 [US1] Add matching threshold and embedding-model settings to `apps/api/src/procurepilot_api/config.py`, reading `.env.example` values through pydantic-settings so routing is environment-backed per research R6
- [ ] T021 [P] [US1] Implement deterministic stub embeddings in `apps/api/src/procurepilot_api/modules/matching/embeddings.py`, producing versioned 256-component vectors labelled by `MATCHING_EMBEDDING_MODEL=stub-hash-v1` for the corrected two-embedding design in research R4
- [ ] T022 [P] [US1] Implement deterministic key matching in `apps/api/src/procurepilot_api/modules/matching/deterministic.py`, checking GTIN, supplier product code and `lower(product_alias.alias_text)` in research R2 order and returning structured reasons
- [ ] T023 [P] [US1] Implement lexical and semantic candidate search in `apps/api/src/procurepilot_api/modules/matching/search.py`, using pg_trgm over canonical brand/name/variant plus workspace `tenant_name` and pgvector cosine over `canonical_product.canonical_embedding` plus `workspace_product.tenant_name_embedding` per research R3 and corrected R4
- [ ] T024 [P] [US1] Implement feature scoring and confidence calibration in `apps/api/src/procurepilot_api/modules/matching/scoring.py`, applying the exact research R5 weights and recording component scores in `reasons`
- [ ] T025 [US1] Implement the reviewed-quotation matching pipeline in `apps/api/src/procurepilot_api/modules/matching/service.py`, persisting ranked `match_candidate` rows, creating automatic `match_decision` rows above threshold, and preserving "not found not forbidden" semantics through tenant-scoped Supabase reads
- [ ] T026 [US1] Implement `GET /quotations/{quotation_id}/matches` in `apps/api/src/procurepilot_api/modules/matching/router.py`, exposing candidates, automatic decisions, open tasks and landed cost only for reviewed quotations per FR-001 and the OpenAPI contract

**Checkpoint**: a reviewed quotation can generate evidence-backed automatic matches without manual intervention.

**Parallel execution note**: T013-T018 can run together after Phase 2; T021-T024 can run in parallel because they touch separate pipeline components; T025 integrates those components before T026 exposes them.

---

## Phase 4: User Story 2 - Human match resolution (P1)

**Goal**: uncertain or no-candidate lines become first-class match tasks that a reviewer resolves, learning aliases without overwriting conflicting meanings.

**Independent Test**: take a line with no strong candidate, resolve it as `no_match_new_product`, and verify a catalogue product, alias, match decision and resolved match task exist.

### Tests for User Story 2

- [ ] T027 [P] [US2] Write contract tests for `GET /match-tasks` and `POST /quotation-lines/{line_id}/match` in `apps/api/tests/contract/test_match_resolution_contract.py`, covering all five outcome types and OpenAPI error envelopes
- [ ] T028 [P] [US2] Write integration tests in `apps/api/tests/integration/test_match_task_queue.py` proving low-confidence, close-candidate and no-candidate lines create or keep one open `match_task`, and a resolved decision moves it to `resolved` per research R9
- [ ] T029 [P] [US2] Write alias-learning integration tests in `apps/api/tests/integration/test_match_alias_learning.py` proving human decisions create or reuse the exact `quotation_line.original_text` alias for the selected product and identical wording later resolves by alias hit per FR-010
- [ ] T030 [P] [US2] Write alias-conflict integration tests in `apps/api/tests/integration/test_match_alias_conflicts.py` proving `(tenant_id, lower(alias_text))` conflicts for a different `workspace_product_id` are refused and never overwritten per research R8
- [ ] T031 [P] [US2] Write matching RBAC tests in `apps/api/tests/integration/test_matching_rbac.py`, following `apps/api/tests/integration/test_catalogue_rbac.py` so owner/buyer can resolve matches and branch_manager/approver/viewer are read-only per FR-019
- [ ] T032 [P] [US2] Write keyboard-first match-resolution E2E coverage in `apps/web/tests/e2e/match-resolution.spec.ts`, proving candidate selection and confirmation work without a mouse per FR-012

### Implementation for User Story 2

- [ ] T033 [US2] Extend queue creation in `apps/api/src/procurepilot_api/modules/matching/service.py` so lines below auto-accept, close calls and no-candidate cases create or reuse `match_task` rows with reason `low_confidence`, `close_candidates` or `no_candidate` per FR-007 and FR-011
- [ ] T034 [US2] Implement match-task listing in `apps/api/src/procurepilot_api/modules/matching/service.py`, supporting `cursor`, capped `limit`, `status`, `priority`, `reason` and `quotation_id` filters for the standalone queue in research R9
- [ ] T035 [US2] Implement human resolution in `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`, accepting `same_product`, `different_pack`, `different_variant`, `compatible_alternative` and `no_match_new_product`, and reusing `CatalogueService.create_product` from `apps/api/src/procurepilot_api/modules/catalogue/service.py` for inline product creation rather than reimplementing chunk 4.2 product creation
- [ ] T036 [US2] Implement alias insert/reuse/conflict handling in `apps/api/src/procurepilot_api/modules/matching/alias_service.py`, following research R8 exactly for exact wording, same-product reuse and different-product conflict refusal
- [ ] T037 [US2] Implement `GET /match-tasks` and `POST /quotation-lines/{line_id}/match` in `apps/api/src/procurepilot_api/modules/matching/router.py`, with owner/buyer mutation guards and read-only access for all workspace roles per FR-019
- [ ] T038 [P] [US2] Build the resolution queue screen in `apps/web/src/app/features/matching/resolution-queue/`, including filters, reason display, ranked candidates and read-only presentation for non-writing roles using only `matching.*` i18n keys
- [ ] T039 [P] [US2] Build the per-line match-resolution screen in `apps/web/src/app/features/matching/match-resolution/`, including candidate comparison, structured reason breakdown, all five outcomes and keyboard-first selection per FR-008 and FR-012
- [ ] T040 [P] [US2] Add matching frontend API models and client methods in `apps/web/src/app/features/matching/matching-api.ts`, matching `specs/004-matching-normalisation/contracts/matching.openapi.yaml` for queue, quotation match state and resolution requests

**Checkpoint**: a reviewer can work the match queue end to end, and every human decision learns or safely refuses an alias.

**Parallel execution note**: T027-T032 can run together; T038-T040 can run in parallel once the OpenAPI schemas from T019 are stable; T035 depends on the catalogue service contract and T036 before T037 exposes mutation.

---

## Phase 5: User Story 3 - Landed cost per matched line (P1)

**Goal**: every matched line exposes a deterministic landed cost on catalogue base-unit quantities, with full money/currency pairs and replay inputs.

**Independent Test**: compute landed cost for a matched line with known quantity, VAT rate, delivery fee and discount, and verify the stored total and rule version match the formula exactly.

### Tests for User Story 3

- [ ] T041 [P] [US3] Write unit tests in `apps/api/tests/unit/test_landed_cost_rules.py` proving `landed-cost-v1` computes `(unit_price_amount * quantity) + derived_vat_amount + delivery_fee_amount - discount_amount + 0 other_charges` exactly on a known input per research R7
- [ ] T042 [P] [US3] Write unit tests in `apps/api/tests/unit/test_landed_cost_replay.py` proving recomputing from stored `raw_inputs` plus `rule_version` yields a bit-identical result and missing `vat_rate` is treated as zero rather than an error per FR-015 and the spec edge case
- [ ] T043 [P] [US3] Write integration tests in `apps/api/tests/integration/test_landed_cost_workflow.py` proving matched quotation lines persist `landed_cost` rows with explicit currencies, derived VAT and `normalised_base_quantity` from `pack_definition.base_quantity` per FR-013 and FR-018
- [ ] T044 [P] [US3] Write contract tests for `GET /quotation-lines/{line_id}/landed-cost` in `apps/api/tests/contract/test_landed_cost_contract.py`, covering the OpenAPI `LandedCost` schema, unmatched-line 409 and cross-tenant 404 shapes

### Implementation for User Story 3

- [ ] T045 [P] [US3] Create landed-cost Pydantic schemas in `apps/api/src/procurepilot_api/modules/landed_cost/schemas.py` for `Money`, `LandedCost` and raw replay input objects matching the OpenAPI contract
- [ ] T046 [P] [US3] Implement the pure rule-versioned landed-cost function in `apps/api/src/procurepilot_api/modules/landed_cost/rules.py`, deriving `vat_amount` from `vat_rate`, treating `other_charges` as zero and using exact Decimal arithmetic per research R7
- [ ] T047 [US3] Implement landed-cost persistence and pack normalisation in `apps/api/src/procurepilot_api/modules/landed_cost/service.py`, reading `match_decision`, `quotation_line` and `pack_definition.base_quantity`, storing full `raw_inputs`, `rule_version`, bitemporal fields and same-currency money pairs
- [ ] T048 [US3] Implement `GET /quotation-lines/{line_id}/landed-cost` in `apps/api/src/procurepilot_api/modules/landed_cost/router.py`, preserving read access for workspace roles and "not found not forbidden" semantics per FR-020

**Checkpoint**: a matched line has a reproducible landed cost with explicit currency and normalised quantity.

**Parallel execution note**: T041-T044 can run together after Phase 2; T045 and T046 can run in parallel, then T047 wires persistence before T048 exposes the endpoint.

---

## Phase 6: User Story 4 - Landed-cost replay and audit (P2)

**Goal**: stored landed-cost computations can be explained after the fact and are never silently rewritten when active rules change.

**Independent Test**: change the active landed-cost rule version, reopen a line priced under the previous version, and verify its stored total, inputs and version are unchanged.

### Tests for User Story 4

- [ ] T049 [P] [US4] Write replay/audit integration tests in `apps/api/tests/integration/test_landed_cost_audit.py` proving a stored `landed_cost` row's `valid_from`, `valid_to`, `recorded_at` and `rule_version` remain unchanged after the active rule version changes per FR-016 and FR-017
- [ ] T050 [US4] Write raw-input inspection tests in `apps/api/tests/integration/test_landed_cost_audit.py` proving every stored computation exposes complete `raw_inputs` for quantity, normalised base quantity, base unit, unit price, VAT rate, derived VAT amount, delivery fee, discount and zero other charges per FR-014

### Implementation for User Story 4

- [ ] T051 [US4] Harden append-only replay behavior in `apps/api/src/procurepilot_api/modules/landed_cost/service.py` so recomputation for a new active rule version inserts a new row when needed and never updates or deletes an existing `landed_cost` computation

**Checkpoint**: historical landed-cost evidence remains stable after rule changes and is inspectable from stored inputs.

**Parallel execution note**: T049 and T050 share `apps/api/tests/integration/test_landed_cost_audit.py` and should be coordinated once US3's stored row shape is stable; T051 depends on the US3 landed-cost service.

---

## Phase 7: Cross-cutting

**Purpose**: feature-wide isolation, RBAC, accessibility, AI quality gates, documentation and constitutional verification.

- [ ] T052 Extend `apps/api/tests/integration/test_tenant_isolation.py` to cover the four new tenant-scoped tables `match_candidate`, `match_task`, `match_decision` and `landed_cost`, and explicitly confirm `workspace_product.tenant_name_embedding` stays covered by existing workspace_product RLS while `canonical_product.canonical_embedding` remains shared by design under the existing canonical_product RLS exception, following chunk 4.2 T038 and chunk 4.3 T063 precedents
- [ ] T053 Extend role coverage in `apps/api/tests/integration/test_matching_rbac.py` for all matching and landed-cost read/mutation surfaces, following the same owner/buyer versus branch_manager/approver/viewer split as `apps/api/tests/integration/test_catalogue_rbac.py`
- [ ] T054 [P] Add `@a11y` specs for the resolution queue and match-resolution screens in both English and Arabic in `apps/web/tests/e2e/matching-a11y.spec.ts`, with RTL checks, keyboard navigation and zero axe violations per FR-012 and Principle VII
- [ ] T055 [P] Implement the matching evaluation harness in `ml/evals/product_matching/run_eval.py`, reporting precision at auto-accept, recall, review-band size, alias hit rate and ECE calibration within 5% per bucket against 500+ labelled product-match pairs with hard negatives in `ml/benchmarks/product_matching/` per docs/quality/test-strategy.md section 4 and research R10, and honestly marking the gate unvalidated until a real benchmark exists
- [ ] T056 [P] Fold this chunk's `[new]` data-model.md fields into `docs/architecture/data-dictionary.md`, including `match_candidate`, `match_task`, `match_decision`, `landed_cost`, the two embedding fields, and correcting the stale `SupplierOffer` placeholder noted in data-model.md
- [ ] T057 [P] Add the matching and landed-cost API surface to `docs/architecture/api-specification.md`, covering the four endpoints in `specs/004-matching-normalisation/contracts/matching.openapi.yaml`
- [ ] T058 Re-run the Constitution Check from `specs/004-matching-normalisation/plan.md` against delivered code and record the result, explicitly confirming no `services/matching-worker` and no docker-compose entry were introduced, following chunk 4.2 T043 and chunk 4.3 T069 precedents

---

## Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES
    ↓
    ├── Phase 3 US1 (P1) Automatic matching        ← MVP matching pipeline base
    │       ↓
    │   Phase 4 US2 (P1) Human resolution          ← queue/resolution uses US1 candidates
    │       ↓
    │   Phase 5 US3 (P1) Landed cost per line      ← requires a match_decision
    │       ↓
    │   Phase 6 US4 (P2) Replay/audit              ← verifies stored landed-cost history
    └── Phase 7 Cross-cutting                      ← final verification across delivered scope
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies - can start immediately.
- **Foundational (Phase 2)**: depends on Setup completion and blocks all user-story work.
- **US1 Automatic matching (P1)**: depends on Foundational and creates candidates/automatic decisions.
- **US2 Human resolution (P1)**: depends on US1 candidate generation and routing, because tasks resolve generated evidence or no-candidate cases.
- **US3 Landed cost (P1)**: depends on match decisions from US1 or US2.
- **US4 Replay/audit (P2)**: depends on US3 stored landed-cost rows and rule-version behavior.
- **Cross-cutting (Phase 7)**: depends on the implemented scope it verifies; docs tasks may start once APIs/data shapes are stable.

### Parallel Opportunities

- Setup tasks T002 and T003 can run in parallel; T001 and T004 touch shared configuration files and should be coordinated.
- Foundational migrations T005-T010 should stay ordered because migration numbers are sequential; skeleton tasks T011-T012 both touch `apps/api/src/procurepilot_api/main.py` and should be coordinated.
- US1 tests T013-T018 can run in parallel; implementation tasks T021-T024 can run in parallel, then T025 integrates them before T026 exposes the API.
- US2 tests T027-T032 can run in parallel; frontend tasks T038-T040 can run in parallel once schemas stabilize; T035-T036 must land before mutation routing in T037.
- US3 tests T041-T044 can run in parallel; T045 and T046 can run in parallel, then T047 and T048 complete the endpoint.
- US4 tests T049-T050 share `apps/api/tests/integration/test_landed_cost_audit.py` and should be coordinated once US3 persistence is stable; T051 is the implementation hardening task.

---

## Delegation lanes

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **A — Backend** | apps/api modules, matching and landed_cost services, ml/evals harness, backend tests | lane `backend` → **codex** | T003-T004, T011-T012, T013-T051, T053, T055 |
| **B — Frontend** | resolution queue, match-resolution screens and web tests | lane `frontend` → agy | T001, T032, T038-T040, T054 |
| **C — Docs** | data dictionary, API spec | lane `backend` → **codex** | T056-T057 |
| **D — Tenancy** | migrations, RLS, tenant-isolation test extension, constitution re-check | **not delegated** — orchestrator | T005-T010, T052, T058 |

Lane D stays in house: Principle V's failure mode is silent, and this chunk adds four tenant-scoped
tables plus tenant-sensitive embedding implications. Migrations, RLS, the tenant isolation test
extension and the constitution re-check are therefore not delegated.

This chunk has **no new service** and **no new docker-compose entry**, unlike chunk 4.3. Matching
and landed-cost logic remain inside `apps/api` as the `matching` and `landed_cost` modules, so the
delegation lanes are simpler: there is no `services/matching-worker` lane or container work.

**Task count**: 58 - Setup 4 · Foundational 8 · US1 14 · US2 14 · US3 8 · US4 3 · Cross-cutting 7.
