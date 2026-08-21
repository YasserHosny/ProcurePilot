---
description: "Task list for Smart Compare and Intelligence implementation"
---

# Tasks: Smart Compare and Intelligence

**Input**: Design documents from `/specs/005-smart-compare-intelligence/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/offers-and-baskets.openapi.yaml, quickstart.md

**Tests**: Included. The spec makes reasoned recommendations, price-history accuracy, basket-job completion or infeasibility reporting, live alerts, tenant isolation, RBAC, accessibility, and the 150 ms compare-grid interaction budget release conditions.

**Organization**: grouped by setup, blocking foundation, then user stories so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable - different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md; setup, foundational and cross-cutting tasks have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: repo-level scaffolding for compare/intelligence i18n, the new optimiser worker package, queue configuration, and local stack wiring.

**Already complete outside this checklist**: the orchestrator already wrote and applied `supabase/migrations/20260821000028_basket_split_alert_dismissal.sql` and `supabase/migrations/20260821000029_basket_split_alert_dismissal_rls.sql`, and already extended `apps/api/tests/integration/test_tenant_isolation.py` for `basket_split_job` and `alert_dismissal` with 39/39 passing. Do not create duplicate migration, RLS, or tenant-isolation-extension tasks in this chunk.

- [ ] T001 [P] Add the `compare.*`, `productIntelligence.*`, `basketSplit.*` and `alerts.*` i18n namespaces to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping English and Arabic keys at parity before any new web screen ships per FR-016
- [ ] T002 [P] Add shell route entries for compare, product intelligence, basket split and alerts screens in `apps/web/src/app/app.routes.ts`, following the established `catalogue`, `quotations` and `matching` feature route style
- [ ] T003 Create the optimiser package manifest in `services/optimiser/pyproject.toml`, mirroring `services/extraction-worker/pyproject.toml` with hatchling, Python `>=3.12,<3.13`, `redis`, `rq`, `psycopg[binary]`, `pydantic`, `ortools`, `pytest==8.3.4`, `pytest-asyncio==0.25.2` and `ruff` per research R8
- [ ] T004 [P] Create the optimiser README in `services/optimiser/README.md`, documenting the isolated venv discipline, `procurepilot_optimiser_worker` package name, `basket-split` queue and "no apps/api imports" boundary from plan.md
- [ ] T005 Add `BASKET_SPLIT_QUEUE_NAME=basket-split` to `.env.example` and expose it through `apps/api/src/procurepilot_api/config.py` without changing tenant resolution or secrets handling
- [ ] T006 [P] Add optimiser local test configuration in `services/optimiser/tests/conftest.py`, keeping the worker test suite isolated from `apps/api` on `PYTHONPATH` like `services/extraction-worker`

**Checkpoint**: i18n parity, queue configuration and optimiser package scaffolding are ready; database migrations/RLS remain the orchestrator-completed work above.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: API module boundaries, response schemas, frontend API clients, and the new worker process shape that all user stories depend on.

⚠️ **Everything else depends on this phase.** No user-story work starts until the API imports, schemas and worker package boundaries are in place.

- [ ] T007 Create the offers module skeleton in `apps/api/src/procurepilot_api/modules/offers/__init__.py`, `apps/api/src/procurepilot_api/modules/offers/schemas.py`, `apps/api/src/procurepilot_api/modules/offers/service.py` and `apps/api/src/procurepilot_api/modules/offers/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T008 Create the alerts module skeleton in `apps/api/src/procurepilot_api/modules/alerts/__init__.py`, `apps/api/src/procurepilot_api/modules/alerts/schemas.py`, `apps/api/src/procurepilot_api/modules/alerts/service.py` and `apps/api/src/procurepilot_api/modules/alerts/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T009 [P] Create shared offer, recommendation, price-history and basket Pydantic schemas in `apps/api/src/procurepilot_api/modules/offers/schemas.py`, matching `specs/005-smart-compare-intelligence/contracts/offers-and-baskets.openapi.yaml` with Money as `{amount,currency}` everywhere
- [ ] T010 [P] Create alert and alert-dismissal Pydantic schemas in `apps/api/src/procurepilot_api/modules/alerts/schemas.py`, matching the OpenAPI `Alert` and `AlertDismissal` shapes and storing only dismissal fingerprints, not alert conditions
- [ ] T011 [P] Add compare/intelligence/basket frontend API models and client methods in `apps/web/src/app/features/offers/offers-api.ts`, using decimal strings and `workspace_product_id`, never the stale `tenant_product_id`
- [ ] T012 [P] Add alerts frontend API models and client methods in `apps/web/src/app/features/alerts/alerts-api.ts`, matching the deterministic alert fingerprint and dismissal response shapes
- [ ] T013 Add `services/optimiser` to `docker-compose.yml` alongside `extraction-worker`, using `python:3.12-slim`, `working_dir: /workspace/services/optimiser`, repo mount, `PYTHONPATH: /workspace/services/optimiser/src`, shared `redis`, shared `db`, `DATABASE_URL`, `REDIS_URL` and `BASKET_SPLIT_QUEUE_NAME`
- [ ] T014 Create optimiser worker skeleton files `services/optimiser/src/procurepilot_optimiser_worker/__init__.py`, `__main__.py`, `settings.py` and `worker.py`, mirroring `services/extraction-worker/src/procurepilot_extraction_worker/__main__.py` with an RQ worker consuming `BASKET_SPLIT_QUEUE_NAME`

**Checkpoint**: FastAPI imports the new modules, the Angular app can compile against typed clients, and compose can start an isolated optimiser container shape.

---

## Phase 3: User Story 1 - Compare and recommend supplier offers (P1) MVP

**Goal**: a buyer can compare current supplier offers for one workspace product and quantity, with exactly one evidence-backed recommendation when an eligible offer exists.

**Independent Test**: open the compare screen for a product with at least two reviewed, matched and costed supplier offers; verify projected landed costs, recommendation evidence, confidence, risk and instant quantity recalculation.

### Tests for User Story 1

- [ ] T015 [P] [US1] Write contract tests for `GET /offers` and `GET /offers/compare` in `apps/api/tests/contract/test_offers_contract.py`, covering `Offer`, `OfferComparison`, `Recommendation`, empty recommendation and 404/422 envelopes
- [ ] T016 [P] [US1] Write offer read-pattern unit tests in `apps/api/tests/unit/test_offer_read_model.py`, proving the latest row per `(workspace_product_id, supplier_id, rule_version)` is selected from existing `match_decision` and `landed_cost`, with no new match or landed-cost computation
- [ ] T017 [P] [US1] Write recommendation scorer unit tests in `apps/api/tests/unit/test_recommendation_scorer.py`, proving the exact research R2 weights `0.55/0.20/0.15/0.10`, confidence thresholds, risk notes, null reliability/lead-time neutral scoring, and stock signal always null
- [ ] T018 [P] [US1] Write deterministic tie-break unit tests in `apps/api/tests/unit/test_recommendation_tie_break.py`, proving the research R3 seven-step rule and that applied tie-break evidence is included in the response
- [ ] T019 [P] [US1] Write offer integration tests in `apps/api/tests/integration/test_offers_compare.py`, proving reviewed quotation status, active/preferred suppliers, expired-offer handling, `include_expired`, explicit currencies and cross-tenant product references returning not found
- [ ] T020 [P] [US1] Write frontend unit tests in `apps/web/src/app/features/offers/compare/compare.component.spec.ts`, proving client-side quantity changes update projected totals and recommendation state within the 150 ms interaction budget without a reload
- [ ] T021 [P] [US1] Write compare E2E coverage in `apps/web/tests/e2e/smart-compare.spec.ts`, proving populated, expired-offer and no-offer empty states in English and Arabic

### Implementation for User Story 1

- [ ] T022 [P] [US1] Implement offer projection helpers in `apps/api/src/procurepilot_api/modules/offers/projection.py`, reading stored `landed_cost.raw_inputs`, `rule_version`, `total_amount/currency` and `pack_definition.base_quantity` from existing data and not creating a second landed-cost implementation or persisted landed-cost row
- [ ] T023 [US1] Implement the offer read query in `apps/api/src/procurepilot_api/modules/offers/service.py`, following research R1's join shape over `workspace_product`, `match_decision`, `landed_cost`, `quotation_line`, `quotation`, `supplier` and `pack_definition`
- [ ] T024 [P] [US1] Implement the recommendation scorer in `apps/api/src/procurepilot_api/modules/offers/recommendation.py`, applying research R2/R3 exactly and surfacing weights, components, margin, risk notes and tie-break evidence
- [ ] T025 [US1] Implement offer-list and compare service methods in `apps/api/src/procurepilot_api/modules/offers/service.py`, excluding expired offers from recommendation eligibility and returning `recommendation=null` for empty eligible sets
- [ ] T026 [US1] Implement `GET /offers` and `GET /offers/compare` in `apps/api/src/procurepilot_api/modules/offers/router.py`, preserving read access for all workspace roles and cross-tenant not-found semantics
- [ ] T027 [P] [US1] Implement the client-side compare projection utility in `apps/web/src/app/features/offers/compare/compare-projection.ts`, using Decimal-safe string handling and the fetched offer payload rather than a server request on each keystroke
- [ ] T028 [US1] Build the compare screen component in `apps/web/src/app/features/offers/compare/compare.component.ts`, `.html` and `.scss`, following the established feature-screen patterns in `catalogue`, `quotations` and `matching`
- [ ] T029 [P] [US1] Add compare-specific UI states in `apps/web/src/app/features/offers/compare/compare.component.html`, showing recommendation evidence, confidence, risk notes, validity window, expired offers and unknown stock via i18n keys only
- [ ] T030 [P] [US1] Add offer/recommendation formatting helpers in `apps/web/src/app/features/offers/offer-formatting.ts`, ensuring every money display includes amount and currency and all RTL spacing uses logical CSS properties

**Checkpoint**: US1 is demonstrable independently from existing matched and landed-costed quotation lines, with no new matching or landed-cost source of truth.

**Parallel execution note**: T015-T021 can run together after Phase 2; T022 and T024 can run in parallel, then T023/T025 integrate them before T026 exposes the API. Frontend T027-T030 can proceed once the contract models in T011 are stable.

---

## Phase 4: User Story 2 - Product price-history intelligence (P1)

**Goal**: a buyer can see workspace-owned historical normalised prices, last paid, trailing-window average and best price for a product.

**Independent Test**: open a product intelligence view with at least two historical `landed_cost` records and verify the chart and summary metrics trace to those rows.

### Tests for User Story 2

- [ ] T031 [P] [US2] Write contract tests for `GET /products/{product_id}/price-history` in `apps/api/tests/contract/test_price_history_contract.py`, covering `PriceHistoryResponse`, nullable summary metrics, pagination and supplier filtering
- [ ] T032 [P] [US2] Write price-history unit tests in `apps/api/tests/unit/test_price_history_metrics.py`, proving last-paid, trailing six-month rolling average and all-time best-price calculations from `landed_cost.recorded_at` and normalised unit price per research R6
- [ ] T033 [P] [US2] Write price-history integration tests in `apps/api/tests/integration/test_price_history.py`, proving the endpoint derives only from existing `landed_cost` joined through `match_decision`, `quotation_line`, `quotation` and `supplier`, with no new ledger and cross-tenant product references returning not found
- [ ] T034 [P] [US2] Write product intelligence frontend unit tests in `apps/web/src/app/features/offers/product-intelligence/product-intelligence.component.spec.ts`, covering populated, supplier-filtered and no-history empty states

### Implementation for User Story 2

- [ ] T035 [US2] Implement price-history query and metric calculation in `apps/api/src/procurepilot_api/modules/offers/price_history.py`, using research R6's trailing six-calendar-month window and source `landed_cost.id` traceability
- [ ] T036 [US2] Expose `GET /products/{product_id}/price-history` in `apps/api/src/procurepilot_api/modules/offers/router.py`, reusing offers schemas and preserving cursor pagination capped at 100
- [ ] T037 [P] [US2] Add the price-history method to `apps/web/src/app/features/offers/offers-api.ts`, including supplier filter, `window_months`, cursor and nullable metric handling
- [ ] T038 [US2] Build the product intelligence screen in `apps/web/src/app/features/offers/product-intelligence/product-intelligence.component.ts`, `.html` and `.scss`, following existing dense feature-screen conventions rather than a marketing-style dashboard
- [ ] T039 [P] [US2] Build the price-history chart view in `apps/web/src/app/features/offers/product-intelligence/price-history-chart.component.ts`, `.html` and `.scss`, using existing Angular/Material capabilities with no new frontend dependency
- [ ] T040 [P] [US2] Write product intelligence E2E coverage in `apps/web/tests/e2e/product-intelligence.spec.ts`, proving chart points, last/average/best summary cards, source-backed empty state and RTL layout

**Checkpoint**: US2 is independently testable from historical `landed_cost` rows without introducing a new purchase-history ledger.

**Parallel execution note**: T031-T034 can run together; T037-T040 can proceed once the response shape from T035/T036 is stable.

---

## Phase 5: User Story 3 - Two-supplier basket split (P2)

**Goal**: a buyer can submit a basket for exactly two named suppliers and receive an async completed result with an allocation, single-supplier baseline, or explicit infeasibility report.

**Independent Test**: submit a basket with two suppliers and multiple products; poll the job until completed and verify the result is feasible with allocation or completed with structured infeasible items.

### Tests for User Story 3

- [ ] T041 [P] [US3] Write contract tests for `POST /baskets/optimise` and `GET /baskets/{id}` in `apps/api/tests/contract/test_basket_optimise_contract.py`, covering `BasketOptimiseRequest`, `BasketSplitJob`, `BasketSplitResult`, infeasible result, 202/403/404/409/422 envelopes and `workspace_product_id`
- [ ] T042 [P] [US3] Write basket API integration tests in `apps/api/tests/integration/test_basket_split_api.py`, proving exactly two unique visible suppliers, positive decimal quantities, idempotency, queued status, durable job polling, owner/buyer submit permission and read access for other workspace roles
- [ ] T043 [P] [US3] Write optimiser solver unit tests in `services/optimiser/tests/test_solver.py`, proving feasible split, all-lines-with-cheaper-single-supplier when splitting saves nothing, and infeasible `no_offer_from_named_suppliers` results per research R5
- [ ] T044 [P] [US3] Write optimiser worker tests in `services/optimiser/tests/test_worker.py`, proving status transitions `queued -> running -> completed/failed`, `started_at`, `completed_at`, `solver_version`, and that commercial infeasibility is `completed` with `result.feasible=false`, not `failed`
- [ ] T045 [P] [US3] Write basket split frontend unit tests in `apps/web/src/app/features/offers/basket-split/basket-split.component.spec.ts`, covering supplier selection, item validation, polling states, feasible result and infeasible result rendering

### Implementation for User Story 3

- [ ] T046 [P] [US3] Add basket request/job/result schemas to `apps/api/src/procurepilot_api/modules/offers/schemas.py`, matching the OpenAPI contract and using Money for every allocation and baseline total
- [ ] T047 [US3] Implement basket job creation and RQ enqueueing in `apps/api/src/procurepilot_api/modules/offers/basket_service.py`, inserting `basket_split_job.status='queued'`, sending payload `{job_id, tenant_id}` to `procurepilot_optimiser_worker.worker.process_basket_split_job`, and never accepting tenant id from the request body
- [ ] T048 [US3] Implement `POST /baskets/optimise` and `GET /baskets/{id}` in `apps/api/src/procurepilot_api/modules/offers/router.py`, guarding submission to owner/buyer while preserving read-only job status access and cross-tenant not-found semantics
- [ ] T049 [P] [US3] Implement optimiser worker models in `services/optimiser/src/procurepilot_optimiser_worker/models.py`, matching the request/result JSON shapes from data-model.md and OpenAPI with decimal strings and explicit currencies
- [ ] T050 [US3] Implement optimiser database access in `services/optimiser/src/procurepilot_optimiser_worker/repository.py`, reading current eligible offers from existing `match_decision` and `landed_cost` joined to the two named suppliers, using stored normalised prices for allocation inputs and not recomputing matching or landed-cost components
- [ ] T051 [US3] Implement the OR-Tools CP-SAT minimum-cost two-supplier solver in `services/optimiser/src/procurepilot_optimiser_worker/solver.py`, with exactly two suppliers, no MOV, delivery-tier, branch, budget or preference-weight constraints per FR-011
- [ ] T052 [US3] Implement `process_basket_split_job` in `services/optimiser/src/procurepilot_optimiser_worker/worker.py`, reading `DATABASE_URL`, updating `basket_split_job`, reporting structured infeasible items, and reserving `failed` for worker/Redis/database/unexpected solver failures
- [ ] T053 [P] [US3] Build the basket split submission and result screen in `apps/web/src/app/features/offers/basket-split/basket-split.component.ts`, `.html` and `.scss`, following the chunk 4.3 job-polling UI pattern from quotation extraction
- [ ] T054 [P] [US3] Add basket split API polling state helpers in `apps/web/src/app/features/offers/basket-split/basket-split-state.ts`, representing queued/running/completed/failed and infeasible completed results distinctly
- [ ] T055 [P] [US3] Write basket split E2E coverage in `apps/web/tests/e2e/basket-split.spec.ts`, proving submission, automatic polling without manual refresh, feasible allocation, no-savings single-supplier recommendation and infeasible item reporting

**Checkpoint**: US3 works as an async advisory optimisation only; it never executes a purchase and never introduces a second landed-cost or matching implementation.

**Parallel execution note**: T041-T045 can run together; API T046-T048 and worker T049-T052 can proceed in parallel after Phase 2, with T047 and T052 agreeing on the queue payload; frontend T053-T055 can proceed once T011's API client shape is stable.

---

## Phase 6: User Story 4 - Alerts inbox (P2)

**Goal**: a buyer can see currently true actionable alerts, dismiss a fingerprint, and see resolved conditions disappear on the next inbox load.

**Independent Test**: create each alert condition, open the alerts inbox, dismiss one alert, then change the underlying condition and verify current live recomputation behavior.

### Tests for User Story 4

- [ ] T056 [P] [US4] Write contract tests for `GET /alerts` and `POST /alerts/{id}/dismiss` in `apps/api/tests/contract/test_alerts_contract.py`, covering `Alert`, `AlertDismissal`, filters, pagination and 403/404 envelopes
- [ ] T057 [P] [US4] Write alert fingerprint unit tests in `apps/api/tests/unit/test_alert_fingerprints.py`, proving deterministic ids over tenant id, kind, product id, relevant supplier id and the research R7 recurrence key for all three alert kinds
- [ ] T058 [P] [US4] Write alert-condition unit tests in `apps/api/tests/unit/test_alert_conditions.py`, proving expiring recommended price within 7 days, disappeared preferred supplier offer, price swing at 15% with at least two rolling-window points, and severity rules
- [ ] T059 [P] [US4] Write alert integration tests in `apps/api/tests/integration/test_alerts.py`, proving alerts are recomputed live from current offers/history, dismissed fingerprints are suppressed, changed underlying conditions recur as new fingerprints, and cross-tenant alert dismissals return not found
- [ ] T060 [P] [US4] Write alerts RBAC integration tests in `apps/api/tests/integration/test_alerts_rbac.py`, proving owner/buyer may dismiss and branch_manager/approver/viewer may read but not dismiss per the OpenAPI contract
- [ ] T061 [P] [US4] Write alerts frontend unit tests in `apps/web/src/app/features/alerts/alerts-inbox/alerts-inbox.component.spec.ts`, covering grouped alert display, dismiss action, current-empty state and action links

### Implementation for User Story 4

- [ ] T062 [US4] Implement alert live condition generation in `apps/api/src/procurepilot_api/modules/alerts/conditions.py`, reusing the offers recommendation and price-history services so conditions are current and no alert condition is persisted
- [ ] T063 [P] [US4] Implement deterministic alert fingerprinting in `apps/api/src/procurepilot_api/modules/alerts/fingerprints.py`, following research R7's recurrence keys exactly
- [ ] T064 [US4] Implement alert listing and dismissal services in `apps/api/src/procurepilot_api/modules/alerts/service.py`, filtering live alerts against `alert_dismissal` and inserting only dismissal fingerprints with membership attribution
- [ ] T065 [US4] Implement `GET /alerts` and `POST /alerts/{id}/dismiss` in `apps/api/src/procurepilot_api/modules/alerts/router.py`, guarding dismissal to owner/buyer and returning not found when a fingerprint is not currently true or not tenant-visible
- [ ] T066 [P] [US4] Build the alerts inbox in `apps/web/src/app/features/alerts/alerts-inbox/alerts-inbox.component.ts`, `.html` and `.scss`, showing severity, evidence, action target and dismiss controls with i18n-only strings
- [ ] T067 [P] [US4] Add alert action navigation helpers in `apps/web/src/app/features/alerts/alert-actions.ts`, routing `compare_product`, `review_supplier` and `view_price_history` to existing or new feature screens without introducing out-of-scope purchase/request actions
- [ ] T068 [P] [US4] Write alerts E2E coverage in `apps/web/tests/e2e/alerts-inbox.spec.ts`, proving all three alert kinds, dismissal, recurrence after condition change, empty state, keyboard operation and RTL layout

**Checkpoint**: US4 is an actionable live-computed inbox with dismissal-only storage, not a stale persisted alert feed.

**Parallel execution note**: T056-T061 can run together after Phase 2; T063 can run independently, then T062/T064 integrate condition generation and dismissal before T065 exposes the API.

---

## Phase 7: Cross-cutting

**Purpose**: feature-wide RBAC, accessibility, performance, documentation and constitutional verification.

- [ ] T069 Extend role coverage in `apps/api/tests/integration/test_smart_compare_rbac.py` for all new offers, price-history, basket and alerts endpoints, following the owner/buyer versus branch_manager/approver/viewer split from `apps/api/tests/integration/test_catalogue_rbac.py` without editing `apps/api/tests/integration/test_tenant_isolation.py`
- [ ] T070 [P] Add a contract drift check in `apps/api/tests/contract/test_smart_compare_openapi_drift.py`, verifying implemented routes and schemas match `specs/005-smart-compare-intelligence/contracts/offers-and-baskets.openapi.yaml`
- [ ] T071 [P] Add `@a11y` specs for compare, product intelligence, basket split and alerts screens in both English and Arabic in `apps/web/tests/e2e/smart-compare-a11y.spec.ts`, with RTL checks, keyboard navigation and zero axe violations
- [ ] T072 [P] Fold this chunk's real tables and response-only entities into `docs/architecture/data-dictionary.md`, correcting sketch-only money fields to amount+currency pairs and using `workspace_product_id`, not stale `tenant_product_id`
- [ ] T073 [P] Update `docs/architecture/api-specification.md` for the seven endpoints in `specs/005-smart-compare-intelligence/contracts/offers-and-baskets.openapi.yaml`, fixing the existing sketch-only `Offers & Compare` and `Baskets` sections so they do not carry bare money numbers
- [ ] T074 [P] Add a recommendation quality note in `apps/api/tests/unit/test_recommendation_scorer.py` covering SC-006's honest gap: no dedicated `ml/evals` harness is created for recommendation acceptance in this chunk because there is no outcome history yet; deterministic scorer behavior is covered by unit/integration tests until chunk 4.6 captures buyer decisions
- [ ] T075 Re-run the Constitution Check from `specs/005-smart-compare-intelligence/plan.md` against delivered code and record the result, explicitly confirming no new landed-cost or matching implementation was introduced and the optimiser is the only new deployable

---

## Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES
    ↓
    ├── Phase 3 US1 (P1) Compare + recommend       ← MVP compare base
    │       ├── Phase 4 US2 (P1) Price history     ← shares offer/history read models
    │       └── Phase 6 US4 (P2) Alerts inbox      ← depends on compare/history conditions
    ├── Phase 5 US3 (P2) Basket split              ← depends on offer read model and optimiser worker
    └── Phase 7 Cross-cutting                      ← final verification across delivered scope
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies - can start immediately. The migration/RLS/tenant-isolation work is already complete and not part of the pending dependency graph.
- **Foundational (Phase 2)**: depends on Setup completion and blocks all user-story work.
- **US1 Compare + recommend (P1)**: depends on Foundational and creates the offer read model used by alerts and basket validation.
- **US2 Price history (P1)**: depends on Foundational; it can proceed alongside US1 once the shared offers schemas are stable, but alert price-swing work depends on it.
- **US3 Basket split (P2)**: depends on Foundational and the offer read model; API and optimiser worker work can run in parallel once the queue payload and result JSON shape are fixed.
- **US4 Alerts inbox (P2)**: depends on the compare recommendation and price-history services because alert conditions are computed live from those read models.
- **Cross-cutting (Phase 7)**: depends on the implemented scope it verifies; docs tasks may start once API and data shapes are stable.

### Parallel Opportunities

- Setup tasks T001-T004 and T006 can run in parallel; T005 touches shared API config and should be coordinated with backend settings work.
- Foundational tasks T007-T010 can run in parallel after module names are fixed; T013-T014 are independent of FastAPI module registration.
- US1 tests T015-T021 can run together; T022 and T024 are independent, then T023/T025 integrate before T026 exposes the API.
- US2 tests T031-T034 can run together; T038 and T039 can run in parallel once the API response shape is stable.
- US3 API tasks T046-T048 and worker tasks T049-T052 can run in parallel after the queue payload is agreed; frontend T053-T055 can run against contract stubs.
- US4 tests T056-T061 can run together; T063 is independent before T062/T064 combine condition generation and dismissal behavior.

---

## Delegation lanes

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator (already done)** | `basket_split_job` and `alert_dismissal` migrations, RLS, and tenant-isolation test extension | **not delegated** - complete before this tasks file | `supabase/migrations/20260821000028_basket_split_alert_dismissal.sql`, `supabase/migrations/20260821000029_basket_split_alert_dismissal_rls.sql`, `apps/api/tests/integration/test_tenant_isolation.py` extension for both tables; 39/39 passing |
| **Backend** | `offers` and `alerts` apps/api modules, schemas, services, routers, RBAC, `services/optimiser`, `docker-compose.yml`, backend tests and SC-006 honest-gap unit coverage | lane `backend` -> **codex** | T003-T006, T007-T010, T013-T019, T022-T026, T031-T033, T035-T036, T041-T044, T046-T052, T056-T060, T062-T065, T069-T070, T074-T075 |
| **Frontend** | compare screen, product intelligence screen with price-history chart, basket-split submission/result screen, alerts inbox, i18n keys, keyboard/E2E/a11y specs using established `apps/web/src/app/features/` patterns | lane `frontend` -> agy | T001-T002, T011-T012, T020-T021, T027-T030, T034, T037-T040, T045, T053-T055, T061, T066-T068, T071 |
| **Docs** | architecture docs updates for data dictionary and API specification, correcting stale sketch-only money and product-id naming | lane `backend` -> **codex** | T072-T073 |

Lane D from prior chunks is represented here by **Orchestrator (already done)** rather than pending checklist tasks: Principle V's migration/RLS/isolation risk was handled before this Phase 2 task breakdown. Implementers must not regenerate those migrations, RLS policies, or the `test_tenant_isolation.py` extension.

No dedicated `ml/evals` harness is planned for the recommendation scorer in this chunk. SC-006 is an honest product-outcome target, but there is no buyer-decision history until chunk 4.6; deterministic scoring, thresholds, tie-breaks and evidence are therefore covered by unit, integration and contract tests in this chunk instead of a misleading benchmark.

**Task count**: 75 - Setup 6 · Foundational 8 · US1 16 · US2 10 · US3 15 · US4 13 · Cross-cutting 7.
