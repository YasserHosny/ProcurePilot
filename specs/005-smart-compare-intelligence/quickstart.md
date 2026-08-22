# Quickstart: Smart Compare + Intelligence

**Prerequisite**: Use a workspace that already has at least one reviewed quotation line from chunk
4.3, a final `match_decision` from chunk 4.4, and a `landed_cost` row for that decision.

All requests use:

```bash
API=http://localhost:8000/api/v1
TOKEN=<supabase_jwt_with_tenant_id_claim>
PRODUCT_ID=<workspace_product_id>
SUPPLIER_A=<supplier_uuid>
SUPPLIER_B=<supplier_uuid>
```

## 1. Compare Offers for a Product

Fetch the compare payload for an already matched and costed product:

```bash
curl -sS "$API/offers/compare?product_id=$PRODUCT_ID&quantity=10.000000" \
  -H "Authorization: Bearer $TOKEN"
```

Expected result:

- `offers[]` contains one current offer per eligible supplier.
- Every money field is `{ "amount": "...", "currency": "..." }`.
- `recommendation` names exactly one offer when any non-expired offer exists.
- `recommendation.evidence` includes score components and tie-break evidence when applicable.
- `stock_signal` is `null` in this chunk because there is no inventory source yet.

To inspect raw offers including expired prices:

```bash
curl -sS "$API/offers?product_id=$PRODUCT_ID&quantity=10.000000&include_expired=true" \
  -H "Authorization: Bearer $TOKEN"
```

## 2. View Price History

```bash
curl -sS "$API/products/$PRODUCT_ID/price-history?window_months=6" \
  -H "Authorization: Bearer $TOKEN"
```

Expected result:

- `points[]` is built from existing `landed_cost` rows.
- `summary.last_paid` points to the latest record-time row.
- `summary.average_paid_rolling_window` uses the trailing six months.
- `summary.best_price` points to the lowest normalised unit price on record.

## 3. Submit a Two-Supplier Basket Split

```bash
curl -sS -X POST "$API/baskets/optimise" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: 11111111-1111-4111-8111-111111111111" \
  -H "Content-Type: application/json" \
  -d "{
    \"supplier_ids\": [\"$SUPPLIER_A\", \"$SUPPLIER_B\"],
    \"items\": [
      { \"workspace_product_id\": \"$PRODUCT_ID\", \"quantity\": \"10.000000\" }
    ]
  }"
```

The response is a `BasketSplitJob` with `status: "queued"` and a pollable `result_url`.

Poll until `status` is `completed` or `failed`:

```bash
JOB_ID=<basket_split_job_id>

curl -sS "$API/baskets/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN"
```

For a feasible basket, `result.feasible` is `true`, `allocation[]` assigns each item to one of the
two named suppliers, and `total_landed_cost` is a Money object.

For an infeasible basket, `status` is still `completed`, but `result.feasible` is `false` and
`result.infeasible_items[]` names each product that neither selected supplier can supply.

## 4. See and Dismiss an Alert

Create one current alert condition in fixture data, such as:

- a recommended offer expiring within 7 days,
- a preferred supplier with historical offers but no current eligible offer, or
- a current recommended price at least 15% away from the trailing six-month average.

Then list alerts:

```bash
curl -sS "$API/alerts?limit=50" \
  -H "Authorization: Bearer $TOKEN"
```

Dismiss one alert by its deterministic id:

```bash
ALERT_ID=<alert_fingerprint>

curl -sS -X POST "$API/alerts/$ALERT_ID/dismiss" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: 22222222-2222-4222-8222-222222222222"
```

Re-list alerts. The same fingerprint no longer appears. If the underlying condition changes later,
the recurrence key changes and a new alert can appear.
