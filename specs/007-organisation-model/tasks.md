---
description: "Task list for Organisation Model implementation"
---

# Tasks: Organisation Model

**Input**: Design documents from `/specs/007-organisation-model/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/organisation.openapi.yaml, quickstart.md

**Tests**: Included. The constitution requires unit/integration tests on every PR, a dedicated tenant-isolation proof for every tenant-scoped table, and this chunk introduces a second isolation axis (branch-scoped visibility) that needs its own proof the same way.

**Organization**: grouped by setup, blocking foundation, then user stories in spec.md order, so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md; setup and foundational tasks may have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: schema, RLS (including branch-scoped policies from the same migration that creates each table, per this repo's own convention), and i18n/routing scaffolding.

- [x] T001 Add `unique (tenant_id, id)` to the existing `membership` table via a new additive migration `supabase/migrations/20260822000036_membership_composite_key.sql`, changing no existing column, data, or behaviour
- [x] T002 Create `branch` with `unique (tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the branch-visibility policy from research.md R1 (including the `current_membership_id()` and `current_member_role()` helper functions it depends on) in `supabase/migrations/20260822000037_branch.sql`
- [x] T003 Create `cost_centre` with `unique (tenant_id, id)`, `unique (tenant_id, code)`, composite FKs to `branch(tenant_id, id)` and `membership(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the same branch-scoped visibility policy shape evaluated against `cost_centre.branch_id` in `supabase/migrations/20260822000038_cost_centre.sql`
- [x] T004 Create `budget` with the `budget_scope_target` check constraint, composite FKs to `branch(tenant_id, id)`, `cost_centre(tenant_id, id)`, and `membership(tenant_id, id)`, RLS `ENABLE`+`FORCE`, and the branch-scoped visibility policy in `supabase/migrations/20260822000039_budget.sql`
- [x] T005 Create `branch_role_assignment` with composite FKs to `membership(tenant_id, id)` and `branch(tenant_id, id)`, the `unique (tenant_id, membership_id, branch_id)` constraint, and RLS `ENABLE`+`FORCE` (owner writes, assigned member reads own rows) in `supabase/migrations/20260822000040_branch_role_assignment.sql`
- [x] T006 [P] Add `organisation.*` i18n keys (branch, cost centre, budget, and org-settings-screen strings) to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping English/Arabic key parity
- [x] T007 [P] Add shell route entries for the organisation settings screen in `apps/web/src/app/app.routes.ts`, following the existing settings-area route style
- [x] T008 [P] Extend `apps/api/tests/integration/test_tenant_isolation.py` with cross-tenant cases for `branch`, `cost_centre`, `budget`, and `branch_role_assignment`, matching the existing uniform pattern for every prior tenant-scoped table

**Checkpoint**: schema, RLS (including branch-scoped visibility), and cross-tenant isolation proof are complete before any module code is written.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: API module boundaries, schemas, and typed frontend clients that every user story depends on.

⚠️ **Everything else depends on this phase.**

- [x] T009 Create the organisation module skeleton in `apps/api/src/procurepilot_api/modules/organisation/__init__.py`, `schemas.py`, `service.py`, and `router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [x] T010 [P] Create Pydantic schemas for `Branch`, `CostCentre`, `Budget`, and `BranchRoleAssignment` (create/update/list variants) in `apps/api/src/procurepilot_api/modules/organisation/schemas.py`, matching `specs/007-organisation-model/contracts/organisation.openapi.yaml` exactly, with `Money` as `{amount, currency}`
- [x] T011 Extend `apps/api/src/procurepilot_api/modules/members/service.py` and `router.py` with branch-role-assignment create/delete, validating the target member currently holds `branch_manager` or `approver` before allowing an assignment (422 otherwise, per the contract)
- [x] T012 [P] Add a typed frontend API client in `apps/web/src/app/features/settings/organisation-api.ts`, using decimal strings for money and the exact OpenAPI endpoint paths
- [x] T013 [P] Add backend contract drift coverage in `apps/api/tests/contract/test_organisation_openapi_drift.py`, verifying implemented route paths and response models against `specs/007-organisation-model/contracts/organisation.openapi.yaml`

**Checkpoint**: FastAPI imports the new module, `members` supports branch-scoped role assignment, and Angular can compile against a typed client.

---

## Phase 3: User Story 1 - Owner structures the business into branches (P1)

**Goal**: an owner creates, edits, and deactivates branches from the organisation settings screen.

**Independent Test**: create, edit, and deactivate a branch through the screen; confirm the branch list reflects each change immediately — no cost centres, budgets, or role assignment required.

### Tests for User Story 1

- [x] T014 [P] [US1] Write contract tests for `GET/POST /organisation/branches` and `PATCH /organisation/branches/{id}` in `apps/api/tests/contract/test_branches_contract.py`, covering OpenAPI shapes, 403/404/422 envelopes, and cursor limits
- [x] T015 [P] [US1] Write branch CRUD integration tests in `apps/api/tests/integration/test_branches.py`, proving create/edit/deactivate, the no-hard-delete guarantee (FR-009), the `confirm_dependents` flow when a branch has cost centres or role assignments attached, and owner-only write access
- [ ] T016 [P] [US1] Write frontend unit tests for the branch list/form in `apps/web/src/app/features/settings/branch-list/branch-list.component.spec.ts`, covering create, edit, deactivate-with-dependents confirmation, and owner-only action visibility
- [ ] T017 [P] [US1] Write branch-management E2E coverage in `apps/web/tests/e2e/organisation-branches.spec.ts`, proving create, edit, deactivate with a dependent cost centre, and Arabic RTL layout

### Implementation for User Story 1

- [ ] T018 [US1] Implement branch create/edit/list/deactivate in `apps/api/src/procurepilot_api/modules/organisation/service.py`, enforcing owner-only writes, the dependent-confirmation flow (FR-009), and cross-tenant/cross-branch not-found semantics (FR-008)
- [ ] T019 [US1] Expose `GET/POST /organisation/branches` and `PATCH /organisation/branches/{id}` in `apps/api/src/procurepilot_api/modules/organisation/router.py`
- [ ] T020 [P] [US1] Build the branch list/create/edit UI in `apps/web/src/app/features/settings/branch-list/branch-list.component.ts`, `.html`, and `.scss`, using only `packages/i18n` strings and CSS logical properties

**Checkpoint**: US1 is independently testable — branches can be fully managed with no other entity required.

---

## Phase 4: User Story 2 - Owner defines cost centres and assigns a budget owner (P1)

**Goal**: an owner creates cost centres, each with a unique code and a designated budget owner, optionally linked to a branch.

**Independent Test**: create a cost centre, assign a budget owner from the existing member list, optionally link it to a branch, and confirm it appears correctly scoped — no budget required yet.

### Tests for User Story 2

- [ ] T021 [P] [US2] Write contract tests for `GET/POST /organisation/cost-centres` and `PATCH /organisation/cost-centres/{id}` in `apps/api/tests/contract/test_cost_centres_contract.py`, covering OpenAPI shapes, the duplicate-code 409, and 403/404/422 envelopes
- [ ] T022 [P] [US2] Write cost-centre integration tests in `apps/api/tests/integration/test_cost_centres.py`, proving duplicate-code rejection (FR-003), the orphan-flagging behaviour when a linked branch is deactivated or the budget owner is removed (FR-010), and owner-only write access
- [ ] T023 [P] [US2] Write frontend unit tests for the cost-centre list/form in `apps/web/src/app/features/settings/cost-centre-list/cost-centre-list.component.spec.ts`, covering create, duplicate-code error display, and orphaned-flag messaging
- [ ] T024 [P] [US2] Write cost-centre-management E2E coverage in `apps/web/tests/e2e/organisation-cost-centres.spec.ts`, proving create with a budget owner and branch link, a duplicate-code rejection, and Arabic RTL layout

### Implementation for User Story 2

- [ ] T025 [US2] Implement cost-centre create/edit/list/archive in `apps/api/src/procurepilot_api/modules/organisation/service.py`, enforcing the unique-code constraint, owner-only writes, and orphan-flagging when a linked branch is deactivated or a budget owner is removed (FR-010)
- [ ] T026 [US2] Expose `GET/POST /organisation/cost-centres` and `PATCH /organisation/cost-centres/{id}` in `apps/api/src/procurepilot_api/modules/organisation/router.py`
- [ ] T027 [P] [US2] Build the cost-centre list/create/edit UI in `apps/web/src/app/features/settings/cost-centre-list/cost-centre-list.component.ts`, `.html`, and `.scss`, including a budget-owner picker sourced from the existing member list and an optional branch picker

**Checkpoint**: US2 is independently testable alongside US1's branches, or on its own using only organisation-wide cost centres.

---

## Phase 5: User Story 3 - Owner defines a budget (P2)

**Goal**: an owner defines a budget with an amount, currency, period, and scope (organisation, branch, or cost centre); this chunk stores it only — no spend-checking.

**Independent Test**: define a budget at each of the three scopes and confirm each appears correctly attributed in the budget list — no purchase-request flow required.

### Tests for User Story 3

- [ ] T028 [P] [US3] Write contract tests for `GET/POST /organisation/budgets` in `apps/api/tests/contract/test_budgets_contract.py`, covering all three scopes, the `budget_scope_target` constraint's 422 shape, and 403/404 envelopes
- [ ] T029 [P] [US3] Write budget integration tests in `apps/api/tests/integration/test_budgets.py`, proving each scope stores and lists correctly, overlapping-period budgets for the same scope are allowed with the `overlap_warning` flag set, and currency is never inferred from `tenant.currency` (research.md R3)
- [ ] T030 [P] [US3] Write frontend unit tests for the budget list/form in `apps/web/src/app/features/settings/budget-list/budget-list.component.spec.ts`, covering scope selection, the overlap warning, and explicit currency entry
- [ ] T031 [P] [US3] Write budget-management E2E coverage in `apps/web/tests/e2e/organisation-budgets.spec.ts`, proving all three scopes and the overlap warning, plus Arabic RTL layout

### Implementation for User Story 3

- [ ] T032 [US3] Implement budget create/list in `apps/api/src/procurepilot_api/modules/organisation/service.py`, validating the scope/reference pairing, computing the `overlap_warning` flag against existing budgets for the same scope, and enforcing owner-only writes
- [ ] T033 [US3] Expose `GET/POST /organisation/budgets` in `apps/api/src/procurepilot_api/modules/organisation/router.py`
- [ ] T034 [P] [US3] Build the budget list/create UI in `apps/web/src/app/features/settings/budget-list/budget-list.component.ts`, `.html`, and `.scss`, with scope-dependent branch/cost-centre pickers and explicit currency selection

**Checkpoint**: US3 is independently testable once US1/US2 exist to provide branch/cost-centre scope targets (organisation-wide budgets need neither).

---

## Phase 6: User Story 4 - Branch manager sees only their own branch's data (P1)

**Goal**: a member holding a branch-scoped role, once assigned to a specific branch, sees organisation screens scoped to that branch only; an owner continues to see everything.

**Independent Test**: assign a member the `branch_manager` role scoped to Branch A, sign in as that member, and confirm Branch B's data and org-wide-only screens are unreachable, while Branch A's own data is fully visible.

### Tests for User Story 4

- [ ] T035 [P] [US4] Write contract tests for `POST /organisation/branch-role-assignments` and `DELETE /organisation/branch-role-assignments/{id}` in `apps/api/tests/contract/test_branch_role_assignments_contract.py`, covering the 422 when the target member does not hold a branch-scopable role, the 409 on duplicate assignment, and 403/404 envelopes
- [ ] T036 [P] [US4] Write branch-scoped-visibility integration tests in `apps/api/tests/integration/test_branch_scoped_visibility.py`, proving a member assigned to Branch A sees only Branch A's branch/cost-centre/budget rows, an owner sees everything, a direct request for Branch B resolves not-found (never forbidden, FR-008), and removing the last assignment returns the member to unscoped (tenant-wide) visibility
- [ ] T037 [P] [US4] Extend `apps/web/src/app/features/team/change-role-dialog/change-role-dialog.component.spec.ts` with tests for the new branch picker shown when the selected role is `branch_manager` or `approver`
- [ ] T038 [P] [US4] Write branch-scoped-visibility E2E coverage in `apps/web/tests/e2e/organisation-branch-scoping.spec.ts`, proving a branch-scoped member's organisation screens show only their own branch's data and a guessed Branch B URL resolves as not found

### Implementation for User Story 4

- [ ] T039 [US4] Confirm and, if needed, correct the branch-visibility RLS policies from T002-T004 against the integration tests in T036 — this phase is primarily a proof phase, since the enforcement mechanism itself (research.md R1) was built as part of Phase 1 Setup, matching this repo's own convention of shipping a table's RLS policy in the same migration that creates it
- [ ] T040 [P] [US4] Add the branch picker to `apps/web/src/app/features/team/change-role-dialog/change-role-dialog.component.ts` and `.html`, calling the new branch-role-assignment endpoints, shown only when the selected role is `branch_manager` or `approver`
- [ ] T041 [P] [US4] Wire branch-scoped filtering into `apps/web/src/app/features/settings/branch-list/`, `cost-centre-list/`, and `budget-list/` components so a branch-scoped member's own screens correctly reflect what the API already returns, with no client-side re-filtering of data the API should not have sent in the first place

**Checkpoint**: the whole chunk's actual payoff — branch-scoped visibility — is proven end to end, not just present as an unenforced label on a role.

---

## Phase 7: Polish and Cross-Cutting

**Purpose**: docs correction and the organisation settings screen that ties branch/cost-centre/budget management together in one place (FR-011).

- [ ] T042 [P] Build the organisation settings shell screen in `apps/web/src/app/features/settings/settings.component.ts`, `.html`, and `.scss`, composing the branch-list, cost-centre-list, and budget-list components into one screen per FR-011
- [ ] T043 [P] Add organisation-settings accessibility coverage in `apps/web/tests/e2e/organisation-a11y.spec.ts`, scanning the settings screen in English and Arabic with zero axe-core WCAG 2.1 AA violations
- [ ] T044 [P] Update `docs/architecture/data-dictionary.md` for the delivered `Branch`, `CostCentre`, `Budget`, and `BranchRoleAssignment` entities
- [ ] T045 [P] Update `docs/architecture/api-specification.md` for the `/organisation/*` endpoints, replacing any existing sketch-only organisation-model section
- [ ] T046 [P] Add an audit-log coverage test in `apps/api/tests/integration/test_organisation_audit.py`, proving every branch/cost-centre/budget/branch-role-assignment create, edit, deactivation, and archival appears in `audit_event` (FR-012)

**Checkpoint**: every screen this chunk ships has automated a11y coverage, docs reflect the real delivered API/data model, and every administrative action is audited.

---

## Dependencies

```text
Phase 1 Setup (schema + RLS, including branch-scoped policies)
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES
    ↓
    ├── Phase 3 US1 (P1) Branches
    │       ↓
    ├── Phase 4 US2 (P1) Cost centres           ← branch_id link optional, can proceed alongside US1
    ├── Phase 5 US3 (P2) Budgets                ← organisation-wide scope needs neither US1 nor US2; branch/cost-centre scope needs the corresponding one
    ├── Phase 6 US4 (P1) Branch-scoped visibility ← proves the RLS built in Setup; needs US1's branches to assign against
    └── Phase 7 Cross-cutting                    ← final screen assembly, a11y, docs, audit proof
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — can start immediately. This is where the branch-scoped RLS mechanism itself is built, per this repo's convention of shipping a table's RLS policy in the same migration that creates it.
- **Foundational (Phase 2)**: depends on Setup and blocks all user-story work.
- **US1 Branches (Phase 3)**: depends on Foundational only.
- **US2 Cost centres (Phase 4)**: depends on Foundational; an organisation-wide cost centre needs nothing from US1, a branch-linked one needs a branch to exist.
- **US3 Budgets (Phase 5)**: depends on Foundational; an organisation-wide budget needs nothing further, a branch- or cost-centre-scoped one needs the corresponding entity from US1/US2.
- **US4 Branch-scoped visibility (Phase 6)**: depends on Foundational and on US1 (needs at least one branch to assign a member to); proves the mechanism Setup already built rather than building a new one.
- **Cross-cutting (Phase 7)**: depends on all four user stories being implemented, since the settings shell screen composes their individual components.

### Parallel Opportunities

- Setup tasks T002-T005 touch different migration files but share the same helper functions (T002) — T003-T005 can start once T002's helpers land; T006-T008 are fully parallel with the migrations.
- Foundational tasks T010 and T012-T013 can run in parallel once T009's module skeleton exists; T011 touches the existing `members` module and should be coordinated with T009 rather than run blind.
- US1 tests T014-T017 can run together; T018 must land before T019; T020 can proceed against a typed client stub.
- US2 tests T021-T024 can run together; T025-T026 depend on US1's branch endpoints only for the optional link, not for cost-centre CRUD itself.
- US3 tests T028-T031 can run together; T032-T033 depend on US1/US2 only for branch-/cost-centre-scoped budgets, not for organisation-wide ones.
- US4 tests T035-T038 can run together; T039 is verification, not new implementation; T040-T041 can proceed in parallel once the branch-role-assignment endpoints from Foundational/T011 exist.
- Cross-cutting T043-T046 can all run in parallel once T042's shell screen composes the three list components from US1-US3.

---

## Delegation lanes

Per the current lane map (`delegate-setup`, updated 2026-08-22): `backend` → codex, `frontend`
and `tests` → opencode (`opencode-go/ox-alpha-free`, variant max, one-week trial), `infra` → agy,
`complex` → claude. Tenancy/RLS work (T001-T005, T036, T039) stays in-house per standing practice,
not delegated to any lane.

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator (in-house)** | Schema, RLS, branch-scoped visibility policies, and their proof — the one thing not delegated by default for this codebase | **not delegated** | T001-T005, T036, T039 |
| **Backend (codex)** | `organisation` module (schemas, service, router); `members` module extension for branch-role assignment; contract/integration/audit tests | lane `backend` → codex | T008-T011, T013, T015, T018-T019, T022, T025-T026, T029, T032-T033, T046 |
| **Frontend (opencode/ox-alpha)** | Branch/cost-centre/budget list-and-form components; organisation settings shell; change-role-dialog branch picker; i18n keys; E2E/a11y specs | lane `frontend`/`tests` → opencode | T006-T007, T012, T014, T016-T017, T020-T021, T023-T024, T027-T028, T030-T031, T034-T035, T037-T038, T040-T043 |
| **Docs (codex)** | Correct architecture docs for the real delivered data/API shapes | lane `backend` → codex | T044-T045 |
