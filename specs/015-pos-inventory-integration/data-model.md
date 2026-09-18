# Data Model: POS & Inventory Integration — Usage Signals (015)

Three new tenant-scoped tables. All carry `tenant_id`, `ENABLE + FORCE` row-level security, and
policies with both `USING` and `WITH CHECK` (Constitution Principle V / non-negotiable #1). Every
cross-module foreign key pins to a `(tenant_id, id)` composite key, never a bare `id` — the pattern
this codebase has had to retrofit five times already this program; new tables get it from the
first migration.

## `pos_connection`

One workspace's authorized link to one external POS/inventory account. Mirrors
`accounting_connection`'s shape exactly (014).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` on delete cascade | |
| `provider` | enum `pos_provider` (`square`) | Single value this release; the column exists so a second provider is additive, not a migration |
| `status` | enum `pos_connection_status` (`active`, `needs_reauth`, `disconnected`) | |
| `external_account_id` | text, not null | Square merchant/location id |
| `external_account_name` | text, not null | Display name shown in the connection-status UI |
| `access_token` | text, encrypted via `shared/token_crypto.py` | Read/written only from a `service_role` session |
| `refresh_token` | text, encrypted | Same as above |
| `connected_by` | uuid, FK → `membership(tenant_id, id)` | Owner who authorized the connection |
| `connected_at` | timestamptz, not null | |
| `last_synced_at` | timestamptz, nullable | Updated on every successful sync completion |
| `disconnected_at` | timestamptz, nullable | Set on disconnect; row is never deleted (FR-001, SC-005 data survives disconnect) |

Constraints:
- `unique (tenant_id) where disconnected_at is null` — at most one active connection per
  workspace, enforced at the data layer, matching `accounting_connection`'s own uniqueness rule.
- RLS: `select` for any authenticated member of the tenant; `insert`/`update` (disconnect,
  status transition) restricted to `current_member_role() = 'owner'` (FR-001's "explicit owner
  authorization"); no `delete` policy — disconnect is a status/timestamp update, never a row
  deletion, consistent with `accounting_connection`.

## `synced_product_signal`

The most recent sales-velocity and/or stock-on-hand figures for one external Square catalog item,
as of the last successful sync. Exists independent of whether it has been matched yet (FR-006's
"ambiguous match left unresolved" requires the row to still be visible for manual review).

**Reconnect dedup design (fixes an analysis-time defect, SC-005)**: uniqueness is keyed on
`(tenant_id, external_item_id)` alone, **not** `pos_connection_id`. `pos_connection_id` is a
"most recently synced via" pointer, updated in place on every sync — not the row's origin. This
is deliberate: if it were part of the uniqueness key, a disconnect followed by a reconnect (which
creates a *new* `pos_connection` row per data-model.md's own `pos_connection` design — the old row
is never reactivated) would cause the very next sync to insert a second signal row for the same
external item under the new connection id, alongside the original row still pointing at the
disconnected connection — exactly the duplicate SC-005 forbids. Keying on `external_item_id`
alone means a reconnect's first sync updates the existing row in place, and any existing
`pos_product_match` (which references `synced_product_signal_id`, not `pos_connection_id`)
survives the reconnect untouched, with no re-matching needed.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` on delete cascade | |
| `pos_connection_id` | uuid, FK → `pos_connection(tenant_id, id)` | Most-recently-synced-via connection; updated on every sync, not immutable (see dedup note above) |
| `external_item_id` | text, not null | Square catalog object id |
| `external_item_name` | text, not null | For display in the manual-match review screen |
| `stock_on_hand` | numeric, nullable | Null when the connection has no inventory tracking for this item (edge case: snapshot-only provider) |
| `stock_synced_at` | timestamptz, nullable | Drives the staleness label (FR-004, SC-003) |
| `sales_velocity_per_day` | numeric, nullable | Trailing 30-day average, recomputed each sync (research.md R5) |
| `velocity_window_days` | integer, not null, default 30 | The target window length; stored alongside the figure per Constitution Principle I |
| `velocity_window_days_observed` | integer, nullable | How many days of actual transaction history the current figure is based on. When less than `velocity_window_days`, the figure is provisional (FR-013) — the frontend MUST show this distinction, never presenting a partial-window figure as equivalent to a full one |
| `velocity_computed_at` | timestamptz, nullable | |
| `created_at` | timestamptz, not null, default now() | |
| `updated_at` | timestamptz, not null, default now() | Bumped on every sync touching this row |

Constraints:
- `unique (tenant_id, external_item_id)` — one row per external item per tenant, surviving a
  disconnect/reconnect cycle; a resync (via the same or a newly reconnected connection) upserts
  by this key, never duplicates (SC-005).
- RLS: `select` for any authenticated member; `insert`/`update` only from the worker's
  tenant-scoped session (`current_member_role() is null`, the established worker-write
  convention, research.md R6) — no member-facing mutation endpoint writes this table directly.

## `pos_product_match`

The link between a `synced_product_signal` and a `workspace_product`, once confidently matched.
Same superseded-by-insert-then-delete shape as `purchase_bill_match` (014) — no `UPDATE` grant.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid, PK | |
| `tenant_id` | uuid, FK → `tenant(id)` on delete cascade | |
| `synced_product_signal_id` | uuid, FK → `synced_product_signal(tenant_id, id)` | |
| `workspace_product_id` | uuid, FK → `workspace_product(tenant_id, id)` | |
| `match_method` | enum `match_method` (`automatic`, `manual`) | Reuses the enum type 014 already created |
| `matched_by` | uuid, nullable, FK → `membership(tenant_id, id)` | Null for automatic; required for manual |
| `matched_at` | timestamptz, not null, default now() | |
| `confidence` | numeric, nullable | Score from the reused similarity pipeline (research.md R4); null for manual matches |

Constraints:
- `unique (tenant_id, synced_product_signal_id)` and `unique (tenant_id, workspace_product_id)` —
  1:1 both directions, identical rule to `purchase_bill_match`.
- `check ((match_method = 'manual') = (matched_by is not null))` — same provenance rule as
  `purchase_bill_match`.
- RLS: `select` for any authenticated member; two permissive `insert` policies (automatic from the
  worker's tenant-scoped session, manual from an owner/buyer confirming a match,
  `current_member_role() in ('owner', 'buyer')`); `delete` split the same way (worker may delete
  only its own automatic matches on resync; owner/buyer may delete any match to unlink); no
  `update` policy at all.

## Relationships

```text
pos_connection (1) ──< synced_product_signal (many)
synced_product_signal (1) ──? pos_product_match (0 or 1) >── workspace_product (1)
```

A `synced_product_signal` with no `pos_product_match` row is an unmatched item, always visible in
a "needs review" list (FR-006) — never silently dropped.

## Audit events

Every connect, disconnect, and sync attempt (started/completed/failed) writes an `audit_event` row
via the existing `shared/audit.py` writer, matching the convention already established by
`ingestion` and `accounting` — no new audit mechanism.

## Reused, unchanged tables

- `workspace_product` — the match target; no schema change required.
- `membership` — `connected_by`/`matched_by` FKs, as above.
- `tenant` — standard cascade-on-delete parent for every new table.

## RLS verification

Extends the existing canonical `test_tenant_isolation.py` file with the three new tables (same
convention as T034 in 013 and its 014 equivalent) — not a new isolation test file.
