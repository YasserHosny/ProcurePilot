# Feature Specification: Optimisation and Supplier IQ

**Feature Branch**: `011-optimisation-supplier-iq`
**Created**: 2026-09-13
**Status**: Draft
**Input**: User description: "R2.4 Optimisation + Supplier IQ: advance the existing Smart Compare, basket split, alerts, and delivery outcome data into a richer optimisation and supplier intelligence release with minimum order values, free-delivery thresholds, quantity tiers, urgency constraints, supplier-preference weighting, supplier scorecards, risk scoring, and anomaly detection v1. Keep this advisory: no autonomous purchasing."

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Optimise a basket with commercial constraints (Priority: P1)

A buyer builds a basket and asks ProcurePilot for the least-cost allocation across eligible
suppliers while respecting supplier minimum order values, delivery fee thresholds, price breaks,
urgency, preferred-supplier weighting, and risk tolerance. The result remains advisory: it explains
the recommended allocation, the constraints applied, the rejected alternatives, expected savings,
confidence, risk, and validity period, but it never places an order.

**Why this priority**: R2.4's core roadmap promise is an advanced basket optimiser. The existing
foundation can split a basket across exactly two suppliers by landed cost only; this story upgrades
it into a realistic procurement recommendation while preserving human authority.

**Independent Test**: Seed suppliers with minimum order values, delivery thresholds, tier prices,
risk scores, and overlapping offers. Submit a basket and verify the returned allocation satisfies
every hard constraint, applies soft weighting deterministically, reports infeasible constraints,
and records no purchase or approval side effect.

**Acceptance Scenarios**:

1. **Given** three suppliers with current offers, delivery thresholds, and minimum order values,
   **When** a buyer optimises a basket, **Then** the result chooses a feasible allocation with all
   hard constraints satisfied and every money value shown with currency.
2. **Given** the cheapest supplier fails the buyer's risk tolerance, **When** the buyer runs the
   optimiser with that tolerance, **Then** the result either chooses a safer supplier or reports
   that no feasible allocation exists under the selected tolerance.
3. **Given** a supplier becomes cheaper only after a quantity tier, **When** the requested quantity
   crosses that tier, **Then** the allocation uses the tiered price and cites the tier as evidence.
4. **Given** no allocation can satisfy the basket, **When** optimisation completes, **Then** the job
   completes with structured infeasible items and violated constraints, not a failed worker state.

---

### User Story 2 - Understand supplier performance and risk (Priority: P1)

A buyer opens a supplier scorecard and sees a concise, evidence-backed picture of how that supplier
has performed: fulfilment rate, lead-time behaviour, price competitiveness, quality incidents,
responsiveness proxies, spend exposure, and an overall risk score. Every score shows the records
behind it and whether the evidence base is sufficient.

**Why this priority**: Advanced optimisation needs trustworthy supplier signals. A buyer should be
able to inspect the same Supplier IQ used by recommendations before accepting or overriding them.

**Independent Test**: Seed delivered requests, quality issues, landed costs, and quotation history
for one supplier, then verify the scorecard metrics and risk score match those source records and
degrade to "insufficient evidence" when history is sparse.

**Acceptance Scenarios**:

1. **Given** a supplier has delivered requests and quality issues, **When** the scorecard opens,
   **Then** fulfilment, delivery, quality, price, spend, and risk metrics are displayed with source
   counts and source links.
2. **Given** a supplier has too little history for a metric, **When** the scorecard opens, **Then**
   that metric is marked as insufficient evidence and is not silently treated as perfect.
3. **Given** a buyer changes the supplier filter in Supplier IQ, **When** the page reloads data,
   **Then** no data from another tenant or hidden supplier can appear.

---

### User Story 3 - Detect procurement anomalies that need review (Priority: P2)

A buyer opens alerts and sees anomaly v1 signals: price spikes, duplicate invoice-like quotation
lines, decimal/quantity anomalies, delivery-cost anomalies, and unusual supplier-quality changes.
Each anomaly includes source evidence, severity, confidence, validity, and a recommended next
action such as compare product, inspect supplier scorecard, review quotation, or open delivery
quality issue history.

**Why this priority**: R2.4 explicitly names anomaly detection v1. The first version should be
rules-based and evidence-backed, reusing the live alert model rather than adding opaque ML.

**Independent Test**: Seed each anomaly condition independently and verify it appears in the alerts
inbox with a deterministic fingerprint, can be dismissed, and reappears only when the underlying
condition changes.

**Acceptance Scenarios**:

1. **Given** a current offer is more than the configured threshold above the product's rolling
   history, **When** alerts are loaded, **Then** a price-spike anomaly appears with the current
   landed cost and historical baseline as evidence.
2. **Given** two quotation lines appear to duplicate the same supplier invoice/product/period,
   **When** alerts are loaded, **Then** a duplicate-line anomaly appears and links to the review
   evidence.
3. **Given** a delivery fee is unusually high versus supplier history, **When** alerts are loaded,
   **Then** a delivery-cost anomaly appears with severity based on the excess amount and confidence
   based on history depth.

---

### User Story 4 - Inspect optimiser and risk decisions from the web UI (Priority: P2)

A buyer uses the existing Compare, Basket Split, Alerts, and Supplier screens without learning a
new workflow. The basket screen exposes constraint controls, results show applied constraints and
trade-offs, alerts link into supplier scorecards, and compare recommendations surface Supplier IQ
signals where they influence the decision.

**Why this priority**: R2.4 should deepen the existing workbench instead of creating another
dashboard. The web UI is what makes the extra reasoning inspectable and actionable.

**Independent Test**: In the web app, run an optimisation with constraints, open a supplier
scorecard from an alert, and verify the result can be understood and acted on with keyboard-only
navigation in both English and Arabic.

**Acceptance Scenarios**:

1. **Given** basket constraints are available, **When** a buyer adjusts risk tolerance or urgency,
   **Then** the UI reruns or refreshes the job without losing the basket contents.
2. **Given** an alert is tied to supplier risk, **When** the buyer follows its action, **Then** the
   supplier scorecard opens with the relevant evidence visible.
3. **Given** the locale is Arabic, **When** the buyer views Supplier IQ or optimisation results,
   **Then** labels come from i18n, layout respects RTL, and no text overlaps.

### Edge Cases

- If supplier commercial terms are missing, the optimiser must treat missing hard terms as no
  constraint and missing scoring signals as insufficient evidence, not as zero risk or zero cost.
- If supplier terms use a different currency than basket offers, the optimiser must refuse to
  combine them unless a recorded conversion rule exists in scope; R2.4 does not introduce FX.
- If hard constraints make every supplier infeasible, the job must complete with actionable
  violations rather than fail.
- If a risk score is based on too few observations, recommendations must show lower confidence.
- If two allocations tie, the tie-break order must be deterministic and disclosed.
- If alert conditions are dismissed, recurrence must be based on changed evidence, not only time.
- If an endpoint receives a cross-tenant product, supplier, or scorecard id, it must return not
  found and must not reveal existence.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extend basket optimisation beyond exactly two suppliers to all eligible
  active/preferred suppliers selected by the buyer, with an upper bound of 10 suppliers per run.
- **FR-002**: System MUST support hard constraints for supplier minimum order value, free-delivery
  threshold, delivery fee, quantity tiers, requested delivery urgency, and explicit supplier
  exclusion.
- **FR-003**: System MUST support soft scoring weights for preferred suppliers, risk tolerance,
  lead time, quality incident rate, and price competitiveness. The weights must be recorded in
  the job request snapshot.
- **FR-004**: System MUST return an optimisation result that includes allocation, baseline
  comparisons, applied constraints, violated constraints, confidence, risk notes, validity window,
  and source landed-cost ids.
- **FR-005**: System MUST keep optimisation advisory only. No endpoint in this feature may create
  a purchase, approval, order, payment, or supplier message.
- **FR-006**: System MUST compute supplier scorecards from existing tenant-scoped records:
  suppliers, landed costs, quotations, purchase requests, delivery confirmations, quality issues,
  purchase records, savings records, and alert/anomaly evidence.
- **FR-007**: System MUST expose supplier scorecard metrics with source counts, source ids, metric
  windows, confidence, and "insufficient evidence" flags.
- **FR-008**: System MUST produce an overall supplier risk score using documented deterministic
  rules, not an opaque model, and every sub-score contribution must be visible.
- **FR-009**: System MUST add anomaly v1 alert kinds for price spike, likely duplicate quotation
  line, decimal/quantity anomaly, delivery-cost anomaly, and supplier-quality trend change.
- **FR-010**: System MUST generate anomaly ids as deterministic fingerprints over tenant, anomaly
  kind, affected product/supplier, source ids, and recurrence evidence.
- **FR-011**: System MUST preserve live alert recomputation and dismissal-only storage. Persisted
  alert conditions are out of scope.
- **FR-012**: System MUST audit human-triggered optimisation submission, supplier scorecard view,
  and anomaly dismissal actions. Audit events remain append-only.
- **FR-013**: System MUST enforce database RLS for every new tenant-scoped table and include
  `USING` and `WITH CHECK` policies with `ENABLE` and `FORCE` RLS.
- **FR-014**: System MUST derive tenant scope only from the verified JWT claim and never from path,
  query, body, or header input.
- **FR-015**: System MUST express every monetary value as `{amount, currency}` and reject bare
  money inputs.
- **FR-016**: System MUST serve all user-facing strings from `packages/i18n` in English and Arabic.
- **FR-017**: System MUST provide web UI coverage for advanced basket constraints, Supplier IQ,
  and anomaly actions with WCAG 2.1 AA automated checks and RTL coverage.
- **FR-018**: System MUST keep optimisation and scorecard calculations deterministic and replayable
  from stored inputs, rule versions, and request snapshots.

### Key Entities *(include if feature involves data)*

- **SupplierCommercialTerm**: Tenant-scoped supplier commercial rules such as minimum order value,
  free-delivery threshold, delivery fee, and quantity tiers, versioned with effective dates.
- **SupplierScorecardSnapshot**: A deterministic, versioned snapshot of supplier metrics and risk
  sub-scores for a window. It is cached for performance but recomputable from source records.
- **OptimisationConstraintSet**: The request snapshot sent to the optimiser: selected suppliers,
  hard constraints, soft weights, urgency, risk tolerance, basket items, and rule version.
- **OptimisationResult**: The advisory allocation, baseline totals, applied/violated constraints,
  risk notes, confidence, source ids, and validity window returned by a basket job.
- **AnomalySignal**: A live-computed alert condition with deterministic fingerprint, severity,
  confidence, source evidence, and recommended action. Only dismissals are persisted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For seeded baskets with supplier terms, every completed optimisation result satisfies
  all hard constraints or returns explicit violated constraints with no silent partial allocation.
- **SC-002**: Supplier scorecard metrics match seeded source records exactly in integration tests,
  including sparse-history "insufficient evidence" cases.
- **SC-003**: Each anomaly v1 kind can be generated, dismissed, and regenerated on changed evidence
  without persisting stale alert rows.
- **SC-004**: Optimisation result polling remains observable and completes or returns infeasible
  within 30 seconds in local worker tests for baskets up to 50 lines and 10 suppliers.
- **SC-005**: Web a11y checks for advanced basket, Supplier IQ, and anomaly flows pass in English
  and Arabic with zero automated WCAG 2.1 AA violations.
- **SC-006**: No R2.4 endpoint or UI path can execute or imply autonomous purchasing.

## Assumptions

- FX conversion is out of scope. Mixed currencies in one optimisation are refused unless all money
  values already share a currency.
- Supplier scorecards are deterministic rules and aggregates in R2.4. Learned risk models are
  deferred until enough labelled outcome history exists.
- The existing `services/optimiser` worker remains the optimiser deployable. R2.4 may extend its
  model and solver but must not create a second worker.
- Existing R2.2/R2.3 mobile delivery data is sufficient for the first quality and fulfilment
  signals, but sparse data must be shown honestly as low-confidence or insufficient evidence.
