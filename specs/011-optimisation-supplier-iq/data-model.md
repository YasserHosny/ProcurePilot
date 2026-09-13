# Phase 1 Data Model: Optimisation and Supplier IQ

R2.4 extends existing smart compare and mobile outcome data. It does not create a second price,
matching, purchase, or alert source of truth.

## New persisted tables

### `supplier_commercial_term`

Versioned tenant-scoped commercial rules for one supplier.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `supplier_id` | uuid | Required composite FK -> Supplier `(tenant_id, id)` |
| `effective_from` | timestamptz | Required |
| `effective_to` | timestamptz | Nullable; null means current until superseded |
| `minimum_order_value_amount` | numeric(18,4) | Nullable money amount |
| `minimum_order_value_currency` | text | Required exactly when MOV amount is set |
| `delivery_fee_amount` | numeric(18,4) | Nullable money amount |
| `delivery_fee_currency` | text | Required exactly when delivery fee amount is set |
| `free_delivery_threshold_amount` | numeric(18,4) | Nullable money amount |
| `free_delivery_threshold_currency` | text | Required exactly when threshold amount is set |
| `quantity_tiers` | jsonb | Array of `{workspace_product_id?, min_quantity, unit_price_amount, unit_price_currency}` |
| `rule_version` | text | Required, for example `supplier-commercial-terms-v1` |
| `created_by_membership_id` | uuid | Required composite FK -> Membership `(tenant_id, id)` |
| `created_at` | timestamptz | Audit field |

Constraints:

- Money pairs are null together or populated together.
- `effective_to is null or effective_to > effective_from`.
- `quantity_tiers` entries are validated by the API before insert.
- RLS: owner/buyer may insert; authenticated tenant members may select visible supplier terms.

### `supplier_scorecard_snapshot`

Cached deterministic scorecard result for a supplier and metric window.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `supplier_id` | uuid | Required composite FK -> Supplier `(tenant_id, id)` |
| `window_start` | date | Required |
| `window_end` | date | Required |
| `rule_version` | text | Required |
| `metrics` | jsonb | Required metric values, sample counts, source ids, confidence flags |
| `risk_score` | jsonb | Required weighted total and sub-scores |
| `source_counts` | jsonb | Required counts by source table |
| `computed_at` | timestamptz | Required |
| `computed_by_membership_id` | uuid | Nullable; set for explicit user-triggered recompute |

Constraints:

- Unique `(tenant_id, supplier_id, window_start, window_end, rule_version)`.
- `window_end >= window_start`.
- Snapshots are recomputable caches, not user-authored truth.
- RLS: authenticated tenant members may select; owner/buyer may recompute/insert through service.

## Extended persisted table

### `basket_split_job`

R2.4 keeps the existing table and extends its JSON snapshots rather than introducing a new job
table.

Existing fields remain. The request snapshot is extended to include:

- `supplier_ids`: 2 to 10 selected supplier ids.
- `hard_constraints`: MOV, free-delivery threshold, delivery fee, quantity tiers, supplier
  exclusions, urgency.
- `soft_weights`: preferred supplier, risk tolerance, lead time, quality, price competitiveness.
- `rule_version`: optimiser rule version used for replay.

The `result` payload is extended to include:

- `allocation`
- `total_landed_cost`
- `single_supplier_baselines`
- `applied_constraints`
- `violated_constraints`
- `risk_notes`
- `confidence`
- `valid_until`
- `source_landed_cost_ids`

## Response-only entities

### `SupplierScorecard`

Returned by `GET /suppliers/{supplier_id}/scorecard`.

Fields: `supplier`, `window_start`, `window_end`, `metrics`, `risk_score`, `source_counts`,
`confidence`, `insufficient_evidence`, `computed_at`, and `rule_version`.

### `AnomalySignal`

Live-computed extension of the existing `Alert` response.

Fields: `id`, `kind`, `workspace_product_id`, `supplier_id`, `severity`, `confidence`, `evidence`,
`action`, `valid_until`, `created_from_current_data_at`, and `dismissed`.

## RLS and audit requirements

Both new tables carry `tenant_id`, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and
policies with `USING` and `WITH CHECK`. Cross-tenant references resolve as not found. Audit events
are append-only and must never be updated or deleted.
