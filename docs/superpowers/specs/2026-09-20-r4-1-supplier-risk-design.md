# R4.1 Supplier IQ v2 and Negotiation Briefs

**Status:** Revised after architecture review; pending final approval
**Date:** 2026-09-20
**Gate posture:** R4.1 proceeds under the recorded G3 exception. G3 remains unmet.

## Goal

Extend the existing Supplier IQ scorecard into a versioned supplier-risk model and turn its
evidence into a human-reviewable negotiation brief. R4.1 must reuse the current scorecard API,
snapshot history, and UI instead of introducing a second supplier-risk source of truth.

The release remains advisory. It does not contact suppliers, dispatch an RFQ, authorise a
purchase, or claim savings that cannot be traced to source records.

## Existing foundation

R2.4 already delivers `SupplierIqService`, `supplier_scorecard_snapshot`,
`GET /api/v1/suppliers/{supplier_id}/scorecard`, and the supplier scorecard route. R4.1 evolves
that implementation to rule version `supplier-scorecard-v2` and risk version
`supplier-risk-v2` while preserving the v1 snapshot history and response compatibility needed
by existing consumers.

The existing JSON snapshot columns remain a backward-compatible cache. New normalized metric
and evidence rows become the auditable source for v2 calculations and negotiation briefs.

## Risk model

### Evidence window

- The default window is 180 days ending on the calculation date.
- The current period is the final 90 days; the baseline period is the preceding 90 days.
- A caller may request 1-24 months for scorecard inspection, but v2 trend metrics require two
  equal half-windows and disclose their exact dates.
- `ready` requires all four risk components, high confidence, and at least 180 observed days.
- `provisional` requires at least three components but has less than 180 observed days or any
  component below high confidence.
- `insufficient_data` applies when fewer than three components are calculable. It has no overall
  score or risk level.

### Confidence

For count-based metrics, fewer than 3 qualifying observations is insufficient, 3-9 is medium
confidence, and 10 or more is high confidence. A ratio that depends on product coverage also
requires at least 3 distinct products. Overall confidence is the lowest confidence among the
components included in the score.

### Components

All component risks are decimal values from 0 to 1. Values are rounded only when serialized;
calculations use `Decimal` throughout.

1. **Concentration risk (30%)**
   - For each currency, divide the supplier's submitted, confirmed, partially received, received,
     or closed purchase-order spend by total tenant purchase-order spend in the same currency and
     evidence window.
   - Never add amounts across currencies. The displayed metric contains every currency bucket.
   - The risk component is the highest qualifying currency share. Each bucket must have at least
     3 tenant orders and at least 1 supplier order.

2. **Price-drift risk (25%)**
   - For each product, base unit, and currency with observations in both half-windows, calculate
     `(current median normalized unit price / baseline median) - 1`.
   - Observations are assigned by landed-cost record time. A product with a zero baseline median
     is excluded and reported rather than divided by zero.
   - The supplier drift is the median of the comparable product drifts.
   - Risk is `clamp(max(drift, 0) / 0.20, 0, 1)`. A 20% or greater median increase is maximum
     drift risk; decreases do not create negative risk.

3. **Reliability risk and decay (25%)**
   - Include non-cancelled orders with an expected delivery date and enough receipt evidence to
     determine completion.
   - Completion date is the earliest receipt date at which cumulative received quantity reaches
     ordered quantity for every order line. Partial receipts remain incomplete until that point.
   - On-time rate is completed-on-or-before-expected orders divided by qualifying orders.
   - Orders are assigned to baseline or current periods by expected delivery date.
   - Decay is `baseline on-time rate - current on-time rate`.
   - Risk is the greater of `1 - current on-time rate` and
     `clamp(max(decay, 0) / 0.25, 0, 1)`.
   - Draft and cancelled orders, orders without expected dates, and still-open orders not yet due
     are excluded and reported in evidence counts.

4. **Single-source exposure (20%)**
   - Start with distinct products purchased from the supplier in the evidence window.
   - A product has an alternative when another active supplier has a valid, currency-compatible
     landed-cost observation for the same normalized product and base unit in the window.
   - Risk is `products_without_alternatives / qualifying_products`.

The overall score is the weighted sum of available components. Weights are renormalized only
when exactly three components are available; fewer than three produces `insufficient_data`.
Risk levels are `low` below 0.35, `medium` from 0.35 up to but excluding 0.65, and `high` at
0.65 or above.

## Negotiation brief

A buyer or owner creates a brief from the latest non-expired v2 scorecard snapshot. Creation is
idempotent for `(tenant, supplier, snapshot, brief_version)`.

The brief ranks deterministic talking points derived from:

- historical spend and order volume per currency;
- price trajectory and comparable alternatives;
- current delivery reliability and reliability decay;
- reconciliation discrepancy rate and delivery-quality incidents;
- purchase frequency, expressed as order count and median days between orders;
- payment context: configured supplier payment terms, paid/open bill counts, overdue open bill
  count, and amount per currency.

The brief contains at most one available point in each category: price trajectory, alternatives,
service performance, concentration and volume, payment context, and purchase pattern. Risk-bearing
points use their normalized component or incident rate. Service performance uses the highest of
reliability, non-matched three-way result rate, and quality-incident rate. Payment risk is overdue
open bills divided by due open bills. Spend, quantities per base unit, and purchase frequency are
context values within their category, not invented risk. Categories sort by descending risk and
then by the fixed order shown above. Purchase frequency requires at least four order dates so its
median is based on at least three intervals.

`synced_bill.due_date` and remaining balance are added to the normalized accounting record and
populated by supported connectors. No paid-lateness assertion is made without a provider-paid
date. Missing payment evidence is labelled unavailable rather than inferred from `updated_at`.

Each talking point stores its kind, rank, calculation version, numeric values, currency where
applicable, confidence, risk, validity period, and links to normalized evidence rows. Display
copy and suggested questions are selected from English and Arabic i18n keys; generated prose is
not stored and no ungrounded text model is used.

The user action is **Prepare negotiation brief**, which creates the immutable brief. A prepared
brief can be acknowledged or dismissed through append-only action events. It is never sent to a
supplier and it does not alter a purchase request or purchase order.

## Data model

### Existing table retained

`supplier_scorecard_snapshot` remains the snapshot header and compatibility cache. A forward-only
migration adds `state`, `confidence`, `release_posture`, `valid_from`, `valid_until`, and
`source_fingerprint`, plus `observed_history_days`. Existing v1 rows remain valid historical
records.

`synced_bill` gains nullable provider-derived `due_date`, `remaining_balance_amount`, and
`remaining_balance_currency` fields. Amount and currency are constrained as a pair. Connectors
populate only values supplied by the provider; historical rows remain null and cannot support an
overdue-payment assertion.

### New normalized tables

- `supplier_scorecard_metric`: immutable child rows keyed by snapshot and metric kind. It stores
  value, numerator, denominator, sample count, confidence, sufficiency, window dates, amount and
  currency where applicable, and calculation version.
- `supplier_scorecard_evidence`: immutable links from a metric to exactly one tenant-pinned
  source record. Nullable composite foreign keys cover purchase orders, delivery receipts,
  landed costs, three-way matches, synced bills, workspace products, quality issues, and supplier
  commercial terms; a check constraint requires exactly one source target per row.
- `negotiation_brief`: immutable header linked to supplier and scorecard snapshot, with version,
  release posture, validity period, creator, and deterministic fingerprint.
- `negotiation_brief_item`: immutable ranked talking points with typed calculation fields and an
  optional link to the supporting scorecard metric.
- `negotiation_brief_item_evidence`: immutable many-to-many links from each brief item to the
  normalized scorecard evidence rows that justify it.
- `negotiation_brief_action`: append-only `acknowledged` or `dismissed` events. Current status is
  derived from the latest event; recommendation outcome history is never overwritten.

Every table carries `tenant_id`, composite tenant foreign keys, indexes, forced RLS, and policies
with both `USING` and `WITH CHECK`. Snapshot, metric, evidence, brief, item, and action rows expose
no update or delete path to authenticated or service roles.

## API

### Existing endpoint evolved

- `GET /api/v1/suppliers/{supplier_id}/scorecard`
  - Returns Supplier IQ v2 by default while preserving existing top-level fields.
  - Adds state, risk level, release posture, validity, currency buckets, and source-link metadata.
  - Unknown and cross-tenant supplier IDs return the standard not-found envelope.

### New endpoints

- `POST /api/v1/supplier-iq/recompute` - owner or buyer; recomputes all visible active suppliers.
- `GET /api/v1/supplier-iq/risks` - any tenant member; cursor-paginated latest snapshots.
- `POST /api/v1/suppliers/{supplier_id}/negotiation-briefs` - owner or buyer; creates or replays a
  brief from the latest valid v2 snapshot.
- `GET /api/v1/negotiation-briefs` - any tenant member; cursor-paginated briefs.
- `GET /api/v1/negotiation-briefs/{brief_id}` - any tenant member; brief, items, and evidence.
- `POST /api/v1/negotiation-briefs/{brief_id}/acknowledge` - owner or buyer; idempotent action.
- `POST /api/v1/negotiation-briefs/{brief_id}/dismiss` - owner or buyer; reason required and
  idempotent by `Idempotency-Key`.

All mutation routes require `Idempotency-Key`, append an audit event, and execute snapshot header,
metric, evidence, brief, item, item-evidence, and action writes within one database transaction.
Partial snapshots, briefs, and actions are rolled back.

## Web experience

The existing supplier scorecard becomes the detail experience for v2 metrics. A new Supplier
Risk queue provides tenant-wide scanning by risk level, confidence, state, evidence age, and
highest-ranked driver. It links to the existing scorecard rather than duplicating it.

The scorecard exposes Prepare negotiation brief only when a valid v2 snapshot has sufficient or
provisional evidence. The brief detail shows calculations and source links before suggested
questions. Insufficient, mixed-currency, missing-payment, stale, and G3-unmet states remain
visible. All copy comes from shared English and Arabic catalogues and layouts use logical CSS.

## Error policy

- No supplier evidence returns `insufficient_data`, never zero risk.
- Fewer than three calculable risk components suppresses the overall score and brief action.
- Mixed currencies remain separate buckets and are never converted or summed.
- Missing due dates suppress overdue-payment claims.
- An expired snapshot requires recomputation before brief creation.
- Database failures use the standard service-unavailable envelope and roll back the transaction.
- Arithmetic or validation failures create no snapshot and emit a failed audit event.

## Verification

- Unit tests cover every formula, boundary, exclusion, confidence state, currency bucket, weight
  renormalization, fingerprint, and talking-point rank.
- Integration tests prove transaction rollback, append-only grants, forced RLS, composite tenant
  foreign keys, and cross-tenant invisibility for every new table and route.
- Contract tests cover RBAC, idempotent replay, pagination, not-found behavior, and response
  compatibility for the existing scorecard endpoint.
- Angular tests cover risk scanning, evidence links, prepared/dismissed states, English,
  Arabic/RTL, keyboard navigation, and zero automated accessibility violations.
- Hosted migration verification, full API and web suites, production build, and physical API
  consumption are required before release.

## Explicit non-goals

- No machine-learning or generative-text risk model.
- No cross-tenant benchmarking.
- No currency conversion.
- No supplier messaging, RFQ dispatch, or autonomous negotiation.
- No autonomous approval or purchasing.
