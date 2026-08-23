# Data Model: Requests + Approvals

**Feature**: 008-requests-approvals
**Date**: 2026-08-23
**Scope**: New entities only. Migration filenames are sketches; SQL is intentionally not written
in this artifact.

## Shared Conventions

- Tenant scope comes from the verified JWT claim, never from path, query, or header input.
- Cross-tenant references return `404 not_found`, never `403 forbidden` — and, per R2.0's
  precedent extended to this chunk, a same-tenant, different-branch reference for a branch-scoped
  member responds the same way.
- Money is stored as `numeric(18,4)` amount plus explicit `supported_currency(code)`.
- All tenant-scoped tables carry `tenant_id`, `ENABLE` and `FORCE` RLS, and a policy with both
  `USING` and `WITH CHECK`.
- Every FK from one tenant-scoped table to another is a composite `(tenant_id, id)` foreign key,
  continuing R2.0's convention (closes the GitHub issue #7 existence-oracle gap). Every table
  below that is referenced by another new table also carries `unique (tenant_id, id)`.

## Enumerations

| Enum | Values |
|---|---|
| `purchase_request_status` | `draft`, `submitted`, `approved`, `rejected`, `withdrawn` |
| `approval_step_status` | `pending`, `approved`, `rejected` |
| `approval_step_source` | `threshold_match`, `delegate`, `owner_fallback` — how this step's assignee was resolved (research.md R3); informational, not a workflow gate |

## `purchase_request`

A requester's ask to buy something, scoped to a branch and optionally a cost centre.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `branch_id` | uuid | yes | Composite FK -> `branch(tenant_id, id)` |
| `cost_centre_id` | uuid | no | Composite FK -> `cost_centre(tenant_id, id)`; null = branch-level, no finer cost-centre attribution |
| `requested_by_membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)` |
| `required_by_date` | date | yes | |
| `status` | `purchase_request_status` | yes | Default `draft` |
| `estimated_total_amount` | numeric(18,4) | no | Sum of line estimates in a single shared currency; null when lines span more than one currency (research.md R2) or no line has any estimate at all |
| `estimated_total_currency` | text | no | FK -> `supported_currency(code)`; paired-nullability with `estimated_total_amount` |
| `has_incomplete_estimate` | boolean | yes | Default `false`; true when any line has no reachable price-history source, or lines span multiple currencies (FR-015) |
| `submitted_at` | timestamptz | no | Stamped once, on the draft→submitted transition; never updated again |
| `withdrawn_at` | timestamptz | no | Stamped on withdrawal (FR-004) |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `unique (tenant_id, id)` — enables composite FK references from `purchase_request_line` and
  `approval_step`.
- Index on `tenant_id`, index on `branch_id`, index on `requested_by_membership_id`, index on
  `(tenant_id, status)` for queue/list queries.
- No hard-delete path: `withdrawn` is the only requester-initiated retirement of a submitted
  request (FR-004); a `draft` request may be hard-deleted by its own requester, since nothing else
  can yet reference a request that was never submitted.
- No in-place edit once `status <> 'draft'` (FR-004) — enforced at the application layer (a
  `PATCH` on a non-draft request is refused), since a check constraint cannot express "no column
  changed except `status`/`withdrawn_at`" cleanly; covered by contract tests instead.

## `purchase_request_line`

One item and quantity within a purchase request, plus its estimated value (research.md R2).

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `purchase_request_id` | uuid | yes | Composite FK -> `purchase_request(tenant_id, id)` |
| `workspace_product_id` | uuid | yes | Composite FK -> `workspace_product(tenant_id, id)` |
| `quantity` | numeric(18,6) | yes | Check `> 0` |
| `note` | text | no | |
| `estimated_unit_price_amount` | numeric(18,4) | no | Captured `last_paid` normalised unit price at estimate time; null when the product has no reachable `landed_cost` row |
| `estimated_unit_price_currency` | text | no | FK -> `supported_currency(code)`; paired-nullability with the amount above |
| `estimated_unit_price_source_landed_cost_id` | uuid | no | Composite FK -> `landed_cost(tenant_id, id)`; the provenance link Principle I requires — null exactly when the amount above is null |
| `estimated_at` | timestamptz | no | When the estimate above was captured; recomputed live (and this column updated) while the parent request is still `draft`, frozen once it is `submitted` |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- Index on `tenant_id`, index on `purchase_request_id`.
- `estimated_unit_price_amount`, `estimated_unit_price_currency`, and
  `estimated_unit_price_source_landed_cost_id` are null together or populated together (paired
  nullability, application-enforced the same way `budget`'s scope/target pairing already is).

## `approval_step`

The record of a single decision (or pending decision) on a request, produced by routing at
submission time (research.md R3).

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `purchase_request_id` | uuid | yes | Composite FK -> `purchase_request(tenant_id, id)` |
| `assigned_membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)`; the resolved approver at submission time — captured, never silently re-resolved (research.md R3) |
| `source` | `approval_step_source` | yes | How `assigned_membership_id` was resolved; informational only |
| `status` | `approval_step_status` | yes | Default `pending` |
| `comment` | text | no | |
| `decided_by_membership_id` | uuid | no | Composite FK -> `membership(tenant_id, id)`; required when `status <> 'pending'` — MUST be a human member; there is no system-originated decision (Principle III) |
| `decided_at` | timestamptz | no | Required when `status <> 'pending'` |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `unique (tenant_id, purchase_request_id)` — this release routes a request to exactly one
  resolved approval step, not a multi-stage chain; a future release may extend this to a sequence,
  out of scope here.
- Index on `tenant_id`, index on `assigned_membership_id`, index on `(tenant_id, status)` for the
  approval-queue query.
- `check (status = 'pending') = (decided_by_membership_id is null and decided_at is null)` —
  a decision fields pair is present if and only if the step is no longer pending, directly
  encoding "no request may become approved without a recorded human decision" (FR-006) at the
  database level, not only the application layer.
- `check decided_by_membership_id is distinct from assigned_membership_id or decided_by_membership_id is null`
  is deliberately **not** added — FR-007's owner-override allows a decision by someone other than
  the resolved assignee (an owner acting as standing override), so `decided_by_membership_id`
  legitimately differs from `assigned_membership_id` in that one case; the RBAC guard, not a check
  constraint, is what enforces "only the assignee or an owner," per research.md R3 and FR-007.

## `threshold_rule`

An owner-defined rule mapping a request-value range and an optional branch scope to the approver
a matching request should route to.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `branch_id` | uuid | no | Composite FK -> `branch(tenant_id, id)`; null = tenant-wide default rule |
| `min_amount` | numeric(18,4) | yes | Inclusive lower bound; `0` for a tenant/branch's lowest tier |
| `max_amount` | numeric(18,4) | no | Exclusive upper bound; null = no upper bound (the top tier) |
| `currency` | text | yes | FK -> `supported_currency(code)`; the currency `min_amount`/`max_amount` are expressed in — compared only against a request whose estimated total shares this currency (research.md R2); a request in a different currency (or with no single-currency total) falls through to owner escalation |
| `approver_membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)` |
| `created_by` | uuid | yes | Composite FK -> `membership(tenant_id, id)` |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `check (max_amount is null or max_amount > min_amount)`.
- Index on `tenant_id`, index on `(tenant_id, branch_id)`.
- No uniqueness constraint preventing overlapping ranges for the same branch/tenant scope —
  research.md R3's tie-break (narrowest range wins) handles a genuine overlap deterministically
  rather than the database refusing an owner's configuration outright; a warning surfaced at
  creation time (mirroring R2.0's budget `overlap_warning` UX) is out of scope for this release and
  may be added later without a schema change.
- Owner-managed only (create/edit/delete); no branch-scoped RLS restriction on reads (research.md
  R1) — every member can read the rules that determine routing, only an owner can write them.

## `approval_delegation`

A time-bounded handoff of one approver's pending and incoming decisions to another eligible
approver.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `delegator_membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)`; the approver stepping away |
| `delegate_membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)`; must hold an approver-eligible role (`approver`, `branch_manager`, or `owner`) — checked at the application layer against the existing role model, not a new column here |
| `starts_on` | date | yes | Inclusive |
| `ends_on` | date | yes | Inclusive; `check ends_on >= starts_on` |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- Index on `tenant_id`, index on `delegator_membership_id`, index on `(tenant_id, starts_on, ends_on)`
  for the "is there an active delegation today" lookup routing performs.
- `check delegator_membership_id <> delegate_membership_id` — an approver cannot delegate to
  themselves.
- No uniqueness constraint preventing overlapping delegation windows for the same delegator (an
  owner or the delegator correcting a mistake by adding a new, narrower window is a normal
  workflow); routing resolves ties the same deterministic way as threshold rules — the
  most-recently-created delegation covering today wins, since two genuinely overlapping active
  delegations for the same person is expected to be rare misconfiguration, not a designed state.

## RLS Summary

| Table | Tenant isolation | Branch-scoped visibility |
|---|---|---|
| `purchase_request` | `tenant_id = current_tenant_id()` | Yes — owner sees all; a member with a `branch_role_assignment` row sees only requests for their assigned branch(es); requester always sees their own request regardless of branch scoping (R2.0's research.md R1 mechanism, extended) |
| `purchase_request_line` | `tenant_id = current_tenant_id()` | Yes — inherited via `purchase_request_id` join, same shape as `purchase_request` |
| `approval_step` | `tenant_id = current_tenant_id()` | Yes — owner sees all; the assigned approver sees their own step; the requester sees the step(s) on their own request (read-only, for status visibility) |
| `threshold_rule` | `tenant_id = current_tenant_id()` | No branch restriction on read (research.md R1); write restricted to owner |
| `approval_delegation` | `tenant_id = current_tenant_id()` | No branch restriction on read; write restricted to the delegator themselves or an owner |

Every policy above supplies both `USING` and `WITH CHECK`, per the constitution's Principle V
requirement and this codebase's uniform convention.
