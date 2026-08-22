# Data Model: Organisation Model

**Feature**: 007-organisation-model
**Date**: 2026-08-22
**Scope**: New entities only. Migration filenames are sketches; SQL is intentionally not written
in this artifact.

## Shared Conventions

- Tenant scope comes from the verified JWT claim, never from path, query, or header input.
- Cross-tenant references return `404 not_found`, never `403 forbidden` — and per this chunk's
  own FR-008, a same-tenant, different-branch reference for a branch-scoped member responds the
  same way, never `403`.
- Money is stored as `numeric(18,4)` amount plus explicit `supported_currency(code)` — see
  research.md R3 on why `budget.currency` is never inferred from `tenant.currency`.
- All tenant-scoped tables carry `tenant_id`, `ENABLE` and `FORCE` RLS, and a policy with both
  `USING` and `WITH CHECK`.
- **New in this chunk**: every FK from one tenant-scoped table to another tenant-scoped table is
  a *composite* `(tenant_id, id)` foreign key, not a bare single-column FK to the referenced
  table's `id` alone. This directly closes the gap tracked in GitHub issue #7 (a single-column FK
  lets a caller reference another tenant's row, passing their own table's RLS `tenant_id` check
  while pointing at data they cannot otherwise see — a data-integrity and existence-oracle risk).
  Every table below that is referenced by another new table in this chunk therefore also carries
  `unique (tenant_id, id)` alongside its primary key, so the composite reference has something to
  point at.

## Enumerations

| Enum | Values |
|---|---|
| `budget_period` | `monthly`, `quarterly`, `annual` |
| `budget_scope` | `organisation`, `branch`, `cost_centre` |

No new status enum for `branch`/`cost_centre` — both use a plain boolean
(`active`/`is_archived`) rather than a multi-value status, since the only states are
active/inactive (branch) and active/archived (cost centre), and a two-state boolean is simpler
than a single-value enum for a genuinely binary condition.

## `branch`

A physical location or organisational division within a tenant.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `name` | text | yes | |
| `address` | text | no | Free text; no structured address validation in this chunk |
| `region` | text | no | FK -> `supported_region(code)`; nullable — a branch may predate region being set, or share the tenant's own region implicitly |
| `is_active` | boolean | yes | Default `true` |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `unique (tenant_id, id)` — enables composite FK references from `cost_centre`,
  `budget`, and `branch_role_assignment` (see Shared Conventions).
- Index on `tenant_id`.
- No hard-delete path (FR-009): deactivation (`is_active = false`) is the only way to retire a
  branch, and it is permitted even when dependents exist (User Story 1, Acceptance Scenario 3) —
  the application layer surfaces a confirmation naming what is still attached, but the database
  itself does not block the update.

## `cost_centre`

A budget-tracking grouping within a tenant, independent of physical location.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `name` | text | yes | |
| `code` | text | yes | Unique per tenant (FR-003) |
| `budget_owner_membership_id` | uuid | no | Composite FK -> `membership(tenant_id, id)`; nullable when the owner has been removed from the workspace (FR-010 orphan-flagging) |
| `branch_id` | uuid | no | Composite FK -> `branch(tenant_id, id)`; null = organisation-wide cost centre |
| `is_orphaned` | boolean | yes | Default `false`; set `true` by application logic when `branch_id`'s branch is deactivated or `budget_owner_membership_id`'s member is removed (FR-010) — a flag, not a derived/computed column, so the orphan state is visible even after the branch or member row itself changes further |
| `is_archived` | boolean | yes | Default `false` |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `unique (tenant_id, id)` — enables composite FK references from `budget`.
- `unique (tenant_id, code)` — enforces FR-003 (no duplicate cost-centre code within a tenant).
- Index on `tenant_id`, index on `branch_id`.
- No hard-delete path: archival (`is_archived = true`) is the only retirement path, same
  reasoning as `branch`.

## `budget`

A defined spending allowance for a period, scoped to exactly one of: the organisation, one
branch, or one cost centre. This chunk defines and stores budgets only — checking real spend
against them is explicitly out of scope until R2.1 (spec.md, User Story 3).

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `amount` | numeric(18,4) | yes | |
| `currency` | text | yes | FK -> `supported_currency(code)`; never inferred from `tenant.currency` — see research.md R3 |
| `period` | `budget_period` | yes | |
| `period_start` | date | yes | Start of the period this specific budget instance covers |
| `scope` | `budget_scope` | yes | |
| `branch_id` | uuid | no | Composite FK -> `branch(tenant_id, id)`; required if and only if `scope = 'branch'` |
| `cost_centre_id` | uuid | no | Composite FK -> `cost_centre(tenant_id, id)`; required if and only if `scope = 'cost_centre'` |
| `created_by` | uuid | yes | Composite FK -> `membership(tenant_id, id)` |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `constraint budget_scope_target check`: `(scope = 'organisation' and branch_id is null and cost_centre_id is null) or (scope = 'branch' and branch_id is not null and cost_centre_id is null) or (scope = 'cost_centre' and cost_centre_id is not null and branch_id is null)` —
  the scope enum and the actual populated reference column can never disagree (mirrors the
  existing `quotation_stated_total_has_currency`-style paired-nullability pattern already used in
  chunk 4.3).
- Index on `tenant_id`, index on `(scope, branch_id)`, index on `(scope, cost_centre_id)`.
- **Deliberately no uniqueness constraint preventing overlapping periods for the same scope**
  (spec.md User Story 3, Acceptance Scenario 3: multiple budgets may legitimately coexist for one
  scope, e.g. a running annual budget plus a supplementary quarterly top-up). Overlap is
  surfaced to the user at creation time by the application layer as a warning, not blocked by the
  database.

## `branch_role_assignment`

The association between a member's role and the specific branch(es) that role is scoped to.
Extends the existing `membership`/role relationship rather than replacing it — `membership.role`
remains the tenant-wide role value (`owner`, `buyer`, `branch_manager`, `approver`, `viewer`,
unchanged from chunk 4.1); this table adds branch scoping *on top of* a `branch_manager` or
`approver` role, and simply has no rows for a member whose role is not branch-scoped.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)` |
| `branch_id` | uuid | yes | Composite FK -> `branch(tenant_id, id)` |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `unique (tenant_id, membership_id, branch_id)` — a member cannot be assigned to the same branch
  twice; supports one member scoped to multiple branches as separate rows (research.md R2,
  spec.md edge case: "a member holds a role scoped to more than one branch").
- Index on `tenant_id`, index on `membership_id`, index on `branch_id`.
- No `is_active`/soft-delete column — removing a branch assignment is a real row deletion here
  (unlike `branch`/`cost_centre` themselves), since this table carries no independent history of
  its own worth preserving; the audit log (FR-012) is where the historical record of an
  assignment change lives, not a soft-delete flag on this join table.

## `membership` (existing table, additive migration only)

- **New**: `unique (tenant_id, id)` constraint added, enabling the composite FK references above.
  Purely additive — no existing column, data, or behaviour changes; the existing
  `membership_one_per_person_per_tenant` unique constraint on `(tenant_id, user_id)` is untouched.

## RLS Summary

| Table | Tenant isolation | Branch-scoped visibility |
|---|---|---|
| `branch` | `tenant_id = current_tenant_id()` | Yes — owner sees all; a member with a `branch_role_assignment` row sees only their assigned branch(es); a member with no assignment row (unscoped role) sees all, per research.md R1 |
| `cost_centre` | `tenant_id = current_tenant_id()` | Yes — same shape as `branch`, evaluated against `cost_centre.branch_id` (null = organisation-wide, always visible) |
| `budget` | `tenant_id = current_tenant_id()` | Yes — same shape, evaluated against `budget.branch_id`/`cost_centre_id` depending on `scope` |
| `branch_role_assignment` | `tenant_id = current_tenant_id()` | Writable by owner only (assigning branch scope is an administrative action); readable by the assigned member for their own row(s) and by owner for all |

Every policy above supplies both `USING` and `WITH CHECK`, per the constitution's Principle V
requirement and this codebase's uniform convention.
