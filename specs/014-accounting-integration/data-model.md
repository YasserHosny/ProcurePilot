# Phase 1 Data Model: Accounting Integration & Reconciliation Foundation

All new tables: `ENABLE + FORCE` row-level security (Constitution Principle V, non-negotiable).
Every foreign key into an existing tenant-scoped table pins to that table's own `(tenant_id, id)`
composite key, not a bare `id` — see research.md R7 for the one existing table (`purchase_record`)
that needs a companion migration to gain that composite key before this feature can follow the
same convention consistently.

## Companion migration: `purchase_record` composite key

```sql
alter table purchase_record
  add constraint purchase_record_tenant_id_key unique (tenant_id, id);
```

## `accounting_connection`

One workspace's authorized link to one external accounting account (spec: "Accounting
Connection"). Exactly one connection per tenant for this release.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` | |
| `provider` | `accounting_provider` enum (`quickbooks`) | Single value for this release; the enum shape (not a bare text column) is what makes adding a second provider in R3.3 a data change, not a schema migration |
| `realm_id` | text | QuickBooks's own company identifier — opaque, provider-specific |
| `display_name` | text | The connected company's name, as QuickBooks reports it, shown in the UI per FR-002 |
| `access_token` | text, encrypted at rest | Short-lived (~1 hour); refreshed at the start of every sync, never cached across runs (research.md R4) |
| `refresh_token` | text, encrypted at rest | Long-lived (~100 days per QuickBooks) |
| `status` | `accounting_connection_status` enum (`active`, `needs_reauth`, `disconnected`) | FR-002 |
| `connected_by` | uuid, FK → `membership(tenant_id, id)` | Owner who authorized the connection (FR-003) |
| `connected_at` | timestamptz | |
| `last_synced_at` | timestamptz, nullable | Null until the first sync completes |
| `disconnected_at` | timestamptz, nullable | Set on disconnect; row is not deleted (FR-004) — a disconnected connection's history remains queryable |

Constraint: `unique (tenant_id) where status <> 'disconnected'` — at most one non-disconnected
connection per tenant at a time (a tenant may reconnect after disconnecting, creating a new row,
per the spec's own edge case that a second account's data must not merge with the first's).

RLS: `SELECT` for any authenticated member (read visibility, matching FR-002's "shown at all
times" requirement); `INSERT`/`UPDATE` (connect, disconnect, status transitions) restricted to
`owner` (FR-003).

## `synced_vendor`

QuickBooks's Vendor entity as of the most recent sync (spec: feeds "Synced Bill" matching, not
itself a spec-named entity but needed to persist the vendor↔supplier link from research.md R3).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` | |
| `connection_id` | uuid, FK → `accounting_connection(tenant_id, id)` | |
| `provider_vendor_id` | text | QuickBooks `Vendor.Id`, unique per connection |
| `display_name` | text | |
| `matched_supplier_id` | uuid, nullable, FK → `supplier(tenant_id, id)` | Set on first successful name match (R3); persisted so later syncs don't re-match by name every time |
| `created_at` / `updated_at` | timestamptz | |

Constraint: `unique (tenant_id, connection_id, provider_vendor_id)`.

RLS: `SELECT` for any authenticated member; `INSERT`/`UPDATE` only via the sync worker's
service-role path (no direct member mutation — this table is sync-derived, not user-edited).

## `synced_bill`

One supplier bill as recorded by the connected accounting system at the time of the most recent
sync (spec: "Synced Bill").

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` | |
| `connection_id` | uuid, FK → `accounting_connection(tenant_id, id)` | |
| `provider_bill_id` | text | QuickBooks `Bill.Id`, unique per connection — the reference used to detect updates on re-sync (spec Acceptance Scenario 2.4) |
| `vendor_id` | uuid, FK → `synced_vendor(tenant_id, id)` | |
| `matched_supplier_id` | uuid, nullable, FK → `supplier(tenant_id, id)` | Denormalized from `vendor_id`'s own match for query convenience; kept in sync when the vendor's match changes |
| `amount` | numeric(18,4) | FR-005, Principle VII |
| `currency` | text, FK → `supported_currency(code)` | FR-005, Principle VII — never a bare number |
| `bill_date` | date | Used for the 14-day matching window (FR-007) and the 30-day discrepancy grace period (FR-010) |
| `provider_status` | `synced_bill_status` enum (`open`, `paid`, `void`) | As QuickBooks reports it (FR-005) |
| `created_at` / `updated_at` | timestamptz | `updated_at` advances on every sync that changes any field — proves the "reflects the update" requirement (spec Acceptance Scenario 2.4) without a separate history table for v1 |

Constraint: `unique (tenant_id, connection_id, provider_bill_id)`.

RLS: `SELECT` for any authenticated member; `INSERT`/`UPDATE` only via the sync worker's
service-role path.

## `purchase_bill_match`

A link between a `synced_bill` and an existing `purchase_record` (spec: "Purchase-Bill Match").

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` | |
| `synced_bill_id` | uuid, FK → `synced_bill(tenant_id, id)` | |
| `purchase_record_id` | uuid, FK → `purchase_record(tenant_id, id)` | Requires the companion migration above |
| `match_method` | `match_method` enum (`automatic`, `manual`) | FR-007 (automatic) vs. a reviewer confirming a match while resolving a discrepancy (FR-011) |
| `matched_by` | uuid, nullable, FK → `membership(tenant_id, id)` | Null for `automatic`; the resolving member for `manual` |
| `matched_at` | timestamptz | |

Constraints: `unique (tenant_id, synced_bill_id)` (a bill has at most one match) and
`unique (tenant_id, purchase_record_id)` (a purchase record has at most one match) — enforces the
spec's own "equally-qualifying candidates are left unmatched" rule (FR-007) at the data layer,
not just in application logic: a 1:1 relationship cannot silently become 1:many.

RLS: `SELECT` for any authenticated member; `INSERT` via the sync worker (automatic) or an
`owner`/`buyer` resolving a discrepancy (manual, FR-011); no `UPDATE`/`DELETE` — a match is
superseded by inserting a new row and deleting the old one inside the same transaction that
changes it, keeping the "how was this decided" trail simple (Principle I's provenance spirit)
rather than allowing silent in-place correction.

## `reconciliation_discrepancy`

A flagged exception needing human review (spec: "Reconciliation Discrepancy").

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` | |
| `discrepancy_type` | `discrepancy_type` enum (`amount_mismatch`, `unmatched_bill`, `unmatched_purchase`) | FR-010 |
| `synced_bill_id` | uuid, nullable, FK → `synced_bill(tenant_id, id)` | Set for `amount_mismatch` and `unmatched_bill`; null for `unmatched_purchase` |
| `purchase_record_id` | uuid, nullable, FK → `purchase_record(tenant_id, id)` | Set for `amount_mismatch` and `unmatched_purchase`; null for `unmatched_bill` |
| `status` | `discrepancy_status` enum (`open`, `resolved`) | FR-011 |
| `detected_at` | timestamptz | When the discrepancy first appeared (recomputed each sync, not reset if it persists — see below) |
| `resolved_by` | uuid, nullable, FK → `membership(tenant_id, id)` | FR-011 |
| `resolved_at` | timestamptz, nullable | FR-011 |
| `resolution_note` | text, nullable | FR-011 |

Constraint: `check ((discrepancy_type = 'unmatched_bill' and synced_bill_id is not null and
purchase_record_id is null) or (discrepancy_type = 'unmatched_purchase' and purchase_record_id is
not null and synced_bill_id is null) or (discrepancy_type = 'amount_mismatch' and synced_bill_id
is not null and purchase_record_id is not null))` — the three discrepancy shapes are mutually
exclusive by construction, not just by convention.

**Re-evaluation on sync** (spec Acceptance Scenario 3.4 — a resolved discrepancy must not stay
silently resolved against stale data): each sync recomputes the current discrepancy set from
`synced_bill`/`purchase_bill_match`/`purchase_record` state. If a previously `resolved` row's
underlying condition still holds (e.g. the amount mismatch persists unchanged), it stays
`resolved` untouched. If the underlying records changed since resolution (the bill or purchase
record's `updated_at` is newer than the discrepancy's `resolved_at`), the existing row is
reopened (`status` reset to `open`, resolution fields cleared) rather than a duplicate row being
created — preserves one discrepancy identity across its full open → resolved → reopened
lifecycle instead of accumulating look-alike rows.

RLS: `SELECT` for any authenticated member; `INSERT` via the sync worker's service-role path
(detecting new discrepancies); `UPDATE` restricted to `owner`/`buyer` and only for the resolution
fields (`status`, `resolved_by`, `resolved_at`, `resolution_note`) — enforced by a policy `WITH
CHECK` mirroring the column-scoped mutation pattern already used elsewhere in this codebase
(e.g. `digest_subscription`'s member-scoped update), not by application-layer trust alone.

## New enums

```sql
create type accounting_provider as enum ('quickbooks');
create type accounting_connection_status as enum ('active', 'needs_reauth', 'disconnected');
create type synced_bill_status as enum ('open', 'paid', 'void');
create type match_method as enum ('automatic', 'manual');
create type discrepancy_type as enum ('amount_mismatch', 'unmatched_bill', 'unmatched_purchase');
create type discrepancy_status as enum ('open', 'resolved');
```

## Audit events (new)

- `accounting.connection_created` / `accounting.connection_disconnected`
- `accounting.sync_started` / `accounting.sync_completed` / `accounting.sync_failed`
- `accounting.discrepancy_resolved`

## Tenant isolation test coverage

Extends the canonical `apps/api/tests/integration/test_tenant_isolation.py` (same convention as
013-automated-ingestion's T034) with the five new tables, plus the
`test_rls_is_enabled_and_forced_on_every_tenant_scoped_table` meta-test's allowlist — not a new,
separate isolation test file.
