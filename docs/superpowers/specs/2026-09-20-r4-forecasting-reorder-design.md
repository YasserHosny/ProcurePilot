# R4.0 Forecasting and Reorder Proposals

## Exception and release posture

This work intentionally starts before G3 is passed at the product owner's direction. G3
remains recorded as unmet and its commercial evidence is not changed by this release. R4.0
is implemented as a controlled release with explicit `g3_unmet` metadata on every forecast,
synthetic data confined to tests, and no claim that the forecasting model is commercially
validated.

The G3 exception permits implementation of R4.0 only; it does not waive tenant isolation,
provenance, uncertainty, human authorisation, currency, i18n, or the no-autonomous-purchase
rules in the constitution.

## Scope

R4.0 adds demand forecasts and reorder proposals for matched POS products. The service uses
the existing `synced_product_signal` velocity and stock fields, returns a forecast horizon,
uncertainty interval, evidence window, confidence, validity, and an explicit cold-start state.
Owners and buyers can prepare a draft purchase request from a proposal; the proposal never
creates, submits, approves, or sends an order automatically.

Supplier risk, negotiation briefs, grounded analyst answers, RFQ automation, and a second
forecast provider remain outside this release.

## Architecture

- `forecasting` is a new API module. It reads POS signals through a narrow query boundary and
  writes immutable forecast snapshots and reorder-proposal state transitions.
- `demand_forecast` stores one immutable forecast snapshot per product and run. It includes
  source signal identity, model version, source window, observed history, uncertainty bounds,
  confidence, validity, and the explicit `g3_unmet` release marker.
- `reorder_proposal` stores the human workflow around a forecast. It is tenant-scoped and
  append-only for decisions: a preparation action creates a draft purchase request and records
  the link; no purchase order is executed.
- All new tables use forced RLS with tenant-scoped `USING` and `WITH CHECK` policies. Reads
  from another tenant resolve to not found through the normal authenticated query path.
- Forecast calculation is a deterministic pure function. With the same velocity, stock,
  horizon, safety factor, and model version it returns the same values.

## Forecast contract

For the initial model, expected demand is `sales_velocity_per_day * horizon_days`. Safety stock
is `expected_daily_demand * safety_days`. Suggested quantity is `max(0, expected demand + safety
stock - stock_on_hand)`, rounded up to the product's normalised base unit. The initial uncertainty
band widens when the signal has less observed history and is recorded as a quantity interval,
not a percentage hidden in UI copy.

Signals with no matched product, no velocity, or no stock figure produce a visible
`insufficient_data` result and no suggested quantity. Results with less than 180 days of history
are marked `provisional`; this makes the pre-G3 exception visible rather than silently treating
30-day POS data as a validated long-horizon forecast.

## API and user flow

- `GET /api/v1/forecasting/reorder-proposals` lists the latest proposals with cursor pagination.
- `POST /api/v1/forecasting/reorder-proposals/{id}/prepare-request` accepts a branch, date, and
  optional cost centre, creates a draft purchase request through the existing requests service,
  and marks the proposal prepared. It is idempotent by proposal and branch.
- A web forecasting screen shows proposal state, stock, expected demand, uncertainty, evidence
  age, confidence, validity, and the G3-unmet warning. Its primary action is `Prepare draft
  request`; it never displays an auto-order action.

## Verification

Unit tests cover deterministic math, rounding, uncertainty widening, and cold-start behavior.
Integration tests cover tenant isolation, RLS, latest-proposal selection, idempotent request
preparation, and the absence of purchase-order side effects. Contract tests cover response
shape and error envelopes. Angular tests cover loading, empty, provisional, insufficient-data,
and prepared states in both locales.

