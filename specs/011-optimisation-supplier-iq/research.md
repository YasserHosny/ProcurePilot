# Phase 0 Research: Optimisation and Supplier IQ

## R1 - Optimiser scope and solver strategy

**Decision**: Extend the existing `services/optimiser` worker and CP-SAT solver rather than adding
a new optimisation service. R2.4 supports up to 10 selected eligible suppliers and 50 basket lines
per job. It keeps jobs asynchronous through `basket_split_job`, with a versioned request snapshot
and result payload.

**Rationale**: The constitution pre-authorises the optimiser as the one candidate for service
extraction when load justifies it. A second optimiser would split ownership and replay semantics.
The current worker already owns queue processing and result status transitions.

## R2 - Commercial constraints

**Decision**: Model supplier commercial terms as versioned, tenant-scoped data: minimum order
value, delivery fee, free-delivery threshold, and quantity tiers. The optimiser treats MOV,
selected supplier exclusion, currency consistency, and requested urgency as hard constraints.
Preferred supplier weighting, supplier risk, lead time, and price competitiveness are soft scoring
terms.

**Rationale**: Supplier terms change over time and must be replayable. Hard and soft constraints
must be separated so users understand why a result is infeasible versus merely less preferred.

## R3 - Supplier scorecard metrics

**Decision**: Compute scorecards from existing data: `supplier`, `landed_cost`, `quotation`,
`purchase_request`, `purchase_request_line`, `delivery_quality_issue`, `purchase_record`,
`saving_record`, and alert evidence. Metrics include price competitiveness, lead-time reliability,
delivery fulfilment, quality incident rate, spend exposure, quotation freshness, and savings
contribution.

**Rationale**: R2.4 should use outcome history already captured by earlier releases. A separate
manual supplier-review marketplace is explicitly out of scope.

**Sparse-data rule**: Each metric carries `sample_count`, `window_start`, `window_end`,
`confidence`, and `insufficient_evidence`. Missing history lowers confidence; it never becomes a
perfect score.

## R4 - Risk score v1

**Decision**: Risk score v1 is deterministic and rules-based:

- delivery fulfilment and short delivery discrepancies
- quality issue rate and trend
- price volatility versus product history
- quotation freshness and expiry exposure
- lead-time reliability
- concentration/spend exposure

The score is represented as sub-scores plus a weighted total and a rule version.

**Rationale**: There is not enough labelled supplier-risk history for an opaque model. The buyer
must see why a supplier is risky before accepting a recommendation.

## R5 - Anomaly detection v1

**Decision**: Add rules-based live alert kinds:

- `price_spike`
- `likely_duplicate_quotation_line`
- `decimal_or_quantity_anomaly`
- `delivery_cost_anomaly`
- `supplier_quality_trend_change`

Each uses deterministic fingerprints over tenant, kind, source ids, and recurrence evidence.
Dismissals remain the only persisted alert state.

**Rationale**: This extends the existing alerts model without creating stale alert rows. It also
keeps every anomaly source-backed and actionable.

## R6 - Audit and tenant isolation

**Decision**: Audit:

- `optimisation.advanced_basket_submitted`
- `supplier_iq.scorecard_viewed`
- `alerts.anomaly_dismissed`

Any new tenant-scoped table uses `tenant_id`, `ENABLE ROW LEVEL SECURITY`,
`FORCE ROW LEVEL SECURITY`, and policies with both `USING` and `WITH CHECK`.

**Rationale**: R2.4 changes decision support and risk presentation. Auditability and cross-tenant
not-found semantics are required before release.

## R7 - UI integration

**Decision**: Extend existing web areas instead of creating a standalone dashboard:

- Basket Split gains constraint controls and richer result explanations.
- Supplier list/detail gains Supplier IQ scorecards.
- Alerts gains anomaly kinds and action routing.
- Compare gains Supplier IQ/risk evidence when it affects the recommendation.

**Rationale**: The product principle says every insight ends in an action. Supplier IQ is most
useful where buyers compare, optimise, and respond to alerts.
