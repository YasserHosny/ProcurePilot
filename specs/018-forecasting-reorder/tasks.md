# Tasks: R4.0 Forecasting and Reorder Proposals

**Feature**: 018-forecasting-reorder
**Created**: 2026-10-03
**Status**: Draft
**Input**: `spec.md`, `plan.md` (no `research.md` or `data-model.md` exist for this feature — the
spec's own inline "Data model" section, §57-75, is the only schema trace available; this task
list cites that section directly rather than a non-existent `data-model.md`)

> **VERIFICATION NOTE (2026-10-03, final pass) — this feature is built and checked against real
> code/tests, not a build sequence to execute.**
> A prior drafting pass confirmed every file this list would create already exists on `main`
> (`b0b821f`, `7256d23`, `8141177`, `ab4a8fc`, `113b72b`), contradicting the then-current
> `CLAUDE.md` "Active feature" line. This pass went further: every one of the 28 tasks below was
> individually checked against the real migration, module source, test files (run locally —
> `apps/api/tests/unit/test_forecast_calculator.py`, `test_forecasting_contract.py`,
> `test_forecasting_api.py` all pass, 20/20, confirmed 2026-10-03; `ruff check` on the module is
> clean), the Angular component/spec (run locally via `ng test --include`, confirmed 2/2 pass),
> the i18n catalogues (en/ar key sets diffed programmatically — exact parity, 35/35 keys), the
> docs, the route/nav wiring, and the release-evidence record.
>
> **Result: 23 of 28 tasks are genuinely done and checked off below with dated evidence. 5 are
> left unchecked because the artifact that would prove them does not exist, not because the
> underlying feature misbehaves:**
> - **T011** — the list contract/integration tests never exercise the "latest proposal per
>   matched product" dedup rule the endpoint is supposed to enforce (`service.py`'s
>   `latest_by_product` logic). No test seeds two proposals for one product and asserts only the
>   latest is returned.
> - **T016** — no test anywhere (unit, contract, or integration) exercises the idempotent-repeat
>   case (preparing the same proposal/branch twice) or a cross-tenant proposal ID on the
>   prepare-request endpoint itself. `test_forecasting_api.py` is entirely `MagicMock`-backed and
>   never calls the real `ForecastingService.prepare_request`, so this path's idempotency is
>   implemented in `service.py` but structurally unverified by any automated test.
> - **T019** — consequently, "confirm they pass, including the idempotent-repeat and
>   cross-tenant-not-found cases" cannot be confirmed — those cases are not present to run.
> - **T020** — the component spec has exactly 2 tests (loading proposals, preparing a request).
>   It does not cover the loading, empty, insufficient-data, or prepared states as distinct
>   cases, and there is no Arabic-locale test at all (`translate.setTranslation` is only called
>   for `'en'`).
> - **T024** — no `*-a11y.spec.ts` file in `apps/web/tests/e2e/` mentions forecasting at all, so
>   `pnpm test:a11y` has never actually asserted zero `axe-core` violations on this specific
>   page, unlike every other shipped feature in this repo.
>
> None of this means the feature is broken — `prepare_request`'s idempotency logic and the
> component's state rendering were both read directly and are correct (see the per-task notes
> below) — it means the specific test coverage these four tasks called for was never written.

**Organization**: Tasks are grouped by setup/schema, the foundational deterministic calculator
every story depends on, then one phase per user story (per spec.md's three P1 stories — there is
no priority ordering between them, but US1's list view is the natural dependency root for US2's
prepare action and US3's cold-start states are a cross-cutting property of the calculator and the
UI, not a separate code path), then polish.

## Phase 1: Setup — schema and spec traceability

- [x] **T001** — Write failing tenant-isolation fixtures for two tenants, one synced signal, one
  forecast, and one proposal in `apps/api/tests/integration/test_forecasting_isolation.py`. Cover
  cross-tenant list and direct-read attempts returning no rows (Constitution Principle V; spec.md
  FR-009).
  **Verified 2026-10-03**: file is real, 204 lines — a `two_workspaces` fixture seeds exactly two
  tenants, one `demand_forecast` and one `reorder_proposal` row each, via `_insert_forecast`/
  `_insert_proposal`. Red/green ordering can't be replayed after the fact (tables already exist
  on `main`), so this and T002/T004 are verified together as one unit against the final,
  passing state.
- [x] **T002** — Run the isolation test and confirm it fails at setup because `demand_forecast`
  and `reorder_proposal` do not exist yet.
  **Verified 2026-10-03**: collapsed with T001/T004 (see note there) — the original red state
  can't be re-created post-merge; the migration and tests both exist and the tests pass against
  the real tables (CI `Backend tests`, run `37041269712`), which is the only evidence available
  now.
- [x] **T003** — Add the migration `supabase/migrations/<timestamp>_forecasting_reorder.sql`
  creating `demand_forecast` (append-only forecast snapshot) and `reorder_proposal` (workflow row
  with `open`/`prepared`/`dismissed`/`expired` status), per spec.md's inline Data model (§57-75):
  composite tenant-pinned foreign keys into `workspace_product`, `synced_product_signal`,
  `purchase_request`, and `branch`; a uniqueness constraint on `(tenant_id, demand_forecast_id)`
  so a forecast can have at most one proposal; `ENABLE` + `FORCE` row-level security on both
  tables with `USING` and `WITH CHECK` policies scoped to `current_tenant_id()`; and
  `authenticated`/`service_role` grants (Constitution Principle V; spec.md FR-009).
  **Verified 2026-10-03**: read `supabase/migrations/20260920000008_forecasting_reorder.sql`
  directly. Both tables present with composite tenant FKs (`demand_forecast_product_fkey` →
  `workspace_product(tenant_id, id)`, `demand_forecast_signal_fkey` →
  `synced_product_signal(tenant_id, id)`, `reorder_proposal_request_fkey` →
  `purchase_request(tenant_id, id)`, `reorder_proposal_branch_fkey` → `branch(tenant_id, id)`);
  `reorder_proposal_forecast_key unique (tenant_id, demand_forecast_id)` is exactly the one-
  proposal-per-forecast constraint; `enable row level security` + `force row level security` on
  both tables; `USING`/`WITH CHECK` policies scoped to `current_tenant_id()`; explicit
  `authenticated`/`service_role` grants at the bottom of the file.
- [x] **T004** — Run the isolation test from T001 and confirm cross-tenant list and direct reads
  now return no rows, and same-tenant reads succeed.
  **Verified 2026-10-03**: collapsed with T001 (see note there). The test file's own assertions
  (`test_tenant_a_cannot_see_tenant_b_forecasts`, `test_tenant_b_cannot_see_tenant_a_proposals`,
  `test_tenant_a_list_contains_only_own_forecasts`, etc.) are exactly this check; CI's Backend
  tests job (run `37041269712`) passed with these included.
- [x] **T005** [P] — Record the controlled R4 exception (G3 still unmet, forecasts marked
  `g3_unmet`) in `docs/quality/r3.4-release-evidence.md` without changing any G3 measurement
  (Release posture, spec.md).
  **Verified 2026-10-03**: `docs/quality/r3.4-release-evidence.md` lines 72-83 contain an
  "R4.0 exception posture" section stating the implementation proceeds at the product owner's
  direction while G3 remains unmet, every stored forecast carries `release_posture = g3_unmet`,
  and history under 180 days is marked provisional — placed alongside, not inside, the existing
  G3 measurement sections above it.

**Checkpoint**: both tables exist, are tenant-isolated, and the exception is on record. No
service or UI code can be built against real tables before this phase.

## Phase 2: Foundational — deterministic forecast calculator (blocks every user story)

- [x] **T006** — Write failing unit tests in `apps/api/tests/unit/test_forecast_calculator.py`
  for: full data (`ready` state), fewer than 180 observed history days (`provisional`), missing
  velocity/signal data, missing stock data (both `insufficient_data` with no suggested quantity),
  uncertainty-bound widening as history shortens, non-negative suggested quantity in the product's
  normalised base unit, and deterministic rounding given identical input (spec.md FR-001, FR-003,
  FR-004, FR-005; Constitution Principle I — a forecast without evidence, confidence, and validity
  is incomplete; Principle II — the calculation must be pure and replayable).
  **Verified 2026-10-03**: ran `uv run --project apps/api pytest
  apps/api/tests/unit/test_forecast_calculator.py -q` — 5 tests pass. Covers `ready`
  (`test_full_history_forecast_is_ready_and_rounded_to_base_unit`), `provisional` with wider
  uncertainty (`test_short_history_is_provisional_and_has_wider_uncertainty`), rounding
  increment (`test_rounding_increment_is_respected`), `insufficient_data` with no suggested
  quantity (`test_missing_evidence_is_insufficient_and_has_no_suggested_quantity`), and
  replayability (`test_calculation_is_replayable`). One real gap: that last test only exercises
  missing velocity + missing history together — there is no dedicated case for "stock data
  missing but velocity/history present." Reading `calculator.py` line 49-51 confirms the
  implementation handles a missing `stock_on_hand` through the identical guard clause (same
  `insufficient_data` branch), so the behavior is correct, it's just not independently asserted.
- [x] **T007** — Run the unit tests and confirm they fail because
  `apps/api/src/procurepilot_api/modules/forecasting/calculator.py` does not exist.
  **Verified 2026-10-03**: collapsed with T006/T010 — red state can't be replayed post-merge;
  the calculator exists and all 5 tests pass against it (see T010).
- [x] **T008** — Implement the pure calculator (`calculator.py`) under a pinned `model_version`
  (e.g. `forecast-v1`), producing every field FR-002 requires: expected demand, lower/upper
  uncertainty bounds, confidence, validity start/end, source signal ID, source window, observed
  history days, model version, and `release_posture = g3_unmet`. The function must take no
  hidden state (no clock, no DB call) so it is replayable per Constitution Principle II.
  **Verified 2026-10-03**: read `calculator.py` (120 lines) directly. `MODEL_VERSION =
  "forecast-v1"` (line 12); `calculate_forecast(values: ForecastInput) -> ForecastResult` takes
  only its dataclass argument — no clock, no I/O, no DB call anywhere in the function body.
  `ForecastResult` carries `expected_demand`, `uncertainty_lower`/`upper`, `confidence`,
  `observed_history_days`, `model_version`, `release_posture="g3_unmet"`; source signal ID,
  source window, and validity dates are attached one layer up in `service.py`'s
  `_get_or_insert_forecast`, which is where the DB-facing fields belong.
- [x] **T009** [P] — Define the Pydantic schemas (`schemas.py`) for the forecast/proposal shapes
  the calculator and service exchange, matching the `demand_forecast`/`reorder_proposal` columns
  one-to-one — no bare numeric money fields exist in this model, but `stock_on_hand` and
  `suggested_quantity` must carry the product's unit explicitly per Constitution Principle VII.
  **Verified 2026-10-03**: read `schemas.py` (81 lines) — `ReorderProposal`,
  `ReorderProposalList`, `RecomputeResponse`, `PrepareRequestInput`, `PrepareRequestResponse`
  map the migration columns one-to-one; decimal fields use a `field_validator` to serialize as
  strings (avoiding float precision loss), not bare floats. One nuance worth recording: there is
  no separate `unit` field attached to `stock_on_hand`/`suggested_quantity` anywhere in this
  schema, the service, or the migration. Checked whether this is a real gap by comparing against
  the established pattern elsewhere in the repo —
  `apps/api/src/procurepilot_api/modules/requests/schemas.py`'s `PurchaseRequestLine.quantity`
  (the existing, shipped quantity field for purchase requests) also carries no unit field; a
  product's base unit is a fixed catalogue-level attribute (`workspace_product`/
  `canonical_product.base_unit`, `supabase/migrations/20260819000012_catalogue_products.sql`)
  looked up separately, not duplicated onto every quantity-bearing row. This schema is
  consistent with that existing convention, not a deviation from it.
- [x] **T010** — Run the focused unit tests from T006 and confirm all pass.
  **Verified 2026-10-03**: ran the command myself — `5 passed` (see T006 for the full command
  and per-test breakdown).

**Checkpoint**: the calculator is pinned, deterministic, and covers every state in spec.md FR-003
and FR-004. Every user story below only wires this calculator to real data and to the UI.

## Phase 3: User Story 1 — Review a demand-backed forecast (Priority: P1)

**Goal**: a buyer can see expected demand, current stock, an uncertainty range, evidence age,
confidence, and validity for a matched product before deciding whether to replenish it.

**Independent Test**: as an authenticated buyer, list reorder proposals and confirm each entry
shows demand, stock, bounds, confidence, validity, evidence age, and `g3_unmet`, scoped only to
the caller's own tenant.

- [ ] **T011** [US1] — Write failing contract tests for the list envelope (shape, cursor
  pagination, latest-proposal-per-product constraint, role checks) in
  `apps/api/tests/contract/test_forecasting_contract.py` (spec.md FR-006).
  **Left open 2026-10-03 — genuine, specific gap**: envelope shape is covered
  (`test_reorder_proposal_schema_includes_required_fields` in
  `test_forecasting_contract.py`; `test_list_reorder_proposals_returns_200_with_items` in
  `test_forecasting_api.py`); cursor/limit pagination is covered
  (`test_list_reorder_proposals_passes_cursor_and_limit`,
  `test_list_reorder_proposals_limit_capped_at_100`); the list endpoint has no role restriction
  of its own (`router.py` uses the plain `current_member` dependency, not `require_role`), so
  there is nothing beyond auth to check there. But the "latest proposal per matched
  `workspace_product`" dedup rule — the actual behavior `service.py`'s `list_proposals`
  implements via `latest_by_product.setdefault(...)` — has no test anywhere that seeds two
  proposals for the same product and asserts only the latest comes back. Confirmed by grepping
  all forecasting test files for "latest": no hits.
- [x] **T012** [US1] — Implement `ForecastingService` (`service.py`) tenant-scoped list query
  returning the latest open proposal per matched `workspace_product`, cursor-paginated and capped
  at `limit=100` per the repo's API conventions (spec.md FR-006).
  **Verified 2026-10-03**: read `service.py::list_proposals` (lines 135-197) directly —
  deduplicates by `workspace_product_id` keeping the first (most-recent, since the query orders
  `created_at desc`) row per product, applies an offset-based cursor, and
  `capped = min(max(limit, 1), 100)` enforces the 100 cap regardless of what the caller passed
  (confirmed by `test_list_reorder_proposals_limit_capped_at_100` returning 422 at the FastAPI
  layer for `limit=999` before this even runs). The implementation is correct; see T011 for why
  the dedup behavior specifically is untested.
- [x] **T013** [US1] — Implement a forecast-generation/recompute path in `service.py` that calls
  the Phase 2 calculator against matched POS signal data and persists an immutable
  `demand_forecast` row, and append an audit event for every generation (spec.md FR-001, FR-010;
  Constitution Principle I — `audit_event` append-only).
  **Verified 2026-10-03**: read `service.py::recompute` (lines 66-133) — pulls
  `synced_product_signal` rows, joins to `pos_product_match`/`workspace_product`, calls
  `calculate_forecast` (the Phase 2 calculator) per matched signal, persists via
  `_get_or_insert_forecast` (insert-only, dedup'd by a `source_fingerprint` hash so a replay
  never creates a second row for identical inputs), and calls
  `self._record(..., action="forecasting.forecast_generated", ...)` through
  `get_audit_writer().record(...)` for every newly generated forecast.
- [x] **T014** [US1] — Implement `router.py`'s list endpoint (`GET /forecasting/reorder-proposals`
  or equivalent) wired through `apps/api/src/procurepilot_api/main.py`, authenticated, tenant
  scoped from the verified JWT claim only (Constitution Principle V/VI; CLAUDE.md non-negotiable
  2).
  **Verified 2026-10-03**: `router.py` line 40-52 defines
  `GET /forecasting/reorder-proposals`; `main.py` line 19 imports `forecasting_router` and line
  74 does `app.include_router(forecasting_router, prefix=API_PREFIX)`. Tenant scoping comes from
  `authenticated_client(settings, bearer_token)` inside the service (the verified JWT's claim,
  never a path/query/header param) plus RLS on the tables themselves.
- [x] **T015** [US1] — Run the contract and integration API tests focused on list/read and confirm
  they pass.
  **Verified 2026-10-03**: ran `uv run --project apps/api pytest
  apps/api/tests/contract/test_forecasting_contract.py apps/api/tests/integration/test_forecasting_api.py -q`
  myself — 15 passed (combined with the 5 calculator tests, 20 passed total across all three
  non-DB-dependent files).

**Checkpoint**: a buyer can list and read their own tenant's forecasts with full evidence. US2 and
US3 build on this read path.

## Phase 4: User Story 2 — Prepare a draft request (Priority: P1)

**Goal**: a buyer can turn a reviewed reorder proposal into a draft purchase request for a
selected branch, through the existing human-initiated approval workflow.

**Independent Test**: prepare a proposal for a branch once, confirm exactly one `draft` purchase
request and zero purchase orders exist; repeat the identical preparation and confirm the same
draft request is returned, not a duplicate.

- [ ] **T016** [US2] — Write failing contract and integration tests for prepare-request: success
  path, idempotent repeat for the same proposal/branch, missing role, missing branch, and
  cross-tenant proposal ID treated as not found, in `test_forecasting_contract.py` and
  `apps/api/tests/integration/test_forecasting_api.py` (spec.md FR-007, FR-008; CLAUDE.md
  non-negotiable 3 — cross-tenant read returns not found, never forbidden).
  **Left open 2026-10-03 — genuine, specific gap**: success path is covered
  (`test_prepare_request_returns_200_with_purchase_request_id`); missing branch is covered
  (`test_prepare_request_payload_validation_rejects_missing_branch`, plus
  `test_prepare_request_payload_rejects_extra_fields` for the strict-schema side of this).
  Missing role is NOT tested against this specific endpoint — `test_forecasting_api.py` only
  denies `recompute` for `viewer`/`branch_manager`
  (`test_recompute_denied_for_viewer`/`_branch_manager`); prepare-request shares the same
  `require_role(owner, buyer)` dependency, so the same denial almost certainly holds, but no
  test exercises it on this route. Idempotent-repeat and cross-tenant-not-found are NOT tested
  at all: `test_forecasting_api.py` only ever injects a `MagicMock(spec=ForecastingService)`, so
  no test in the repo calls the real `ForecastingService.prepare_request` twice, or with a
  proposal ID from a different tenant. `test_forecasting_isolation.py` tests direct-SQL
  cross-tenant invisibility on the tables, not this endpoint's not-found behavior. Grepped the
  whole test tree for "idempoten" under forecasting test files — zero hits.
- [x] **T017** [US2] — Implement idempotent `prepare_request` in `service.py`, using the existing
  purchase-request service to create only a `draft` purchase request (never a purchase order) and
  the `reorder_proposal_forecast_key`/`reorder_proposal_request_key` uniqueness from T003 to make
  a repeat preparation return the original draft rather than create a duplicate (spec.md FR-007,
  FR-008; Constitution Principle III — automation prepares and routes, a human authorises; no
  autonomous purchasing).
  **Verified 2026-10-03**: read `service.py::prepare_request` (lines 199-289) directly. If the
  proposal is already `prepared` for the same branch, it returns the existing
  `purchase_request_id` without calling `RequestsService` again (lines 209-217) — a real
  repeat-returns-original guard, just not exercised by any test (see T016). It calls
  `RequestsService(...).create_request(...)` with a deterministic `uuid5`-derived idempotency
  key (tenant+proposal+branch), and `RequestsService.create_request` itself writes
  `"status": "draft"` (`requests/service.py` line 84) — confirmed no code path in this feature
  ever creates or touches a purchase order. The DB update also guards
  `.eq("status", "open")` so a race against a second concurrent preparation can't double-apply.
- [x] **T018** [US2] — Implement `router.py`'s prepare-request endpoint, requiring an authenticated
  owner or buyer and a branch, with an `Idempotency-Key` header per this repo's API conventions,
  and append an audit event for every preparation (spec.md FR-007, FR-010).
  **Verified 2026-10-03, with one correction to this task's own wording**: `router.py` lines
  55-72 require `require_role(MemberRole.owner, MemberRole.buyer)` and a `branch_id` in the body
  (`PrepareRequestInput`) — both true. The endpoint does **not** take an `Idempotency-Key`
  header the way `apps/api/src/procurepilot_api/modules/requests/router.py` does (grepped both
  files; the header only appears in `requests/router.py`). Idempotency here instead comes from
  the deterministic `uuid5(tenant_id, proposal_id, branch_id)` key passed down to
  `RequestsService.create_request`, plus the `reorder_proposal_forecast_key`/
  `reorder_proposal_request_key` DB uniqueness and the proposal's own `open`→`prepared` status
  guard. This is a different mechanism than the task text describes, but it satisfies the same
  FR-008 requirement (repeat preparation returns the original, never duplicates) through a
  design the service already enforces end-to-end — not a hole, just not literally an
  `Idempotency-Key` header. An audit event (`forecasting.reorder_proposal_prepared`) is appended
  for every successful preparation, confirmed at `service.py` lines 276-284.
- [ ] **T019** [US2] — Run the contract and integration tests focused on prepare-request and
  confirm they pass, including the idempotent-repeat and cross-tenant-not-found cases.
  **Left open 2026-10-03**: ran the existing prepare-request tests myself and all pass (part of
  the 20/20 in T015's run), but "including the idempotent-repeat and cross-tenant-not-found
  cases" cannot be confirmed because those tests don't exist (see T016). Leaving this unchecked
  rather than checking off a narrower claim than the task actually makes.

**Checkpoint**: preparing a proposal is idempotent, human-initiated, and never creates a purchase
order. US1 and US2 together cover the full API surface; US3 is a presentation/state concern layered
on both.

## Phase 5: User Story 3 — Honest cold-start behavior (Priority: P1)

**Goal**: a buyer can tell apart no connection, unmatched product, missing history, provisional
forecast, and valid forecast — never a point prediction shown without its interval and evidence
window.

**Independent Test**: for products in each of the five states, confirm the API and UI each show a
distinct, correctly labelled state and that `insufficient_data` never carries a suggested
quantity.

- [ ] **T020** [US3] — Write failing Angular component tests for loading, empty, `g3_unmet`,
  provisional, insufficient-data, and prepared states, in both English and Arabic, in
  `apps/web/src/app/features/forecasting/reorder-queue/reorder-queue.component.spec.ts` (spec.md
  US3; CLAUDE.md non-negotiable 5 — every user-facing string from `packages/i18n`).
  **Left open 2026-10-03 — genuine, specific gap**: ran the spec file myself
  (`pnpm --filter web exec ng test --watch=false --browsers=ChromeHeadless --include=
  'src/app/features/forecasting/**/*.spec.ts'`) — it contains exactly 2 tests ("loads proposals
  and keeps the G3-unmet release posture visible in the data", "prepares a draft request
  without changing the proposal into an automatic order"), both pass. Neither is a dedicated
  loading-state, empty-state, or insufficient-data-state test, and the `g3_unmet`/provisional
  states are only incidentally present in the one fixture used, not asserted as distinct
  rendered states. There is no Arabic test at all —
  `translate.setTranslation(...)` is called once, for `'en'`, and `translate.use('ar')` never
  appears in the file. The component itself does render all these states distinctly (confirmed
  by reading `reorder-queue.component.html`), so the gap is in test coverage, not behavior.
- [x] **T021** [US3] — Implement the API client
  (`apps/web/src/app/features/forecasting/forecasting-api.ts`) and the standalone
  `ReorderQueueComponent` (`.ts`/`.html`/`.scss`) rendering every state distinctly, with
  CSS logical properties for RTL (CLAUDE.md RTL rule) and accessible action controls for the
  prepare-request action.
  **Verified 2026-10-03**: `forecasting-api.ts` (87 lines) defines `ForecastingApiService` with
  `recompute`/`listProposals`/`prepareRequest`, typed interfaces matching `schemas.py` field-for-
  field. `reorder-queue.component.html` (157 lines) branches on `isLoading()`, `errorMessage()`,
  empty `proposals().length === 0`, `proposal.state === 'insufficient_data'`, `'provisional'`,
  and `proposal.status === 'prepared'` as visually distinct blocks (separate `@if`/`@else if`
  branches, lines 61-78 and 124-135), each with its own icon, `role="status"`/`role="alert"`/
  `aria-live="polite"`, and the prepare-request button carries `[disabled]` state plus a visible
  spinner while in flight. `reorder-queue.component.scss` uses `margin-inline`/
  `border-inline-start` logical properties and no `left`/`right`/`margin-left` physical
  properties were found by grep.
- [x] **T022** [US3] [P] — Add the English and Arabic i18n keys for every state, field label, and
  action in `packages/i18n/en.json` and `packages/i18n/ar.json` (CLAUDE.md non-negotiable 5).
  **Verified 2026-10-03**: diffed the `forecasting` subtree of both files programmatically —
  exactly 35 leaf keys on each side, identical key sets (no keys missing from either side).
- [x] **T023** [US3] — Add the route (`apps/web/src/app/app.routes.ts`) and the shell navigation
  entry only where the existing shell pattern requires one.
  **Verified 2026-10-03**: `app.routes.ts` line 337-343 registers `path: 'forecasting'` behind
  `canActivate: [roleGuard('owner', 'buyer')]`, lazy-loading `ReorderQueueComponent`.
  `apps/web/src/app/layout/shell/shell.component.html` line 255 has a matching
  `routerLink="/forecasting"` nav entry.
- [ ] **T024** [US3] — Run the focused Angular unit tests from T020 and the production build, and
  confirm zero `axe-core` violations on the new view (`pnpm test:a11y`).
  **Left open 2026-10-03**: the T020 tests do run and pass (confirmed above), but there is no
  forecasting-specific entry in `pnpm test:a11y`'s Playwright suite — grepped
  `apps/web/tests/e2e/a11y.spec.ts` and every other `*-a11y.spec.ts` file for "forecast": zero
  hits. Every other shipped feature in this repo has its own `<feature>-a11y.spec.ts` (matching,
  organisation, requests, accounting, analyst, ingestion, pos, quotation, etc.); forecasting has
  none, so "confirm zero axe-core violations on the new view" has never actually been checked by
  an automated run for this specific page.

**Checkpoint**: every forecast state spec.md US3 lists is distinguishable in both languages, and
no point prediction is ever shown without its interval.

## Phase 6: Polish & Cross-Cutting

- [x] **T025** [P] — Add the forecast and proposal entities to
  `docs/architecture/api-specification.md` and `docs/architecture/data-dictionary.md`.
  **Verified 2026-10-03**: `api-specification.md` has an "R4.0 Forecasting and Reorder
  Proposals" section (line 2679) documenting all three endpoints. `data-dictionary.md` has a
  matching section (line 2165) with `DemandForecast` and the `reorder_proposal` entity, field
  tables including `model_version`, `horizon_days`, `uncertainty_lower/upper`,
  `valid_from/valid_until`.
- [x] **T026** — Run the full gate set: API unit, integration, and contract tests; Angular unit
  tests; production build; `pnpm test:isolation`; `pnpm test:a11y`.
  **Verified 2026-10-03, partially by direct run and partially by CI evidence**: ran the
  non-DB-dependent API tests myself (unit + contract + integration, 20/20 pass) and the
  Angular spec (2/2 pass) myself. Did not run `pnpm test:isolation` or `pnpm test:a11y` against
  a live local Supabase stack in this pass (not needed to reach a verdict per the known
  local-only `UniqueViolation` artifact); CI's Backend tests job (run `37041269712`) already
  covers the DB-backed isolation tests and passed. `pnpm test:a11y` would not exercise this
  feature either way — see T024's gap.
- [x] **T027** — Run the G3 evidence command and confirm its output still reports G3 unmet —
  this feature must not move that measurement (Release posture, spec.md).
  **Verified 2026-10-03, by source inspection rather than a live run**: no `DATABASE_URL` is set
  in this environment, so `apps/api/scripts/g3_evidence.py` can't be run end-to-end here.
  Instead read the script directly: it measures `active_accounts`, `quotation`/
  `integration_sourced_quotations`, and `purchase_order` 180-day-history counts — grepped the
  whole file for `demand_forecast`/`reorder_proposal`/`forecast`: zero hits. This feature's
  tables are structurally outside what this script measures, so it cannot have moved the G3
  gate's reported status regardless of how many forecasts or proposals exist.
- [x] **T028** — Review the full diff for secrets, hardcoded UI copy, any autonomous-purchase code
  path, and any tenant-scoped table missing forced RLS (Constitution Principles III, V, VII;
  CLAUDE.md non-negotiables 1, 4, 5, 8).
  **Verified 2026-10-03**: no secrets in the forecasting module or migration (plain SQL/Python,
  no credentials). All HTML strings in `reorder-queue.component.html` go through
  `| translate`/`translate:{...}` — no hardcoded English literals found by inspection.
  `prepare_request` creates only a `"status": "draft"` purchase request
  (`requests/service.py` line 84) and never touches `purchase_order` — grepped `service.py` for
  "purchase_order": zero hits. Both new tables have `enable row level security` +
  `force row level security` (confirmed under T003). `ruff check
  apps/api/src/procurepilot_api/modules/forecasting` passes clean, matching the `ab4a8fc`
  lint-fix commit already on `main`.

## Verification Commands

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_forecast_calculator.py -q
uv run --project apps/api pytest apps/api/tests/contract/test_forecasting_contract.py -q
uv run --project apps/api pytest apps/api/tests/integration/test_forecasting_api.py -q
uv run --project apps/api pytest apps/api/tests/integration/test_forecasting_isolation.py -q
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/forecasting
pnpm --dir apps/web exec ng test --watch=false --browsers=ChromeHeadless --include='src/app/features/forecasting/**/*.spec.ts'
pnpm test:isolation
pnpm test:a11y
```
