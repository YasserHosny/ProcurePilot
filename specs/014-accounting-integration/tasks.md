# Tasks: Accounting Integration & Reconciliation Foundation

**Feature**: 014-accounting-integration
**Created**: 2026-09-18
**Status**: Draft
**Input**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/accounting-integration.openapi.yaml`, `quickstart.md`

**A real dependency note, unlike the generic template's default assumption of independent
stories**: the three user stories here form an actual pipeline, not three unrelated slices. US2
(sync + match) has nothing to sync without US1 (a connection). US3 (discrepancies) is computed
*from* US2's match results. They are still each independently *testable* (a stub connector lets
US2/US3 be tested without a real live connection), but they are not independently *implementable*
in parallel the way the template usually assumes — build them in order.

## Phase 1 — Setup

- [x] **T001** — Config: add `accounting_provider_mode` (`stub`/`quickbooks`, default `stub`),
  `quickbooks_client_id`, `quickbooks_client_secret` (SecretStr), `quickbooks_redirect_uri`,
  `quickbooks_environment` (`sandbox`/`production`) to `apps/api/src/procurepilot_api/config.py`,
  matching `EXTRACTION_PROVIDER_MODE`'s existing settings shape exactly (research.md R5).
- [x] **T002** [P] — Module skeleton: `apps/api/src/procurepilot_api/modules/accounting/
  __init__.py`, `schemas.py` (empty Pydantic models per data-model.md's tables — fill in as each
  story needs them), `router.py` wired into `main.py`'s router registration, matching
  `modules/ingestion/__init__.py`'s own T008 precedent.

## Phase 2 — Foundational (blocking — every user story needs this)

- [x] **T003** — Migration: `purchase_record` composite key fix
  (`supabase/migrations/202609XX000001_purchase_record_composite_key.sql`) — add
  `alter table purchase_record add constraint purchase_record_tenant_id_key unique (tenant_id,
  id);` exactly as research.md R7 specifies. Pure additive constraint, no backfill needed.
- [x] **T004** [P] — Migration: `accounting_connection` table
  (`supabase/migrations/202609XX000002_accounting_connection.sql`) — per data-model.md exactly:
  columns, `accounting_provider`/`accounting_connection_status` enums, the
  `unique (tenant_id) where status <> 'disconnected'` partial constraint, `ENABLE + FORCE` RLS
  with `SELECT` for any member and `INSERT`/`UPDATE` owner-only.
- [x] **T005** [P] — Migration: `synced_vendor` table
  (`supabase/migrations/202609XX000003_synced_vendor.sql`) — per data-model.md, FK into
  `accounting_connection(tenant_id, id)` and `supplier(tenant_id, id)`, `ENABLE + FORCE` RLS
  (`SELECT` any member, `INSERT`/`UPDATE` service-role sync path only).
- [x] **T006** [P] — Migration: `synced_bill` table
  (`supabase/migrations/202609XX000004_synced_bill.sql`) — per data-model.md,
  `synced_bill_status` enum, FK into `accounting_connection`/`synced_vendor`/`supplier`
  (all `(tenant_id, id)`-pinned), `ENABLE + FORCE` RLS matching `synced_vendor`'s pattern.
- [x] **T007** [P] — Migration: `purchase_bill_match` table
  (`supabase/migrations/202609XX000005_purchase_bill_match.sql`) — per data-model.md,
  `match_method` enum, FK into `synced_bill`/`purchase_record` (both `(tenant_id, id)`-pinned —
  depends on T003), the two 1:1 uniqueness constraints, `ENABLE + FORCE` RLS with no
  `UPDATE`/`DELETE` grant at all (supersede-by-insert, per data-model.md's Principle-I rationale).
- [x] **T008** [P] — Migration: `reconciliation_discrepancy` table
  (`supabase/migrations/202609XX000006_reconciliation_discrepancy.sql`) — per data-model.md,
  `discrepancy_type`/`discrepancy_status` enums, the mutual-exclusivity `check` constraint,
  `ENABLE + FORCE` RLS with `UPDATE` restricted to `owner`/`buyer` and only the resolution
  columns (mirror `digest_subscription`'s column-scoped update policy).
- [x] **T009** — Connector abstraction: `AccountingConnector` protocol (typed methods:
  `list_bills(since: date) -> list[RawBill]`, `list_vendors() -> list[RawVendor]`,
  `company_info() -> CompanyInfo`  — no write method exists on the protocol at all, enforcing
  FR-013 at the type level, not just by convention) plus `StubConnector` (returns fixture data)
  in `apps/api/src/procurepilot_api/modules/accounting/connector.py`.
- [x] **T010** — `QuickBooksClient`: OAuth2 authorization-code + refresh-token flow and the three
  read-only REST calls (`Bill`, `Vendor`, `CompanyInfo` via QuickBooks's `/v3/company/{realmId}/
  query` endpoint), built on `httpx` per research.md R1 — implements the same
  `AccountingConnector` protocol as `StubConnector`, in
  `apps/api/src/procurepilot_api/modules/accounting/quickbooks_client.py`. No SDK dependency.
- [x] **T011** [P] — Unit tests for `QuickBooksClient`'s OAuth token exchange/refresh logic and
  REST response parsing (mocked `httpx` responses, no real network call) in
  `apps/api/tests/unit/test_quickbooks_client.py`.

**Checkpoint**: connector abstraction, all five tables, and the composite-key fix exist. No user
story can be implemented before this phase is done.

## Phase 3 — User Story 1: Connect an accounting account (Priority: P1) 🎯 MVP

**Goal**: An owner can connect, see connection status at all times, disconnect without losing
history, and see the "needs re-authorization" state when appropriate — no sync or reconciliation
logic yet.

**Independent Test**: Connect (or fail to connect) using the stub connector's own fake
authorization flow, and verify connection state transitions correctly through every acceptance
scenario in spec.md's User Story 1 — no bills, matches, or discrepancies involved.

- [x] **T012** [US1] — `ConnectionService` (connect: mint the provider authorization URL;
  complete: exchange the callback code for tokens via the connector, create the
  `accounting_connection` row; disconnect: set `status = 'disconnected'`, `disconnected_at`,
  never delete the row; status: read current state) in
  `apps/api/src/procurepilot_api/modules/accounting/service.py`. Every method takes `member:
  CurrentMember` and runs through `_authenticated_db`, matching every other ingestion/reporting
  service's own established pattern.
- [x] **T013** [US1] — Router: `POST /accounting/connect`, `GET /accounting/connect/callback`,
  `GET /accounting/connection`, `POST /accounting/disconnect` in
  `apps/api/src/procurepilot_api/modules/accounting/router.py`, matching the contract exactly
  (`contracts/accounting-integration.openapi.yaml`). `connect`/`disconnect` gated
  `require_role(owner)` (FR-003); `connection` (GET) open to any authenticated member.
  Record `accounting.connection_created`/`accounting.connection_disconnected` audit events.
- [x] **T014** [US1] — Pydantic schemas for the four endpoints
  (`AccountingConnection`, `StartConnectionResponse`) in
  `apps/api/src/procurepilot_api/modules/accounting/schemas.py`, matching the contract's
  component schemas field-for-field.
- [x] **T015** [US1] — Integration tests in
  `apps/api/tests/integration/test_accounting_connection.py`: owner can connect (stub connector),
  non-owner gets 403, a second connect attempt while one is active returns 409, disconnect
  preserves the row (`status = 'disconnected'`, not deleted), a declined/failed callback leaves
  no connection row at all (spec Acceptance Scenario 1.3), a connection whose refresh fails
  transitions to `needs_reauth` (spec Acceptance Scenario 1.4), cross-tenant connection lookup
  resolves not-found.
- [x] **T016** [P] [US1] — Frontend: `apps/web/src/app/features/accounting/connection-settings/`
  component — connection status card, "Connect" button (redirects to the authorization URL),
  "Disconnect" button (owner-only, `*appRole="'owner'"` display gate matching
  `email-config.component.ts`'s own established pattern), needs-reauth banner. Karma spec
  alongside it, following `email-config.component.spec.ts`'s `.overrideComponent()` pattern if
  `MatSnackBar` is used for feedback (see the standing gotcha in `delegate-heavily-to-codex`/prior
  wave docs — a plain `TestBed.configureTestingModule({ providers })` override silently fails
  for a standalone component here).
- [x] **T017** [P] [US1] — `apps/web/src/app/features/accounting/accounting-api.ts` — typed API
  client for the four US1 endpoints, matching `ingestion-api.ts`'s own shape and error handling.

**Checkpoint**: an owner can connect/disconnect and see status. Fully functional and demoable on
its own (US1 has no dependency on US2/US3 to be independently *tested*, even though the reverse
is not true).

## Phase 4 — User Story 2: See synced bills and invoices alongside purchase records (Priority: P2)

**Goal**: Once connected, bills and vendors sync (daily + on-demand) and automatically match
against `purchase_record` per FR-007's exact tolerance.

**Independent Test**: With a stub-connector connection already established (US1), trigger a sync
and verify bills appear with correct fields, matching behaves exactly per the 14-day/$0.01 rule,
and re-syncing reflects provider-side changes (spec Acceptance Scenario 2.4) — no discrepancy UI
needed yet to verify this story's own value.

- [ ] **T018** [US2] — `SyncService.sync(connection)`: calls the connector's `list_vendors()`
  then `list_bills()`, upserts `synced_vendor`/`synced_bill` by `(tenant_id, connection_id,
  provider_*_id)`, applies research.md R3's name-based vendor matching (persisting
  `matched_supplier_id` on first match, reusing the stored link on subsequent syncs), updates
  `accounting_connection.last_synced_at`, and invokes `MatchingService` (T019) once bills are
  upserted. First sync scopes to `bill_date >= connected_at - 90 days` (FR-015); later syncs are
  unbounded. In `apps/api/src/procurepilot_api/modules/accounting/sync_service.py`.
- [ ] **T019** [US2] — `MatchingService.match_bill(bill)`: finds `purchase_record` candidates for
  `bill.matched_supplier_id` where `total_paid_amount` is within $0.01 of `bill.amount` (same
  currency) and `bill.bill_date` is within 14 days of the purchase record's own date; creates a
  `purchase_bill_match` row (`match_method = 'automatic'`) only when exactly one qualifying
  candidate exists — more than one candidate is left unmatched for manual review (FR-007's own
  tie-breaking rule), not auto-picked. In
  `apps/api/src/procurepilot_api/modules/accounting/matching_service.py`. Add a one-line module
  docstring note disambiguating SC-002's ≥90% bill↔purchase-record auto-match rate from the
  constitution's unrelated "Matching precision at auto-accept ≥92%" gate (quotation-line↔
  canonical-product matching, a different system entirely) — the two numbers are easy to conflate
  later since both are ~90% matching thresholds in the same codebase.
- [ ] **T020** [P] [US2] — Unit tests for `MatchingService`'s matching/tie-breaking logic
  (no DB — pure function over in-memory candidate lists) in
  `apps/api/tests/unit/test_matching_service.py`: exact match, $0.01-rounding match, just-inside/
  just-outside the 14-day window, multiple equally-qualifying candidates left unmatched, zero
  candidates left unmatched.
- [ ] **T021** [US2] — Worker: `apps/api/src/procurepilot_api/workers/accounting_sync_worker.py` — daily
  `FOR UPDATE SKIP LOCKED` claim loop over connections due for sync (mirrors
  `email_ingestion_worker.py`'s exact shape: claim, call `SyncService.sync`, mark
  `accounting.sync_completed`/`accounting.sync_failed`, `tenant_id` read from the claimed
  connection row, never re-derived from any external payload since there is none here).
- [ ] **T022** [US2] — Router: `POST /accounting/sync` (manual trigger, refuses with 409 if a
  sync for this connection is already running — FR-009, checked via a `status = 'syncing'`
  transitional connection state or an advisory lock, pick one and document the choice) and
  `GET /accounting/bills` (cursor-paginated, `match_status` filter) in `router.py`, matching the
  contract. `sync` gated `require_role(owner, buyer)`; `bills` open to any authenticated member.
- [ ] **T023** [US2] — Integration tests in
  `apps/api/tests/integration/test_accounting_sync.py`: a full sync creates the expected
  `synced_bill`/`synced_vendor` rows with correct fields (spec Acceptance Scenario 2.1), a
  provider-side bill update is reflected on re-sync (Acceptance Scenario 2.4), the 90-day initial
  window is respected, two concurrent sync triggers for the same connection — one wins, one
  gets 409 (FR-009, edge case), a `needs_reauth` connection's sync attempt fails gracefully
  without crashing the worker loop.
- [ ] **T024** [P] [US2] — Integration tests in
  `apps/api/tests/integration/test_accounting_matching.py`: exact match creates a
  `purchase_bill_match`, a synced bill with no matching purchase record stays unmatched and
  visible (not hidden — Acceptance Scenario 2.3), cross-tenant purchase records are never
  candidates (proven here directly, not just assumed from RLS), **and SC-002's own aggregate
  claim specifically**: seed a batch of purchase records where a known fraction are genuinely
  matchable (same supplier, amount within $0.01, date within 14 days) and the rest are not, run
  matching, and assert the computed match rate over that batch is ≥90% — a per-case assertion
  alone doesn't prove the measurable success criterion the spec actually states.
- [ ] **T025** [P] [US2] — Integration test for the worker's own claim loop in
  `apps/api/tests/integration/test_accounting_sync_worker.py`, modeled directly on
  `test_email_ingestion_worker.py`'s real-overlapping-transactions concurrency proof — do not
  reintroduce a sleep-based race.
- [x] **T026** [P] [US2] — Frontend: `apps/web/src/app/features/accounting/bills/` component —
  bill list with matched/unmatched filter, showing supplier, amount+currency, date, status, and
  a link to the matched purchase record where one exists. Karma spec alongside it.
- [x] **T027** [US2] — Extend `accounting-api.ts` with the sync-trigger and bills-list methods.

**Checkpoint**: bills sync and match automatically. US1 + US2 together are demoable as "connect
and see your real bills reconciled against purchases."

## Phase 5 — User Story 3: Review and resolve reconciliation discrepancies (Priority: P3)

**Goal**: Every sync derives the current discrepancy set (amount mismatches, unmatched bills,
unmatched purchases past 30 days), and an owner/buyer can resolve one, with re-evaluation if the
underlying records change again later.

**Independent Test**: Seed a mix of matched, unmatched, and amount-mismatched bill/purchase pairs
directly (bypassing a real sync), run discrepancy derivation, and confirm exactly the expected
set appears with the right type/detail — independent of whether US2's own live sync path is what
produced that state.

- [x] **T028** [US3] — `ReconciliationService.recompute_discrepancies(connection)`: derives the
  current discrepancy set per data-model.md's three shapes and re-evaluation rule (a `resolved`
  discrepancy whose underlying `synced_bill`/`purchase_record` `updated_at` is newer than its own
  `resolved_at` is reopened, not duplicated); `resolve(discrepancy_id, member, note)`: sets
  `status = 'resolved'`, `resolved_by`, `resolved_at`, `resolution_note`. Called by
  `SyncService.sync` at the end of every sync (T018), not only on manual request. In
  `apps/api/src/procurepilot_api/modules/accounting/reconciliation_service.py`.
- [x] **T029** [US3] — Router: `GET /accounting/discrepancies` (cursor-paginated, `status` filter,
  default `open`) and `POST /accounting/discrepancies/{discrepancy_id}/resolve` in `router.py`,
  matching the contract. `resolve` gated `require_role(owner, buyer)` (FR-011). Record
  `accounting.discrepancy_resolved` audit events.
- [x] **T030** [US3] — Integration tests in
  `apps/api/tests/integration/test_reconciliation_discrepancies.py`: an amount mismatch on a
  matched pair is detected and shows both figures (Acceptance Scenario 3.1), an unmatched bill
  appears immediately while an unmatched purchase record appears only after 30 days (Acceptance
  Scenario 3.2 — test both the just-under and just-over boundary), resolving records
  resolver/timestamp/note (Acceptance Scenario 3.3), a resolved discrepancy reopens (not
  duplicates) when its underlying records change again on a later sync (Acceptance Scenario
  3.4), resolving an already-resolved discrepancy returns 409, cross-tenant discrepancy lookup
  resolves not-found.
- [x] **T031** [P] [US3] — Frontend: `apps/web/src/app/features/accounting/discrepancies/`
  component — discrepancy list (open by default), per-type detail rendering (side-by-side
  amounts for mismatches; supplier/amount/date for unmatched bills/purchases), resolve action
  with an optional note field. Karma spec alongside it.
- [x] **T032** [US3] — Extend `accounting-api.ts` with the discrepancy-list and resolve methods.

**Checkpoint**: all three user stories work end to end — connect, sync + match, review +
resolve.

## Phase 6 — Polish & Cross-Cutting Concerns

- [ ] **T033** — i18n: add the `accounting.*` namespace (connection settings, bills, discrepancy
  labels and messages) to `packages/i18n/en.json` and `packages/i18n/ar.json` — real Arabic, not
  transliterated. Should land before T016/T026/T031 in practice (matching how 013-automated-
  ingestion sequenced its own i18n task first so five parallel frontend builds never touched the
  same two JSON files) — listed here for completeness of the polish phase's own file, but treat
  it as an early, not final, task in actual execution order.
- [ ] **T034** — Routing + navigation: add the four `/accounting/*` routes to
  `apps/web/src/app/app.routes.ts` (matching `/ingestion`'s own route-registration shape,
  `connect`/`sync` role-gated `roleGuard('owner', 'buyer')` where the router itself should guard
  rather than relying on component-level display gating alone) and one hub sidenav entry in
  `apps/web/src/app/layout/shell/shell.component.html` (single entry point, matching
  `/ingestion`'s own hub-and-spoke pattern — the bills/discrepancies sub-pages are reached from
  within the connection-settings/dashboard view, not their own separate sidenav items).
- [ ] **T035** — Tenant isolation: extend the canonical `apps/api/tests/integration/
  test_tenant_isolation.py` with all five new tables (visibility + cross-tenant-write pairs,
  matching 013-automated-ingestion's T034 pattern exactly) and add them to
  `test_rls_is_enabled_and_forced_on_every_tenant_scoped_table`'s allowlist.
- [ ] **T036** — E2E: `apps/web/tests/e2e/accounting.spec.ts` — connect (stub-backed test
  environment), trigger a sync, see bills and at least one automatic match, see and resolve a
  discrepancy — one continuous flow given the real pipeline dependency between the three stories.
  Include SC-001 and SC-003's own timing claims explicitly rather than leaving them
  unverified: assert the connect flow (from clicking "Connect" through seeing the active
  connection state) completes well within 2 minutes, and the resolve-a-discrepancy flow (from
  opening the discrepancy list through the resolved state) well within 60 seconds — a generous
  assertion margin against the stated budget (e.g. assert under half the stated limit) is fine;
  the point is catching a real regression, not chasing a tight CI timing budget.
- [ ] **T037** — a11y: `apps/web/tests/e2e/accounting-a11y.spec.ts` — axe-core WCAG 2.1 AA on all
  three new screens in English and Arabic, keyboard navigation for the resolve-discrepancy action.
- [ ] **T038** — Docs: add the accounting integration section to
  `docs/architecture/api-specification.md` and `docs/architecture/data-dictionary.md`, and
  reconcile `contracts/accounting-integration.openapi.yaml` against the real implementation
  (expect real drift, same as 013-automated-ingestion's own T041 — do not assume the pre-written
  contract survived implementation unchanged).
- [ ] **T039** — Security review: OAuth token storage/encryption, the callback endpoint's `state`
  parameter (CSRF protection on the OAuth flow — verify it's checked, not just passed through),
  read-only enforcement (grep the whole `modules/accounting/` tree for any QuickBooks write call
  — there should be none), rate-limiting on the sync-trigger and resolve endpoints, tenant
  isolation re-confirmation. Follow the R3.0/T042 precedent: done in-house, findings fixed not
  just recorded.

## Dependencies & Execution Order

- **Setup (Phase 1)** → **Foundational (Phase 2)**: strictly sequential, no user story starts
  before Phase 2 completes.
- **US1 (Phase 3)**: depends only on Phase 2.
- **US2 (Phase 4)**: depends on Phase 2 **and** US1 (needs a real connection to sync from) — not
  parallelizable with US1 despite the template's usual assumption.
- **US3 (Phase 5)**: depends on Phase 2 **and** US2 (discrepancies are derived from sync/match
  results) — not parallelizable with US2 either.
- **Polish (Phase 6)**: depends on all three stories, except T033 (i18n) and T034 (routing),
  which should actually land *before* each story's own frontend task despite being listed in the
  polish phase — see T033's own note.

### Parallel opportunities within a phase

- Phase 2: T004–T008 (the five migrations) are independent files, parallelizable; T003 must land
  before T007 specifically (the FK it enables). T011 is independent of T009/T010's own
  implementation once their interfaces are stable enough to mock against.
- Within each user story phase: the frontend task ([P]-marked) and its own backend tasks touch
  different files and can proceed in parallel once that story's contract/schema shape is fixed;
  the [P]-marked test files within a story are mutually independent.

## Implementation Strategy

**MVP**: Phase 1 + Phase 2 + Phase 3 (US1) — a real, demoable "connect your QuickBooks account"
capability, even before any sync/matching logic exists. Matches this feature's own spec-level
prioritization (P1).

**Incremental delivery**: US1 → US2 → US3, in that order, each a real increment — this is not
just a suggested delivery order, it is the actual dependency order (see above), so there is no
alternative sequencing to choose between here the way a fully independent-stories feature would
have.
