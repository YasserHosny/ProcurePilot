---
description: "Task list for Mobile MVP implementation"
---

# Tasks: Mobile MVP

**Input**: Design documents from `/specs/009-mobile-app-mvp/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mobile.openapi.yaml, quickstart.md

**Tests**: Included. The constitution requires unit/integration tests on every PR, a dedicated
tenant-isolation proof for all three new tables, branch-scoped-visibility proof for
`low_stock_report` (R2.0's second isolation axis, extended), server-side idempotent-replay proof
for `low_stock_report` (FR-011, research.md R4 revised), and — since FR-009 is this chunk's own
version of "no autonomous purchasing" (no approve/reject surface may exist on mobile at all) — a
direct proof that no mobile-reachable code path, not just no visible widget, can call
`POST /requests/{id}/approve`\|`/reject`.

**Organization**: grouped by setup, blocking foundation, then user stories in spec.md priority
order (P1, P1, P2, P2, P3), so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1-US5 from spec.md; setup and foundational tasks may have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: schema/RLS for the three new tables, the Flutter project scaffold itself (currently a
README placeholder per CLAUDE.md), and i18n/asset scaffolding.

- [ ] T001 [P] Create `device_registration` with `unique (tenant_id, member_id, push_token)`,
  composite FK to `membership(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the member-own-rows-only
  policy (data-model.md RLS Summary — no owner read-all) in
  `supabase/migrations/20260911000049_device_registration.sql`
- [ ] T002 [P] Create `low_stock_report` with composite FKs to `branch(tenant_id, id)`,
  `membership(tenant_id, id)`, and `workspace_product(tenant_id, id)`, the nullable
  `idempotency_key` column with a **partial** `unique (tenant_id, idempotency_key) where
  idempotency_key is not null` index (research.md R4 revised — real server-side dedup for the
  offline-retry case, not just an accepted-but-unenforced header), RLS `ENABLE`+`FORCE`, and the
  branch-scoped visibility policy reused from 008's `purchase_request` mechanism (data-model.md RLS
  Summary) in `supabase/migrations/20260911000050_low_stock_report.sql`
- [ ] T003 [P] Create `push_notification` with composite FKs to `purchase_request(tenant_id, id)`
  and `membership(tenant_id, id)`, the `status`/`attempts`/`sent_at` columns, RLS `ENABLE`+`FORCE`
  with no client-facing read policy this release (service-role only — data-model.md), in
  `supabase/migrations/20260911000051_push_notification.sql` — the durable outbox row research.md
  R1 (revised) relies on so an enqueue failure or worker outage is observable and replayable
  instead of a silent drop
- [ ] T004 [P] Scaffold the Flutter project in `apps/mobile/` (`pubspec.yaml`, `lib/main.dart`,
  platform folders for iOS/Android), replacing the current placeholder README, with
  `flutter_secure_storage`, `local_auth`, and an MMKV or SQLite package declared per plan.md's
  Primary Dependencies — no feature code yet, just a buildable empty shell
  (`flutter build`/`flutter test` both succeed on an empty app)
- [ ] T005 [P] Add `devices.*` and `lowStock.*` i18n keys (device registration is silent/no UI
  copy of its own; low-stock report screen copy, confirmation states) to `packages/i18n/en.json`
  and `packages/i18n/ar.json`, keeping English/Arabic key parity
- [ ] T006 [P] Declare `packages/i18n/en.json` and `packages/i18n/ar.json` as Flutter assets in
  `apps/mobile/pubspec.yaml` (research.md R6 — raw asset read, not a codegen step)
- [ ] T007 [P] Extend `apps/api/tests/integration/test_tenant_isolation.py` with cross-tenant cases
  for `device_registration`, `low_stock_report`, and `push_notification`, matching the existing
  uniform pattern

**Checkpoint**: schema, RLS, and cross-tenant isolation proof are complete, and an empty Flutter
shell builds, before any module or feature code is written.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the `devices` module (registration + sign-out removal), the `requests` module
extension, the durable push-outbox job pair, and the mobile app's core (auth/biometric gate,
API client, i18n loader, offline-queue primitive) every user story depends on.

⚠️ **Everything else depends on this phase.**

- [ ] T008 Create the devices module skeleton in
  `apps/api/src/procurepilot_api/modules/devices/__init__.py`, `schemas.py`, `service.py`, and
  `router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T009 [P] Create Pydantic schemas for `DeviceRegistration`/`DeviceRegistrationCreate` in
  `apps/api/src/procurepilot_api/modules/devices/schemas.py`,
  `LowStockReport`/`LowStockReportCreate` in `apps/api/src/procurepilot_api/modules/requests/schemas.py`,
  and an internal (non-API-exposed) `PushNotification` dataclass/model in
  `apps/api/src/procurepilot_api/modules/devices/schemas.py`, matching
  `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml` exactly for the two client-facing shapes
- [ ] T010 [US1] Implement `POST /devices` (upsert on `(tenant_id, member_id, push_token)`) and
  `DELETE /devices/{id}` (member-own-row-only; not_found for anyone else's, never forbidden) in
  `apps/api/src/procurepilot_api/modules/devices/service.py`, exposed in
  `apps/api/src/procurepilot_api/modules/devices/router.py` — the DELETE half is what the mobile
  sign-out flow (T023) calls, per research.md R1 (revised)
- [ ] T011 [P] Implement the push-send job in
  `apps/api/src/procurepilot_api/modules/devices/push_job.py`, queued onto the existing RQ worker
  (research.md R1 revised) — takes a `push_notification.id`, fans out to every current
  `device_registration` row for that notification's member via FCM/APNs, and updates the row's
  `status`/`attempts`/`sent_at` on completion; never raises in a way that could propagate back to
  its caller
- [ ] T012 [P] Implement a periodic retry-sweep task in
  `apps/api/src/procurepilot_api/modules/devices/push_job.py` (or a sibling `push_sweep.py`),
  mirroring the extraction worker's existing stuck-job recovery pattern — finds `push_notification`
  rows still `queued`/`failed` past a short threshold and re-enqueues T011's job for them, so a lost
  enqueue or a worker outage is recovered rather than left permanently stuck (research.md R1 revised)
- [ ] T013 [P] Add a typed frontend API client for the new endpoints in
  `apps/web/src/app/features/requests/requests-api.ts` (low-stock reports, for any future web
  admin visibility) and generate the Dart equivalent from
  `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml` into `apps/mobile/lib/core/api/` —
  including `DELETE /devices/{id}` — decimal strings for money-shaped fields, exact OpenAPI
  endpoint paths
- [ ] T014 [P] Add backend contract drift coverage in
  `apps/api/tests/contract/test_mobile_openapi_drift.py`, verifying implemented `/devices`,
  `/devices/{id}`, and `/low-stock-reports` route paths and response models against
  `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`
- [ ] T015 [P] Build the mobile auth core in `apps/mobile/lib/core/auth/` — sign-in against the
  existing Supabase Auth endpoint (research.md R3, no new backend surface), refresh-token storage
  via `flutter_secure_storage`, a biometric-unlock gate via `local_auth` that only ever gates use of
  an already-valid stored refresh token, and a sign-out action that calls `DELETE /devices/{id}`
  (T010, T013) for the current device's registration before clearing the local session
- [ ] T016 [P] Build the i18n loader in `apps/mobile/lib/core/i18n/`, reading the bundled
  `packages/i18n/{en,ar}.json` assets (T006) with the same dotted-key lookup shape
  `@ngx-translate/core` uses on web, plus `Directionality`/RTL switching driven by the selected
  locale (research.md R6)
- [ ] T017 [P] Build the offline-queue primitive in `apps/mobile/lib/core/offline_queue/` — local
  persistence (MMKV/SQLite) for a queued request/low-stock submission, stamping an
  `Idempotency-Key` at creation time (not send time), and a connectivity-triggered replay that
  reuses that same key on retry (research.md R4 revised)

**Checkpoint**: FastAPI imports the new `devices` module (register + sign-out removal) and the
extended `requests` schemas, the push-send/retry-sweep job pair exists as independently-invokable
units, and the Flutter app has a working auth/i18n/offline-queue core every feature screen can
build on.

---

## Phase 3: User Story 1 - Sign in and land on a role-aware home (P1)

**Goal**: a member signs in, enables biometric re-entry, and lands on a home screen reflecting
their role — including, for an approver, a read-only pending-decision count with no way to act on
it; signing out removes that device's push eligibility immediately.

**Independent Test**: sign in on a fresh device, confirm biometric re-entry works on the next app
open without re-entering a password, and confirm the home screen's primary action and (for an
approver) pending count match the signed-in member's actual role and branch scope.

### Tests for User Story 1

- [ ] T018 [P] [US1] Write Flutter widget tests for the sign-in, biometric-enable, and sign-out flow
  in `apps/mobile/test/features/auth/auth_flow_test.dart`, covering first sign-in, biometric-enable
  prompt, next-launch biometric unlock reaching the home screen without credential re-entry, and
  sign-out actually invoking `DELETE /devices/{id}` (T010) before clearing the local session
- [ ] T019 [P] [US1] Write Flutter tests proving FR-009 two ways in
  `apps/mobile/test/features/home/home_screen_test.dart` and
  `apps/mobile/test/core/no_approval_surface_test.dart`: (a) a widget test covering the branch-
  manager primary action and the approver's pending-count display, asserting **no widget tree
  anywhere on the home screen contains an approve/reject control or a route to one**, and (b) a
  static assertion over T013's generated Dart API client and the app's route table confirming
  **no method or route reachable from anywhere in the mobile app calls or names**
  `POST /requests/{id}/approve`\|`/reject` — (a) alone was flagged on review as proving only the
  home screen's own widget tree, not the stronger "no mobile-reachable code path at all" FR-009
  actually requires
- [ ] T020 [P] [US1] Write an integration test in
  `apps/api/tests/integration/test_session_revocation.py` proving a revoked refresh token fails to
  refresh regardless of a valid biometric match having occurred client-side (FR-014) — the
  server-side half of research.md R3's guarantee

### Implementation for User Story 1

- [ ] T021 [US1] Build the sign-in, biometric-enable, and sign-out screens/actions in
  `apps/mobile/lib/features/auth/`, using the auth core (T015, including its sign-out ->
  `DELETE /devices/{id}` call) and only `packages/i18n` strings (via T016's loader)
- [ ] T022 [US1] Build the role-aware home screen in `apps/mobile/lib/features/home/`, calling the
  existing (unchanged) `GET /approvals/pending` for the approver's pending count (count only — the
  response's decision-capable fields are read but never rendered as actionable, and no route from
  this screen or anywhere else in the app's navigation graph leads to an approve/reject action) and
  gating the primary "Request items" action by the member's role/branch (FR-002, FR-015)

**Checkpoint**: US1 is independently testable — sign-in, biometric re-entry, sign-out's immediate
device de-registration, and the correct role-aware home screen (with FR-009 proven at both the
widget and code-path level) all work with no request-submission or push code required to observe
the behaviour.

---

## Phase 4: User Story 2 - Submit a purchase request from the branch floor (P1)

**Goal**: a branch manager searches the catalogue, builds a request, and submits it through R2.1's
existing pipeline unchanged; can also check its status and the approver's comment once decided.

**Independent Test**: a signed-in branch manager creates a request naming one or more lines and a
required-by date, submits it, and it appears with status "submitted" in their own mobile request
list — and, independently, the same request is visible and correctly routed in the existing R2.1
web approval queue, proving mobile submission is not a second, divergent code path.

### Tests for User Story 2

- [ ] T023 [P] [US2] Write Flutter widget tests for the request form in
  `apps/mobile/test/features/requests/request_form_test.dart`, covering catalogue search, line
  add/remove, required-by date, draft persistence on navigating away, submit, and the zero-lines
  refusal (FR-004)
- [ ] T024 [P] [US2] Write Flutter widget tests for the request list/detail in
  `apps/mobile/test/features/requests/request_list_test.dart`, covering status display and, once
  decided, the approver's comment rendering identically to web's shape (FR-005)
- [ ] T025 [P] [US2] Write an end-to-end proof in
  `apps/mobile/test/integration/mobile_request_submission_test.dart` (against the same disposable-
  Postgres `apps/api` recipe already used elsewhere this session) that a request created via the
  mobile API client appears correctly routed in `GET /approvals/pending` — proving SC-003's "no
  channel-specific behaviour gap" directly, not by inspection

### Implementation for User Story 2

- [ ] T026 [US2] Build the request form screen in `apps/mobile/lib/features/requests/`, calling
  the existing (unchanged) `POST/GET/PATCH /requests` and `POST /requests/{id}/submit` endpoints
  via T013's generated client — no new backend logic, mobile is a new caller of an existing surface
  (FR-003)
- [ ] T027 [US2] Build the request list/detail screens in `apps/mobile/lib/features/requests/`,
  calling the existing `GET /requests` and rendering `approval_step`'s comment/decided-at exactly
  as `request-form.component.html`'s web equivalent already does (FR-005)

**Checkpoint**: US2 is independently testable — a request can be created and submitted from mobile
and observed correctly routed on web, on top of US1's working sign-in.

---

## Phase 5: User Story 3 - Report low stock in one tap (P2)

**Goal**: a branch manager flags a product as running low, with an optional count, as a fast signal
distinct from and unlinked to any purchase request — and a replayed offline submission never
creates a duplicate.

**Independent Test**: a signed-in branch manager taps "running low" on a product with and without
an optional count, and each is recorded as a low-stock report attributed to that member, branch,
and product — without creating or affecting any purchase request.

### Tests for User Story 3

- [ ] T028 [P] [US3] Write contract tests for `POST/GET /low-stock-reports` in
  `apps/api/tests/contract/test_low_stock_contract.py`, covering the OpenAPI shape, the 200-vs-201
  idempotent-replay response distinction, and 404/422 envelopes
- [ ] T029 [P] [US3] Write integration tests in `apps/api/tests/integration/test_low_stock_reports.py`,
  proving report creation with and without `count_remaining`, branch-scoped visibility (data-model.md
  RLS Summary), that creating a low-stock report leaves every existing `purchase_request` row for
  that tenant completely unchanged (FR-006), and — the server-side idempotency enforcement research
  found missing on review — that two `POST /low-stock-reports` calls with the same
  `Idempotency-Key` return the same row rather than creating a second one (FR-011, research.md R4
  revised)
- [ ] T030 [P] [US3] Write Flutter widget tests for the low-stock report screen in
  `apps/mobile/test/features/low_stock/low_stock_report_test.dart`, covering the one-tap submit
  with and without a count, the confirmation state, and that a rapid double-tap produces exactly
  one client-side submission (spec.md's edge case)

### Implementation for User Story 3

- [ ] T031 [US3] Implement `POST/GET /low-stock-reports` in
  `apps/api/src/procurepilot_api/modules/requests/service.py` and expose them in
  `apps/api/src/procurepilot_api/modules/requests/router.py` — insert-only, no linkage written to
  any `purchase_request` row (research.md R2); `POST` does
  `insert ... on conflict (tenant_id, idempotency_key) do nothing returning *` when a key is
  supplied, falling back to reading the existing row (200) when the insert affects zero rows, and
  plain insert (201) when no key is supplied or none conflicts (research.md R4 revised, T002's
  partial unique index)
- [ ] T032 [P] [US3] Build the low-stock report screen in `apps/mobile/lib/features/low_stock/`,
  reachable from a product in the catalogue search already built for US2, using T013's client and
  debouncing the tap client-side (spec.md's double-tap edge case)

**Checkpoint**: US3 is independently testable and fully additive — US1/US2's request loop already
works completely without it; its own offline-retry safety no longer depends on an unenforced header.

---

## Phase 6: User Story 4 - Stay informed without opening the app (P2)

**Goal**: a member gets a push notification the moment a request they submitted is decided, deep-
linking into that request's status; the app works fully without notification permission granted;
an enqueue or worker failure is recoverable, not a silent drop.

**Independent Test**: a signed-in member with notifications enabled has one of their submitted
requests approved or rejected, and a push notification arrives and deep-links into that request's
status screen.

### Tests for User Story 4

- [ ] T033 [P] [US4] Write a unit test for the push-send job's fan-out logic (T011) in
  `apps/api/tests/unit/test_push_job.py`, covering: sends to every current device_registration for
  the notification's member, no send attempted when the member has zero registrations (declined
  permission, FR-008), the job marks the `push_notification` row `sent`/`failed` correctly, and the
  job never raises in a way that could affect its caller (research.md R1 revised)
- [ ] T034 [P] [US4] Write a unit test for the retry-sweep task (T012) in
  `apps/api/tests/unit/test_push_sweep.py`, covering: a `push_notification` row stuck `queued` past
  the threshold is re-enqueued, a `sent` row is left alone, and a row that has exhausted its retry
  budget stops being re-swept (research.md R1 revised)
- [ ] T035 [P] [US4] Write an integration test in
  `apps/api/tests/integration/test_decision_push_trigger.py` proving an approve/reject decision
  writes exactly one `push_notification` row (`queued`) in the same transaction as the decision and
  enqueues T011's job for it, with the correct request id and outcome, without slowing or altering
  `POST /requests/{id}/approve`\|`/reject`'s existing response contract — and that the row survives
  (stays queryable, is not lost) even if the enqueue call itself is simulated as failing
- [ ] T036 [P] [US4] Write Flutter widget/integration tests for notification permission handling
  and deep-linking in `apps/mobile/test/features/notifications/push_notification_test.dart`,
  covering: permission granted → registration call (T015's device registration flow), permission
  declined → app remains fully functional and the decision is still visible on next open (FR-008),
  and tapping a notification opens directly to that request's status view

### Implementation for User Story 4

- [ ] T037 [US4] Wire a `push_notification` row write (`queued`, same transaction as the decision)
  plus the T011 job enqueue into the approve/reject decision path in
  `apps/api/src/procurepilot_api/modules/requests/service.py`, passing the request id, new status,
  and the submitter's member id (research.md R1 revised)
- [ ] T038 [P] [US4] Build notification-permission handling and deep-link routing in
  `apps/mobile/lib/features/notifications/` (or `apps/mobile/lib/core/notifications/` if shared
  infra), calling `POST /devices` (T013) on permission grant and routing a tapped notification to
  the request detail screen (T027)

**Checkpoint**: US4 is independently testable — a decided request reliably produces exactly one
durable, recoverable push record, and the app degrades correctly with permission declined, on top
of US1/US2's working sign-in-and-submit loop.

---

## Phase 7: User Story 5 - Keep working with a weak or no connection (P3)

**Goal**: a request or low-stock report built offline queues locally and sends automatically once
connectivity returns, exactly once, never silently lost or duplicated — for both mutation types
FR-011 actually covers.

**Independent Test**: put the device in airplane mode, build and submit a request or low-stock
report, confirm it shows as queued/pending rather than failed, then restore connectivity and
confirm it completes exactly once with no duplicate.

### Tests for User Story 5

- [ ] T039 [P] [US5] Write Flutter tests for the offline-queue primitive (T017) in
  `apps/mobile/test/core/offline_queue_test.dart`, covering: a draft persists locally with no
  connectivity, a queued submission's `Idempotency-Key` is stamped at creation and unchanged across
  retries, and the queue never marks an item "submitted" before a confirmed server response
  (FR-012)
- [ ] T040 [P] [US5] Write integration tests in `apps/api/tests/integration/test_idempotent_replay.py`
  proving **both** of FR-011's mutation types are safe to replay: a `/requests` POST replayed with
  the same `Idempotency-Key` after a simulated dropped response returns the original result and
  creates no second row, **and** a `/low-stock-reports` POST does the same via T031's `on conflict`
  handling (research.md R4 revised) — narrowed from the original version of this task, which only
  covered `/requests` despite FR-011 naming "a request or low-stock report"
- [ ] T041 [P] [US5] Write a Flutter integration test in
  `apps/mobile/test/integration/offline_submission_test.dart` simulating airplane mode, building
  and submitting a request/low-stock report, confirming it is shown queued (not failed, not silently
  "done"), then restoring connectivity and confirming it completes exactly once (SC-005, SC-006)

### Implementation for User Story 5

- [ ] T042 [US5] Wire the offline-queue primitive (T017) into the request form (T026) and low-stock
  report screen (T032) — a submit action while offline enqueues rather than erroring, and a
  connectivity-restored event triggers automatic replay
- [ ] T043 [P] [US5] Build the honest three-state submission indicator (local draft / queued /
  confirmed) across the request and low-stock UI in
  `apps/mobile/lib/core/offline_queue/status_widgets.dart`, consumed by both T026 and T032 so
  neither screen invents its own success-state logic (FR-012)

**Checkpoint**: US5 is independently testable and additive — US1-US4 already work correctly on a
normal connection; this phase only adds resilience for a degraded one, now proven for both of
FR-011's mutation types, not just one.

---

## Phase 8: Polish and Cross-Cutting

**Purpose**: branch-scoped-visibility proof for `low_stock_report`, full audit coverage for both
new mobile-originated write paths, the cold-start/app-size budget check, and docs correction.

- [ ] T044 [P] Extend `apps/api/tests/integration/test_branch_scoped_visibility.py` with cases for
  `low_stock_report`: a branch-scoped member sees only their own branch's reports, a member always
  sees reports they personally raised regardless of branch scoping since, and a direct reference to
  another branch's report resolves not-found (never forbidden)
- [ ] T045 [P] Add an audit-log coverage test in `apps/api/tests/integration/test_mobile_audit.py`,
  following the existing `test_requests_audit.py` pattern, proving every mobile-originated
  `purchase_request` submission and every `low_stock_report` creation appears in `audit_event`
  (FR-016) with no gap for "submitted from mobile" — backed by a live HTTP round-trip, matching this
  codebase's standing verification discipline for audit claims
- [ ] T046 [P] Add a build-size and cold-start check to CI or a documented manual gate in
  `apps/mobile/` (script or CI job, per plan.md's Performance Goals — cold start <2.5s, app size
  <30MB) before any store submission is attempted
- [ ] T047 [P] Add Flutter accessibility coverage (semantic labels, minimum tap targets, screen-
  reader navigation) for the sign-in, home, request form, and low-stock screens in
  `apps/mobile/test/a11y/`, mirroring the rigor of the web app's axe-core coverage
  (`apps/web/tests/e2e/requests-a11y.spec.ts`) even though Flutter has no axe-core equivalent
- [ ] T048 [P] Update `docs/architecture/data-dictionary.md` for the delivered `DeviceRegistration`,
  `LowStockReport`, and `PushNotification` entities
- [ ] T049 [P] Update `docs/architecture/api-specification.md` for the `/devices`, `/devices/{id}`,
  and `/low-stock-reports` endpoints

**Checkpoint**: branch-scoped visibility and full audit coverage are proven for both client-facing
new tables, performance budgets are checked before any store submission, and docs reflect the real
delivered API/data model.

---

## Dependencies

```text
Phase 1 Setup (schema + RLS for 3 tables + empty Flutter shell)
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES (devices module incl. sign-out removal, push
    │                    send+sweep job pair, auth/i18n/offline core)
    ↓
    ├── Phase 3 US1 (P1) Sign in, role-aware home, sign-out device removal
    │       ↓
    ├── Phase 4 US2 (P1) Submit a request from mobile   ← needs sign-in (US1) to reach any screen
    │       ↓
    ├── Phase 5 US3 (P2) Low-stock report (now idempotent) ← needs the catalogue search built for US2
    ├── Phase 6 US4 (P2) Durable push notifications on decision ← needs a submittable request (US2)
    ├── Phase 7 US5 (P3) Offline queue, both mutation types ← needs the request form (US2) and
    │                                                          low-stock screen (US3) to wrap
    └── Phase 8 Cross-cutting                              ← branch-scoped visibility proof, audit,
                                                               perf budget, docs
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — can start immediately.
- **Foundational (Phase 2)**: depends on Setup and blocks all user-story work; this is where the
  `devices` module (registration + sign-out removal), the push-send/retry-sweep job pair, and the
  mobile app's auth/i18n/offline-queue core are built.
- **US1 Sign in, role-aware home, sign-out (Phase 3)**: depends on Foundational only.
- **US2 Submit a request (Phase 4)**: depends on US1 to reach any in-app screen at all, and on
  Foundational's typed API client; the backend endpoints it calls are already complete (008), so
  its own backend work is zero — this phase is pure mobile UI.
- **US3 Low-stock report (Phase 5)**: depends on Foundational (the `low_stock_report`
  schema/endpoints, now with real idempotency enforcement) and reuses US2's catalogue-search UI as
  its entry point; independently testable via its own screen even before US2's full submit flow is
  polished.
- **US4 Push notifications (Phase 6)**: depends on Foundational's push-send/retry-sweep job pair and
  needs US2's submit flow to have something to decide on for its own integration test, but its unit
  tests (T033-T034) and the job wiring (T037) have no UI dependency at all.
- **US5 Offline queue (Phase 7)**: depends on Foundational's offline-queue primitive and wraps
  US2's request form and US3's low-stock screen — both must exist as UI before this phase's wiring
  task (T042) has anything to wrap; its own idempotent-replay proof (T040) depends on US3's `on
  conflict` implementation (T031) existing.
- **Cross-cutting (Phase 8)**: depends on all five user stories being implemented.

### Parallel Opportunities

- Setup tasks T001-T003 touch different migration files and reuse existing RLS helper functions —
  fully parallel; T004-T007 are independent of the migrations and of each other.
- Foundational tasks T009, T011-T017 can all run in parallel once T008's module skeleton exists;
  T010 depends only on T008/T009.
- US1 tests T018-T020 can run together; T021-T022 depend on T015-T016 (auth/i18n core, including
  T015's sign-out wiring) but not on each other's completion.
- US2 tests T023-T025 can run together; T026-T027 depend on T013's generated client but can proceed
  in parallel with each other once it exists.
- US3 tests T028-T030 can run together; T031 (backend) and T032 (mobile UI) are independent of each
  other once T009's schemas and T002's migration exist.
- US4 tests T033-T036 can run together; T033-T034 have zero UI dependency and can start the moment
  T011-T012 (push job pair) exist; T037-T038 are independent of each other.
- US5 tests T039-T041 can run together; T039 has zero dependency beyond T017; T040 depends on T031's
  `on conflict` implementation; T042-T043 depend on US2/US3's screens existing to wrap, but not on
  each other.
- Cross-cutting T044-T049 can all run in parallel once the five user stories land.

---

## Delegation lanes

Per the current lane map (`delegate-setup`): `backend` → codex, `frontend`/`mobile` and `tests` →
opencode, `infra` → agy, `complex` → claude. Tenancy/RLS work (T001-T003, T007, T044) stays
in-house per standing practice, not delegated to any lane; the push-outbox write+enqueue wiring
(T037), the retry-sweep task (T012), and the offline-queue/idempotency-key discipline (T002, T017,
T031, T042) are good candidates for in-house or `complex` review given they encode this chunk's own
correctness properties (no lost/duplicated offline submission, no silently-dropped push, no
push-latency coupling to the approval path) rather than routine CRUD — this list grew directly out
of Codex's review findings on the first version of this plan. Per the parallel-execution-plan's
cross-cutting rule, any `apps/web/src/**` component/template/style touch (T013's web-side client
addition) routes through Agy, not direct edits — Flutter code under `apps/mobile/` has no such
routing requirement, since Agy is scoped to the existing Angular UI.

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator (in-house)** | Schema, RLS, branch-scoped visibility policy and its proof; push-send job + push-outbox write/enqueue wiring; retry-sweep task; offline-queue/idempotency-key discipline | **not delegated** | T001-T003, T007, T011-T012, T017, T031, T037, T042, T044 |
| **Backend (codex)** | `devices` module (incl. sign-out removal), `requests` module extension, contract/integration/audit tests | lane `backend` → codex | T008-T009, T010, T014, T020, T023's backend fixtures, T028-T029, T033-T035, T040, T045 |
| **Mobile (opencode)** | Flutter screens, widget/integration tests, i18n loader, offline UI wiring | lane `mobile`/`tests` → opencode | T004-T006, T015-T016, T018-T019, T021-T022, T024-T027, T030, T032, T036, T038-T039, T041, T043, T046-T047 |
| **Frontend web (Agy, via delegation)** | The one web-side client addition | routes through Agy per plan.md §5 | T013 (web half only — the Dart client is a mobile-lane task) |
| **Docs (codex)** | Correct architecture docs for the real delivered data/API shapes | lane `backend` → codex | T048-T049 |
