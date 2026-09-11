---
description: "Task list for Mobile MVP implementation"
---

# Tasks: Mobile MVP

**Input**: Design documents from `/specs/009-mobile-app-mvp/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mobile.openapi.yaml, quickstart.md

**Tests**: Included. The constitution requires unit/integration tests on every PR, a dedicated
tenant-isolation proof for both new tables, branch-scoped-visibility proof for `low_stock_report`
(R2.0's second isolation axis, extended), and — since FR-009 is this chunk's own version of "no
autonomous purchasing" (no approve/reject surface may exist on mobile at all) — a direct proof that
no mobile-reachable code path can call `POST /requests/{id}/approve`\|`/reject`.

**Organization**: grouped by setup, blocking foundation, then user stories in spec.md priority
order (P1, P1, P2, P2, P3), so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1-US5 from spec.md; setup and foundational tasks may have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: schema/RLS for the two new tables, the Flutter project scaffold itself (currently a
README placeholder per CLAUDE.md), and i18n/asset scaffolding.

- [ ] T001 [P] Create `device_registration` with `unique (tenant_id, member_id, push_token)`,
  composite FK to `membership(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the member-own-rows-only
  policy (data-model.md RLS Summary — no owner read-all) in
  `supabase/migrations/20260911000049_device_registration.sql`
- [ ] T002 [P] Create `low_stock_report` with composite FKs to `branch(tenant_id, id)`,
  `membership(tenant_id, id)`, and `workspace_product(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the
  branch-scoped visibility policy reused from 008's `purchase_request` mechanism (data-model.md RLS
  Summary) in `supabase/migrations/20260911000050_low_stock_report.sql`
- [ ] T003 [P] Scaffold the Flutter project in `apps/mobile/` (`pubspec.yaml`, `lib/main.dart`,
  platform folders for iOS/Android), replacing the current placeholder README, with
  `flutter_secure_storage`, `local_auth`, and an MMKV or SQLite package declared per plan.md's
  Primary Dependencies — no feature code yet, just a buildable empty shell
  (`flutter build`/`flutter test` both succeed on an empty app)
- [ ] T004 [P] Add `devices.*` and `lowStock.*` i18n keys (device registration is silent/no UI
  copy of its own; low-stock report screen copy, confirmation states) to `packages/i18n/en.json`
  and `packages/i18n/ar.json`, keeping English/Arabic key parity
- [ ] T005 [P] Declare `packages/i18n/en.json` and `packages/i18n/ar.json` as Flutter assets in
  `apps/mobile/pubspec.yaml` (research.md R6 — raw asset read, not a codegen step)
- [ ] T006 [P] Extend `apps/api/tests/integration/test_tenant_isolation.py` with cross-tenant cases
  for `device_registration` and `low_stock_report`, matching the existing uniform pattern

**Checkpoint**: schema, RLS, and cross-tenant isolation proof are complete, and an empty Flutter
shell builds, before any module or feature code is written.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the `devices` module and `requests` module extension, the mobile app's core
(auth/biometric gate, API client, i18n loader, offline-queue primitive), and the push-send job
skeleton every user story depends on.

⚠️ **Everything else depends on this phase.**

- [ ] T007 Create the devices module skeleton in
  `apps/api/src/procurepilot_api/modules/devices/__init__.py`, `schemas.py`, `service.py`, and
  `router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T008 [P] Create Pydantic schemas for `DeviceRegistration`/`DeviceRegistrationCreate` in
  `apps/api/src/procurepilot_api/modules/devices/schemas.py` and
  `LowStockReport`/`LowStockReportCreate` in
  `apps/api/src/procurepilot_api/modules/requests/schemas.py`, matching
  `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml` exactly
- [ ] T009 [P] Implement the push-send job in `apps/api/src/procurepilot_api/modules/devices/push_job.py`,
  queued onto the existing RQ worker (research.md R1) — takes a `member_id` and a notification
  payload, fans out to every current `device_registration` row for that member via FCM/APNs, and
  is invoked (not awaited inline) from wherever `approval_step.status` transitions
- [ ] T010 [P] Add a typed frontend API client for the two new endpoints in
  `apps/web/src/app/features/requests/requests-api.ts` (low-stock reports, for any future web
  admin visibility) and generate the Dart equivalent from
  `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml` into `apps/mobile/lib/core/api/` —
  decimal strings for money-shaped fields, exact OpenAPI endpoint paths
- [ ] T011 [P] Add backend contract drift coverage in
  `apps/api/tests/contract/test_mobile_openapi_drift.py`, verifying implemented `/devices` and
  `/low-stock-reports` route paths and response models against
  `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`
- [ ] T012 [P] Build the mobile auth core in `apps/mobile/lib/core/auth/` — sign-in against the
  existing Supabase Auth endpoint (research.md R3, no new backend surface), refresh-token storage
  via `flutter_secure_storage`, and a biometric-unlock gate via `local_auth` that only ever gates
  use of an already-valid stored refresh token, never a standalone credential
- [ ] T013 [P] Build the i18n loader in `apps/mobile/lib/core/i18n/`, reading the bundled
  `packages/i18n/{en,ar}.json` assets (T005) with the same dotted-key lookup shape
  `@ngx-translate/core` uses on web, plus `Directionality`/RTL switching driven by the selected
  locale (research.md R6)
- [ ] T014 [P] Build the offline-queue primitive in `apps/mobile/lib/core/offline_queue/` — local
  persistence (MMKV/SQLite) for a queued request/low-stock submission, stamping an
  `Idempotency-Key` at creation time (not send time), and a connectivity-triggered replay that
  reuses that same key on retry (research.md R4)

**Checkpoint**: FastAPI imports the new `devices` module and the extended `requests` schemas, the
push-send job exists as an independently-invokable unit, and the Flutter app has a working
auth/i18n/offline-queue core every feature screen can build on.

---

## Phase 3: User Story 1 - Sign in and land on a role-aware home (P1)

**Goal**: a member signs in, enables biometric re-entry, and lands on a home screen reflecting
their role — including, for an approver, a read-only pending-decision count with no way to act on
it.

**Independent Test**: sign in on a fresh device, confirm biometric re-entry works on the next app
open without re-entering a password, and confirm the home screen's primary action and (for an
approver) pending count match the signed-in member's actual role and branch scope.

### Tests for User Story 1

- [ ] T015 [P] [US1] Write Flutter widget tests for the sign-in and biometric-enable flow in
  `apps/mobile/test/features/auth/auth_flow_test.dart`, covering first sign-in, biometric-enable
  prompt, and next-launch biometric unlock reaching the home screen without credential re-entry
- [ ] T016 [P] [US1] Write Flutter widget tests for the role-aware home screen in
  `apps/mobile/test/features/home/home_screen_test.dart`, covering the branch-manager primary
  action, the approver's pending-count display, and — directly proving FR-009 — that **no widget
  tree anywhere on the home screen contains an approve/reject control or a route to one**
- [ ] T017 [P] [US1] Write an integration test in
  `apps/api/tests/integration/test_session_revocation.py` proving a revoked refresh token fails to
  refresh regardless of a valid biometric match having occurred client-side (FR-014) — the
  server-side half of research.md R3's guarantee

### Implementation for User Story 1

- [ ] T018 [US1] Build the sign-in and biometric-enable screens in
  `apps/mobile/lib/features/auth/`, using the auth core (T012) and only `packages/i18n` strings
  (via T013's loader)
- [ ] T019 [US1] Build the role-aware home screen in `apps/mobile/lib/features/home/`, calling the
  existing (unchanged) `GET /approvals/pending` for the approver's pending count (count only — the
  response's decision-capable fields are read but never rendered as actionable) and gating the
  primary "Request items" action by the member's role/branch (FR-002, FR-015)

**Checkpoint**: US1 is independently testable — sign-in, biometric re-entry, and the correct
role-aware home screen all work with no request-submission or push code required to observe the
behaviour.

---

## Phase 4: User Story 2 - Submit a purchase request from the branch floor (P1)

**Goal**: a branch manager searches the catalogue, builds a request, and submits it through R2.1's
existing pipeline unchanged; can also check its status and the approver's comment once decided.

**Independent Test**: a signed-in branch manager creates a request naming one or more lines and a
required-by date, submits it, and it appears with status "submitted" in their own mobile request
list — and, independently, the same request is visible and correctly routed in the existing R2.1
web approval queue, proving mobile submission is not a second, divergent code path.

### Tests for User Story 2

- [ ] T020 [P] [US2] Write Flutter widget tests for the request form in
  `apps/mobile/test/features/requests/request_form_test.dart`, covering catalogue search, line
  add/remove, required-by date, draft persistence on navigating away, submit, and the zero-lines
  refusal (FR-004)
- [ ] T021 [P] [US2] Write Flutter widget tests for the request list/detail in
  `apps/mobile/test/features/requests/request_list_test.dart`, covering status display and, once
  decided, the approver's comment rendering identically to web's shape (FR-005)
- [ ] T022 [P] [US2] Write an end-to-end proof in `apps/mobile/test/integration/mobile_request_submission_test.dart`
  (against the same disposable-Postgres `apps/api` recipe already used elsewhere this session) that
  a request created via the mobile API client appears correctly routed in `GET /approvals/pending`
  — proving SC-003's "no channel-specific behaviour gap" directly, not by inspection

### Implementation for User Story 2

- [ ] T023 [US2] Build the request form screen in `apps/mobile/lib/features/requests/`, calling
  the existing (unchanged) `POST/GET/PATCH /requests` and `POST /requests/{id}/submit` endpoints
  via T010's generated client — no new backend logic, mobile is a new caller of an existing surface
  (FR-003)
- [ ] T024 [US2] Build the request list/detail screens in `apps/mobile/lib/features/requests/`,
  calling the existing `GET /requests` and rendering `approval_step`'s comment/decided-at exactly
  as `request-form.component.html`'s web equivalent already does (FR-005)

**Checkpoint**: US2 is independently testable — a request can be created and submitted from mobile
and observed correctly routed on web, on top of US1's working sign-in.

---

## Phase 5: User Story 3 - Report low stock in one tap (P2)

**Goal**: a branch manager flags a product as running low, with an optional count, as a fast signal
distinct from and unlinked to any purchase request.

**Independent Test**: a signed-in branch manager taps "running low" on a product with and without
an optional count, and each is recorded as a low-stock report attributed to that member, branch,
and product — without creating or affecting any purchase request.

### Tests for User Story 3

- [ ] T025 [P] [US3] Write contract tests for `POST/GET /low-stock-reports` in
  `apps/api/tests/contract/test_low_stock_contract.py`, covering the OpenAPI shape and 404/422
  envelopes
- [ ] T026 [P] [US3] Write integration tests in `apps/api/tests/integration/test_low_stock_reports.py`,
  proving report creation with and without `count_remaining`, branch-scoped visibility (data-model.md
  RLS Summary), and — directly proving FR-006 — that creating a low-stock report leaves every
  existing `purchase_request` row for that tenant completely unchanged
- [ ] T027 [P] [US3] Write Flutter widget tests for the low-stock report screen in
  `apps/mobile/test/features/low_stock/low_stock_report_test.dart`, covering the one-tap submit
  with and without a count, the confirmation state, and that a rapid double-tap produces exactly
  one client-side submission (spec.md's edge case)

### Implementation for User Story 3

- [ ] T028 [US3] Implement `POST/GET /low-stock-reports` in
  `apps/api/src/procurepilot_api/modules/requests/service.py` and expose them in
  `apps/api/src/procurepilot_api/modules/requests/router.py` — insert-only, no linkage written to
  any `purchase_request` row (research.md R2)
- [ ] T029 [P] [US3] Build the low-stock report screen in `apps/mobile/lib/features/low_stock/`,
  reachable from a product in the catalogue search already built for US2, using T010's client and
  debouncing the tap client-side (spec.md's double-tap edge case)

**Checkpoint**: US3 is independently testable and fully additive — US1/US2's request loop already
works completely without it.

---

## Phase 6: User Story 4 - Stay informed without opening the app (P2)

**Goal**: a member gets a push notification the moment a request they submitted is decided, deep-
linking into that request's status; the app works fully without notification permission granted.

**Independent Test**: a signed-in member with notifications enabled has one of their submitted
requests approved or rejected, and a push notification arrives and deep-links into that request's
status screen.

### Tests for User Story 4

- [ ] T030 [P] [US4] Write a unit test for the push-send job's fan-out logic in
  `apps/api/tests/unit/test_push_job.py`, covering: sends to every current device_registration for
  the request's original submitter, no send attempted when the member has zero registrations
  (declined permission, FR-008), and the job never raises in a way that could affect the calling
  approve/reject request (research.md R1)
- [ ] T031 [P] [US4] Write an integration test in `apps/api/tests/integration/test_decision_push_trigger.py`
  proving the push-send job (T009) is enqueued exactly once per approve/reject decision, with the
  correct request id and outcome in its payload, without slowing or altering
  `POST /requests/{id}/approve`\|`/reject`'s existing response contract
- [ ] T032 [P] [US4] Write Flutter widget/integration tests for notification permission handling
  and deep-linking in `apps/mobile/test/features/notifications/push_notification_test.dart`,
  covering: permission granted → registration call (T012's device registration flow), permission
  declined → app remains fully functional and the decision is still visible on next open (FR-008),
  and tapping a notification opens directly to that request's status view

### Implementation for User Story 4

- [ ] T033 [US4] Wire the push-send job invocation (T009) into the approve/reject decision path in
  `apps/api/src/procurepilot_api/modules/requests/service.py`, passing the request id, new status,
  and the submitter's member id
- [ ] T034 [P] [US4] Build notification-permission handling and deep-link routing in
  `apps/mobile/lib/features/notifications/` (or `apps/mobile/lib/core/notifications/` if shared
  infra), calling `POST /devices` (T010) on permission grant and routing a tapped notification to
  the request detail screen (T024)

**Checkpoint**: US4 is independently testable — a decided request reliably produces exactly one
push, and the app degrades correctly with permission declined, on top of US1/US2's working
sign-in-and-submit loop.

---

## Phase 7: User Story 5 - Keep working with a weak or no connection (P3)

**Goal**: a request or low-stock report built offline queues locally and sends automatically once
connectivity returns, exactly once, never silently lost or duplicated.

**Independent Test**: put the device in airplane mode, build and submit a request or low-stock
report, confirm it shows as queued/pending rather than failed, then restore connectivity and
confirm it completes exactly once with no duplicate.

### Tests for User Story 5

- [ ] T035 [P] [US5] Write Flutter tests for the offline-queue primitive (T014) in
  `apps/mobile/test/core/offline_queue_test.dart`, covering: a draft persists locally with no
  connectivity, a queued submission's `Idempotency-Key` is stamped at creation and unchanged across
  retries, and the queue never marks an item "submitted" before a confirmed server response
  (FR-012)
- [ ] T036 [P] [US5] Write an integration test in `apps/api/tests/integration/test_idempotent_replay.py`
  proving a `/requests` POST replayed with the same `Idempotency-Key` after a simulated dropped
  response returns the original result and creates no second row (research.md R4) — the
  server-side half of the offline-retry guarantee
- [ ] T037 [P] [US5] Write a Flutter integration test in
  `apps/mobile/test/integration/offline_submission_test.dart` simulating airplane mode, building
  and submitting a request/low-stock report, confirming it is shown queued (not failed, not silently
  "done"), then restoring connectivity and confirming it completes exactly once (SC-005, SC-006)

### Implementation for User Story 5

- [ ] T038 [US5] Wire the offline-queue primitive (T014) into the request form (T023) and low-stock
  report screen (T029) — a submit action while offline enqueues rather than erroring, and a
  connectivity-restored event triggers automatic replay
- [ ] T039 [P] [US5] Build the honest three-state submission indicator (local draft / queued / 
  confirmed) across the request and low-stock UI in `apps/mobile/lib/core/offline_queue/status_widgets.dart`,
  consumed by both T023 and T029 so neither screen invents its own success-state logic (FR-012)

**Checkpoint**: US5 is independently testable and additive — US1-US4 already work correctly on a
normal connection; this phase only adds resilience for a degraded one.

---

## Phase 8: Polish and Cross-Cutting

**Purpose**: branch-scoped-visibility proof for `low_stock_report`, full audit coverage for both
new mobile-originated write paths, the cold-start/app-size budget check, and docs correction.

- [ ] T040 [P] Extend `apps/api/tests/integration/test_branch_scoped_visibility.py` with cases for
  `low_stock_report`: a branch-scoped member sees only their own branch's reports, a member always
  sees reports they personally raised regardless of branch scoping since, and a direct reference to
  another branch's report resolves not-found (never forbidden)
- [ ] T041 [P] Add an audit-log coverage test in `apps/api/tests/integration/test_mobile_audit.py`,
  following the existing `test_requests_audit.py` pattern, proving every mobile-originated
  `purchase_request` submission and every `low_stock_report` creation appears in `audit_event`
  (FR-016) with no gap for "submitted from mobile" — backed by a live HTTP round-trip, matching this
  codebase's standing verification discipline for audit claims
- [ ] T042 [P] Add a build-size and cold-start check to CI or a documented manual gate in
  `apps/mobile/` (script or CI job, per plan.md's Performance Goals — cold start <2.5s, app size
  <30MB) before any store submission is attempted
- [ ] T043 [P] Add Flutter accessibility coverage (semantic labels, minimum tap targets, screen-
  reader navigation) for the sign-in, home, request form, and low-stock screens in
  `apps/mobile/test/a11y/`, mirroring the rigor of the web app's axe-core coverage
  (`apps/web/tests/e2e/requests-a11y.spec.ts`) even though Flutter has no axe-core equivalent
- [ ] T044 [P] Update `docs/architecture/data-dictionary.md` for the delivered `DeviceRegistration`
  and `LowStockReport` entities
- [ ] T045 [P] Update `docs/architecture/api-specification.md` for the `/devices` and
  `/low-stock-reports` endpoints

**Checkpoint**: branch-scoped visibility and full audit coverage are proven for both new tables,
performance budgets are checked before any store submission, and docs reflect the real delivered
API/data model.

---

## Dependencies

```text
Phase 1 Setup (schema + RLS + empty Flutter shell)
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES (devices module, auth/i18n/offline core, push job skeleton)
    ↓
    ├── Phase 3 US1 (P1) Sign in, role-aware home
    │       ↓
    ├── Phase 4 US2 (P1) Submit a request from mobile   ← needs sign-in (US1) to reach any screen
    │       ↓
    ├── Phase 5 US3 (P2) Low-stock report                ← needs the catalogue search built for US2
    ├── Phase 6 US4 (P2) Push notifications on decision   ← needs a submittable request (US2) to decide on
    ├── Phase 7 US5 (P3) Offline queue                    ← needs the request form (US2) and low-stock screen (US3) to wrap
    └── Phase 8 Cross-cutting                              ← branch-scoped visibility proof, audit, perf budget, docs
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — can start immediately.
- **Foundational (Phase 2)**: depends on Setup and blocks all user-story work; this is where the
  `devices` module, the push-send job skeleton, and the mobile app's auth/i18n/offline-queue core
  are built.
- **US1 Sign in, role-aware home (Phase 3)**: depends on Foundational only.
- **US2 Submit a request (Phase 4)**: depends on US1 to reach any in-app screen at all, and on
  Foundational's typed API client; the backend endpoints it calls are already complete (008), so
  its own backend work is zero — this phase is pure mobile UI.
- **US3 Low-stock report (Phase 5)**: depends on Foundational (the `devices`-module-adjacent
  `low_stock_report` schema/endpoints) and reuses US2's catalogue-search UI as its entry point;
  independently testable via its own screen even before US2's full submit flow is polished.
- **US4 Push notifications (Phase 6)**: depends on Foundational's push-job skeleton and needs US2's
  submit flow to have something to decide on for its own integration test, but its unit test (T030)
  and the job wiring (T033) have no UI dependency at all.
- **US5 Offline queue (Phase 7)**: depends on Foundational's offline-queue primitive and wraps
  US2's request form and US3's low-stock screen — both must exist as UI before this phase's wiring
  task (T038) has anything to wrap.
- **Cross-cutting (Phase 8)**: depends on all five user stories being implemented.

### Parallel Opportunities

- Setup tasks T001-T002 touch different migration files and reuse existing RLS helper functions —
  fully parallel; T003-T006 are independent of the migrations and of each other.
- Foundational tasks T008-T014 can all run in parallel once T007's module skeleton exists.
- US1 tests T015-T017 can run together; T018-T019 depend on T012-T013 (auth/i18n core) but not on
  each other's completion.
- US2 tests T020-T022 can run together; T023-T024 depend on T010's generated client but can proceed
  in parallel with each other once it exists.
- US3 tests T025-T027 can run together; T028 (backend) and T029 (mobile UI) are independent of each
  other once T008's schemas exist.
- US4 tests T030-T032 can run together; T030 has zero UI dependency and can start the moment T009
  (push job skeleton) exists; T033-T034 are independent of each other.
- US5 tests T035-T037 can run together; T035 has zero dependency beyond T014; T038-T039 depend on
  US2/US3's screens existing to wrap, but not on each other.
- Cross-cutting T040-T045 can all run in parallel once the five user stories land.

---

## Delegation lanes

Per the current lane map (`delegate-setup`): `backend` → codex, `frontend`/`mobile` and `tests` →
opencode, `infra` → agy, `complex` → claude. Tenancy/RLS work (T001-T002, T006, T040) stays
in-house per standing practice, not delegated to any lane; the push-job trigger wiring (T033) and
the offline-queue idempotency-key discipline (T014, T038) are good candidates for in-house or
`complex` review given they encode this chunk's own correctness properties (no lost/duplicated
offline submission, no push-latency coupling to the approval path) rather than routine CRUD. Per
the parallel-execution-plan's cross-cutting rule, any `apps/web/src/**` component/template/style
touch (T010's web-side client addition) routes through Agy, not direct edits — Flutter code under
`apps/mobile/` has no such routing requirement, since Agy is scoped to the existing Angular UI.

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator (in-house)** | Schema, RLS, branch-scoped visibility policy and its proof; push-job trigger wiring; offline-queue idempotency-key discipline | **not delegated** | T001-T002, T006, T009, T014, T033, T038, T040 |
| **Backend (codex)** | `devices` module, `requests` module extension, contract/integration/audit tests | lane `backend` → codex | T007-T008, T011, T017, T020's backend fixtures, T025-T026, T028, T030-T031, T036, T041 |
| **Mobile (opencode)** | Flutter screens, widget/integration tests, i18n loader, offline UI wiring | lane `mobile`/`tests` → opencode | T003-T005, T012-T013, T015-T016, T018-T019, T021-T022, T027, T029, T032, T034-T035, T037, T039, T042-T043 |
| **Frontend web (Agy, via delegation)** | The one web-side client addition | routes through Agy per plan.md §5 | T010 (web half only — the Dart client is a mobile-lane task) |
| **Docs (codex)** | Correct architecture docs for the real delivered data/API shapes | lane `backend` → codex | T044-T045 |
