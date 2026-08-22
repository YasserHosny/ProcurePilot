# Data Model: Value Proof + Launch Readiness

**Feature**: 006-value-proof-launch
**Date**: 2026-08-21
**Scope**: New entities only. Migration filenames are sketches; SQL is intentionally not written
in this artifact.

## Shared Conventions

- Tenant scope comes from the verified JWT claim, never from path, query, or header input.
- Cross-tenant references return `404 not_found`, never `403 forbidden`.
- Money is stored as `numeric(18,4)` amount plus explicit `supported_currency(code)`.
- API money shape is always `Money { amount, currency }` with amount as a decimal string.
- Decimal quantities use `numeric(18,6)`.
- All tenant-scoped tables carry `tenant_id`, `ENABLE` and `FORCE` RLS, and a policy with both
  `USING` and `WITH CHECK`.

## Enumerations

| Enum | Values |
|---|---|
| `saving_record_status` | `pending`, `verified` |
| `baseline_policy` | `last_paid`, `rolling_average_6m`, `none_available` |
| `purchase_delivery_result` | `ordered`, `partially_delivered`, `delivered`, `cancelled`, `disputed` |
| `export_job_status` | `queued`, `running`, `completed`, `failed` |
| `export_format` | `xlsx`, `pdf` |
| `billing_account_status` | `active`, `past_due`, `cancelled` |
| `plan_status` | `active`, `archived` |

## `purchase_record`

Factual outcome capture: what was ordered, from whom, at what price, and with what delivery
result.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)`, RLS isolation boundary |
| `workspace_product_id` | uuid | yes | FK -> `workspace_product(id)` |
| `supplier_id` | uuid | no | FK -> `supplier(id)`; nullable when outcome is recorded without a known supplier row |
| `quotation_line_id` | uuid | no | FK -> `quotation_line(id)`; evidence link when outcome followed a quoted line |
| `match_decision_id` | uuid | no | FK -> `match_decision(id)`; evidence link when outcome followed a confirmed match |
| `landed_cost_id` | uuid | no | FK -> `landed_cost(id)`; evidence link to the compared offer when present |
| `recorded_by` | uuid | yes | FK -> `membership(id)` |
| `quantity` | numeric(18,6) | yes | Must be `> 0` |
| `base_unit` | text | yes | FK -> `supported_base_unit(code)` |
| `unit_price_amount` | numeric(18,4) | yes | Actual paid unit price |
| `unit_price_currency` | text | yes | FK -> `supported_currency(code)` |
| `total_paid_amount` | numeric(18,4) | yes | Actual total paid for the recorded quantity |
| `total_paid_currency` | text | yes | FK -> `supported_currency(code)` |
| `delivery_result` | `purchase_delivery_result` | yes | Outcome state |
| `ordered_at` | timestamptz | no | Real-world order time, if known |
| `delivered_at` | timestamptz | no | Real-world delivery time, if known |
| `recorded_at` | timestamptz | yes | Default `now()` |
| `notes` | text | no | Internal note; not a substitute for evidence links |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()`; updates allowed only while paired saving is pending |

Constraints and indexes:

- Check `unit_price_currency = total_paid_currency`; no currency conversion in Phase 1.
- Check `delivered_at is null or ordered_at is null or delivered_at >= ordered_at`.
- Index `(tenant_id, workspace_product_id, recorded_at desc)`.
- Index `(tenant_id, supplier_id, recorded_at desc)`.

RLS:

- Tenant-scoped uniform policy.
- Owner/buyer may insert and update pending outcomes through API RBAC.
- Other active roles may read.
- Once the paired `saving_record` is verified, application code must refuse edits because evidence
  would otherwise drift from the verified claim.

## `saving_record`

Computed savings-ledger row paired to one purchase outcome. Values are captured at record time;
verification later changes only status metadata.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)` |
| `purchase_record_id` | uuid | yes | Unique FK -> `purchase_record(id)` |
| `workspace_product_id` | uuid | yes | FK -> `workspace_product(id)` for filtering and ledger display |
| `supplier_id` | uuid | no | FK -> `supplier(id)` copied from purchase for filtering |
| `status` | `saving_record_status` | yes | Default `pending` |
| `baseline_policy` | `baseline_policy` | yes | Actual policy used at record time |
| `baseline_source_landed_cost_ids` | uuid[] | yes | Source `landed_cost` rows from chunk 4.5 price history summary; empty only for `none_available` |
| `baseline_unit_price_amount` | numeric(18,4) | no | Normalised unit baseline; nullable for `none_available` |
| `baseline_unit_price_currency` | text | no | FK -> `supported_currency(code)`; required with amount |
| `baseline_value_amount` | numeric(18,4) | no | Baseline unit price multiplied by recorded quantity; nullable for `none_available` |
| `baseline_value_currency` | text | no | FK -> `supported_currency(code)`; required with amount |
| `actual_value_amount` | numeric(18,4) | yes | Copied from `purchase_record.total_paid_amount` |
| `actual_value_currency` | text | yes | FK -> `supported_currency(code)` |
| `delta_amount` | numeric(18,4) | no | `baseline_value - actual_value`; nullable for `none_available` |
| `delta_currency` | text | no | FK -> `supported_currency(code)`; required with amount |
| `calculation_version` | text | yes | Example: `saving-baseline-v1` |
| `calculation_inputs` | jsonb | yes | Replay snapshot: quantity, selected policy, source point ids, window months, actual total |
| `recorded_by` | uuid | yes | FK -> `membership(id)`; copied from purchase |
| `recorded_at` | timestamptz | yes | Time values were captured |
| `verified_by` | uuid | no | FK -> `membership(id)`; only set by explicit verification |
| `verified_at` | timestamptz | no | Only set by explicit verification |
| `created_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- Unique `(tenant_id, purchase_record_id)`.
- Check verified metadata consistency:
  `(status = 'verified') = (verified_at is not null and verified_by is not null)`.
- Check pending rows have no verification metadata.
- Check money pair nullability for optional baseline and delta fields.
- Check baseline, actual, and delta currencies match when baseline exists.
- Index `(tenant_id, status, recorded_at desc)`.
- Index `(tenant_id, supplier_id, recorded_at desc)`.
- Index `(tenant_id, workspace_product_id, recorded_at desc)`.

Immutability:

- Database trigger `saving_record_verified_immutability` refuses `UPDATE` or `DELETE` when
  `old.status = 'verified'`.
- Verification update is the final allowed mutation and changes only `status`, `verified_at`, and
  `verified_by`.
- No role, including service role, may update or delete a row after it is verified.

RLS:

- Tenant-scoped uniform policy.
- Active roles may read.
- Owner/buyer may create pending records and verify through API RBAC.

## `export_job`

Durable, tenant-scoped polling resource for savings-ledger exports.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | FK -> `tenant(id)` |
| `requested_by` | uuid | yes | FK -> `membership(id)` |
| `kind` | text | yes | Const-like value `savings_ledger` for this chunk |
| `format` | `export_format` | yes | `xlsx` or `pdf` |
| `filters` | jsonb | yes | `{period_start, period_end, supplier_id?, branch_id?}` |
| `status` | `export_job_status` | yes | Default `queued` |
| `storage_bucket` | text | no | Set when completed, e.g. `exports` |
| `storage_path` | text | no | Set when completed |
| `download_url` | text | no | Optional signed URL or API download URL |
| `row_count` | integer | no | Number of verified savings rendered; zero is valid |
| `error` | jsonb | no | Structured failure `{code,message,details?}` |
| `created_at` | timestamptz | yes | Default `now()` |
| `started_at` | timestamptz | no | Set by worker |
| `completed_at` | timestamptz | no | Set for `completed` or `failed` |

Constraints and indexes:

- Check `(status in ('completed','failed')) = (completed_at is not null)`.
- Check completed jobs have `storage_bucket`, `storage_path`, and non-null `row_count`.
- Check failed jobs have `error`.
- Index `(tenant_id, requested_by, created_at desc)`.

RLS:

- Tenant-scoped uniform policy.
- Owner/buyer may create export jobs.
- Active roles may read export status for jobs in their workspace.

## `plan`

Small shared reference table for product tiers. This is intentionally not tenant-scoped.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `code` | text | yes | PK, e.g. `starter`, `growth` |
| `name` | text | yes | Display name key/source value; UI strings still come from i18n |
| `status` | `plan_status` | yes | Default `active` |
| `monthly_price_amount` | numeric(18,4) | yes | Seeded `0.0000` for stub plans |
| `monthly_price_currency` | text | yes | FK -> `supported_currency(code)` |
| `limits` | jsonb | yes | Example `{ "active_catalogue_products": 100 }` |
| `features` | jsonb | yes | Feature flags or included capabilities for display |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Seed data:

- `starter`: active, `0.0000 GBP`, limits `{ "active_catalogue_products": 100 }`.
- `growth`: active, `0.0000 GBP`, limits `{ "active_catalogue_products": 1000 }`.

RLS exception:

- `plan` has no `tenant_id` because it contains no workspace-specific data.
- It mirrors `canonical_product`: authenticated users may `select`; authenticated users have no
  insert/update/delete policy; service role seeds and updates rows.

## `billing_account`

Tenant-scoped assignment of a workspace to a shared plan through the billing-provider abstraction.

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `id` | uuid | yes | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | yes | Unique FK -> `tenant(id)` |
| `plan_code` | text | yes | FK -> `plan(code)` |
| `provider` | text | yes | `stub` for this chunk |
| `provider_customer_id` | text | yes | `stub_customer:{tenant_id}` |
| `provider_subscription_id` | text | no | `stub_subscription:{tenant_id}:starter` |
| `status` | `billing_account_status` | yes | Default `active` |
| `current_period_start` | timestamptz | no | Nullable for stub |
| `current_period_end` | timestamptz | no | Nullable for stub |
| `assigned_at` | timestamptz | yes | Default `now()` |
| `created_at` | timestamptz | yes | Default `now()` |
| `updated_at` | timestamptz | yes | Default `now()` |

Constraints and indexes:

- Unique `tenant_id`.
- Check `provider in ('stub')` for this chunk.
- Check `current_period_end is null or current_period_start is null or current_period_end >= current_period_start`.
- Index `(tenant_id, plan_code)`.

RLS:

- Tenant-scoped uniform policy.
- Active roles may read their workspace's billing account and plan.
- Plan assignment normally occurs during workspace creation through the provider abstraction.
- Only owner-level API surfaces may trigger any future plan-management action; no real payment
  action exists in this chunk.

## Migration Sketch

File names only:

- `supabase/migrations/20260821000030_value_proof_enums.sql`
- `supabase/migrations/20260821000031_purchase_saving_records.sql`
- `supabase/migrations/20260821000032_export_jobs.sql`
- `supabase/migrations/20260821000033_plan_billing_account.sql`
- `supabase/migrations/20260821000034_value_proof_rls.sql`
- `supabase/migrations/20260821000035_saving_record_immutability.sql`

`20260821000034_value_proof_rls.sql` should place all RLS policy definitions for this chunk in one
readable file, following the existing catalogue, quotation, matching, and basket/alert RLS files.
