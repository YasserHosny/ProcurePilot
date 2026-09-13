# Tasks: Mobile Approvals and Delivery Receipt

**Input**: Design documents from `/specs/010-mobile-approvals-receipt/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/mobile-approvals-receipt.openapi.yaml, quickstart.md

**Tests are included** — every prior chunk in this codebase (007-009) has treated a contract/
integration test per new endpoint and a widget test per new mobile screen as non-optional, and
this chunk follows the same standing practice, not the generic "tests only if requested" default.

**Organization**: Tasks are grouped by user story from spec.md so each story is independently
completable and testable, mirroring 009-mobile-app-mvp/tasks.md's own structure exactly.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are absolute-from-repo-root

---

## Phase 1: Setup (schema)

**Purpose**: Every migration this chunk needs. `approval_step`/`ApprovalStep` itself is untouched
(research.md R2) — nothing here alters the decision data model, only what a request records once
it moves past being decided.

- [ ] T001 Migration adding `'ordered'` and `'delivered'` to the `purchase_request_status` enum,
  **in its own migration file with no other statement** — `ALTER TYPE ... ADD VALUE` cannot be
  referenced in the same transaction block it runs in (data-model.md Migration Note). File:
  `supabase/migrations/<next>_purchase_request_delivery_status.sql`
- [ ] T002 Migration adding `delivered_at`, `delivery_confirmed_by_membership_id`,
  `has_delivery_discrepancy` to `purchase_request`, and `quantity_received` to
  `purchase_request_line`, with the `check (quantity_received is null or quantity_received >= 0)`
  constraint (data-model.md). Must run **after** T001 lands (needs the new enum values to exist
  before anything can reference them, even indirectly via a later migration). File:
  `supabase/migrations/<next>_purchase_request_delivery_columns.sql`
- [ ] T003 [P] Migration creating `delivery_quality_issue` (tenant-scoped, FK to `purchase_request`,
  `check (char_length(description) > 0)`, `ENABLE`+`FORCE` RLS with a derived-visibility
  RESTRICTIVE policy via `EXISTS` join to the parent request, insert-only grant to `authenticated`
  per data-model.md's RLS Summary). File:
  `supabase/migrations/<next>_delivery_quality_issue.sql`
- [ ] T004 [P] Migration creating `delivery_quality_issue_photo` (tenant-scoped, FK to
  `delivery_quality_issue`, same derived-visibility/insert-only shape as T003). File:
  `supabase/migrations/<next>_delivery_quality_issue_photo.sql`
- [ ] T005 [P] Migration creating the `quality-issue-photos` Storage bucket and its
  tenant-isolation-by-object-path policy, mirroring
  `supabase/migrations/20260819000020_quotation_storage.sql` exactly (research.md R3 — read that
  file first, copy its policy shape, do not invent a new one). File:
  `supabase/migrations/<next>_quality_issue_photo_storage.sql`

**Checkpoint**: Schema complete. `uv run pytest` (or the disposable-Postgres recipe) should still
show every pre-existing test passing — these migrations are purely additive.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The one backend change every later story either triggers or depends on, plus the
mobile-side plumbing more than one story needs.

**⚠️ CRITICAL**: No user-story phase below should be started until this phase is done.

- [ ] T006 Wire the `approved -> ordered` automatic transition into
  `RequestsService.approve_request()` in
  `apps/api/src/procurepilot_api/modules/requests/service.py` — the moment a decision approves a
  request, its status becomes `ordered` in the same write, not a second call (research.md R1: no
  separate "place the order" action exists this release). `reject_request()` is unaffected.
- [ ] T007 [P] Add `deliveredAt`, `deliveryConfirmedByMembershipId`, `hasDeliveryDiscrepancy` to the
  `PurchaseRequest` Dart model, and `quantityReceived` to `PurchaseRequestLine`, in
  `apps/mobile/lib/core/api/models.dart`.
- [ ] T008 [P] Define a `NotificationPermission`-style injectable camera abstraction (an interface
  plus a real implementation and a test fake, mirroring
  `apps/mobile/lib/core/auth/biometric_gate.dart`'s own shape exactly — research.md R4) in
  `apps/mobile/lib/core/camera/`. Do not add a concrete camera/image-picker package to
  `pubspec.yaml` as part of this task if one isn't already selected — pick the current
  ecosystem-standard package at this point, pin an exact version, and wire it behind this
  abstraction so screens never depend on the concrete plugin directly.

**Checkpoint**: An existing `approved` request now auto-carries `ordered` status on approval — this
is directly observable via the existing web approval flow already, with no mobile UI needed yet to
verify it.

---

## Phase 3: User Story 1 - Decide on a pending request from mobile (Priority: P1) 🎯 MVP

**Goal**: An approver reviews full decision context and approves/rejects a pending request from
mobile, using 008's existing decision endpoints unchanged.

**Independent Test**: Sign in as an approver, open a pending request from the mobile approval
queue, review its lines/total/budget/requester, approve it with a comment, and confirm the
resulting status/comment/audit entry match what the same decision would produce from the web
approval queue.

### Tests for User Story 1

- [ ] T009 [P] [US1] Widget test for the approval queue screen in
  `apps/mobile/test/features/approvals/approval_queue_screen_test.dart`: renders pending requests
  from `ApprovalsApiClient.listPendingApprovals()`, empty state when none are pending.
- [ ] T010 [P] [US1] Widget test for the decision detail screen in
  `apps/mobile/test/features/approvals/approval_decision_screen_test.dart`: renders lines,
  estimated total, budget status (when present), requester identity; approve and reject both call
  the right client method with the entered comment; a request already decided by someone else
  shows the conflict message from Acceptance Scenario 4, not a silent failure.

### Implementation for User Story 1

- [ ] T011 [US1] Replace `PendingApprovalsList`'s deliberately-untyped `Map<String, dynamic>` items
  (added in 009 specifically so action-relevant fields could not be rendered — see that class's
  own doc comment) with proper `PurchaseRequest` objects, now that mobile is authorized to act on
  them, in `apps/mobile/lib/core/api/approvals_api_client.dart`.
- [ ] T012 [US1] Add `approveRequest(requestId, {comment})` and `rejectRequest(requestId,
  {comment})` methods to `ApprovalsApiClient` (or `RequestsApiClient`, whichever this codebase's
  existing convention favors — check where `submitRequest`/`withdrawRequest` already live and
  match it) calling `POST /requests/{id}/approve`\|`/reject` — the exact unchanged
  008-requests-approvals endpoints (research.md R2), in
  `apps/mobile/lib/core/api/approvals_api_client.dart`.
- [ ] T013 [US1] Build the approval queue screen in
  `apps/mobile/lib/features/approvals/approval_queue_screen.dart` listing pending requests via
  T011's typed client call.
- [ ] T014 [US1] Build the decision detail screen in
  `apps/mobile/lib/features/approvals/approval_decision_screen.dart` — lines, estimated total,
  budget status, requester (reuse `RequestDetailScreen`'s existing rendering pieces where they
  already fit, don't duplicate that layout logic), a comment field, and approve/reject actions
  calling T012. On a `409` conflict response, show the request was already decided (Acceptance
  Scenario 4) rather than a generic error.
- [ ] T015 [US1] Turn the existing read-only pending-approvals count on
  `apps/mobile/lib/features/home/home_screen.dart` (009) into a tappable link into T013's approval
  queue, for a member holding approval authority only.
- [ ] T016 [US1] Add `approvals.*` i18n keys for the new screens to `packages/i18n/en.json` and
  `packages/i18n/ar.json` in exact parity — check first whether anything reusable already exists
  from the web approval queue's own keys before adding new ones.

**Checkpoint**: User Story 1 fully functional — a decision from mobile is indistinguishable, in
its result, from one made on web.

---

## Phase 4: User Story 2 - Confirm delivery of an approved order (Priority: P1)

**Goal**: A branch member records what was actually received against an `ordered` request,
transitioning it to `delivered` and flagging any shortfall.

**Independent Test**: Given an `ordered` request (any request approved via Phase 3's flow, or an
existing one approved on web after T006 lands), confirm delivery with the full ordered quantity on
every line and confirm no discrepancy is recorded; separately, confirm a different `ordered`
request with a short quantity on one line and confirm the shortage is recorded specifically
against that line.

### Tests for User Story 2

- [ ] T017 [P] [US2] Contract test for `POST /requests/{request_id}/confirm-delivery` in
  `apps/api/tests/contract/test_confirm_delivery_contract.py`: request/response shape matches
  `contracts/mobile-approvals-receipt.openapi.yaml`, `409` with reason `not_ordered` for a request
  not in `ordered` status.
- [ ] T018 [P] [US2] Integration test in
  `apps/api/tests/integration/test_confirm_delivery.py` against a real disposable Postgres:
  full-quantity delivery leaves `has_delivery_discrepancy = false`; a short quantity on one line
  leaves it `true` and records the exact `quantity_received` on that line only; a `draft`/
  `submitted`/`approved`-but-not-yet-`ordered` (should not occur post-T006, but assert it anyway)
  request refuses with `409 not_ordered`; a same-tenant different-branch request resolves `404`,
  never `403` (constitution Principle III).

### Implementation for User Story 2

- [ ] T019 [US2] `RequestsService.confirm_delivery()` in
  `apps/api/src/procurepilot_api/modules/requests/service.py` — the `ordered -> delivered`
  transition, per-line `quantity_received` write, and `has_delivery_discrepancy` derivation
  (data-model.md). Requires the caller to be the requester or hold branch-scoped write access,
  matching this file's own existing authorization pattern for other requester-initiated actions.
- [ ] T020 [US2] `POST /requests/{request_id}/confirm-delivery` route and its Pydantic
  request/response schemas in
  `apps/api/src/procurepilot_api/modules/requests/router.py` and `schemas.py`.
- [ ] T021 [US2] `confirmDelivery(requestId, lines)` method on `RequestsApiClient` in
  `apps/mobile/lib/core/api/requests_api_client.dart`.
- [ ] T022 [US2] Delivery confirmation screen in
  `apps/mobile/lib/features/delivery/delivery_confirmation_screen.dart` — one quantity-received
  field per line, pre-filled with the ordered quantity, submitting via T021.
- [ ] T023 [US2] Add `delivery.*` i18n keys for the new screen to `packages/i18n/en.json`/`ar.json`
  in exact parity.

**Checkpoint**: User Stories 1 AND 2 both independently functional. A request can now go all the
way from submitted to delivered without leaving the app.

---

## Phase 5: User Story 3 - Report a delivery quality issue with photo evidence (Priority: P2)

**Goal**: A branch member reports a problem with a delivered request, with an optional
camera-captured photo, durably retrievable afterward.

**Independent Test**: Given a `delivered` request (seed one directly via test fixture — this story
does not need to wait for Phase 4's own screen to be built, only for a `delivered` row to exist,
per spec.md's independent-test framing), report a quality issue with a description and a photo,
and confirm both are retrievable against that specific request afterward; separately, confirm a
quality issue can be submitted with no photo at all.

### Tests for User Story 3

- [ ] T024 [P] [US3] Contract test for `POST`/`GET /requests/{request_id}/quality-issues` in
  `apps/api/tests/contract/test_quality_issues_contract.py`: shapes match the OpenAPI contract;
  `409 not_delivered` for a request not yet `delivered`.
- [ ] T025 [P] [US3] Contract test for `POST /quality-issues/{issue_id}/photos` in the same file:
  multipart upload accepted, returns a signed URL, never a raw/public path.
- [ ] T026 [P] [US3] Integration test in
  `apps/api/tests/integration/test_quality_issues.py` against a real disposable Postgres: a
  quality issue with zero photos is valid (FR-007); a quality issue against a non-`delivered`
  request refuses with `409 not_delivered`; an uploaded photo's Storage path is
  server-allocated under `tenants/{tenant_id}/quality-issues/{issue_id}/...` and unreachable
  from a different tenant's session (mirrors `quotation-documents`' own isolation test, research.md
  R3 — check `test_tenant_isolation.py` for that existing test's shape and mirror it, don't
  reinvent the assertion style).

### Implementation for User Story 3

- [ ] T027 [US3] `RequestsService.create_quality_issue()` and `.attach_quality_issue_photo()` in
  `apps/api/src/procurepilot_api/modules/requests/service.py` — the `delivered`-status precondition
  check (FR-006) and the server-side Storage path allocation (research.md R3; never trust a
  client-supplied path).
- [ ] T028 [US3] `POST`/`GET /requests/{request_id}/quality-issues` and
  `POST /quality-issues/{issue_id}/photos` routes and schemas in
  `apps/api/src/procurepilot_api/modules/requests/router.py` and `schemas.py`.
- [ ] T029 [US3] `reportQualityIssue(requestId, description)` and
  `uploadQualityIssuePhoto(issueId, file)` methods on `RequestsApiClient` in
  `apps/mobile/lib/core/api/requests_api_client.dart`.
- [ ] T030 [US3] Quality-issue report screen in
  `apps/mobile/lib/features/delivery/quality_issue_screen.dart` — description field, camera
  capture via T008's abstraction, photo preview/remove before submit; submitting with zero photos
  MUST succeed (FR-007) — a declined or absent camera permission must never block submission.
- [ ] T031 [US3] Wire quality-issue reporting (and its photo attachment) into the existing
  `OfflineQueue` interface (`apps/mobile/lib/core/offline_queue/`, Wave 7) so a report made offline
  queues and replays automatically once connectivity returns (spec.md FR-009) — a queued photo
  file must be cached locally and its upload deferred until the record it belongs to has synced,
  not attempted independently first.
- [ ] T032 [US3] Add `qualityIssue.*` i18n keys for the new screen to `packages/i18n/en.json`/
  `ar.json` in exact parity.

**Checkpoint**: All three user stories independently functional and integrated.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Branch-scoped visibility proof, audit coverage, accessibility, and docs — mirroring
009-mobile-app-mvp's own Phase 8 exactly, for the entities and screens this chunk adds.

- [ ] T033 [P] Extend `apps/api/tests/integration/test_branch_scoped_visibility.py` with cases for
  `delivery_quality_issue`: a branch-scoped member sees only issues on their own branch's
  requests, always sees an issue they personally reported, and a direct reference to another
  branch's issue resolves not-found, never forbidden — mirroring this same file's existing
  `purchase_request`/`low_stock_report` cases exactly.
- [ ] T034 [P] Extend `apps/api/tests/integration/test_mobile_audit.py` (009's Wave 8 file) with
  cases proving a mobile-originated decision, delivery confirmation, and quality-issue report each
  land the correct `audit_event` row via a live HTTP round-trip, matching that file's own
  established pattern.
- [ ] T035 [P] Extend `apps/mobile/test/a11y/screens_a11y_test.dart` (009's Wave 8 file) with the
  approval queue, decision detail, delivery confirmation, and quality-issue screens, using the
  same `flutter_test` built-in guideline matchers already established there.
- [ ] T036 [P] Update `docs/architecture/data-dictionary.md` for `purchase_request`'s new status
  values/columns, `delivery_quality_issue`, and `delivery_quality_issue_photo`.
- [ ] T037 [P] Update `docs/architecture/api-specification.md` for
  `POST /requests/{id}/confirm-delivery`, `POST`/`GET /requests/{id}/quality-issues`, and
  `POST /quality-issues/{id}/photos`.

**Checkpoint**: Branch-scoped visibility and full audit coverage proven for the new entities,
accessibility checked for the new screens, docs reflect the real delivered API/data model — the
same bar 009's own Phase 8 set.

---

## Dependencies & Execution Order

```text
Phase 1 Setup (schema: enum extension, delivery columns, quality-issue tables, storage bucket)
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES (approved->ordered wiring, shared Dart models,
    │                    camera abstraction)
    ↓
    ├── Phase 3 US1 (P1) Decide on mobile           ← pure mobile-client work, needs only Phase 2
    ├── Phase 4 US2 (P1) Confirm delivery            ← needs Phase 2's ordered-transition; does NOT
    │                                                    need US1's mobile screens, only *some*
    │                                                    request to already be ordered (via web
    │                                                    approval + T006, or via US1 once built)
    └── Phase 5 US3 (P2) Quality issue + photo       ← needs a delivered request to exist; testable
                                                          via direct fixture seeding without waiting
                                                          on US2's own screen (see its own
                                                          Independent Test)
    ↓
Phase 6 Cross-cutting                                ← branch-scoped visibility proof, audit,
                                                          a11y, docs — needs all three stories done
```

- **Setup (Phase 1)**: no dependencies — can start immediately.
- **Foundational (Phase 2)**: depends on Setup (T006 needs T001/T002's enum values to exist) and
  blocks all user-story work.
- **US1 (Phase 3)**: depends on Foundational only — it is pure mobile-client work against an
  already-unchanged backend endpoint.
- **US2 (Phase 4)**: depends on Foundational (T006's automatic `ordered` transition) but not on
  US1 — an `ordered` request can come from a decision made on web just as validly as one made from
  US1's new mobile screen.
- **US3 (Phase 5)**: depends on Foundational and, functionally, on a `delivered` request existing —
  but its own tests can seed one directly rather than waiting on US2's screen to be built and
  polished, matching spec.md's own "independently testable" framing for this story.
- **Cross-cutting (Phase 6)**: depends on all three user stories being implemented.

### Parallel Opportunities

- Setup tasks T003-T005 are independent of each other and of T001/T002 (different tables/objects)
  — fully parallel; T001 must land before T002 (same enum), and both before anything that assumes
  `ordered`/`delivered` exist.
- Foundational tasks T007-T008 are independent of each other and of T006 — parallel.
- US1's tests (T009-T010) can run together; its implementation tasks T011-T016 mostly depend on
  T011 (the typed list) landing first, then T012-T016 can proceed with some parallelism (T016's
  i18n work is independent of the screen code itself).
- US2's tests (T017-T018) can run together and can start as soon as Foundational lands, in
  parallel with all of US1's work (different files, no shared state).
- US3's tests (T024-T026) can run together; T027-T032 depend on T027/T028 (the backend surface)
  existing before the mobile client (T029) can call it, but T031 (offline-queue wiring) and T032
  (i18n) can proceed in parallel with T030 once T029 exists.
- Cross-cutting T033-T037 can all run in parallel once the three user stories land.

## Implementation Strategy

**MVP first**: Phase 3 (US1, decide from mobile) alone is a complete, shippable increment — it
closes the roadmap's single most-cited mobile job ("an owner deciding in under 30 seconds") without
needing anything from US2/US3. Phases 4 and 5 add real, separately valuable capability on top but
are not required to call US1 "done."

**Incremental delivery**: Setup → Foundational → US1 → ship/validate → US2 → ship/validate → US3 →
ship/validate → Cross-cutting. Each user-story phase ends in a working, demonstrable increment,
matching 009's own delivery discipline.

## Delegation Lanes

Per this session's own standing dynamic-orchestration policy (no fixed implementer, switch pool
members on a limit hit): backend tasks (schema, service, router — T001-T006, T019-T020, T027-T028,
T033-T034, T036-T037) suit the `backend` lane; mobile tasks (T007-T008, T009-T016, T021-T023,
T029-T032, T035) suit the `mobile` lane. Tenancy/RLS-bearing migrations (T001-T005) and the
approve-endpoint change (T006) are candidates for in-house handling given this project's standing
practice of keeping correctness-critical write-path and RLS-policy work in-house rather than
delegating it by default — a final call for whichever wave plan dispatches this tasks.md, not
fixed here.
