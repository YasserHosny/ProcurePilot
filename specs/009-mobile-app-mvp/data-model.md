# Data Model: Mobile MVP

**Feature**: 009-mobile-app-mvp
**Date**: 2026-09-11
**Scope**: New entities only. `purchase_request`, `purchase_request_line`, and `approval_step`
(008-requests-approvals) are reused completely unchanged — nothing in this document alters their
schema, RLS, or state machine. Migration filenames are sketches; SQL is intentionally not written
in this artifact.

## Shared Conventions

- Tenant scope comes from the verified JWT claim, never from path, query, or header input.
- Cross-tenant references return `404 not_found`, never `403 forbidden` (same convention every
  prior chunk uses).
- All tenant-scoped tables carry `tenant_id`, `ENABLE` and `FORCE` RLS, and a policy with both
  `USING` and `WITH CHECK`.
- Every FK from one tenant-scoped table to another is a composite `(tenant_id, id)` foreign key,
  continuing R2.0/R2.1's convention.
- Neither new table stores money — no currency/amount pairing concern applies to this chunk
  (Constitution Principle VII is satisfied trivially here; the money-handling discipline is
  exercised entirely by the unchanged `purchase_request`/`purchase_request_line`).

## Enumerations

No new enumerated status column this chunk — neither new table has a lifecycle to model.
`device_registration` and `low_stock_report` are both simple, mostly-append records, not
state machines.

## `device_registration`

A signed-in member's mobile device, registered to receive push notifications (research.md R1).

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `member_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)`; the signed-in owner of this device registration |
| `platform` | text | yes | `ios` \| `android`; informational, used only to pick the FCM vs. APNs send path |
| `push_token` | text | yes | Opaque token issued by the OS/push provider |
| `last_seen_at` | timestamptz | yes | Default `now()`; bumped on every app-open — the staleness signal used instead of a separate unregister endpoint (research.md R1) |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `unique (tenant_id, member_id, push_token)` — an upsert target; re-registering the same token
  (e.g. every app-open) updates `last_seen_at` in place rather than accumulating duplicate rows.
- Index on `tenant_id`, index on `member_id`.
- No hard lifecycle: a superseded or stale registration is left in place (research.md R1) rather
  than deleted — the send job simply targets the most-recently-seen row(s) for a member; pruning
  genuinely stale rows is an operational concern, not a correctness one, and is out of scope for
  this release.

## `low_stock_report`

A branch manager's quick "running low" signal for a product at their branch (research.md R2).
Informational only — carries no approval, routing, or purchase-request linkage of its own.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `branch_id` | uuid | yes | Composite FK -> `branch(tenant_id, id)` |
| `member_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)`; who raised the signal |
| `workspace_product_id` | uuid | yes | Composite FK -> `workspace_product(tenant_id, id)` |
| `count_remaining` | numeric(18,6) | no | Optional — the member's rough count of what's left, if they chose to enter one (FR-006, User Story 3) |
| `created_at` | timestamptz | yes | Default `now()`; the report's own timestamp — there is no `updated_at`, since the record is never edited after creation |

Constraints and indexes:

- Index on `tenant_id`, index on `branch_id`, index on `workspace_product_id`, index on
  `(tenant_id, branch_id, workspace_product_id, created_at)` for "recent low-stock signals for this
  branch/product" queries.
- Insert-only: no `PATCH`/`DELETE` surface this release. A duplicate double-tap is collapsed
  client-side (spec.md's edge case) — no server-side uniqueness constraint collapses two genuinely
  separate reports on different occasions, since both are legitimate signals.
- No FK from `purchase_request` to this table and no FK the other direction — the two are
  deliberately unlinked (research.md R2); a future release that wants to let an owner convert a
  low-stock report into a request would add that linkage explicitly then, not implicitly now.

## RLS Summary

| Table | Tenant isolation | Branch-scoped visibility |
|---|---|---|
| `device_registration` | `tenant_id = current_tenant_id()` | No branch scoping — a member manages only their own device registrations (`member_id = current_membership_id()`); an owner has no operational need to browse another member's push tokens, so owner read-all is not extended here the way it is for `purchase_request` |
| `low_stock_report` | `tenant_id = current_tenant_id()` | Yes — same branch-scoped visibility shape as `purchase_request` (R2.0/008's `current_membership_id()`/`current_member_role()` mechanism, research.md R1 of 008): a branch-scoped member sees their own branch's reports, an owner sees all, a member always sees reports they personally raised regardless of branch scope changes since |

Both tables' policies supply `USING` and `WITH CHECK`, per the constitution's Principle V
requirement. Neither table introduces a new isolation axis — both reuse the exact
`current_tenant_id()`/`current_membership_id()`/`current_member_role()` mechanism R2.0 built and
008 already extended (Constitution Check, plan.md).
