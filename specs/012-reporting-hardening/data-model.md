# Phase 1 Data Model: Reporting and Hardening

R2.5 adds scheduling and digest subscription state, and extends the existing `export_job` artifact
record. It does not create a second savings, purchase, or alert source of truth; report content is
computed from existing tables through tenant-pinned readers (research R5).

## New persisted tables

### `report_schedule`

A member-owned recurring report definition.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `created_by_membership_id` | uuid | Required composite FK -> Membership `(tenant_id, id)` |
| `kind` | text | Required; one of `savings_ledger`, `spend_by_supplier`, `alerts_summary` |
| `format` | export_format | Required; widened enum (csv/xlsx/pdf) |
| `filters` | jsonb | Required; `{period derived at run time, supplier_id?, branch_id?}` — stored as the fixed filter part |
| `filters_digest` | text | Required; sha256 of canonical filters JSON, computed by the API |
| `weekday` | smallint | Required; 0–6 (Monday-based) for the weekly cadence |
| `status` | report_schedule_status | Required; `active` or `paused` |
| `next_run_at` | timestamptz | Required; the next due instant in the tenant reporting timezone |
| `last_run_at` | timestamptz | Nullable |
| `rule_version` | text | Required; renderer rule version for replay |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

Constraints:

- Unique `(tenant_id, created_by_membership_id, kind, format, filters_digest)` — one schedule per
  member per kind/format/filters combination.
- `weekday between 0 and 6`.
- Kind/format compatibility is validated at the API and contract boundary against the matrix in
  research R2. The database constrains `kind` to the R2.5 value set with a CHECK; a CHECK may not
  reference the `csv` enum value inside the migration that adds it, so no `(kind, format)` DB
  CHECK ships in R2.5.
- RLS: tenant members may select; owner/buyer may insert/update/delete (delete is a hard delete of
  the schedule config — schedules are configuration, not outcome history; artifacts remain).

### `digest_subscription`

A per-member weekly digest definition.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `membership_id` | uuid | Required composite FK -> Membership `(tenant_id, id)`; the subscriber |
| `kind` | text | Required; `weekly_digest` (single value in R2.5) |
| `locale` | text | Required; `en` or `ar` — the digest render language, defaulting to the member's preferred locale |
| `filters` | jsonb | Required; `{branch_id?: uuid}` |
| `filters_digest` | text | Required; canonical digest of filters |
| `channel` | digest_channel | Required; `email` or `in_app` |
| `status` | digest_subscription_status | Required; `active` or `paused` |
| `next_run_at` | timestamptz | Required |
| `last_delivery_at` | timestamptz | Nullable |
| `last_delivery_status` | text | Nullable; `succeeded`, `failed`, `email_unconfigured` |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

Constraints:

- Unique `(tenant_id, membership_id, kind, filters_digest)`.
- Every new membership is provisioned with one active subscription (in-app channel, or email when
  SMTP is configured) at acceptance, per FR-008; the provisioning is a service behaviour on top
  of this table.
- The scheduler skips subscriptions whose membership is no longer active.
- RLS: a member may select/insert/update/delete only their own subscription rows
  (`membership_id = (auth.jwt() ->> 'membership_id')`); owners may additionally select all rows
  in the tenant for visibility, not modify them.

## Extended persisted tables

### `tenant`

Add `reporting_timezone` text not null default `'UTC'`, validated as an IANA timezone name by the
API (owner-editable via the existing `PATCH /api/v1/tenant`; region, currency, and tax model stay
immutable).

### `export_job`

Remains the single job-and-artifact record for on-demand and scheduled generation. Extensions:

- `schedule_id` uuid nullable, composite FK -> `report_schedule (tenant_id, id)`.
- `locale` text not null default `'en'` — the artifact render language (FR-029).
- `rule_version` text not null default `''` (set by the renderer at run time).
- `schedule_snapshot` jsonb nullable — an immutable copy of the schedule definition (kind, format,
  filters, weekday, locale, rule version at creation) taken when the scheduled run is enqueued, so
  replay survives schedule edits and deletion.
- `expires_at` timestamptz nullable (set at completion: completion time + retention window).
- `kind` widens to `savings_ledger | spend_by_supplier | alerts_summary` (text column; the API and
  a new CHECK constraint enforce the value set).
- `format` widens via `ALTER TYPE export_format ADD VALUE 'csv'` (forward-only; runs in a separate
  migration statement as the type alteration requires it).
- `status` widens with `expired` (reached by the purge pass; `expired` behaves as terminal for
  downloads, `completed_at` remains set).
- Unique partial index `(tenant_id, schedule_id, filters->>'period_start')` where `schedule_id is
  not null` — the per-period idempotency key (research R4).
- Existing CHECK `export_job_completed_has_storage` unchanged; new CHECK
  `export_job_expired_only_after_completion`.

### New indexes for report queries

- `export_job_tenant_created_idx` on `(tenant_id, created_at desc)` — Reports center listing.
- `report_schedule_due_idx` partial on `(next_run_at)` where `status = 'active'` — due-list claim.
- `digest_subscription_due_idx` partial on `(next_run_at)` where `status = 'active'`.
- `saving_record` and `purchase_record` already carry `(tenant_id, recorded_at desc)`-shaped
  indexes from earlier chunks; `spend_by_supplier` reuses them.

## Authorization-pinned reader functions

SECURITY DEFINER functions owned by migrations, `SET search_path` pinned, each taking `tenant_id`
plus filters, and — wherever member-specific visibility matters (digest content, branch-scoped
reports) — the effective `membership_id` and optional `branch_id`, validating active membership
and branch visibility inside the function before returning rows (research R5; security critique
finding 3):

- `reporting_savings_for_period(tenant_id, period_start, period_end, supplier_id, branch_id)`
- `reporting_purchases_for_period(tenant_id, period_start, period_end, supplier_id, branch_id)`
  — spend aggregation source.
- `reporting_alert_snapshot(tenant_id, period_start, period_end, branch_id)` — runs the R2.4 alert
  condition functions parameterised by tenant instead of by member connection.
- `reporting_validity_expiring(tenant_id, now, horizon_days, branch_id)` — offers whose validity
  window ends inside the horizon (digest section three).

Each function is covered by the isolation test with a tenant-A/tenant-B marker-record case, plus
a branch-A/branch-B case for the member-scoped readers.

## Declared column schemas per report kind

- `savings_ledger`: short saving reference, recorded date, branch name, supplier name, product
  name, SKU/unit, quantity, baseline unit price and total (currency-explicit), actual unit price
  and total paid, verified saving amount, PO/reference, evidence web link.
- `spend_by_supplier`: grouped by (supplier, currency) — supplier name, tax registration number,
  currency, total spend, order count, verified savings realised, primary branch. Never sums
  across currencies.
- `alerts_summary`: alert id, triggered date, alert type, severity, supplier name, product name,
  branch name, estimated financial exposure (currency-explicit), status, dismissed by,
  dismissal reason.

## Response-only entities

### `ReportSchedule`

Returned by the schedules CRUD endpoints: `id`, `kind`, `format`, `filters`, `weekday`,
`status`, `next_run_at`, `last_run_at`, `rule_version`, `created_at`, `updated_at`.

### `ReportArtifact`

Returned by `GET /reports/artifacts` (cursor list over `export_job`): `id`, `kind`, `format`,
`filters`, `status`, `row_count`, `rule_version`, `schedule_id`, `download_url` (present only
while downloadable), `expires_at`, `error`, `created_at`, `started_at`, `completed_at`.

### `DigestSubscription`

`id`, `kind`, `filters`, `channel`, `status`, `next_run_at`, `last_delivery_at`,
`last_delivery_status`, `email_configured` (workspace-level, from settings), `created_at`,
`updated_at`.

### `DigestView`

The in-app digest render: `subscription_id`, `period_start`, `period_end`, `sections` in fixed
order — verified savings (hero position), pending outcome verifications, pending approvals for
the subscriber, anomalies, expiring validity (each item with `label`, `money` where applicable,
`evidence_ref`, `deep_link`), `rendered_at`, `delivery_status`.

## Audit events

Append-only, no update or delete for any role. Every event carries the mandatory payload contract
from FR-011: actor membership (or the explicit system-actor marker for worker-triggered events),
trace or correlation id, source schedule or subscription id, period window, filters digest, row
count where applicable, storage path reference where applicable, and outcome-specific detail.

- `reports.schedule_created` / `schedule_updated` / `schedule_paused` / `schedule_resumed` /
  `schedule_deleted`
- `reports.export_requested` (on-demand)
- `reports.run_started` / `run_completed` / `run_failed` (scheduled and on-demand generation)
- `reports.artifact_downloaded`
- `reports.artifact_purged`
- `digests.subscription_created` / `subscription_updated` / `subscription_paused` /
  `subscription_resumed` / `subscription_deleted`
- `digests.delivery_attempted` / `delivery_succeeded` / `delivery_failed` /
  `delivery_skipped_email_unconfigured`

## RLS and audit requirements

Both new tables carry `tenant_id`, `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and
policies with `USING` and `WITH CHECK`. Cross-tenant schedule, artifact, export job, and digest
references resolve as not found. The tenant-pinned reader functions are reviewed in the R2.5
security record alongside the policies. `audit_event` remains append-only.
