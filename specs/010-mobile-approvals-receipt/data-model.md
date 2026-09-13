# Data Model: Mobile Approvals and Delivery Receipt

**Feature**: 010-mobile-approvals-receipt
**Date**: 2026-09-13
**Scope**: `approval_step` is reused completely unchanged — nothing in this document alters its
schema, RLS, or state machine (research.md R2). `purchase_request` gains new status values and new
columns; `delivery_quality_issue` is a new table. Migration filenames are sketches; SQL is
intentionally not written in this artifact, per this project's own data-model.md convention.

## Shared Conventions

- Tenant scope comes from the verified JWT claim, never from path, query, or header input.
- Cross-tenant references return `404 not_found`, never `403 forbidden`.
- All tenant-scoped tables carry `tenant_id`, `ENABLE` and `FORCE` RLS, and a policy with both
  `USING` and `WITH CHECK`.
- Every FK from one tenant-scoped table to another is a composite `(tenant_id, id)` foreign key,
  continuing R2.0/R2.1/R2.2's convention.
- Neither change in this document introduces a money field — Constitution Principle VII is
  satisfied trivially here.

## `purchase_request` (extended, not replaced)

Two new enum values on the existing `purchase_request_status` type, and new columns for the
delivery half of the lifecycle (research.md R1).

**Status**: `draft | submitted | approved | rejected | withdrawn` (unchanged) `| ordered |
delivered` (new). `ordered` and `delivered` are reachable only from `approved` — there is no path
from `draft`/`submitted`/`rejected`/`withdrawn` directly to either, and no path backward out of
`delivered`. This feature does not add a distinct "place the order" human action (spec.md scope):
an approved request is considered `ordered` the moment a human approved it, so in practice the
mobile client transitions `approved -> ordered` automatically alongside approval, and a branch
member's own action is what transitions `ordered -> delivered`.

| Field (new) | Type | Required | Notes |
|---|---:|:---:|---|
| `delivered_at` | timestamptz | no | Stamped on `ordered -> delivered`; null before then |
| `delivery_confirmed_by_membership_id` | uuid | no | Composite FK -> `membership(tenant_id, id)`; who confirmed delivery — null before `delivered` |
| `has_delivery_discrepancy` | boolean | yes | Default `false`; `true` when any line's received quantity was less than ordered |

Per-line received quantity lives on `purchase_request_line` (below), not as a single aggregate
here — a discrepancy is a line-level fact (spec.md Acceptance Scenario 2, Story 2), and
`has_delivery_discrepancy` is a derived summary flag for fast filtering/display, not the source of
truth.

**Migration note for implementation**: `ALTER TYPE purchase_request_status ADD VALUE` cannot be
used in the same transaction block as a statement that references the new value — this is a
standing PostgreSQL restriction, not specific to this project. Add the two new enum values in their
own migration file with no other statement in it, and reference `'ordered'`/`'delivered'` only in a
*later* migration (or later application code), the same discipline this project already applies to
forward-only migrations generally.

## `purchase_request_line` (extended, not replaced)

One new column for the per-line delivery fact.

| Field (new) | Type | Required | Notes |
|---|---:|:---:|---|
| `quantity_received` | numeric(18,6) | no | Null until the parent request is `delivered`; `check (quantity_received is null or quantity_received >= 0)` |

A line's own discrepancy is `quantity_received < quantity` once both are set — computed at read
time (mirroring how `has_incomplete_estimate` is a computed-and-cached flag at the parent level
while the per-line comparison itself is not separately stored), not a second stored boolean per
line.

## `delivery_quality_issue` (new)

A report of a problem with a delivered request, distinct from the plain quantity-shortfall fact
`purchase_request`/`purchase_request_line` already capture (research.md R1; spec.md Key Entities).

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `purchase_request_id` | uuid | yes | Composite FK -> `purchase_request(tenant_id, id)`, `on delete cascade` |
| `reported_by_membership_id` | uuid | yes | Composite FK -> `membership(tenant_id, id)` |
| `description` | text | yes | Required — a quality issue always needs a description; a photo is optional (spec.md FR-007) |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- `check (char_length(description) > 0)` — an empty description is not a real report.
- The parent `purchase_request` MUST be `delivered` at the time of insert (spec.md FR-006) —
  enforced at the service layer against the row's current status, the same "application-layer
  authorization/precondition, database only isolates" pattern `approval_step`'s own migration
  already documents for its assignee/owner write check, not a database trigger.
- Index on `(tenant_id, purchase_request_id)`.

No `status`/lifecycle of its own this release — a quality issue is a durable report, not a ticket
with its own resolution workflow (spec.md scope: reporting, not triage). A future release could add
one without touching this table's existing shape.

## `delivery_quality_issue_photo` (new)

One row per photo attached to a quality issue — a many-to-one child, not a single photo column on
the issue itself, so FR-007's "zero or more photos" is a natural cardinality rather than an
artificial limit.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `delivery_quality_issue_id` | uuid | yes | Composite FK -> `delivery_quality_issue(tenant_id, id)`, `on delete cascade` |
| `storage_path` | text | yes | Path within the `quality-issue-photos` bucket (research.md R3) — server-allocated, never client-supplied |
| `created_at` | timestamptz | yes | Default `now()` |

## RLS Summary

- `purchase_request`'s new columns and `purchase_request_line`'s new column ride the parent
  table's own existing branch-scoped RESTRICTIVE policy verbatim (008-requests-approvals) — they
  are columns on an already-governed row, not a new isolation surface. No new policy is needed.
- `delivery_quality_issue` and `delivery_quality_issue_photo` derive their visibility from their
  parent `purchase_request` via an `EXISTS` join, mirroring exactly how `purchase_request_line`'s
  own RESTRICTIVE policy already re-derives the parent's visibility rather than duplicating
  `branch_id` onto the child table (008's data-dictionary entry for `PurchaseRequestLine`). Both
  new tables still carry their own `tenant_id` and `ENABLE`+`FORCE` RLS per the blanket
  constitution requirement — the derived-visibility policy is *in addition to*, not instead of,
  tenant isolation.
- Write access to `delivery_quality_issue`/`_photo`: insert-only for `authenticated` (no
  `UPDATE`/`DELETE` surface this release — a filed quality issue is not editable or retractable,
  the same insert-only posture `low_stock_report` already established for its own "raw signal"
  data, revoking `UPDATE`/`DELETE` explicitly rather than relying on a RESTRICTIVE policy alone,
  matching 009's own review-fix precedent).
- `quality-issue-photos` Storage bucket: identical tenant-isolation-by-object-path policy to
  `quotation-documents` (research.md R3) — `storage.foldername(name)`'s tenant segment must match
  `current_tenant_id()`.

## State Transition Summary

```text
draft -> submitted -> approved -> ordered -> delivered
              \-> rejected
       \-> withdrawn
```

- `approved -> ordered`: automatic, alongside the existing approval decision (no new human action
  this release — spec.md scope).
- `ordered -> delivered`: a branch member's delivery-confirmation action (spec.md Story 2),
  stamping `delivered_at`, `delivery_confirmed_by_membership_id`, per-line `quantity_received`, and
  the derived `has_delivery_discrepancy` flag.
- `delivery_quality_issue` rows may only be created against a request already in `delivered`
  (service-layer check, spec.md FR-006) — they do not themselves transition `purchase_request`'s
  status further.
