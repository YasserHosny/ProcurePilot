# Feature Specification: Mobile Approvals and Delivery Receipt

**Feature Branch**: `010-mobile-approvals-receipt`
**Created**: 2026-09-13
**Status**: Draft
**Input**: User description: "Mobile approvals and delivery receipt (R2.3, roadmap §7.2, M12-M13).
Extend the Flutter mobile app (specs/009-mobile-app-mvp) so an approver can review and decide on a
pending purchase request from their phone with full context (lines, estimated total, budget
status, requester), not just receive a push notification about it. Also let a branch member
confirm delivery of an order (marking it received, flagging quantity/quality discrepancies) and
report a delivery quality issue, including a camera-captured photo as evidence. Scope: approval
flow on mobile (approve/reject with comment, same decision semantics and audit trail as the
existing web approval queue and requests/service.py — FR-009's no-autonomous-purchasing constraint
still applies, a human always decides), delivery receipt confirmation, quality issue reporting, and
the camera capture pipeline needed for photo evidence. Do not implement anything yet — this is
planning only."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Decide on a pending request from mobile (Priority: P1)

An owner or approver gets a push notification (already shipped in R2.2) that a request needs their
decision. Instead of that notification only opening a read-only status view, they now land on the
same full decision context they would see on web — the request's lines, its estimated total, its
budget impact, and who requested it — and can approve or reject with an optional comment, right
there, without waiting until they are back at a desk.

**Why this priority**: This is the roadmap's own named strategic job for mobile — "an owner
deciding in under 30 seconds, with enough evidence to be confident" (roadmap §12.1). R2.2 shipped
the awareness half (a pending count, a push notification); this closes the loop with the action
itself, which is the reason approvals were called out as a *later* release rather than cut
entirely.

**Independent Test**: Can be fully tested by a signed-in approver opening a pending request from
mobile (via the approval queue or a notification deep link), reviewing its lines/total/budget/
requester, approving or rejecting with a comment, and confirming the request's status, the decision
comment, and the audit trail entry are all identical to what the same decision would have produced
from the existing web approval queue.

**Acceptance Scenarios**:

1. **Given** a request pending the signed-in member's decision, **When** they open it from the
   mobile approval queue, **Then** they see its lines, estimated total, budget status (when
   applicable), and the requester's identity — the same information the web approval detail
   already shows.
2. **Given** that same request, **When** the approver approves it with a comment, **Then** the
   request moves to "approved," the comment and decision are recorded on the request exactly as a
   web decision would record them, and the requester is notified (R2.2's existing push).
3. **Given** a request the signed-in member is not authorized to decide on (not the assigned
   approver, not an owner), **When** they attempt to view or decide on it, **Then** the app
   refuses the same way the web API already does — this is not a new authorization surface.
4. **Given** a request that has already been decided by someone else (e.g., an owner overriding a
   pending step) by the time the approver acts, **When** they attempt to submit their own decision,
   **Then** the app tells them plainly that it was already decided, rather than silently failing or
   double-recording a decision.
5. **Given** a decided request, **When** the approver or the requester later views it, **Then**
   the decision, its comment, and its timestamp are visible identically on mobile and web.

---

### User Story 2 - Confirm delivery of an approved order (Priority: P1)

A branch team member is at the loading dock or stockroom when an approved order arrives. They open
the request on mobile, confirm what actually showed up — the full ordered quantity, or something
less — and mark it received. If everything matches, that is the whole interaction; if quantities
are short, they flag it right there instead of only noticing later when someone reconciles an
invoice.

**Why this priority**: This is the roadmap's third named strategic job for mobile — "receipt,
shortage, or quality problem at the point of delivery" (roadmap §12.1) — and closes the loop that
Story 1 and R2.2's request flow open: a request that was approved but never confirmed as received
is a gap in the record, not a smaller version of the same job.

**Independent Test**: Can be fully tested by a signed-in branch member confirming delivery of an
approved request with the full ordered quantity, confirming it now shows as delivered with no
discrepancy, and separately confirming delivery of a different approved request with a short
quantity, confirming the shortage is recorded and visible against that specific request.

**Acceptance Scenarios**:

1. **Given** an approved request that has been fulfilled, **When** a branch member confirms
   delivery with the full ordered quantity for every line, **Then** the request is marked
   delivered with no discrepancy recorded.
2. **Given** the same scenario, **When** the branch member instead records a lower quantity
   received for one or more lines, **Then** the request is marked delivered with the specific
   shortage recorded against those lines, not just a generic "problem" flag.
3. **Given** a request that has not yet been approved, **When** a branch member attempts to
   confirm its delivery, **Then** the app refuses — there is nothing to receive against a request
   that was never ordered.
4. **Given** a request already confirmed as delivered, **When** anyone views its status, **Then**
   the confirmed quantities and any recorded discrepancy are visible, matching what was actually
   entered at the point of delivery.

---

### User Story 3 - Report a delivery quality issue with photo evidence (Priority: P2)

After receiving a delivery, a branch team member notices a problem that is not just "the count was
short" — damaged packaging, a spoiled item, the wrong product entirely. They open the delivered
request, describe the problem, and attach one or more photos taken on the spot as evidence, so
whoever follows up (an owner deciding whether to raise it with the supplier) has more than a
written description to go on.

**Why this priority**: A named, valuable capability in its own right — the roadmap explicitly
calls out "photo of damage, quality rating" as part of the delivery job — but Story 2 already
delivers the core "did it arrive correctly" loop without it; this is a richer follow-up path for
the subset of deliveries that have an actual problem.

**Independent Test**: Can be fully tested by a signed-in branch member opening a delivered
request, reporting a quality issue with a description and at least one photo captured through the
app, and confirming the issue — description, photo, and who reported it — is durably retrievable
against that specific request afterward.

**Acceptance Scenarios**:

1. **Given** a delivered request, **When** a branch member reports a quality issue and captures a
   photo through the app's camera, **Then** the issue and its photo are saved and associated with
   that request.
2. **Given** the same flow, **When** the member has no camera access or declines to grant it,
   **Then** they can still submit a quality issue with a written description alone — a photo is
   valuable evidence, never a requirement to report a real problem.
3. **Given** a quality issue already reported with a photo, **When** an owner or the original
   reporter views that request later, **Then** the photo is still viewable, not just a broken or
   expired link.
4. **Given** a request that has not been delivered yet, **When** a branch member attempts to
   report a quality issue against it, **Then** the app refuses — a quality issue is reported
   against what arrived, not what was merely ordered.

---

### Edge Cases

- What happens if an approver's connection drops between opening a request and submitting their
  decision? The decision itself requires a live connection to submit — unlike a request submission
  or low-stock report (R2.2's FR-011), a decision is time-sensitive and evidence-dependent; queuing
  it for later replay risks an approver acting on data that has since changed (a budget consumed by
  another decision, a request withdrawn). The app tells them plainly the decision did not go
  through and to retry once connectivity returns, rather than silently queuing something this
  consequential.
- What happens if two people with decision authority (e.g., the assigned approver and an owner)
  both try to decide the same request from different devices at nearly the same moment? The same
  race the existing web approval flow already resolves — the first decision to actually land wins,
  and whoever's decision arrives second is told the request was already decided, exactly as
  Acceptance Scenario 4 in Story 1 describes. This is not a new race mobile introduces.
- What happens to delivery confirmation and quality-issue reporting when the device is offline?
  Unlike a decision, these are factual records of something that already physically happened —
  they queue locally and sync automatically once connectivity returns, the same offline-tolerance
  guarantee R2.2 already gives request submission and low-stock reports (FR-011). A queued photo
  waits for connectivity before it uploads, the same as the record it belongs to.
- What happens to R2.2's read-only "pending approvals" count on the home screen now that deciding
  on mobile is possible? It becomes the entry point into the mobile approval queue this feature
  adds, rather than a number with nothing to do about it — R2.2's own FR-009 ("MUST NOT surface an
  approve/reject action anywhere on mobile") is explicitly superseded by this release for the
  approval queue and detail screens only; every other mobile screen's existing scope is unchanged.
- What happens if a branch member records a delivery discrepancy or quality issue for a request
  outside their own branch scope? The same branch-scoped visibility every other mobile screen
  already enforces (R2.2's FR-015) — they cannot act on, or even see, a request outside their
  scope, whether it is pending, approved, or delivered.
- Does approval delegation (already shipped in 008-requests-approvals) apply to mobile decisions?
  Yes, unchanged — a delegate sees and decides on the requests they have been delegated exactly as
  they would on web; mobile is a new way to reach the same decision, not a new routing rule.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The mobile app MUST let an approver (assigned approver or owner) view a pending
  request's full decision context — lines, estimated total, budget status when applicable, and
  the requester's identity — before deciding, matching what the existing web approval detail shows.
- **FR-002**: The mobile app MUST let an approver approve or reject a pending request with an
  optional comment, using 008-requests-approvals' existing decision logic, authorization rules,
  and audit actions unchanged — mobile MUST NOT introduce a second, divergent decision path or a
  way to approve without a recorded human decision (constitution: Evidence Over Assertion; no
  autonomous purchasing).
- **FR-003**: The mobile app MUST require a live connection to submit a decision; a decision MUST
  NOT be queued for later offline replay, since deciding on stale, unsynced context risks an
  uninformed decision.
- **FR-004**: The mobile app MUST tell an approver plainly, not silently fail or double-record,
  when they attempt to decide on a request that has already been decided by someone else.
- **FR-005**: The mobile app MUST let a branch member confirm delivery of an approved request,
  recording the quantity actually received for each line and flagging any shortfall against what
  was ordered.
- **FR-006**: The mobile app MUST refuse delivery confirmation for a request that has not been
  approved, and MUST refuse a quality-issue report for a request that has not been confirmed
  delivered.
- **FR-007**: The mobile app MUST let a branch member report a delivery quality issue against a
  delivered request, with a written description and zero or more photos captured through the
  app's camera — a photo MUST be optional, never required, to submit a real quality issue.
- **FR-008**: The system MUST durably store photo evidence attached to a quality issue and keep it
  retrievable against that specific request indefinitely, not as an expiring or temporary link.
- **FR-009**: The mobile app MUST allow delivery confirmation and quality-issue reports (including
  their attached photos) to be queued while offline and sent automatically once connectivity
  returns, without creating a duplicate record if a queued submission is retried after a partial
  failure — the same offline-tolerance guarantee R2.2 already gives request submission and
  low-stock reports (009-mobile-app-mvp FR-011, FR-012).
- **FR-010**: The mobile app MUST scope the approval queue, decision screens, and delivery/quality
  screens to the signed-in member's role and branch assignment exactly as every other mobile
  screen already is (009-mobile-app-mvp FR-015) — a branch-scoped member acts only within their
  own branch; an owner acts across the tenant.
- **FR-011**: The system MUST record every mobile-originated decision, delivery confirmation, and
  quality-issue report in the existing append-only audit log, on the same terms as every other
  administrative action — the audit trail MUST NOT have a gap for "decided," "confirmed," or
  "reported from mobile."
- **FR-012**: The mobile app's home screen MUST turn the existing read-only pending-approvals
  count (009-mobile-app-mvp FR-002) into an actionable entry point into the mobile approval queue
  for a member holding approval authority — R2.2's blanket "no approve/reject action anywhere on
  mobile" restriction (FR-009) is superseded by this release for the approval queue and decision
  screens specifically; no other mobile screen's scope changes.
- **FR-013**: The mobile app MUST support English and Arabic with full right-to-left layout for
  every screen this feature adds, drawn from the shared `packages/i18n` string catalogue — no
  feature-specific hardcoded copy, matching every prior release's standing requirement.

### Key Entities

- **Approval decision**: Reused unchanged from 008-requests-approvals' `ApprovalStep` — mobile is
  a new way to make and view a decision, not a new definition of what a decision is or how it is
  authorized.
- **Delivery confirmation**: A record of what was actually received against a specific approved
  request — the quantity received per line and any shortfall against the ordered quantity.
  Attributed to the member who confirmed it and the moment they did. This is a new capability: the
  existing purchase-request lifecycle (008-requests-approvals) ends at `approved`/`rejected`/
  `withdrawn` today, with no concept yet of what happened to an approved request afterward.
- **Delivery quality issue**: A report of a problem with a delivered request — damaged, wrong item,
  spoiled — distinct from a simple quantity shortfall (which delivery confirmation itself already
  captures). Carries a description, zero or more photos, and is attributed to the member who
  reported it and the moment they did.
- **Photo evidence**: An image captured through the app and durably associated with a specific
  quality issue report.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An approver can review a pending request's full context and record a decision from
  mobile in under 30 seconds (roadmap §12.1's own target for the "Approve" job).
- **SC-002**: 100% of decisions made from mobile appear identically — status, comment, timestamp,
  audit entry — in the existing web approval queue and request history; no channel-specific
  behaviour gap.
- **SC-003**: A branch member can confirm delivery of a straightforward, no-discrepancy order in
  under 30 seconds.
- **SC-004**: Zero delivery confirmations or quality-issue reports submitted while offline are lost
  or duplicated once connectivity returns.
- **SC-005**: 100% of quality-issue photos remain viewable against their request at least 12 months
  after submission (matching this product's general evidence-retention expectation for anything
  used to justify a supplier or financial decision).
- **SC-006**: Zero requests are ever marked approved without a recorded human decision — this
  release introduces no path around that guarantee.

## Assumptions

- **The purchase-request lifecycle gains new states rather than this feature inventing a separate,
  disconnected record.** The roadmap's own "My requests" screen already describes "Draft,
  submitted, approved, ordered, delivered states with timeline" (roadmap §12.3) as one continuous
  progression of a single request — not a purchase request plus a second, unrelated delivery
  entity. This spec follows that lead: delivery confirmation and quality-issue reporting are new
  facts recorded *against* a `purchase_request`, not a new top-level object a request merely
  references.
  - **Note for `/speckit.plan`**: this codebase already has an unrelated `PurchaseRecord` entity
    (006-value-proof-launch) with its own `delivery_result` enum (`ordered`/`partially_delivered`/
    `delivered`/`cancelled`/`disputed`) and `ordered_at`/`delivered_at` fields — but it exists for a
    different job (owner/buyer-only outcome recording tied to quotations and savings evidence, with
    no link to `purchase_request` at all today) and is written by a different, narrower set of
    roles. Planning should explicitly decide whether this feature's delivery/quality data reuses
    that table, links to it, or stays deliberately separate — and say why — rather than silently
    duplicating a concept this codebase already named once.
- **A decision requires connectivity; a delivery/quality record does not.** This asymmetry is
  deliberate (see Edge Cases) and should not be "fixed" into symmetry with R2.2's offline queue
  during planning — the two have genuinely different risk profiles (acting on stale context vs.
  recording something that already happened).
- **No barcode scanning or request-time photo capture is in this feature's scope**, even though the
  roadmap's mobile screen set (§12.3) mentions a "Scan / photo capture" screen for the *request*
  flow (identifying a product, evidence of a shelf). That is request-submission tooling, not
  delivery/quality tooling, and the feature description driving this spec did not ask for it —
  treat it as a separate, not-yet-scoped piece of R2.3 or later, the same way 009's own spec
  explicitly deferred it.
- **Quality rating** (a simple satisfaction score alongside a quality issue, mentioned in roadmap
  §12.3's screen table) is not included as its own requirement here — the feature description
  asked for issue *reporting* with photo evidence, not a supplier-facing rating mechanism. If a
  rating is wanted, it is a small, separable addition planning can flag rather than something this
  spec should invent unasked.
