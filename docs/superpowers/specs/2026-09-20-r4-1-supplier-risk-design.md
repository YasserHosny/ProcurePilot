# R4.1 Supplier Risk and Negotiation Briefs

**Status:** Approved design, implementation pending
**Date:** 2026-09-20
**Gate posture:** R4.1 proceeds under the recorded G3 exception. G3 remains unmet.

## Goal

Give procurement users a deterministic, evidence-backed view of supplier risk and a
human-reviewable negotiation brief that turns the risk evidence into a concrete next step.
The release must improve purchasing decisions without sending supplier communications or
authorising purchases automatically.

## Scope

R4.1 will calculate four supplier-level risk dimensions over an explicit evidence window:

- **Concentration:** the supplier's share of tenant purchase exposure where comparable
  currency evidence exists.
- **Price drift:** change in comparable landed-cost observations between the current and
  baseline windows, grouped by product and currency.
- **Delivery reliability:** on-time delivery performance from purchase orders and delivery
  receipts, including the sample size used.
- **Reconciliation quality:** discrepancy rate from three-way match and reconciliation
  outcomes, including the sample size used.

Each dimension will disclose its value, denominator, evidence window, currency where relevant,
confidence, and data sufficiency. A supplier snapshot will expose an overall risk level only
when the component evidence is sufficient; otherwise it will be labelled `insufficient_data`.
Short history will be labelled `provisional`, never silently treated as mature evidence.

Negotiation briefs will be generated from the latest risk snapshot. A brief will contain a
small set of ranked, source-linked talking points, the relevant calculation, suggested human
questions, and any monetary leverage expressed as an amount plus currency. It will not claim
savings that cannot be traced to source records.

## Release constraints

- Every snapshot and brief carries `release_posture = g3_unmet`.
- No risk score or brief may use cross-tenant rows; database RLS is mandatory and application
  filters are not sufficient.
- Risk snapshots are append-only evidence. Recomputing the same source window and model
  version is idempotent.
- A brief is a workflow artifact, not an outbound communication. Users may inspect, prepare,
  dismiss, or route it for human follow-up; the system will not email, message, negotiate, or
  create a purchase order.
- User-facing copy is added to the shared English and Arabic i18n catalogues and the UI must
  support RTL.

## Proposed architecture

### Backend

Add a focused `supplier_risk` module with:

- Pure, versioned calculation functions for component metrics and risk classification.
- Pydantic schemas for snapshots, component metrics, briefs, and workflow actions.
- A service that reads existing tenant-scoped order, delivery, invoice, reconciliation,
  quotation, and landed-cost evidence through the authenticated Supabase client.
- Routes to recompute snapshots, list supplier risks, retrieve a risk detail, list briefs, and
  prepare or dismiss a brief.
- Audit events for recomputation, brief preparation, and dismissal.

### Database

Add a forward-only migration containing:

- `supplier_risk_snapshot`: immutable tenant-scoped snapshot with model version, evidence
  window, overall state, confidence, release posture, and validity period.
- `supplier_risk_metric`: immutable tenant-scoped child rows for concentration, price drift,
  delivery reliability, and reconciliation quality, with explicit denominators and source
  windows. The schema will use first-class columns for metric values and currencies, not an
  opaque evidence blob.
- `negotiation_brief`: tenant-scoped human workflow row linked to a snapshot, with status,
  prepared/dismissed actor and timestamps, and deterministic source fingerprinting.

All tables will have tenant columns, composite tenant foreign keys, forced RLS, `USING` and
`WITH CHECK` policies, appropriate indexes, and grants matching existing module conventions.

### Web

Add a Supplier Risk route and navigation entry. The primary view will support scanning supplier
risk level, confidence, evidence age, and the highest-ranked risk drivers. A detail view will
show the underlying calculations and source links, followed by the negotiation brief action.
The only primary action is human preparation or dismissal of a brief; insufficient and
provisional evidence states remain prominent.

## API shape

- `POST /api/v1/supplier-risk/recompute`
- `GET /api/v1/supplier-risk/suppliers`
- `GET /api/v1/supplier-risk/suppliers/{supplier_id}`
- `GET /api/v1/supplier-risk/briefs`
- `POST /api/v1/supplier-risk/briefs/{brief_id}/prepare`
- `POST /api/v1/supplier-risk/briefs/{brief_id}/dismiss`

All list responses are tenant-scoped and cursor-paginated where applicable. Unknown or
cross-tenant identifiers return the standard not-found envelope. Mutating actions are
idempotent where replay can occur.

## Error and data sufficiency policy

- No supplier records: return an empty result, not a fabricated zero-risk score.
- Mixed currencies: calculate concentration and price drift per currency bucket and disclose
  that no cross-currency aggregate was produced.
- Missing delivery or reconciliation evidence: retain the metric as `insufficient_data` with
  the observed sample count.
- Database or dependency failure: return the standard service-unavailable envelope and never
  persist a partial snapshot.
- Stale snapshots: expose validity and evidence dates so the UI can prompt recomputation.

## Verification

- Unit tests first for deterministic metric calculations, thresholds, currency bucketing,
  insufficient-data states, and replay fingerprints.
- API tests for authentication, tenant isolation, cursor behavior, idempotent recomputation,
  workflow transitions, and standard not-found responses.
- Hosted Supabase migration verification with forced-RLS checks.
- Angular unit and accessibility tests for English and Arabic/RTL states.
- Production web build and focused live API consumption after deployment.

## Explicit non-goals

- No predictive machine-learning model in R4.1.
- No cross-tenant benchmarking.
- No autonomous approval or purchasing.
- No supplier messaging, RFQ dispatch, or external integration work; those belong to later
  roadmap releases.

