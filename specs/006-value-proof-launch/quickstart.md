# Quickstart: Value Proof + Launch Readiness

This walkthrough assumes the developer already has chunk 4.5 data: an active workspace product,
reviewed quotation lines, confirmed matches, landed-cost rows, and a compare recommendation visible
from `/offers/compare`.

Base URL: `/api/v1`
Auth: `Authorization: Bearer <supabase_jwt>`

## 1. Confirm the Compared Product Has Price History

```bash
curl -sS "$API_URL/api/v1/products/$WORKSPACE_PRODUCT_ID/price-history?window_months=6" \
  -H "Authorization: Bearer $TOKEN"
```

Confirm the response has `summary.last_paid` or `summary.average_paid_rolling_window`. The savings
service will read this same price-history model when recording the purchase outcome; it will not
run a separate baseline algorithm.

## 2. Record the Actual Purchase Outcome

```bash
curl -sS -X POST "$API_URL/api/v1/purchases" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -d '{
    "workspace_product_id": "'"$WORKSPACE_PRODUCT_ID"'",
    "supplier_id": "'"$SUPPLIER_ID"'",
    "quotation_line_id": "'"$QUOTATION_LINE_ID"'",
    "match_decision_id": "'"$MATCH_DECISION_ID"'",
    "landed_cost_id": "'"$LANDED_COST_ID"'",
    "quantity": "10.000000",
    "base_unit": "each",
    "unit_price": { "amount": "8.8000", "currency": "GBP" },
    "total_paid": { "amount": "88.0000", "currency": "GBP" },
    "delivery_result": "delivered",
    "ordered_at": "2026-08-21T09:00:00Z",
    "delivered_at": "2026-08-21T11:00:00Z"
  }'
```

Expected result: `201 Created` with a `purchase_record` and a paired `saving_record` in
`pending` status. The baseline, actual, and delta are already stored. Verification later will not
recompute them.

## 3. Read the Ledger and Evidence

```bash
curl -sS "$API_URL/api/v1/savings?status=pending&limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

```bash
curl -sS "$API_URL/api/v1/savings/$SAVING_RECORD_ID/evidence" \
  -H "Authorization: Bearer $TOKEN"
```

Expected evidence: the saving row, purchase record, originating quotation/line where present,
competing offers from the compare context, and the stored calculation inputs.

## 4. Verify the Saving

Owner or buyer may verify, including the buyer who recorded the outcome.

```bash
curl -sS -X POST "$API_URL/api/v1/savings/$SAVING_RECORD_ID/verify" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $VERIFY_IDEMPOTENCY_KEY"
```

Expected result: the same `saving_record` with `status: "verified"`, `verified_at`, and
`verified_by` set. Baseline, actual, delta, source IDs, and calculation inputs are unchanged.

After this point, any attempt to update or delete the row must be refused by the database
immutability trigger.

## 5. Export the Verified Ledger

```bash
curl -sS -X POST "$API_URL/api/v1/exports" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $EXPORT_IDEMPOTENCY_KEY" \
  -d '{
    "kind": "savings_ledger",
    "format": "xlsx",
    "filters": {
      "period_start": "2026-08-01",
      "period_end": "2026-08-31",
      "supplier_id": "'"$SUPPLIER_ID"'",
      "branch_id": null
    }
  }'
```

Expected result: `202 Accepted` with an `export_job` in `queued` status.

Poll until terminal:

```bash
curl -sS "$API_URL/api/v1/exports/$EXPORT_JOB_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Expected terminal result:

- `completed` with `row_count >= 0` and a `download_url`, including the empty-export case.
- `failed` with structured `error` JSON if rendering or storage upload failed.

Repeat with `"format": "pdf"` to exercise PDF rendering.

## 6. Check Current Plan and Catalogue Limit

```bash
curl -sS "$API_URL/api/v1/billing/account" \
  -H "Authorization: Bearer $TOKEN"
```

Expected result: a `billing_account` assigned by the stub provider, normally on `starter`.

```bash
curl -sS "$API_URL/api/v1/billing/limits/active-catalogue-products" \
  -H "Authorization: Bearer $TOKEN"
```

Expected starter-plan values:

```json
{
  "resource": "active_catalogue_products",
  "plan_code": "starter",
  "limit": 100,
  "used": 42,
  "remaining": 58,
  "allowed": true
}
```

When the workspace reaches 100 active catalogue products, creating or unarchiving another active
product must return a clear plan-limit error instead of silently allowing product 101.

## 7. Launch-Readiness Audit

Run the whole-product accessibility and RTL suite in both locales after the value-proof flows pass.
The scan covers:

- auth and onboarding
- catalogue
- quotations
- matching
- offers
- alerts
- new savings, exports, and billing screens

The chunk is not complete while any known WCAG 2.1 AA or RTL layout issue remains unfixed.
