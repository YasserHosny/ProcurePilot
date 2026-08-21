# Phase 0 Research: Value Proof + Launch Readiness

**Feature**: 006-value-proof-launch
**Date**: 2026-08-21
**Scope**: Planning decisions only. No implementation, migrations, or task breakdown.

## R1. Baseline Capture and Verification Semantics

**Decision**: `record_purchase` creates both a `purchase_record` and its paired
`saving_record` in one transaction. The `saving_record` captures
`baseline_policy`, `baseline_value`, `actual_value`, and `delta` at record time by reading chunk
4.5's existing product price-history read model. Verification is a later explicit human action
that changes only `status`, `verified_at`, and `verified_by`.

**Mechanism**:

1. The caller submits the actual outcome: `workspace_product_id`, optional `supplier_id`, optional
   `quotation_line_id`, optional `match_decision_id`, optional `landed_cost_id`, `quantity`,
   `unit_price`, `delivery_result`, and optional notes/evidence references.
2. The savings service validates every referenced row is visible through the caller's tenant RLS
   context. Cross-tenant or absent rows return `404`, never `403`.
3. The service computes `actual_value` as the submitted total paid for the actual outcome. If the
   API accepts unit price plus quantity, it stores both the unit price and the computed total on
   `purchase_record`; the `saving_record.actual_value` is the stored total.
4. The service reads chunk 4.5 price history for the same `workspace_product_id`, using the same
   source shape implemented in `apps/api/src/procurepilot_api/modules/offers/service.py`:
   `match_decision -> landed_cost -> quotation_line -> quotation -> supplier`.
5. It uses the same normalised unit-price calculation implemented in
   `apps/api/src/procurepilot_api/modules/offers/price_history.py`:
   `landed_cost.total_amount / landed_cost.normalised_base_quantity`, rounded to 4 decimal
   places, and the same `price_history_summary()` policies:
   `last_paid` from the newest point by `(recorded_at, landed_cost_id)` or
   `average_paid_rolling_window` from points inside the configured window.
6. This chunk does not introduce a second baseline computation. It selects one metric from the
   existing summary and multiplies that normalised unit price by the recorded outcome quantity to
   store the `baseline_value`.
7. `delta = baseline_value - actual_value`, stored as a signed `Money`. Positive means money
   saved; zero and negative values are valid and must be displayed truthfully.

`baseline_policy` values:

| Value | Meaning |
|---|---|
| `last_paid` | Use the latest price-history point's normalised unit price. |
| `rolling_average_6m` | Use the rolling average from the last 6 calendar months. |
| `none_available` | No historical baseline exists. The purchase is recorded, but no verified saving can be produced until a baseline exists or a later correction model is specified. |

For Phase 1, the workspace baseline policy is not a new tenant setting unless implementation finds
one already present. The implementation default is `last_paid`; `rolling_average_6m` is supported
in the table and contract because chunk 4.5 already exposes the metric. If the chosen metric is
missing but another supported metric exists, the service may fall back in this order:
`last_paid`, then `rolling_average_6m`; it must persist the actual policy used.

**Verification**:

`POST /savings/{id}/verify` is an explicit transition from `pending` to `verified`. It must not
re-read price history and must not recompute baseline, actual, or delta. The only persisted changes
are:

- `status = 'verified'`
- `verified_at = now()`
- `verified_by = current membership id`

**Rationale**: The product needs a defensible record of what was known when the outcome was
recorded. Live price history can change as new quotations arrive; verified savings must remain the
historical claim, not a moving calculation.

## R2. Verification RBAC

**Decision**: Owners and buyers may verify a `saving_record`, including the same buyer who recorded
the purchase.

**Rationale**: Phase 1 has no approval workflow or second-review role. Requiring a different human
would create a workflow dependency on Phase 2. The important constitutional boundary is that
verification is deliberate and human, not automatic. Owner/buyer-only verification mirrors existing
write roles for purchasing decisions in `offers` and `alerts`.

View-only roles may read the ledger and evidence but may not record outcomes, verify savings, or
request exports.

## R3. Export Job Design

**Decision**: Exports are tracked with an `export_job` row and rendered asynchronously by
`apps/api`'s own worker entrypoint:
`python -m procurepilot_api.workers.export_worker`. The worker consumes the `exports` RQ queue,
renders `.xlsx` using `openpyxl`, renders `.pdf` using `reportlab`, uploads the file to Supabase
Storage, and marks the job completed with a durable result reference.

**Library choices**:

| Format | Library | Reason |
|---|---|---|
| `.xlsx` | `openpyxl` | Mature pure-Python Excel writer, no office runtime, straightforward Docker footprint. |
| `.pdf` | `reportlab` | Pure Python plus common binary wheels, no browser engine or system CSS/Pango stack. Simpler container dependency footprint than WeasyPrint for a ledger summary. |

**Worker shape**:

- API inserts `export_job(status='queued')` under authenticated RLS context, then enqueues an RQ job
  to queue name `exports`.
- Redis/RQ is only a delivery mechanism. The durable `export_job` row is the polling source of
  truth, matching `basket_split_job` and `extraction_job`.
- Worker entrypoint: `python -m procurepilot_api.workers.export_worker`.
- RQ callable: `procurepilot_api.workers.export_worker.process_export_job`.
- Payload: `{ "job_id": "...", "tenant_id": "..." }`.
- The worker marks `running`, queries only verified savings matching the stored filters, renders
  an intentionally empty file when no rows match, uploads to Supabase Storage, then marks
  `completed`.
- On worker/system failure, it stores structured `error` JSON and marks `failed`.

**Storage**:

Use the existing Supabase Storage pattern from document extraction: service-role access in worker
code for object upload, but durable metadata remains in Postgres. Store export files under a
dedicated bucket such as `exports` with paths:
`{tenant_id}/savings/{export_job_id}.{format}`. The API returns a `download_url` or a stable
`result` reference only after completion; the URL must be tenant-checked before serving or signing.

**Export filters**:

- `period_start` and `period_end` are required ISO dates.
- `supplier_id` is optional.
- `branch_id` is optional and accepted for contract compatibility, but Phase 1 has no `Branch`
  entity. Implementations must treat it as currently always null: a non-null value either returns
  an empty export or `422` with `branch_id: unsupported_in_phase_1`; it must not create a Branch
  dependency.

## R4. Billing Provider and Plan Gating

**Decision**: Billing is an in-process Python abstraction with one stub implementation this chunk.
No real Stripe SDK or credentials are introduced.

Provider shape:

```python
class BillingProvider(Protocol):
    def assign_default_plan(self, tenant_id: UUID) -> BillingAccount: ...
    def current_account(self, tenant_id: UUID) -> BillingAccount: ...
    def check_limit(self, tenant_id: UUID, resource: str) -> LimitCheck: ...
```

Suggested models:

```python
class LimitCheck(BaseModel):
    resource: Literal["active_catalogue_products"]
    plan_code: str
    limit: int | None
    used: int
    allowed: bool
    remaining: int | None
```

`StubBillingProvider` behavior:

- On workspace creation, assign `starter` unless a test override explicitly asks for another seeded
  plan.
- Provider references are deterministic strings:
  `stub_customer:{tenant_id}` and `stub_subscription:{tenant_id}:starter`.
- `check_limit("active_catalogue_products")` reads active `workspace_product` count and compares
  it to the assigned plan's `limits.active_catalogue_products`.

Plan seed data:

| code | name | status | monthly_price | limits |
|---|---|---|---|---|
| `starter` | Starter | `active` | `{ "amount": "0.0000", "currency": "GBP" }` | `{ "active_catalogue_products": 100 }` |
| `growth` | Growth | `active` | `{ "amount": "0.0000", "currency": "GBP" }` | `{ "active_catalogue_products": 1000 }` |

**Concrete gated behavior for FR-011**: maximum active catalogue product count. For the `starter`
plan, the exact limit is **100 active `workspace_product` rows**. Attempts to create or unarchive
the 101st active product return a clear plan-limit response, not a silent failure.

**Rationale**: Catalogue size is already Phase 1 data, easy to count under RLS, and does not depend
on Phase 2 seats, branches, budgets, or approvals.

## R5. RLS Plan

**Decision**: `purchase_record`, `saving_record`, `export_job`, and `billing_account` are
tenant-scoped and use the uniform RLS pattern from chunks 4.1-4.5. `plan` is a deliberate shared
reference table exception mirroring `canonical_product`.

Tenant-scoped tables:

- Carry `tenant_id uuid not null references tenant(id) on delete cascade`.
- `alter table ... enable row level security`.
- `alter table ... force row level security`.
- One `tenant_isolation` policy for all authenticated operations:
  `using (tenant_id = current_tenant_id()) with check (tenant_id = current_tenant_id())`.
- Grants follow the existing chunk pattern, with application RBAC enforcing owner/buyer mutations.

`plan` shared-reference exception:

- No `tenant_id`.
- Contains only product tier definitions, no workspace-identifying data.
- `select` allowed to authenticated users with `using (true)`.
- No authenticated insert/update/delete policy.
- Service role may seed/update plan definitions.

**Rationale**: Plan definitions are global product metadata, the same class of safe shared data as
`canonical_product` and supported reference tables. The tenant-specific assignment lives in
`billing_account`, which is RLS-protected.

## R6. Whole-Product A11y and RTL Audit

**Decision**: US4 is a retrospective fix pass over every shipped Phase 1 screen, not a report-only
audit. Any WCAG 2.1 AA or RTL issue found on existing screens is fixed in this chunk.

Feature directories to scan:

- `apps/web/src/app/features/auth`
- `apps/web/src/app/features/onboarding`
- `apps/web/src/app/features/catalogue`
- `apps/web/src/app/features/quotations`
- `apps/web/src/app/features/matching`
- `apps/web/src/app/features/offers`
- `apps/web/src/app/features/alerts`
- New chunk 4.6 savings/billing/onboarding screens once implemented

Method:

- Run Playwright journeys that reach each screen in English (`dir="ltr"`) and Arabic (`dir="rtl"`).
- Run axe-core on every reached route; target zero WCAG 2.1 AA violations.
- Visually inspect representative screenshots across the accumulated surface area for RTL
  mirroring, especially tables, compare grids, steppers, dialogs, icon ordering, and form
  validation placement.
- Fix violations in the owning feature directory in this chunk. Logging without fixing is not
  launch-ready.
- Verify all user-facing strings introduced or touched by fixes come from `packages/i18n` in both
  English and Arabic.

## R7. Verified Saving Immutability

**Decision**: Enforce verified `saving_record` immutability with a database trigger that refuses
`UPDATE` or `DELETE` when `old.status = 'verified'`. Do not rely on application-layer enforcement.

Migration-level shape:

```sql
create or replace function refuse_verified_saving_record_mutation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status = 'verified' then
    raise exception 'verified saving records are immutable'
      using errcode = 'restrict_violation';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create trigger saving_record_verified_immutability
  before update or delete on saving_record
  for each row
  execute function refuse_verified_saving_record_mutation();
```

Additionally, application code must expose verification as a narrow SQL update that changes only
`status`, `verified_at`, and `verified_by` from `pending` to `verified`. The trigger is the
constitutional guarantee; the application restriction is a cleaner API boundary.

**Rationale**: This is the same class of protection as `audit_event` append-only behavior and the
membership owner-guard trigger: a Principle-critical invariant belongs in the database so future
code paths cannot bypass it accidentally.

## Additional Design Decisions

- `purchase_record` remains editable only while its paired `saving_record` is pending. Once the
  saving is verified, attempts to alter the evidence chain must be refused because they would
  undermine the verified claim.
- `saving_record` has a one-to-one relationship with `purchase_record` for Phase 1. Corrections or
  supersession after verification are out of scope and need a future explicit model.
- Exports include only `verified` savings. Pending savings remain visible in the ledger but are
  excluded from verified totals and export rows.
- No currency conversion is performed. Baseline and actual currencies must match. A mismatch is a
  validation error until a future currency-conversion policy exists.
