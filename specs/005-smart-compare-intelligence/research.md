# Phase 0 Research: Smart Compare + Intelligence

**Feature**: `005-smart-compare-intelligence`  
**Date**: 2026-08-21  
**Scope**: Planning only. No implementation, migrations, or task breakdown.

## R1. Offer Read Pattern

**Decision**: An `Offer` is derived at request time from existing chunk 4.4 and 4.2 rows:

- `match_decision`: `id`, `tenant_id`, `quotation_line_id`, `matched_workspace_product_id`,
  `confidence`, `decided_at`
- `landed_cost`: `id`, `tenant_id`, `quotation_line_id`, `match_decision_id`, `quantity`,
  `normalised_base_quantity`, `base_unit`, all amount/currency component columns, `total_amount`,
  `total_currency`, `raw_inputs`, `rule_version`, `valid_from`, `valid_to`, `recorded_at`
- `quotation_line`: `id`, `quotation_id`
- `quotation`: `id`, `supplier_id`, `status`
- `supplier`: `id`, `name`, `lead_time_days`, `reliability_score`, `status`
- `workspace_product`: `id`, `tenant_id`, `tenant_name`, `preferred_supplier_id`, `status`
- `pack_definition`: `workspace_product_id`, `base_quantity`

Query shape:

1. Resolve `workspace_product.id = :product_id` through RLS. No caller-supplied tenant id exists.
2. Join `match_decision` on `matched_workspace_product_id = workspace_product.id`.
3. Join `landed_cost` on `match_decision_id = match_decision.id`.
4. Join `quotation_line` and `quotation` to obtain `quotation.supplier_id`.
5. Join `supplier` for lead time, reliability and active/preferred/blocked status.
6. Keep quotation rows where `quotation.status = 'reviewed'`, `workspace_product.status = 'active'`,
   and `supplier.status in ('active', 'preferred')`.
7. Pick the latest row per `(matched_workspace_product_id, supplier_id, rule_version)` using
   `recorded_at desc, landed_cost.id desc`. The API may expose all current supplier offers, but
   there is one current offer per supplier.
8. Expired rows are included only when `include_expired=true`; otherwise they are excluded from
   eligible recommendations. Expired means `valid_to is not null and valid_to < now()`.

The compare endpoint projects landed cost for the requested quantity by reusing chunk 4.4's
stored replay inputs and rule version. There is no new persisted landed-cost row and no second
implementation of landed-cost rules. The display-level projection is:

- `required_base_quantity = requested_quantity * pack_definition.base_quantity`
- `normalised_unit_price = projected_total / required_base_quantity`
- `projected_total` is produced by the existing landed-cost rule function at the row's
  `rule_version`, using the row's `raw_inputs` and the substituted requested quantity.

**Rationale**: This keeps chunk 4.4 as the single source of landed-cost truth while still allowing
the compare grid to update quantity-sensitive totals.

## R2. Recommendation Scorer

**Decision**: v1 uses a deterministic weighted score, grounded in `engineering-spec.md` §5.2's
"weighted scoring with calibrated thresholds":

```
score =
  0.55 * cost_score
+ 0.20 * match_confidence_score
+ 0.15 * reliability_score
+ 0.10 * lead_time_score
```

Where:

- `cost_score = cheapest_projected_total_amount / offer_projected_total_amount`, capped to `[0,1]`.
- `match_confidence_score = match_decision.confidence`.
- `reliability_score = supplier.reliability_score`; null reliability is scored as `0.500`.
- `lead_time_score = 1 - min(lead_time_days, 30) / 30`; null lead time is scored as `0.500`.
- Stock is not scored in this chunk because there is no source field (see R4).

Only non-expired offers are eligible for recommendation. A single eligible offer is recommended
with its actual score and evidence.

Confidence calibration:

- `high`: score `>= 0.850` and winning margin over second place `>= 0.050`
- `medium`: score `>= 0.700`, or score `>= 0.850` with margin `< 0.050`
- `low`: score `< 0.700`

Risk notes:

- `price_expiring_soon`: recommended offer `valid_to` is within 7 days.
- `low_match_confidence`: `match_decision.confidence < 0.850`.
- `low_supplier_reliability`: `supplier.reliability_score < 0.600`.
- `none`: no current risk note.

**Rationale**: Cost dominates, but the recommendation is not a bare lowest-price rule. Match
confidence remains prominent because a wrong match fabricates savings. Reliability and lead time
matter, but are weaker in v1 because they are sparse or supplier-level rather than line-specific.

## R3. Deterministic Tie-Break

**Decision**: Offers are considered equally recommendable when their weighted scores are equal
after rounding to four decimals. The deterministic tie-break order is:

1. Lower `projected_total.amount`.
2. Higher `match_decision.confidence`.
3. Higher `supplier.reliability_score`, with null last.
4. Lower `supplier.lead_time_days`, with null last.
5. Later `valid_to`, with null treated as open-ended and therefore first for stability.
6. Lexicographic `supplier.name`.
7. Lexicographic `supplier.id`.

The response must include the tie-break rule that was applied in `recommendation.evidence`.

**Rationale**: The rule is stable across re-renders and auditable. It also keeps commercial
evidence visible to the buyer instead of hiding arbitrary ordering.

## R4. Stock Signal Gap

**Decision**: `Offer.stock_signal` is nullable in the data model and OpenAPI contract. In this
chunk's first version it is always `null`.

**Rationale**: The existing schema has no stock, availability or inventory field. The supplier
table has `reliability_score`, `lead_time_days`, `minimum_order_value_amount/currency`, and
`delivery_fee_amount/currency`, but no inventory source. Phase 1 explicitly excludes ERP and
inventory tracking. Inventing a stock field or fabricating availability would violate Evidence
Over Assertion. The UI can show an absent/unknown state, translated through `packages/i18n`.

## R5. Basket Split Request and Result Shape

**Decision**: The buyer names exactly two suppliers at submission time:

```json
{
  "supplier_ids": ["uuid-supplier-a", "uuid-supplier-b"],
  "items": [
    { "workspace_product_id": "uuid-product", "quantity": "10.000000" }
  ]
}
```

Validation:

- `supplier_ids` length must be exactly 2.
- Supplier ids must be unique and visible in the caller's tenant.
- Every item uses `workspace_product_id`, not the stale `tenant_product_id` name.
- Quantities are decimal strings greater than zero.
- Owner and buyer may submit; other roles may read only.

The API inserts `basket_split_job` with `status='queued'` and enqueues an RQ job to the
`basket-split` queue. The optimiser reads current eligible offers for only the named suppliers.

Infeasibility is reported through the job result, not silently:

```json
{
  "feasible": false,
  "infeasible_items": [
    {
      "workspace_product_id": "uuid-product",
      "requested_quantity": "10.000000",
      "reason": "no_offer_from_named_suppliers",
      "missing_supplier_ids": ["uuid-supplier-a", "uuid-supplier-b"]
    }
  ],
  "allocation": [],
  "total_landed_cost": null
}
```

An infeasible solve is a completed job with `result.feasible=false`; `failed` is reserved for
worker, Redis, database or unexpected solver failures.

**Rationale**: The spec assumption says the buyer chooses the two suppliers. Reporting infeasible
items as structured result data satisfies FR-010 without turning normal commercial absence into a
system error.

## R6. Price History Query Shape

**Decision**: Price history is derived entirely from `landed_cost` joined through
`match_decision`, `quotation_line`, `quotation`, and `supplier`.

Default query:

- Product: one `workspace_product_id`.
- Supplier filter: optional `supplier_id`.
- Window: trailing 6 calendar months from request time for rolling averages.
- History points use `landed_cost.recorded_at` as the x-axis timestamp and
  `landed_cost.total_amount / landed_cost.normalised_base_quantity` as the normalised unit price.
- `last_paid`: latest row by `recorded_at desc, landed_cost.id desc`.
- `average_paid_rolling_window`: arithmetic mean of normalised unit prices where
  `recorded_at >= now() - interval '6 months'`, grouped in the response by requested filters.
- `best_price`: lowest normalised unit price on all available record-time history for the product.

**Rationale**: The spec asks for the workspace's own existing landed-cost records, not a new ledger.
"Paid" is product copy for buyer context in this chunk; the actual savings/outcome ledger arrives
in chunk 4.6.

## R7. Alert Conditions

**Decision**: Alerts are computed live on every `GET /alerts` request, then filtered against
dismissal fingerprints.

Alert kinds:

- `recommended_price_expiring`: current recommendation exists and its `valid_to` is not null,
  greater than or equal to now, and less than or equal to `now() + interval '7 days'`.
- `preferred_supplier_offer_disappeared`: `workspace_product.preferred_supplier_id` is set, the
  preferred supplier has at least one historical landed-cost row for the product, and the current
  eligible offer set no longer contains that supplier.
- `price_swing`: current recommended offer's normalised unit price differs from the trailing
  6-month rolling average by at least 15%, with at least two historical points in that rolling
  window. Both increase and decrease are surfaced; severity is higher for increases.

Alert ids are deterministic fingerprints over tenant id, alert kind, product id, relevant supplier
id if any, and a condition-specific recurrence key:

- expiring price: `landed_cost.id + valid_to`
- disappeared preferred offer: preferred supplier id + current latest non-preferred offer ids
- price swing: current `landed_cost.id` + rounded swing percentage

Dismissal suppresses only the same fingerprint. If the underlying condition changes, a new
fingerprint appears.

**Rationale**: FR-014 forbids persisting stale alert conditions. Persisting only dismissals keeps
alerts current while letting a buyer action an item.

## R8. `services/optimiser` Shape

**Decision**: The optimiser mirrors `services/extraction-worker`:

- Own directory: `services/optimiser`.
- Own `pyproject.toml`, hatchling build, Python `>=3.12,<3.13`.
- Own isolated dependencies and venv; no `apps/api` imports.
- Runtime dependencies: `redis>=5.2,<6`, `rq>=2.1,<3`, `psycopg[binary]>=3.2,<4`,
  `pydantic>=2.10,<3`, `ortools`.
- Dev dependencies: `pytest==8.3.4`, `pytest-asyncio==0.25.2`, `ruff`.
- Worker package: `procurepilot_optimiser_worker`.
- Entrypoint: `python -m procurepilot_optimiser_worker`, creating `rq.Worker` for queue
  `BASKET_SPLIT_QUEUE_NAME` defaulting to `basket-split`.
- API enqueue target string:
  `procurepilot_optimiser_worker.worker.process_basket_split_job`.
- Communication: Redis payload contains `job_id` and `tenant_id`; worker reads/writes the database
  with `DATABASE_URL`.
- Docker shape mirrors extraction-worker: `python:3.12-slim`, `working_dir:
  /workspace/services/optimiser`, mounted repo, `PYTHONPATH: /workspace/services/optimiser/src`,
  shared Redis and DB dependencies.

**Rationale**: This preserves the isolation discipline chunk 4.3 established and avoids a direct
runtime coupling between the FastAPI monolith and the CPU-bound optimiser.

## R9. RLS Plan

**Decision**: Two new tenant-scoped tables are planned:

- `basket_split_job`
- `alert_dismissal`

Both tables carry `tenant_id uuid not null references tenant(id) on delete cascade`, `ENABLE ROW
LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and the uniform policy:

```sql
using (tenant_id = current_tenant_id())
with check (tenant_id = current_tenant_id())
```

The implementation migration should grant authenticated users table permissions consistent with
existing chunks, then rely on FastAPI RBAC to restrict basket submission and alert dismissal to the
intended roles.

**Rationale**: The new tables are tenant-scoped operational state. Derived offers,
recommendations, price history and alert conditions add no storage surface, but all read paths must
join only through tenant-scoped rows or through the deliberately shared `canonical_product` spine.
