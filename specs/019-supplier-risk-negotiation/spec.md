# Feature Specification: R4.1 Supplier IQ v2 and Negotiation Briefs

**Feature Branch**: `019-supplier-risk-negotiation`
**Created**: 2026-09-20
**Status**: Draft for approval
**Roadmap Release**: R4.1, Phase 4 Predictive Procurement
**Input**: Product-owner direction to proceed with R4.1 while keeping G3 unmet.

## Release posture

G3 remains unmet. R4.1 is an implementation exception, not a gate pass or commercial validation.
Every v2 scorecard and negotiation brief carries `release_posture = g3_unmet`. Synthetic records
may verify behavior but do not count toward G3 evidence.

## User stories

### US1 - Review tenant-wide supplier risk (P1)

As a buyer, I can scan active suppliers by risk level, confidence, evidence sufficiency, validity,
and highest-ranked risk driver so I know which supplier relationship needs attention.

**Acceptance scenarios**

1. Given suppliers with v2 snapshots, when a member opens the risk queue, then only the latest
   tenant-visible snapshot per supplier is shown with cursor pagination capped at 100.
2. Given fewer than three calculable components, when a supplier is listed, then it is labelled
   `insufficient_data` and has no overall score or negotiation action.
3. Given mixed-currency purchasing, when concentration is shown, then each currency bucket is
   separate and no converted or summed amount is displayed.

### US2 - Inspect risk evidence and trends (P1)

As a buyer, I can inspect concentration, price drift, reliability decay, and single-source
exposure with calculations, confidence, dates, and source records before acting.

**Acceptance scenarios**

1. Given a v2 scorecard, when the buyer opens it, then every metric shows its calculation inputs,
   sample count, evidence window, confidence, validity, and source links.
2. Given a supplier ID from another tenant, when it is requested, then the API returns the
   standard not-found envelope and reveals no existence information.
3. Given fewer than 180 observed days but at least three calculable components, when the scorecard
   is shown, then its state is `provisional` and the observed window remains visible.

### US3 - Prepare an evidence-backed negotiation brief (P1)

As an owner or buyer, I can prepare a negotiation brief from the latest valid scorecard so I can
conduct a human-led supplier conversation using traceable evidence.

**Acceptance scenarios**

1. Given a valid sufficient or provisional v2 snapshot, when an owner or buyer prepares a brief,
   then the response includes ranked talking points covering available price, volume,
   alternatives, service, payment, and purchase-frequency evidence.
2. Given the same supplier, snapshot, brief version, and idempotency key, when preparation is
   replayed, then the original brief is returned and no duplicate rows are created.
3. Given an insufficient or expired snapshot, when brief preparation is attempted, then the API
   rejects it with the standard unprocessable-entity envelope and creates no partial records.
4. Given a prepared brief, when it is viewed, then each talking point shows evidence, confidence,
   risk, validity, and a localized suggested question; no supplier communication is sent.

### US4 - Record a human brief decision (P2)

As an owner or buyer, I can acknowledge or dismiss a brief while preserving an append-only action
history.

**Acceptance scenarios**

1. Given a prepared brief, when it is acknowledged, then an immutable action and audit event are
   appended and the derived status becomes acknowledged.
2. Given a dismissal with a reason, when the request is replayed with the same idempotency key,
   then only one dismissal action exists.
3. Given an ordinary requester, when a mutation is attempted, then the API returns forbidden;
   read access remains available within that requester's tenant.

## Functional requirements

- **FR-001**: R4.1 MUST extend the existing Supplier IQ service, scorecard snapshot, scorecard
  endpoint, and scorecard UI; it MUST NOT create a second supplier-risk source of truth.
- **FR-002**: V2 risk MUST use deterministic rule versions `supplier-scorecard-v2` and
  `supplier-risk-v2`, `Decimal` arithmetic, a source fingerprint, and an explicit 180-day default
  evidence window split into equal 90-day baseline and current periods.
- **FR-003**: Concentration MUST be calculated independently per currency as supplier qualifying
  purchase-order spend divided by tenant qualifying purchase-order spend. Qualifying statuses are
  submitted, confirmed, partially received, received, and closed. The risk component MUST use the
  highest qualifying currency share and MUST NOT convert or add currencies.
- **FR-004**: Price drift MUST compare median normalized unit price by product, base unit, and
  currency between current and baseline periods using landed-cost record time. Zero baseline
  medians MUST be excluded and reported. Risk MUST equal
  `clamp(max(median_drift, 0) / 0.20, 0, 1)`.
- **FR-005**: Reliability MUST derive order completion from cumulative append-only receipt lines.
  It MUST exclude draft/cancelled orders, orders without expected dates, and not-yet-due open
  orders. Orders MUST be assigned to baseline or current periods by expected delivery date. Risk
  MUST be the greater of current failure rate and normalized positive reliability decay, with 25
  percentage points of decay equal to maximum decay risk.
- **FR-006**: Single-source exposure MUST be the share of purchased products lacking another
  active supplier with a valid, currency-compatible landed-cost observation for the same product
  and base unit.
- **FR-007**: Overall risk weights MUST be concentration 30%, price drift 25%, reliability 25%,
  and single-source exposure 20%. Exactly three available components MAY be renormalized;
  fewer than three MUST produce `insufficient_data` with no overall score.
- **FR-008**: Risk levels MUST be `low` for scores below 0.35, `medium` for scores from 0.35 up to
  but excluding 0.65, and `high` for scores at or above 0.65.
- **FR-009**: Count-based metrics MUST require at least 3 qualifying observations. Confidence
  MUST be low below 3, medium from 3 through 9, and high at 10 or more; product-coverage metrics
  MUST also require at least 3 distinct products.
- **FR-010**: Snapshot state MUST be `ready` only when all four components are calculable with
  high confidence and observed history covers at least 180 days; `provisional` when at least three
  are calculable but maturity or confidence is lower; otherwise it MUST be `insufficient_data`.
- **FR-011**: Negotiation briefs MUST rank deterministic talking points from available historical
  price, currency-specific spend and volume, alternatives, delivery/reconciliation/quality
  performance, payment context, and purchase frequency.
- **FR-011A**: A brief MUST contain at most one available talking point for each category: price
  trajectory, alternatives, service performance, concentration and volume, payment context, and
  purchase pattern. Service risk MUST be the highest of reliability risk, non-matched qualifying
  three-way result rate, and quality incidents per qualifying completed order. Payment risk MUST
  equal overdue open bills divided by due open bills. Spend, quantities per base unit, and purchase
  frequency MUST remain context values rather than invented risk.
- **FR-011B**: Talking-point categories MUST sort by descending risk and then by the fixed category
  order in FR-011A. Purchase frequency requires at least four order dates to produce three
  intervals.
- **FR-012**: Payment context MUST use supplier payment terms and normalized accounting evidence.
  Open-overdue claims MUST require a provider due date. Paid-lateness MUST NOT be asserted without
  a provider-paid date, and timestamps such as `updated_at` MUST NOT be used as payment dates.
- **FR-013**: Brief text MUST be rendered from typed talking-point data and shared English/Arabic
  i18n keys. R4.1 MUST NOT store or display ungrounded generated prose.
- **FR-014**: Every derived metric and talking point MUST expose source record links, calculation
  version, confidence, risk, evidence window, and validity. Monetary values MUST include currency.
- **FR-015**: Existing v1 scorecard snapshots MUST remain readable. V2 normalized metric and
  evidence rows MUST be immutable and linked to the existing snapshot header.
- **FR-016**: Brief headers and items MUST be immutable. Acknowledgement and dismissal MUST append
  immutable action rows; current status MUST be derived from the latest action.
- **FR-017**: Owners and buyers MAY recompute scorecards, prepare briefs, acknowledge, and dismiss.
  All tenant members MAY read tenant-visible risk and brief data.
- **FR-018**: Every mutation MUST require `Idempotency-Key`, execute atomically, and append an
  audit event. Failure MUST leave no partial snapshot, metric, evidence, brief, item, or action.
- **FR-019**: Every new tenant-scoped table MUST carry `tenant_id`, composite tenant foreign keys,
  forced RLS, policies with `USING` and `WITH CHECK`, and automated cross-tenant isolation tests.
- **FR-020**: Unknown and cross-tenant supplier, snapshot, and brief identifiers MUST return the
  standard not-found envelope.
- **FR-021**: Risk and brief lists MUST use cursor pagination with limits from 1 through 100 and
  return only the latest applicable snapshot per supplier.
- **FR-022**: Every v2 response and stored header MUST expose `release_posture = g3_unmet` without
  changing G3 evidence.
- **FR-023**: All user-facing strings MUST come from shared English and Arabic catalogues; the UI
  MUST support RTL, keyboard operation, and WCAG 2.1 AA.
- **FR-024**: No R4.1 operation may email or message a supplier, dispatch an RFQ, create or mutate
  a purchase request or purchase order, approve spending, or execute a purchase.

## Data model

### Extended `supplier_scorecard_snapshot`

Existing immutable header and compatibility JSON cache, extended with `state`, `confidence`,
`release_posture`, `valid_from`, `valid_until`, `source_fingerprint`, and
`observed_history_days`. Existing v1 rows are not rewritten.

### Extended `synced_bill`

Adds nullable provider-derived `due_date`, `remaining_balance_amount`, and
`remaining_balance_currency`. The amount and currency are paired. Historical or provider-missing
values remain null and cannot support overdue-payment claims.

### `supplier_scorecard_metric`

Immutable normalized metric rows with tenant and snapshot keys, metric kind, scalar value,
numerator, denominator, optional amount/currency, sample count, confidence, insufficiency flag,
baseline/current windows, and calculation version.

### `supplier_scorecard_evidence`

Immutable metric-source links. Exactly one typed, tenant-pinned source reference is present per
row: purchase order, delivery receipt, landed cost, three-way match, synced bill, workspace
product, delivery quality issue, or supplier commercial term.

### `negotiation_brief`

Immutable supplier/snapshot header with brief version, source fingerprint, release posture,
validity, creator, and creation timestamp. Unique by tenant, supplier, snapshot, and version.

### `negotiation_brief_item`

Immutable ranked and typed talking point with calculation version, scalar or monetary value,
confidence, risk, validity, i18n question key, and optional scorecard metric reference.

### `negotiation_brief_item_evidence`

Immutable links from brief items to one or more normalized scorecard evidence rows. Every talking
point must have at least one evidence link before the brief transaction may commit.

### `negotiation_brief_action`

Append-only `acknowledged` or `dismissed` event with actor, reason where required, idempotency key,
and timestamp. Brief status is derived from the latest action; no brief row is updated.

## API contract

- `GET /api/v1/suppliers/{supplier_id}/scorecard`
- `POST /api/v1/supplier-iq/recompute`
- `GET /api/v1/supplier-iq/risks`
- `POST /api/v1/suppliers/{supplier_id}/negotiation-briefs`
- `GET /api/v1/negotiation-briefs`
- `GET /api/v1/negotiation-briefs/{brief_id}`
- `POST /api/v1/negotiation-briefs/{brief_id}/acknowledge`
- `POST /api/v1/negotiation-briefs/{brief_id}/dismiss`

## Success criteria

- Pure unit tests reproduce every score bit-identically for pinned source fixtures and cover all
  thresholds and exclusions.
- Existing scorecard consumers continue to pass against v2-compatible responses.
- Hosted RLS checks prove tenant A cannot read, create, mutate, or enumerate tenant B evidence.
- A failed recompute or brief creation leaves zero partial rows.
- Replaying every mutation returns the original result without duplicate evidence or actions.
- A prepared brief contains only source-linked talking points and sends zero external messages.
- English and Arabic/RTL UI tests pass with zero automated accessibility violations.
- Full API tests, Angular tests, production build, migration verification, and physical API
  consumption pass while G3 remains recorded as unmet.

## Out of scope

- Generative prose, machine-learning risk models, and cross-tenant benchmarking.
- Currency conversion or an inferred tenant default currency.
- Supplier messaging, RFQ dispatch, and autonomous negotiation.
- Purchase-request or purchase-order creation, approval, submission, or payment.
