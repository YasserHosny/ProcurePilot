# Data Model: 024 RFQ Basket Split

## Changed: `basket_split_job`

| Column | Type | Notes |
|---|---|---|
| `rfq_id` | uuid null | FK `(tenant_id, rfq_id)` → `rfq (tenant_id, id)`. Set when the job was started from an RFQ. |

`request_snapshot` gains `rfq: {rfq_id, price_quotation_ids: uuid[], rfq_response_ids: uuid[], pack_base_quantities: {product_id: numeric}}`.
The optimiser reads `price_quotation_ids` (research R2).

## New: `purchase_request_group`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | |
| `tenant_id` | uuid not null | FK tenant; RLS ENABLE + FORCE |
| `rfq_id` | uuid not null | FK `(tenant_id, rfq_id)`; **unique (tenant_id, rfq_id)**, so there is one split per RFQ |
| `basket_split_job_id` | uuid not null | FK `(tenant_id, id)` |
| `branch_id` | uuid not null | FK; every request in the group uses it |
| `combined_total_amount` / `_currency` | numeric(18,4) / text | Sum of the requests' estimated totals at preparation |
| `best_single_total_amount` / `_currency` | numeric(18,4) / text | From the job result |
| `saving_amount` / `_currency` | numeric(18,4) / text | best single − combined, ≥ 0 |
| `idempotency_key` | uuid not null | unique (tenant_id, idempotency_key) |
| `created_by_membership_id` | uuid not null | FK `(tenant_id, id)` → membership |
| `created_at` | timestamptz | |

Each amount has a currency column next to it, with a check that the two are null together
(Constitution VII).

**RLS:**

- select: members of the tenant (same visibility as `purchase_request`);
- insert: owner or buyer, `WITH CHECK tenant_id = current_tenant_id()`;
- no update or delete for client roles. The group is immutable evidence, and its state is the
  state of its requests.

## Changed: `purchase_request`

| Column | Type | Notes |
|---|---|---|
| `request_group_id` | uuid null | FK `(tenant_id, request_group_id)` → `purchase_request_group (tenant_id, id)` |

The service enforces that all requests of a group share one status. A test asserts that no group
ever has mixed statuses after any group action.

## Changed: `approval_step.source`

New value `group_threshold_match`, used when the approver was resolved from the group's combined
total. `owner_fallback` still applies.

## Request group state (derived from its requests)

```text
draft ──submit group──▶ submitted ──approve group──▶ approved ──(each)──▶ PO per request
  │                        │
  └─withdraw group──▶ withdrawn  └─reject group──▶ rejected
```

Single-request transitions on a grouped request are refused with 409 `part_of_split`.

## Audit events

| Action | Target |
|---|---|
| `offers.rfq_split_started` | `rfq_id`, `basket_split_job_id`, `price_quotation_ids` |
| `requests.group_prepared` | `request_group_id`, `rfq_id`, `basket_split_job_id`, `purchase_request_ids`, totals |
| `requests.group_submitted` / `group_approved` / `group_rejected` / `group_withdrawn` | `request_group_id`, `purchase_request_ids`, `approval_step_ids`, actor, comment |

## API shape addition

`PurchaseRequest.request_group`:

```json
{"id": "…", "rfq_id": "…", "position": 1, "size": 2,
 "combined_total": {"amount": "4063.00", "currency": "SAR"},
 "best_single_total": {"amount": "4137.00", "currency": "SAR"},
 "saving": {"amount": "74.00", "currency": "SAR"},
 "sibling_request_ids": ["…"]}
```

The value is `null` for an ordinary request.
