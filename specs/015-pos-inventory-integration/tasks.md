# Tasks: POS & Inventory Integration — Usage Signals

**Feature**: 015-pos-inventory-integration
**Created**: 2026-09-19 (revised 2026-09-19 post-`/speckit.analyze`)
**Status**: Draft
**Input**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/pos-integration.openapi.yaml`, `quickstart.md`

**A real dependency note, unlike the generic template's default assumption of independent
stories**: US2 (sync + velocity/stock display) has nothing to sync without US1 (a connection) —
not parallelizable with US1. US3 (purchasing unaffected by disconnect) is a regression-proofing
story that only becomes meaningfully testable once US1 and US2 exist to disconnect *from* — build
in priority order, same shape as 014-accounting-integration's own pipeline dependency.

**Post-analysis note**: `/speckit.analyze` found two CRITICAL issues before implementation began —
a reconnect-dedup design flaw (SC-005) and a missing Constitution Principle I disclosure
requirement for partial-window velocity figures (now FR-013) — plus a missing SC-002 aggregate
test, a missing `pos.sync_started` audit event, and an unpinned sync interval. All five are folded
into the task descriptions below (T005, T016, T019, T025, T026) rather than left as follow-up
work.

## Phase 1 — Setup

- [x] **T001** — Config: add `pos_provider_mode` (`stub`/`square`, default `stub`),
  `square_application_id`, `square_application_secret` (SecretStr), `square_redirect_uri`,
  `square_environment` (`sandbox`/`production`), `pos_token_encryption_key` (SecretStr),
  `rate_limit_pos_sync` (default `"10/minute"`), `rate_limit_pos_match` (default `"30/minute"`) to
  `apps/api/src/procurepilot_api/config.py`, matching `accounting_provider_mode`'s existing
  settings shape exactly (research.md R1/R3). Extend the `empty_secret_to_none` validator to cover
  `pos_token_encryption_key`.
- [x] **T002** [P] — Module skeleton: `apps/api/src/procurepilot_api/modules/pos/__init__.py`,
  `schemas.py` (empty Pydantic models per data-model.md's tables — fill in as each story needs
  them), `router.py` wired into `main.py`'s router registration, matching
  `modules/accounting/__init__.py`'s own precedent. Do **not** add
  `from __future__ import annotations` to `router.py` — combining deferred annotations with a
  `@mutation_limiter.limit()` decorator on a path-parameter endpoint breaks FastAPI/pydantic's
  forward-ref resolution (the exact bug found and fixed in `modules/accounting/router.py` this
  program; `modules/ingestion/router.py` is the working precedent to match).
- [x] **T003** — Extract `encrypt_token()`/`decrypt_token()` from
  `apps/api/src/procurepilot_api/modules/accounting/token_crypto.py` into
  `apps/api/src/procurepilot_api/shared/token_crypto.py` (research.md R3), generalizing only the
  settings-key lookup (accept the encryption key as a constructor/function argument rather than
  reading `accounting_token_encryption_key` directly). Update
  `modules/accounting/service.py`/`sync_service.py` to import from `shared/` instead. Run the full
  existing accounting test suite afterward to confirm zero behavior change — this must not be a
  refactor-and-hope move.

## Phase 2 — Foundational (blocking — every user story needs this)

- [x] **T004** [P] — Migration: `pos_connection` table
  (`supabase/migrations/202609XX000001_pos_connection.sql`) — per data-model.md exactly: columns,
  `pos_provider`/`pos_connection_status` enums, the
  `unique (tenant_id) where disconnected_at is null` partial constraint, `ENABLE + FORCE` RLS with
  `SELECT` for any member and `INSERT`/`UPDATE` owner-only. Column-targeted
  `on delete set null (...)` on every optional multi-column FK, not plain `on delete set null` —
  this exact bug has been found and fixed five times already this program; new tables get it right
  from the first migration.
- [x] **T005** [P] — Migration: `synced_product_signal` table
  (`supabase/migrations/202609XX000002_synced_product_signal.sql`) — per data-model.md exactly,
  including the analysis-time fix (research.md R8/R9): FK into `pos_connection(tenant_id, id)`
  where `pos_connection_id` is a floating "last synced via" pointer, **not** part of the
  uniqueness key; `unique (tenant_id, external_item_id)` only, so a row survives a
  disconnect/reconnect cycle instead of duplicating (SC-005); `velocity_window_days_observed`
  column alongside `velocity_window_days` (FR-013). `ENABLE + FORCE` RLS (`SELECT` any member,
  `INSERT`/`UPDATE` worker's tenant-scoped session only — `current_member_role() is null`, no
  member-facing mutation endpoint writes this table).
- [x] **T006** [P] — Migration: `pos_product_match` table
  (`supabase/migrations/202609XX000003_pos_product_match.sql`) — per data-model.md, reuses the
  `match_method` enum already created by 014-accounting-integration's own migration (do not
  recreate it), FK into `synced_product_signal`/`workspace_product` (both `(tenant_id, id)`-
  pinned), the two 1:1 uniqueness constraints, `ENABLE + FORCE` RLS with no `UPDATE` grant at all
  (supersede-by-insert, matching `purchase_bill_match`'s own provenance-preserving shape), `DELETE`
  split between worker (automatic matches only) and owner/buyer (any match). Because
  `synced_product_signal_id` is now stable across reconnects (T005), a match made before a
  disconnect remains valid after a reconnect with no extra handling needed here.
- [x] **T007** — Connector abstraction: `PosConnector` protocol (typed methods:
  `list_sales_transactions(since: date) -> list[RawSalesTransaction]`,
  `list_inventory_levels() -> list[RawInventoryLevel]`, `get_account_info() -> PosAccountInfo` —
  no write method exists on the protocol at all, enforcing FR-002/FR-004's read-only constraint at
  the type level) plus `StubConnector` (returns fixture sales/inventory data covering: a matched
  item with both signals, an item with stock but no sales history, an item with sales but no
  inventory tracking, an item name close enough to two real catalogue products to exercise the
  ambiguous-match edge case, and an item with fewer than `velocity_window_days` of transaction
  history to exercise FR-013's provisional-figure path) in
  `apps/api/src/procurepilot_api/modules/pos/connector.py`.
- [x] **T008** — `SquareClient`: OAuth2 authorization-code + refresh-token flow, and the two
  read-only REST calls (Orders API for sales transactions, Inventory API for stock counts) built
  on `httpx` per research.md R1 — implements the same `PosConnector` protocol as `StubConnector`,
  in `apps/api/src/procurepilot_api/modules/pos/square_client.py`. No SDK dependency.
- [x] **T009** [P] — Unit tests for `SquareClient`'s OAuth token exchange/refresh logic and REST
  response parsing (mocked `httpx` responses, no real network call) in
  `apps/api/tests/unit/test_square_client.py`.

**Checkpoint**: connector abstraction, all three tables, and the token-crypto extraction exist. No
user story can be implemented before this phase is done.

## Phase 3 — User Story 1: Connect a POS account and see real demand signal (Priority: P1) 🎯 MVP

**Goal**: An owner can connect, see connection status at all times, disconnect without losing
history, and see the "needs re-authorization" state when appropriate — no sync, velocity, or stock
data yet.

**Independent Test**: Connect (or fail to connect) using the stub connector's own fake
authorization flow, and verify connection state transitions correctly through every acceptance
scenario in spec.md's User Story 1 — no signals or matches involved.

- [x] **T010** [US1] — `ConnectionService` (connect: mint the provider authorization URL;
  complete: exchange the callback code for tokens via the connector — encrypt via
  `shared/token_crypto.py` (T003) before writing, create a **new** `pos_connection` row (a
  reconnect after a prior disconnect always inserts a new row — the old, disconnected row is never
  reactivated, preserving connection history for FR-010's audit trail per research.md R8);
  disconnect: set `disconnected_at`, never delete the row; status: read current state) in
  `apps/api/src/procurepilot_api/modules/pos/service.py`. Every member-facing method takes
  `member: CurrentMember` and runs through the existing `_authenticated_db` pattern; token
  read/write goes through a literal `service_role` session exactly as `accounting_connection`'s
  own tokens do (data-model.md).
- [x] **T011** [US1] — Router: `POST /pos/connect`, `GET /pos/connect/callback`,
  `GET /pos/connection`, `POST /pos/disconnect` in
  `apps/api/src/procurepilot_api/modules/pos/router.py`, matching the contract exactly
  (`contracts/pos-integration.openapi.yaml`). `connect`/`disconnect` gated `require_role(owner)`
  (FR-001); `connection` (GET) open to any authenticated member. Record
  `pos.connection_created`/`pos.connection_disconnected` audit events.
- [x] **T012** [US1] — Pydantic schemas for the four endpoints (`PosConnection`,
  `StartConnectionResponse`) in `apps/api/src/procurepilot_api/modules/pos/schemas.py`, matching
  the contract's component schemas field-for-field.
- [x] **T013** [US1] — Integration tests in `apps/api/tests/integration/test_pos_connection.py`:
  owner can connect (stub connector), non-owner gets 403, a second connect attempt while one is
  active returns 409, disconnect preserves the row (`disconnected_at` set, not deleted, previously
  synced data stays queryable — Acceptance Scenario 1.2), a declined/failed callback leaves no
  connection row at all (Acceptance Scenario 1.3), a connection whose token refresh fails
  transitions to `needs_reauth` on the next sync attempt (Acceptance Scenario 1.4), cross-tenant
  connection lookup resolves not-found, reconnecting after a disconnect creates a distinct new
  `pos_connection` row (both old and new rows queryable, confirming connection history is
  preserved per T010's note).
- [x] **T014** [P] [US1] — Frontend: `apps/web/src/app/features/pos/connection-settings/`
  component — connection status card, "Connect" button (redirects to the authorization URL),
  "Disconnect" button (owner-only display gate matching `email-config.component.ts`'s established
  pattern), needs-reauth banner. Karma spec alongside it.
- [x] **T015** [P] [US1] — `apps/web/src/app/features/pos/pos-api.ts` — typed API client for the
  four US1 endpoints, matching `accounting-api.ts`'s own shape and error handling.

**Checkpoint**: an owner can connect/disconnect and see status. Fully functional and demoable on
its own.

## Phase 4 — User Story 2: See stock-on-hand and sales velocity before ordering (Priority: P2)

**Goal**: Once connected, sales transactions and inventory levels sync (daily + on-demand), Square
catalog items are matched to `workspace_product` rows, and matched products show sales-velocity
and stock-on-hand as read-only context on the screens a buyer already uses to decide how much to
order — with a partial-history figure visibly marked provisional (FR-013), and identity that
survives a disconnect/reconnect cycle without duplicating (SC-005).

**Independent Test**: With a stub-connector connection already established (US1), trigger a sync
and verify signals appear with correct stock/velocity fields and matching behaves per FR-006's
tie-breaking rule, independent of whether the inline display on Smart Compare/catalogue is wired
up yet.

- [x] **T016** [US2] — `SyncService.sync(connection)`: calls the connector's
  `list_sales_transactions(since)` and `list_inventory_levels()`, upserts `synced_product_signal`
  **by `(tenant_id, external_item_id)` only** (T005's dedup key — always sets `pos_connection_id`
  to *this* sync's connection id on every upsert, whether the row is new or pre-existing from a
  prior, now-disconnected connection, per research.md R8), computes `sales_velocity_per_day` as a
  30-day trailing average recomputed from stored transaction data each sync — never an
  incrementally-updated running counter (research.md R5, Constitution Principle II) — and sets
  `velocity_window_days_observed` to the actual number of days of transaction history available
  (may be less than `velocity_window_days` for a recently-matched or recently-connected item,
  FR-013/research.md R9), leaves `stock_on_hand`/`sales_velocity_per_day` null where the connector
  reports no data for that signal type (FR-005's "absence must never look like zero"), updates
  `pos_connection.last_synced_at`, records a `pos.sync_started` audit event when the advisory lock
  (T019) is acquired and `pos.sync_completed`/`pos.sync_failed` on completion (FR-010's full
  started/completed/failed triple), and invokes `ProductMatchingService` (T017) for every signal
  with no existing `pos_product_match`. In
  `apps/api/src/procurepilot_api/modules/pos/sync_service.py`.
- [x] **T017** [US2] — `ProductMatchingService.match_signal(signal)`: reuses
  `modules/matching/search.py`'s `build_similarity_candidates` and
  `modules/matching/embeddings.py` (research.md R4) scored against `workspace_product.tenant_name`
  joined to `canonical_product.name`/`brand`, creates a `pos_product_match` row
  (`match_method='automatic'`, `confidence` set from the score) only when exactly one candidate
  clears the same auto-accept confidence threshold quotation-line matching already uses — more
  than one qualifying candidate, or none, is left unmatched for manual review (FR-006), not
  auto-picked. In `apps/api/src/procurepilot_api/modules/pos/matching_service.py`.
- [x] **T018** [P] [US2] — Unit tests for `ProductMatchingService`'s tie-breaking logic (mocked
  candidate lists, no DB) in `apps/api/tests/unit/test_pos_matching_service.py`: single confident
  match, multiple equally-qualifying candidates left unmatched (the bundle-vs-component edge case
  from spec.md), zero candidates left unmatched.
- [x] **T019** [US2] — Worker: `apps/api/src/procurepilot_api/workers/pos_sync_worker.py` — daily
  `pg_try_advisory_lock(hashtext(connection_id))`-guarded claim loop over connections due for sync
  (mirrors `accounting_sync_worker.py`'s exact shape: acquire the lock, record `pos.sync_started`,
  call `SyncService.sync`, mark `pos.sync_completed`/`pos.sync_failed` — the `sync_started` event
  must land here even if `SyncService.sync` itself later hangs or crashes, so a stuck sync still
  leaves an audit trace, closing the gap `/speckit.analyze` found). Worker-initiated writes use the
  tenant-scoped `authenticated`-without-member-claims session convention (research.md R6), never a
  literal `service_role` connection.
- [x] **T020** [US2] — Router: `POST /pos/sync` (manual trigger; the advisory lock from T019 makes
  a concurrent attempt fail fast — return 409 rather than queueing, FR-002) and `GET /pos/signals`
  (cursor-paginated, `match_status` and `workspace_product_id` filters) in `router.py`, matching
  the contract. Decorate `sync` with `@mutation_limiter.limit(_pos_sync_limit)` reading
  `rate_limit_pos_sync` (T001) — reuse the existing `mutation_limiter` from
  `shared/rate_limit.py`, already fixed to key on the route template
  (`key_style="endpoint"`), not the literal URL. `sync` gated `require_role(owner, buyer)`;
  `signals` open to any authenticated member.
- [x] **T021** [US2] — Router: `POST /pos/signals/{signal_id}/match` (manual match — FR-006's
  resolution path) in `router.py`, matching the contract. Decorate with
  `@mutation_limiter.limit(_pos_match_limit)` reading `rate_limit_pos_match`. Gated
  `require_role(owner, buyer)`. Returns 409 if the signal or the target product already has a
  match (the 1:1 constraints from T006 are the real enforcement; the endpoint just surfaces a
  clean error).
- [x] **T022** [US2] — Integration tests in `apps/api/tests/integration/test_pos_sync.py`: a full
  sync creates the expected `synced_product_signal` rows with correct stock/velocity fields
  (Acceptance Scenario 2.1), an item with no inventory tracking shows null stock rather than zero
  (Acceptance Scenario 2.2), a stale stock figure's `stock_synced_at` reflects real staleness
  (Acceptance Scenario 2.3), an item with fewer than 30 days of transaction history gets
  `velocity_window_days_observed` set below `velocity_window_days` (FR-013), two concurrent sync
  triggers for the same connection — one wins, one gets 409, a `needs_reauth` connection's sync
  attempt fails gracefully without crashing the worker loop (Acceptance Scenario 1.4), and a
  `pos.sync_started` audit event is recorded even when `SyncService.sync` is made to raise
  immediately after lock acquisition (proves the started event isn't just implied by a completed
  one).
- [x] **T023** [P] [US2] — Integration tests in
  `apps/api/tests/integration/test_pos_matching.py`: a confident single-candidate match creates a
  `pos_product_match`, ambiguous candidates are left unmatched and visible for manual review, a
  manual match via `POST /pos/signals/{id}/match` succeeds and is recorded with `matched_by`,
  cross-tenant workspace products are never candidates (proven directly, not just assumed from
  RLS).
- [x] **T024** [P] [US2] — SC-002 aggregate coverage test in
  `apps/api/tests/integration/test_pos_sync.py` (or a dedicated
  `test_pos_signal_coverage.py` if that file is getting crowded): seed a batch of Square fixture
  items where a known ≥90% fraction are confidently matchable to existing `workspace_product` rows
  by name/brand and the rest are not, run a full sync, and assert the resulting proportion of
  top-selling (by transaction count) items showing a computed `sales_velocity_per_day` meets
  SC-002's own ≥90% claim — a per-case assertion in T022/T023 does not by itself prove the
  spec's stated aggregate outcome. Mirrors 014-accounting-integration's own equivalent test for
  its SC-002.
- [x] **T025** [US2] — Reconnect-dedup regression test in
  `apps/api/tests/integration/test_pos_sync.py`: connect (stub), sync (creates
  `synced_product_signal` rows and at least one automatic `pos_product_match`), disconnect,
  reconnect (creates a **new** `pos_connection` row per T010), sync again, and assert (a) no
  duplicate `synced_product_signal` row exists for any `external_item_id` seen before the
  disconnect, (b) each such row's `pos_connection_id` now points at the new connection, and (c)
  the `pos_product_match` row created before the disconnect is untouched (same `id`, no
  re-matching triggered) — directly proves the fix for the design flaw `/speckit.analyze` found
  (research.md R8), not just the absence of an error.
- [x] **T026** [P] [US2] — Integration test for the worker's own claim loop in
  `apps/api/tests/integration/test_pos_sync_worker.py`, modeled directly on
  `test_accounting_sync_worker.py`'s real-overlapping-transactions concurrency proof — do not
  reintroduce a sleep-based race.
- [x] **T027** [P] [US2] — Frontend: `apps/web/src/app/features/pos/signals-review/` component —
  unmatched-signal list with a "match to product" action (product picker), matched-signal list for
  reference. Karma spec alongside it.
- [x] **T028** [US2] — Extend `pos-api.ts` (T015) with the sync-trigger, signals-list, and
  manual-match methods.
- [x] **T029** [US2] — Frontend: extend the existing `offers/compare/compare.component` (Smart
  Compare) and the catalogue product detail view to show `sales_velocity_per_day` (with its
  window label) and `stock_on_hand` (with its last-synced label) inline when a matched signal
  exists for that product, and show nothing when it doesn't (FR-005) — when
  `velocity_window_days_observed < velocity_window_days`, render the figure visibly as provisional
  (e.g. "≈4.2 units/day · based on 6 of 30 days", FR-013) rather than identically to a full-window
  figure. **No new route, no new dashboard** (research.md R7). Verify explicitly that
  `modules/offers/recommendation.py`'s scoring logic is untouched by this task (FR-003) — this is
  a display-only addition to an existing component's template/view model, not a change to what it
  recommends.

**Checkpoint**: US1 + US2 together are demoable as "connect Square and see real stock/velocity
context while comparing offers or browsing the catalogue," including a disconnect/reconnect cycle
that never duplicates data and a provisional-figure state that's honest about how little history
it's based on.

## Phase 5 — User Story 3: Purchasing keeps working without the integration (Priority: P3)

**Goal**: A tenant that never connects, or disconnects mid-use, sees every purchasing workflow
(compare, request, record purchase) behave exactly as it did before this feature existed.

**Independent Test**: With no POS connection ever created, exercise every purchasing screen and
confirm no error state, stuck loading indicator, or layout change; then connect, disconnect, and
confirm the same screens behave identically immediately afterward with no lost in-progress work.

- [x] **T030** [US3] — Audit `offers/compare/compare.component` and the catalogue product detail
  view (touched in T029) for a defensive-rendering guarantee: absence of a `pos_connection`,
  absence of a matched signal, and a `needs_reauth`/`disconnected` connection all render the
  screen exactly as it rendered before this feature shipped (Acceptance Scenario 1) — no error
  state, no spinner waiting on a request that will never resolve, no layout shift reserving space
  for data that isn't coming. Fix any gap found rather than assuming T029 already handles it.
- [x] **T031** [US3] — Integration/component tests proving the guarantee: a backend test in
  `apps/api/tests/integration/test_pos_sync.py` (or a new
  `test_pos_purchasing_unaffected.py` if that file is getting crowded) confirming
  purchase-request creation and offer comparison endpoints are entirely unaffected by POS
  connection state (never query `pos_connection` on the hot path of those endpoints at all — grep
  to confirm, don't just test the happy path), plus a frontend spec confirming the compare/
  catalogue components render their pre-existing states correctly with `pos-api.ts` mocked to
  return "not connected."
- [x] **T032** [US3] — Manual verification note (recorded in quickstart.md or this file's own
  checkpoint, not a new automated test): disconnecting mid-session (via `POST /pos/disconnect`)
  while a purchase request is being drafted does not interrupt or lose that draft — drafts live
  entirely in the existing `requests` module/local component state, which this feature never
  touches (Acceptance Scenario 2). Confirm by reading `features/requests/`'s own draft-persistence
  mechanism, not by assuming.

**Checkpoint**: all three user stories verified — connect, sync + match + display, and
graceful-without-it confirmed as a first-class, tested guarantee rather than an assumption.

## Phase 6 — Polish & Cross-Cutting Concerns

- [x] **T033** — i18n: add the `pos.*` namespace (connection settings, signals-review, and the
  inline velocity/stock labels — including the provisional-figure label, FR-013 — added to Smart
  Compare/catalogue) to `packages/i18n/en.json` and `packages/i18n/ar.json` — real Arabic, not
  transliterated. Land this before T014/T027/T029 in actual execution order (matching 014's own
  T033 sequencing note) despite being listed here for completeness of the polish phase's own file.
- [x] **T034** — Routing + navigation: add the `/pos/*` routes to `apps/web/src/app/app.routes.ts`
  (matching `/accounting`'s own route-registration shape, `connect`/`sync`/`match` role-gated at
  the router level, not just component display gating) and one hub sidenav entry in
  `apps/web/src/app/layout/shell/shell.component.html` (single entry point; the signals-review
  sub-page is reached from within the connection-settings view, matching `/accounting`'s own
  hub-and-spoke pattern).
- [ ] **T035** — Tenant isolation: extend the canonical
  `apps/api/tests/integration/test_tenant_isolation.py` with all three new tables (visibility +
  cross-tenant-write pairs, matching 014's own equivalent task exactly) and add them to
  `test_rls_is_enabled_and_forced_on_every_tenant_scoped_table`'s allowlist.
- [ ] **T036** — E2E: `apps/web/tests/e2e/pos.spec.ts` — connect (stub-backed test environment),
  trigger a sync, see stock/velocity context on Smart Compare and a catalogue product, manually
  match an unmatched signal, disconnect and confirm purchasing screens are unaffected (covers
  User Story 3's Acceptance Scenario 2 end to end, not just at the unit level). Assert SC-001's
  connect-in-under-2-minutes budget with a generous margin, same convention as 014's own T036.
- [ ] **T037** — a11y: `apps/web/tests/e2e/pos-a11y.spec.ts` — axe-core WCAG 2.1 AA on the
  connection-settings and signals-review screens, plus the modified Smart Compare/catalogue
  screens, in English and Arabic.
- [x] **T038** — Docs: add the POS/inventory integration section to
  `docs/architecture/api-specification.md` and `docs/architecture/data-dictionary.md`, and
  reconcile `contracts/pos-integration.openapi.yaml` against the real implementation — expect real
  drift, same as every prior feature's own contract reconciliation step.
- [x] **T039** [P] — Rate-limit regression tests extending
  `apps/api/tests/integration/test_mutation_rate_limits.py` with
  `test_pos_sync_rate_limit_refuses_without_syncing` and
  `test_pos_match_rate_limit_refuses_without_matching` (seed enough distinct signals to avoid a
  409-vs-429 ambiguity, mirroring the accounting rate-limit tests' own seeding fix).
- [x] **T040** — Security review: OAuth token storage/encryption via the extracted
  `shared/token_crypto.py` (verify both accounting and pos actually use the shared module post-T003,
  not a stale duplicate), the callback endpoint's `state` parameter (CSRF protection — verify it's
  checked, not just passed through), read-only enforcement (grep the whole `modules/pos/` tree for
  any Square write call — there should be none), rate-limiting on `/pos/sync` and
  `/pos/signals/{id}/match`, tenant isolation re-confirmation. Findings fixed in-house, not just
  recorded.

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)**: strictly sequential, no user story starts
  before Phase 2 completes.
- **US1 (Phase 3)**: depends only on Phase 2.
- **US2 (Phase 4)**: depends on Phase 2 **and** US1 (needs a real connection to sync from) — not
  parallelizable with US1.
- **US3 (Phase 5)**: depends on US1 **and** US2 (there is nothing meaningful to "disconnect from"
  or "keep working despite" until both exist) — not parallelizable with US2.
- **Polish (Phase 6)**: depends on all three stories, except T033 (i18n) and T034 (routing), which
  should land *before* each story's own frontend task despite being listed in the polish phase.

### Parallel opportunities within a phase

- Phase 2: T004–T006 (the three migrations) are independent files, parallelizable; T006 reuses an
  enum from 014's own migration but does not depend on any Phase-2 task here. T009 is independent
  of T007/T008's own implementation once their interfaces are stable enough to mock against.
- Within each user story phase: the frontend task ([P]-marked) and its own backend tasks touch
  different files and can proceed in parallel once that story's contract/schema shape is fixed;
  the [P]-marked test files within a story are mutually independent. T025 (reconnect-dedup) is
  sequential with T022 (both write to `test_pos_sync.py`), not parallelizable with it despite both
  being US2 test tasks.

## Implementation Strategy

**MVP**: Phase 1 + Phase 2 + Phase 3 (US1) — a real, demoable "connect your Square account"
capability, even before any sync/velocity/stock logic exists. Matches this feature's own
spec-level prioritization (P1).

**Incremental delivery**: US1 → US2 → US3, in that order, each a real increment — this is the
actual dependency order (see above), not just a suggested one.
