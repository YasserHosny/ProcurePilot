# Phase 1 Data Model: Smart Compare + Intelligence

**Feature**: `005-smart-compare-intelligence`  
**Date**: 2026-08-21  
**Scope**: Planning artifact only. Migration SQL is intentionally not written here.

## Summary

`Offer`, `Recommendation`, `PriceHistoryPoint`, and `Alert` are response shapes derived at request
time. They are not new tables and do not become a second source of price, match or alert truth.

Two real tables are introduced:

- `basket_split_job`: tracks async two-supplier optimisation work.
- `alert_dismissal`: tracks which live-computed alert fingerprints a human dismissed.

## Response-Only Entities

### Offer

Derived from `match_decision`, `landed_cost`, `quotation_line`, `quotation`, `supplier`,
`workspace_product`, and `pack_definition`.

| Field | Type | Required | Source / Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Stable response id, use current `landed_cost.id`. |
| `workspace_product_id` | uuid | yes | `match_decision.matched_workspace_product_id`. |
| `supplier_id` | uuid | yes | `quotation.supplier_id`. |
| `supplier_name` | text | yes | `supplier.name`. |
| `quotation_line_id` | uuid | yes | `landed_cost.quotation_line_id`. |
| `match_decision_id` | uuid | yes | `landed_cost.match_decision_id`. |
| `landed_cost` | Money | yes | Projected total using chunk 4.4 rule version and stored replay inputs. |
| `normalised_unit_price` | Money | yes | Projected total divided by requested base quantity. |
| `requested_quantity` | numeric string | yes | Caller-supplied quantity. |
| `base_unit` | text | yes | `landed_cost.base_unit`. |
| `lead_time_days` | integer nullable | no | `supplier.lead_time_days`. |
| `reliability_score` | decimal string nullable | no | `supplier.reliability_score`. |
| `stock_signal` | enum nullable | no | Always null in this chunk; no source data exists. |
| `match_confidence` | decimal string | yes | `match_decision.confidence`. |
| `valid_from` | timestamptz | yes | `landed_cost.valid_from`. |
| `valid_to` | timestamptz nullable | no | `landed_cost.valid_to`. |
| `is_expired` | boolean | yes | `valid_to < now()` when `valid_to` is not null. |
| `rule_version` | text | yes | `landed_cost.rule_version`. |
| `recorded_at` | timestamptz | yes | `landed_cost.recorded_at`. |

### Recommendation

Computed for one product and requested quantity. Not stored.

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `recommended_offer_id` | uuid | yes | References an offer in the same response. |
| `score` | decimal string | yes | Weighted score rounded to 4 decimals. |
| `confidence` | enum | yes | `high`, `medium`, or `low`. |
| `valid_from` | timestamptz | yes | Recommended offer validity start. |
| `valid_to` | timestamptz nullable | no | Recommended offer validity end. |
| `risk_notes` | string array | yes | Fixed risk codes. Empty when no risk applies. |
| `evidence` | object | yes | Structured score components, weights, margin, and tie-break evidence. |

### PriceHistoryPoint

Derived from `landed_cost` history. Not stored.

| Field | Type | Required | Source / Notes |
|---|---:|---:|---|
| `landed_cost_id` | uuid | yes | Source `landed_cost.id`. |
| `workspace_product_id` | uuid | yes | Matched product id. |
| `supplier_id` | uuid | yes | Joined quotation supplier. |
| `supplier_name` | text | yes | `supplier.name`. |
| `recorded_at` | timestamptz | yes | Record-time x-axis. |
| `valid_from` | timestamptz | yes | Price valid-time start. |
| `valid_to` | timestamptz nullable | no | Price valid-time end. |
| `normalised_unit_price` | Money | yes | `total_amount / normalised_base_quantity`. |
| `landed_cost_total` | Money | yes | Stored `landed_cost.total_amount/currency`. |
| `quantity` | numeric string | yes | Stored `landed_cost.quantity`. |
| `base_unit` | text | yes | Stored `landed_cost.base_unit`. |

### Alert

Alert conditions are computed live. Only dismissals are stored.

| Field | Type | Required | Notes |
|---|---:|---:|---|
| `id` | text | yes | Deterministic fingerprint. |
| `kind` | enum | yes | `recommended_price_expiring`, `preferred_supplier_offer_disappeared`, `price_swing`. |
| `workspace_product_id` | uuid | yes | Product concerned. |
| `supplier_id` | uuid nullable | no | Supplier concerned, when applicable. |
| `severity` | enum | yes | `info`, `warning`, `critical`. |
| `evidence` | object | yes | Current condition facts only. |
| `action` | enum | yes | `compare_product`, `review_supplier`, `view_price_history`. |
| `created_from_current_data_at` | timestamptz | yes | Request evaluation time, not persisted condition time. |
| `dismissed` | boolean | yes | False for `GET /alerts`; true only if returned after dismissal in mutation response. |

## Real Tables

### `basket_split_job`

| Column | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Primary key, default `gen_random_uuid()`. |
| `tenant_id` | uuid | yes | FK to `tenant(id)`, RLS scope. |
| `requested_by` | uuid | yes | FK to `membership(id)`. |
| `supplier_ids` | uuid[] | yes | Exactly two unique supplier ids. |
| `items` | jsonb | yes | Array of `{workspace_product_id, quantity}`; stored to make solve replayable. |
| `status` | enum | yes | `queued`, `running`, `completed`, `failed`. |
| `result` | jsonb nullable | no | Completed allocation or infeasible result. |
| `error` | jsonb nullable | no | Worker/system failure only. |
| `created_at` | timestamptz | yes | Default `now()`. |
| `started_at` | timestamptz nullable | no | Worker sets on start. |
| `completed_at` | timestamptz nullable | no | Worker sets on completion/failure. |

Result JSON shape:

- `feasible`: boolean.
- `allocation`: array of supplier allocation objects.
- `total_landed_cost`: Money or null.
- `single_supplier_baselines`: array comparing all-items-with-supplier A/B totals when feasible.
- `infeasible_items`: array of product-level blockers.
- `solver_version`: text.
- `computed_at`: timestamptz.

RLS: tenant-scoped with `ENABLE` + `FORCE`, `USING` and `WITH CHECK`.

### `alert_dismissal`

| Column | Type | Required | Notes |
|---|---:|---:|---|
| `id` | uuid | yes | Primary key, default `gen_random_uuid()`. |
| `tenant_id` | uuid | yes | FK to `tenant(id)`, RLS scope. |
| `alert_fingerprint` | text | yes | Deterministic alert id from current condition. |
| `kind` | text | yes | Alert kind at dismissal time. |
| `workspace_product_id` | uuid | yes | Product concerned. |
| `supplier_id` | uuid nullable | no | Supplier concerned, if any. |
| `dismissed_by` | uuid | yes | FK to `membership(id)`. |
| `dismissed_at` | timestamptz | yes | Default `now()`. |

Constraints and indexes:

- Unique `(tenant_id, alert_fingerprint)`.
- Index `(tenant_id, kind, workspace_product_id)`.

RLS: tenant-scoped with `ENABLE` + `FORCE`, `USING` and `WITH CHECK`.

## Migration Sketch

File names only; SQL is out of scope for this planning task.

- `supabase/migrations/20260821000028_basket_split_alert_dismissal.sql`
- `supabase/migrations/20260821000029_basket_split_alert_dismissal_rls.sql`

The RLS migration should follow the generated-loop pattern from
`20260819000016_catalogue_rls.sql`, `20260819000021_quotation_rls.sql`, and
`20260819000027_matching_rls.sql`.
