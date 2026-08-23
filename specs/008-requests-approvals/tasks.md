---
description: "Task list for Requests + Approvals implementation"
---

# Tasks: Requests + Approvals

**Input**: Design documents from `/specs/008-requests-approvals/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/requests-approvals.openapi.yaml, quickstart.md

**Tests**: Included. The constitution requires unit/integration tests on every PR, a dedicated tenant-isolation proof for every tenant-scoped table, branch-scoped-visibility proof extended to the new tables (R2.0's second isolation axis), and — since this chunk's core subject is "no purchase without human authorisation" — direct proof that no approval path can originate anywhere but a recorded human decision.

**Organization**: grouped by setup, blocking foundation, then user stories in spec.md order, so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md; setup and foundational tasks may have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: schema, RLS (branch-scoped policies reused verbatim from R2.0 per research.md R1), and i18n/routing scaffolding.

- [x] T001 Create `purchase_request` with `unique (tenant_id, id)`, composite FKs to `branch`/`cost_centre`/`membership(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the branch-scoped visibility policy from R2.0's `current_membership_id()`/`current_member_role()` (research.md R1) — extended so the requester always sees their own request regardless of branch scope — in `supabase/migrations/20260823000041_purchase_request.sql`
- [x] T002 Add `unique (tenant_id, id)` to the existing `workspace_product` and `landed_cost` tables via a new additive migration `supabase/migrations/20260823000042_workspace_product_landed_cost_composite_keys.sql` (neither was retrofitted by R2.0, which only added this to `membership` — needed here so `purchase_request_line` can reference both with a composite FK per this chunk's own convention), then create `purchase_request_line` with composite FKs to `purchase_request(tenant_id, id)`, `workspace_product(tenant_id, id)`, and `landed_cost(tenant_id, id)`, the paired-nullability check on the three `estimated_unit_price_*` columns, and RLS `ENABLE`+`FORCE` inheriting visibility via its parent request, in `supabase/migrations/20260823000043_purchase_request_line.sql`
- [x] T003 Create `approval_step` with `unique (tenant_id, purchase_request_id)`, the `status='pending' iff decided_by/decided_at are null` check constraint, composite FKs to `purchase_request` and `membership(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the branch-scoped visibility policy (assignee sees own step, requester sees their own request's step, owner sees all) in `supabase/migrations/20260823000044_approval_step.sql`
- [x] T004 Create `threshold_rule` with the `max_amount > min_amount` check constraint, composite FKs to `branch(tenant_id, id)` and `membership(tenant_id, id)`, and RLS `ENABLE`+`FORCE` with tenant-isolation only (no branch-scoped read restriction, per research.md R1 — every member can read routing configuration, only owner can write) in `supabase/migrations/20260823000045_threshold_rule.sql`
- [x] T005 Create `approval_delegation` with the `delegator <> delegate` and `ends_on >= starts_on` check constraints, composite FKs to `membership(tenant_id, id)` (both delegator and delegate), and RLS `ENABLE`+`FORCE` (delegator or owner writes, tenant-wide read) in `supabase/migrations/20260823000046_approval_delegation.sql`
- [x] T006 [P] Add `requests.*` and `approvals.*` i18n keys (request form, request list/detail, approval queue, threshold-rule and delegation management) to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping English/Arabic key parity
- [x] T007 [P] Add shell route entries for the requests list/detail and approval queue screens in `apps/web/src/app/app.routes.ts`, following the existing feature-area route style
- [x] T008 [P] Extend `apps/api/tests/integration/test_tenant_isolation.py` with cross-tenant cases for `purchase_request`, `purchase_request_line`, `approval_step`, `threshold_rule`, and `approval_delegation`, matching the existing uniform pattern for every prior tenant-scoped table

**Checkpoint**: schema, RLS (including branch-scoped visibility reused from R2.0), and cross-tenant isolation proof are complete before any module code is written.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: API module boundaries, the two pure-function cores (routing resolution, value estimation) this chunk's correctness hinges on, and typed frontend clients every user story depends on.

⚠️ **Everything else depends on this phase.**

- [ ] T009 Create the requests module skeleton in `apps/api/src/procurepilot_api/modules/requests/__init__.py`, `schemas.py`, `service.py`, and `router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T010 [P] Create Pydantic schemas for `PurchaseRequest`, `PurchaseRequestLine`, `ApprovalStep`, `ThresholdRule`, and `ApprovalDelegation` (create/update/list variants) in `apps/api/src/procurepilot_api/modules/requests/schemas.py`, matching `specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml` exactly, with `Money` as `{amount, currency}`
- [ ] T011 [P] Implement `resolve_approver()` as a pure function (no DB write) in `apps/api/src/procurepilot_api/modules/requests/routing.py`, encoding research.md R3's most-specific-wins threshold resolution, delegation redirect, and owner fallback, directly unit-testable with plain Python fixtures
- [ ] T012 [P] Implement request-line value estimation in `apps/api/src/procurepilot_api/modules/requests/valuation.py`, reusing `offers/price_history.py`'s `last_paid` computation for a `workspace_product_id` (research.md R2), returning the estimated unit price, its source `landed_cost_id`, or both-null when no price history exists
- [ ] T013 [P] Add a typed frontend API client in `apps/web/src/app/features/requests/requests-api.ts` (and a thin re-export or sibling `approvals-api.ts` for the approval-queue/threshold-rule/delegation endpoints), using decimal strings for money and the exact OpenAPI endpoint paths
- [ ] T014 [P] Add backend contract drift coverage in `apps/api/tests/contract/test_requests_openapi_drift.py`, verifying implemented route paths and response models against `specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml`

**Checkpoint**: FastAPI imports the new module, routing resolution and value estimation exist as independently-testable pure functions, and Angular can compile against a typed client.

---

## Phase 3: User Story 1 - Buyer submits a purchase request (P1)

**Goal**: a buyer creates a draft request naming branch, cost centre, required-by date, and lines; submits it; can withdraw it before a decision.

**Independent Test**: create a request, submit it, confirm status=submitted with the correct requester/branch/cost-centre attached — independent of who approves it or how routing resolves.

### Tests for User Story 1

- [ ] T015 [P] [US1] Write contract tests for `POST/GET/PATCH /requests` and `POST /requests/{id}/submit`+`/withdraw` in `apps/api/tests/contract/test_requests_contract.py`, covering OpenAPI shapes, the zero-lines 422, and 404/409 envelopes
- [ ] T016 [P] [US1] Write purchase-request integration tests in `apps/api/tests/integration/test_purchase_requests.py`, proving draft creation with live-recomputed line estimates, submit freezing those estimates (`estimated_at` stops changing even after a price-history change), the zero-lines rejection (FR-003), no-edit-after-submit (FR-004), and withdraw from `submitted` but not from `approved`/`rejected`
- [ ] T017 [P] [US1] Write frontend unit tests for the request creation form and list in `apps/web/src/app/features/requests/request-form/request-form.component.spec.ts`, covering line add/remove, the live estimate display, submit, and withdraw
- [ ] T018 [P] [US1] Write request-creation E2E coverage in `apps/web/tests/e2e/purchase-request-submission.spec.ts`, proving create-draft, submit, and withdraw through the real UI, plus Arabic RTL layout

### Implementation for User Story 1

- [ ] T019 [US1] Implement draft create/edit/submit/withdraw in `apps/api/src/procurepilot_api/modules/requests/service.py`, wiring in `valuation.py` (T012) for live line estimates on draft, freezing them on submit, and enforcing FR-003/FR-004
- [ ] T020 [US1] Expose `POST/GET/PATCH /requests` and `POST /requests/{id}/submit`+`/withdraw` in `apps/api/src/procurepilot_api/modules/requests/router.py`
- [ ] T021 [P] [US1] Build the request creation form, list, and detail UI in `apps/web/src/app/features/requests/`, using only `packages/i18n` strings and CSS logical properties, and add a real, enabled `shell.component.html` nav entry to `/requests` in the same task — not a disabled "coming soon" placeholder, which is how R2.0's own Settings screen shipped fully built but unreachable from navigation (a gap found and left unfixed pending a decision on `main`/PR #8; do not repeat it here)

**Checkpoint**: US1 is independently testable — a request can be created, submitted, and withdrawn with no approver or routing logic required to observe the behaviour.

---

## Phase 4: User Story 2 - Approver decides on a request from the approval queue (P1)

**Goal**: an approver sees every request routed to them, with full context, and approves or rejects.

**Independent Test**: seed a submitted request with a known `approval_step.assigned_membership_id`, sign in as that approver, and approve/reject from the queue — independent of how routing picked them.

### Tests for User Story 2

- [ ] T022 [P] [US2] Write contract tests for `GET /approvals/pending` and `POST /requests/{id}/approve`+`/reject` in `apps/api/tests/contract/test_approvals_contract.py`, covering the embedded-context shape (FR-005) and 403/404/409 envelopes
- [ ] T023 [P] [US2] Write approval-decision integration tests in `apps/api/tests/integration/test_approvals.py`, proving approve/reject transitions, the 403 refusal for anyone other than the assigned approver or an owner (FR-007), that `decided_by_membership_id`/`decided_at` are always populated together on any non-pending step (FR-006, the database check constraint from T003), and that a decided request no longer appears in `GET /approvals/pending`
- [ ] T024 [P] [US2] Write frontend unit tests for the approval queue in `apps/web/src/app/features/approvals/approval-queue/approval-queue.component.spec.ts`, covering the embedded context per row and the approve/reject actions with a comment
- [ ] T025 [P] [US2] Write approval-queue E2E coverage in `apps/web/tests/e2e/approval-queue.spec.ts`, proving an approver sees a routed request with full context, approves it, and that a different, unrelated member cannot decide on it, plus Arabic RTL layout

### Implementation for User Story 2

- [ ] T026 [US2] Implement `GET /approvals/pending` listing and approve/reject in `apps/api/src/procurepilot_api/modules/requests/service.py`, enforcing the assignee-or-owner rule (FR-007) and requiring a recorded `decided_by`/`decided_at` pair for every decision (FR-006) — no code path may set `status='approved'` without them
- [ ] T027 [US2] Expose `GET /approvals/pending` and `POST /requests/{id}/approve`+`/reject` in `apps/api/src/procurepilot_api/modules/requests/router.py`
- [ ] T028 [P] [US2] Build the approval queue screen in `apps/web/src/app/features/approvals/approval-queue/`, showing requester, branch, cost centre, lines, required-by date, and (once US4 lands) budget status inline, with approve/reject actions, and add a real, enabled `shell.component.html` nav entry to `/approvals` in the same task (see T021's note on not repeating R2.0's unreachable-Settings-screen gap)

**Checkpoint**: US2 is independently testable — a seeded request routes to a known approver and can be decided on, proving the minimum useful submit-then-decide loop end to end with US1.

---

## Phase 5: User Story 3 - Threshold-based routing with delegation and owner fallback (P2)

**Goal**: submitting a request resolves the correct approver via threshold rules, branch scope, active delegation, and an owner fallback when nothing else resolves.

**Independent Test**: define two threshold tiers with different approvers, submit requests at values landing in each, confirm correct routing; separately, delegate and confirm a new request redirects to the delegate.

### Tests for User Story 3

- [ ] T029 [P] [US3] Write direct unit tests for `resolve_approver()` (T011) in `apps/api/tests/unit/test_request_routing.py`, covering most-specific-branch-wins, the narrowest-range tie-break, delegation redirecting the threshold-resolved assignee, and owner fallback (no matching rule; resolved approver removed from workspace) — no DB required, per research.md R3
- [ ] T030 [P] [US3] Write contract tests for `GET/POST /approvals/threshold-rules`, `PATCH/DELETE /approvals/threshold-rules/{id}`, and `GET/POST /approvals/delegations`+`DELETE /approvals/delegations/{id}` in `apps/api/tests/contract/test_threshold_rules_contract.py`, covering owner-only writes and 403/404/422 envelopes
- [ ] T031 [P] [US3] Write end-to-end routing integration tests in `apps/api/tests/integration/test_request_routing.py`, proving a real submitted request lands in the correct approver's `GET /approvals/pending` per threshold tier and branch, that an active delegation redirects it, and that `requests.approval_step_escalated` is recorded when routing falls through to the owner
- [ ] T032 [P] [US3] Write frontend unit tests for threshold-rule and delegation management in `apps/web/src/app/features/settings/threshold-rule-list/threshold-rule-list.component.spec.ts`, covering tier creation, branch scoping, and owner-only visibility of write actions
- [ ] T033 [P] [US3] Write routing/delegation E2E coverage in `apps/web/tests/e2e/threshold-routing.spec.ts`, proving requests at different value tiers route to the correct approver through the real UI/API, and a delegation redirects a newly submitted request to the delegate

### Implementation for User Story 3

- [ ] T034 [US3] Wire `resolve_approver()` (T011) into the submit flow in `apps/api/src/procurepilot_api/modules/requests/service.py`, creating the `approval_step` with the resolved `assigned_membership_id`/`source`, and recording `requests.approval_step_escalated` when the source is `owner_fallback`
- [ ] T035 [US3] Implement `threshold_rule` CRUD (owner-only) and `approval_delegation` CRUD (delegator or owner) in `apps/api/src/procurepilot_api/modules/requests/service.py`
- [ ] T036 [US3] Expose `GET/POST /approvals/threshold-rules`, `PATCH/DELETE /approvals/threshold-rules/{id}`, and `GET/POST /approvals/delegations`+`DELETE /approvals/delegations/{id}` in `apps/api/src/procurepilot_api/modules/requests/router.py`
- [ ] T037 [P] [US3] Build threshold-rule management UI in `apps/web/src/app/features/settings/threshold-rule-list/`, added alongside the existing branch/cost-centre/budget lists on the settings screen

**Checkpoint**: US3 is independently testable — routing correctness is proven both as a pure function (T029) and end-to-end (T031), on top of US1/US2's already-working submit-then-decide loop.

---

## Phase 6: User Story 4 - Budget status visibility (P2)

**Goal**: a request's estimated value is compared against the remaining R2.0 budget for its scope, surfaced as an informational warning wherever the request is visible.

**Independent Test**: define a budget, submit a request within it (no warning) and one that would exceed it (warning shown, still submittable/approvable either way).

### Tests for User Story 4

- [ ] T038 [P] [US4] Write unit tests for the budget-remaining-amount comparison in `apps/api/tests/unit/test_budget_status.py`, covering within-budget (no warning), exceeding (warning with correct remaining amount), and no-applicable-budget (no `budget_status` at all, per FR-012)
- [ ] T039 [P] [US4] Write integration tests in `apps/api/tests/integration/test_request_budget_status.py`, proving `budget_status` appears correctly on both `GET /requests/{id}` and the matching row in `GET /approvals/pending`, and that an exceeding request still submits and can still be approved (FR-011)
- [ ] T040 [P] [US4] Write frontend unit tests for the budget-status display in `apps/web/src/app/features/requests/request-detail/request-detail.component.spec.ts` and the approval-queue row, covering the warning's presence/absence
- [ ] T041 [P] [US4] Write budget-status E2E coverage in `apps/web/tests/e2e/request-budget-status.spec.ts`, proving the warning appears on both the requester's and the approver's view for an exceeding request, and is absent for one within budget or with no applicable budget

### Implementation for User Story 4

- [ ] T042 [US4] Implement the budget-status comparison in `apps/api/src/procurepilot_api/modules/requests/service.py` (or a small `budget_status.py` helper), resolving the applicable R2.0 budget for a request's scope and period, and computing `remaining_amount`/`exceeds` — informational only, never blocking (FR-011, FR-012)
- [ ] T043 [P] [US4] Surface `budget_status` in the request detail screen and each approval-queue row in `apps/web/src/app/features/requests/request-detail/` and `apps/web/src/app/features/approvals/approval-queue/`

**Checkpoint**: US4 is independently testable and additive — everything from US1-US3 already works correctly with `budget_status` simply absent until this phase lands.

---

## Phase 7: Polish and Cross-Cutting

**Purpose**: branch-scoped-visibility proof extended to the new tables, full audit coverage, accessibility, and docs correction.

- [ ] T044 [P] Extend `apps/api/tests/integration/test_branch_scoped_visibility.py` with cases for `purchase_request` and `approval_step`: a branch-scoped member sees only their own branch's requests, a requester always sees their own request regardless of branch scope, and a direct request for another branch's request resolves not-found (never forbidden)
- [ ] T045 [P] Add an audit-log coverage test in `apps/api/tests/integration/test_requests_audit.py`, following the R2.0 `test_organisation_audit.py` pattern, proving `requests.purchase_request_submitted`, `requests.purchase_request_withdrawn`, `requests.approval_step_approved`, `requests.approval_step_rejected`, `requests.approval_step_escalated`, and `requests.threshold_rule_created`/`updated`/`deleted` all appear in `audit_event` (FR-013), backed by a live HTTP round-trip verification the same way T046 (R2.0) was
- [ ] T046 [P] Add accessibility coverage in `apps/web/tests/e2e/requests-a11y.spec.ts`, scanning the request creation/list/detail screens and the approval queue in English and Arabic with zero axe-core WCAG 2.1 AA violations
- [ ] T047 [P] Update `docs/architecture/data-dictionary.md` for the delivered `PurchaseRequest`, `PurchaseRequestLine`, `ApprovalStep`, `ThresholdRule`, and `ApprovalDelegation` entities, replacing the sketch-only placeholder entries under "Planned later domain entities"
- [ ] T048 [P] Update `docs/architecture/api-specification.md` for the `/requests/*` and `/approvals/*` endpoints, replacing the existing sketch-only "Requests & Approvals (Phase 2)" section

**Checkpoint**: branch-scoped visibility, full audit coverage, and accessibility are proven for every screen and table this chunk ships, and docs reflect the real delivered API/data model.

---

## Dependencies

```text
Phase 1 Setup (schema + RLS, reusing R2.0's branch-scoped mechanism)
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES (includes the two pure-function cores)
    ↓
    ├── Phase 3 US1 (P1) Submit a request
    │       ↓
    ├── Phase 4 US2 (P1) Decide from the approval queue  ← needs a submitted request to exist (US1), but is independently testable with a seeded one
    ├── Phase 5 US3 (P2) Threshold routing + delegation   ← refines WHO US2's queue routes to; US1/US2's loop already works without it
    ├── Phase 6 US4 (P2) Budget status visibility          ← additive on top of US1/US2; independent of US3
    └── Phase 7 Cross-cutting                               ← branch-scoped visibility proof, audit, a11y, docs
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — can start immediately. Reuses R2.0's RLS mechanism rather than building a new one.
- **Foundational (Phase 2)**: depends on Setup and blocks all user-story work; this is where `resolve_approver()` and value estimation are built as pure functions, independently of any HTTP surface.
- **US1 Submit a request (Phase 3)**: depends on Foundational only.
- **US2 Approval queue (Phase 4)**: depends on Foundational; needs US1's submit endpoint to exist for its own E2E test to create real data, but its integration tests can seed a submitted request directly and are independently testable.
- **US3 Threshold routing (Phase 5)**: depends on Foundational (the pure `resolve_approver()` function) and wires into US1's submit flow; US1/US2's loop already functions correctly without it (a request just always escalates to the owner until threshold rules exist).
- **US4 Budget status (Phase 6)**: depends on Foundational and R2.0's budget entities; purely additive to US1/US2's request/approval views.
- **Cross-cutting (Phase 7)**: depends on all four user stories being implemented.

### Parallel Opportunities

- Setup tasks T001-T005 touch different migration files but reuse the same R2.0 helper functions — no new helper to build, so all five can proceed in parallel; T006-T008 are fully parallel with the migrations.
- Foundational tasks T010-T014 can all run in parallel once T009's module skeleton exists; T011 and T012 are pure-function modules with no dependency on the DB layer at all.
- US1 tests T015-T018 can run together; T019 must land before T020; T021 can proceed against a typed client stub.
- US2 tests T022-T025 can run together; T026-T027 depend on US1's submit flow existing (to have a submitted request to act on), not on US1's UI.
- US3 tests T029-T033 can run together; T029 has zero dependencies beyond T011 and can start the moment Foundational lands; T034-T036 depend on US1's submit flow (T019) to wire routing into.
- US4 tests T038-T041 can run together; T038 has zero dependencies beyond R2.0's existing budget entities; T042-T043 depend on US1/US2's request/approval views existing to surface the status in.
- Cross-cutting T044-T048 can all run in parallel once the four user stories land.

---

## Delegation lanes

Per the current lane map (`delegate-setup`): `backend` → codex, `frontend` and `tests` → opencode,
`infra` → agy, `complex` → claude. Tenancy/RLS work (T001-T005, T044) stays in-house per standing
practice, not delegated to any lane; the pure-function routing/valuation cores (T011-T012, T029)
are good candidates for in-house or `complex` review given they encode this chunk's core
correctness property (no autonomous purchasing) rather than routine CRUD.

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator (in-house)** | Schema, RLS, branch-scoped visibility policies and their proof; the routing/valuation pure-function cores this chunk's correctness hinges on | **not delegated** | T001-T005, T011-T012, T029, T044 |
| **Backend (codex)** | `requests` module (schemas, service, router); contract/integration/audit tests | lane `backend` → codex | T008-T010, T013-T014, T016, T019-T020, T023, T026-T027, T030-T031, T034-T036, T038-T039, T042, T045 |
| **Frontend (opencode)** | Request form/list/detail, approval queue, threshold-rule management, i18n keys, E2E/a11y specs | lane `frontend`/`tests` → opencode | T006-T007, T015, T017-T018, T021-T022, T024-T025, T028, T032-T033, T037, T040-T041, T043, T046 |
| **Docs (codex)** | Correct architecture docs for the real delivered data/API shapes | lane `backend` → codex | T047-T048 |
