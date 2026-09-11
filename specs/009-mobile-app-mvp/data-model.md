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
- A reinstall or token rotation is left as passive staleness (research.md R1) — the old row is not
  deleted, the send job simply targets the most-recently-seen row(s) for a member; pruning genuinely
  stale rows is an operational concern, not a correctness one, out of scope for this release.
  **Sign-out is different and is NOT passive**: the mobile app calls `DELETE /devices/{id}` for its
  own current registration on sign-out, deleting the row outright — a signed-out but still-installed
  device must stop being eligible for push immediately, not eventually (research.md R1, revised).

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
| `idempotency_key` | uuid | no | Client-stamped at creation time (research.md R4, revised); null for a report created online in one shot with no retry concern, populated for one built/queued offline so a replayed submission after a dropped response is recognized instead of duplicated |
| `created_at` | timestamptz | yes | Default `now()`; the report's own timestamp — there is no `updated_at`, since the record is never edited after creation |

Constraints and indexes:

- Index on `tenant_id`, index on `branch_id`, index on `workspace_product_id`, index on
  `(tenant_id, branch_id, workspace_product_id, created_at)` for "recent low-stock signals for this
  branch/product" queries.
- `unique (tenant_id, idempotency_key)` where `idempotency_key is not null` — a partial unique
  index, so two genuinely separate reports with no key (the common, online-submission case) never
  collide, while a replayed offline submission's second attempt is rejected by the same insert and
  the endpoint returns the original row instead of creating a duplicate (research.md R4, revised —
  this is real server-side enforcement, not a restatement of the header's existence).
- Insert-only: no `PATCH`/`DELETE` surface this release. A duplicate double-tap with no
  connectivity gap is collapsed client-side (spec.md's edge case) before it ever reaches the
  network — the `idempotency_key` uniqueness above is the server-side backstop for the genuinely
  offline-retry case, not a replacement for the client-side debounce.
- No FK from `purchase_request` to this table and no FK the other direction — the two are
  deliberately unlinked (research.md R2); a future release that wants to let an owner convert a
  low-stock report into a request would add that linkage explicitly then, not implicitly now.

## `push_notification`

A durable, internal record of one decision-triggered push send attempt (research.md R1, revised) —
not client-facing this release; no endpoint reads or writes it directly, it exists so an enqueue
failure or a worker outage leaves a visible, replayable row instead of a silently dropped job.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `purchase_request_id` | uuid | yes | Composite FK -> `purchase_request(tenant_id, id)`; the decided request the notification is about |
| `member_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)`; the original submitter being notified |
| `status` | text | yes | `queued` \| `sent` \| `failed`; default `queued`. Not a formal enum type — this is an internal delivery-tracking flag, not a domain lifecycle worth the ceremony of a shared enum |
| `attempts` | integer | yes | Default `0`; incremented on each send attempt, read by the retry sweep to back off/give up rather than hammer a persistently failing provider |
| `created_at` | timestamptz | yes | Default `now()`; written in the same transaction as the triggering decision (research.md R1) |
| `sent_at` | timestamptz | no | Stamped on a successful send; null while `queued`/`failed` |

Constraints and indexes:

- Index on `tenant_id`, index on `(tenant_id, status, created_at)` for the retry sweep's "find
  stuck rows" query.
- No RLS-visible read path for a member or owner this release (service-role only) — this is
  operational plumbing, not a user-facing record; still carries `tenant_id` + `ENABLE`+`FORCE` RLS
  per the constitution's blanket requirement for every tenant-scoped table, even one with no client
  read surface yet.

## RLS Summary

| Table | Tenant isolation | Branch-scoped visibility |
|---|---|---|
| `device_registration` | `tenant_id = current_tenant_id()` | No branch scoping — a member manages only their own device registrations (`member_id = current_membership_id()`); an owner has no operational need to browse another member's push tokens, so owner read-all is not extended here the way it is for `purchase_request` |
| `low_stock_report` | `tenant_id = current_tenant_id()` | Yes — same branch-scoped visibility shape as `purchase_request` (R2.0/008's `current_membership_id()`/`current_member_role()` mechanism, research.md R1 of 008): a branch-scoped member sees their own branch's reports, an owner sees all, a member always sees reports they personally raised regardless of branch scope changes since |
| `push_notification` | `tenant_id = current_tenant_id()` | No client-facing read policy this release — service-role only (research.md R1, revised) |

All three tables' policies supply `USING` and `WITH CHECK`, per the constitution's Principle V
requirement. None introduces a new isolation axis — all three reuse the exact
`current_tenant_id()`/`current_membership_id()`/`current_member_role()` mechanism R2.0 built and
008 already extended (Constitution Check, plan.md).
