# Feature Specification: R4.3 Automated RFQ Sourcing and Guarded Autonomous Workflows

**Feature Branch**: `021-rfq-sourcing-autonomy`
**Created**: 2026-09-24
**Status**: Draft for approval
**Roadmap Release**: R4.3, Phase 4 Predictive Procurement (final release of Phase 4)
**Input**: Automated RFQ sourcing and guarded autonomous workflows — structured RFQ dispatch to
suppliers with automated response ingestion, and rules-based auto-approval workflows within
tight, tenant-defined guardrails. Purchasing remains human-authorised at all times: automation
may prepare, route, and dispatch outbound requests, and may auto-approve within explicit
tenant-configured limits, but it never executes an autonomous purchase.

## Release posture

G3 remains unmet. R4.3 is an implementation exception, not a gate pass or commercial validation,
the same posture as R4.0–R4.2. Every RFQ and every auto-prepared draft carries
`release_posture = g3_unmet`.

This release sits directly on Constitution Principle III (Human Authority Over Automation,
NON-NEGOTIABLE): "No purchase may be executed without human authorisation, in any phase, under
any configuration." The two capabilities in this release are both already-permitted automation
verbs under that principle — **route** (dispatching an RFQ is a request for information, not a
commitment) and **prepare** (auto-creating a draft is exactly what R4.0's reorder-proposal
"prepare request" already does today, just without requiring a human to click prepare first,
inside tight guardrails). Neither capability creates a new path to sending a real purchase order
or committing spend without a human's explicit approval action. "Auto-approval" in the roadmap's
own phrasing means auto-*preparing* a draft into the existing human approval queue (chunk
008's purchase-request/approval workflow, unchanged) — it does not mean auto-*approving* that
draft. That distinction is binding on every requirement below.

## User stories

### US1 - Send a structured RFQ to chosen suppliers (P1)

A buyer has a product need — a one-off purchase, a low-stock alert, or a reorder forecast — and
wants competitive quotes without drafting and sending a separate email to each supplier by hand.
They pick the product(s)/quantity/needed-by date and the suppliers to ask, review the request the
system has structured for them, and send it.

**Why this priority**: this is the entry point for every other capability in this release — there
is no response to ingest, compare, or auto-prepare from until a request has gone out.

**Independent Test**: create an RFQ for a known product and two suppliers with on-file email
contacts, send it, and confirm both suppliers receive a structured, complete request (product
identity, quantity, needed-by date, any tenant terms) without needing to contact the buyer for
clarification.

**Acceptance Scenarios**:

1. **Given** a product with at least one supplier that has a contact email on file, **When** a
   buyer creates and sends an RFQ for that product to that supplier, **Then** the supplier
   receives one structured, complete request and the RFQ's status becomes "sent."
2. **Given** a supplier with no contact email on file, **When** a buyer tries to include that
   supplier in an RFQ, **Then** the system blocks that recipient specifically and explains why,
   without blocking the rest of the RFQ.
3. **Given** an RFQ drafted but not yet sent, **When** the buyer edits the product, quantity, or
   recipient list, **Then** the changes are reflected before send; nothing is dispatched until the
   buyer explicitly sends it.

---

### US2 - Automatically capture supplier responses (P1)

A supplier replies to an RFQ with a quotation. The buyer wants that reply to become a structured,
comparable quotation line automatically — the same way an emailed quotation already becomes one
through the existing ingestion pipeline — without re-typing prices from an email or PDF.

**Why this priority**: automated dispatch without automated ingestion just moves the manual work
from "draft an email" to "re-type a reply"; the response side is where the actual time saving
lives, and it is a near-direct reuse of the quotation-inbox-extraction pipeline already shipped
in R003.

**Independent Test**: send an RFQ, reply to it as the supplier with a priced quotation, and confirm
the reply appears as a structured quotation linked to that RFQ, with the same extraction-confidence
and human-review-on-mismatch behaviour the existing quotation inbox already has.

**Acceptance Scenarios**:

1. **Given** a sent RFQ, **When** the supplier replies to the same thread with a quotation,
   **Then** the reply is captured and extracted into a structured quotation linked to that RFQ,
   using the existing extraction and confidence/review pipeline unchanged.
2. **Given** an RFQ with three suppliers asked, **When** only two reply before the needed-by date,
   **Then** the RFQ shows two structured responses and one still-awaiting, never blocks on the
   slowest supplier.
3. **Given** a supplier reply whose extracted totals don't reconcile with its own line items
   (the same arithmetic-mismatch condition the existing quotation pipeline already detects),
   **When** it's ingested, **Then** it's routed to the existing mandatory review task, exactly as
   any other quotation with that condition already is — RFQ responses get no special exemption
   from that check.

---

### US3 - Compare responses and prepare a request by hand (P1)

A buyer has one or more structured responses to an RFQ and wants to compare them side by side —
reusing the existing offer-comparison view — pick a winner, and turn that choice into a draft
purchase request that goes through the existing human approval queue.

**Why this priority**: this closes the loop for every RFQ a buyer sends, and is the baseline,
always-available path — the guarded automation in US4 is an *optional* acceleration of this same
action, not a replacement for it.

**Independent Test**: with two structured responses to one RFQ, open the comparison view, select
one, and confirm a draft purchase request is created referencing that response, entering the same
approval workflow any other purchase request already does.

**Acceptance Scenarios**:

1. **Given** two or more structured responses to the same RFQ, **When** a buyer opens the
   comparison view, **Then** they see the same side-by-side comparison already available for any
   set of offers today (price, unit, supplier, delivery), scoped to this RFQ's responses.
2. **Given** a buyer selects a winning response, **When** they choose "prepare request," **Then**
   a draft purchase request is created citing that response as its source and enters the existing
   approval workflow unchanged — no purchase order is sent to any supplier at this step.
3. **Given** an RFQ with zero responses by its needed-by date, **When** the buyer views it,
   **Then** it's shown as expired with no response to compare, and no request can be prepared from
   it.

---

### US4 - Configure guardrails for automatic preparation (P2)

An owner wants routine, low-risk RFQs to skip the manual "review responses and click prepare"
step entirely when they clearly meet criteria the owner has set in advance — a maximum order
value, specific pre-approved suppliers or categories, a minimum number of responses received, and
a maximum acceptable price variance from the tenant's own recent purchase history. When every
configured condition is met, the system prepares the draft purchase request the same way US3's
manual action would — the draft still lands in the existing human approval queue unchanged.

**Why this priority**: this is the "guarded autonomous workflow" the roadmap names, and it is
explicitly the second, optional layer on top of US1–US3 — off by default, and it changes *who*
initiates the prepare step, never what happens after preparation.

**Independent Test**: configure a guardrail (e.g. max order value, one pre-approved supplier,
minimum one response), send a qualifying RFQ, receive a response that satisfies every condition,
and confirm a draft purchase request is auto-prepared and appears in the approval queue without
any buyer action between response and draft — and that a response failing even one condition
falls back to requiring the manual US3 action.

**Acceptance Scenarios**:

1. **Given** no auto-preparation guardrail configured for a tenant, **When** a qualifying response
   arrives, **Then** nothing is auto-prepared — the default is off, and every RFQ response
   requires the manual US3 action.
2. **Given** a guardrail configured with a maximum order value and a set of pre-approved
   suppliers, **When** a response arrives from a pre-approved supplier at or under that value,
   with all other configured conditions met, **Then** the system automatically prepares a draft
   purchase request identical in shape to one a human would have prepared manually, and records
   which guardrail rule triggered it.
3. **Given** the same guardrail, **When** a response arrives from a supplier that is *not*
   pre-approved, or exceeds the maximum value, **Then** nothing is auto-prepared and the response
   waits for the manual US3 action, with the reason the guardrail did not apply shown to the
   buyer.
4. **Given** an auto-prepared draft purchase request sitting in the approval queue, **When** an
   approver reviews it, **Then** it looks and behaves exactly like a manually-prepared request —
   same approve/reject actions, same audit trail — with an additional, clearly visible note that
   it was auto-prepared and which guardrail rule triggered it.
5. **Given** a tenant disables or tightens a guardrail, **When** RFQs are already in flight under
   the old rule, **Then** only responses arriving after the change are evaluated against the new
   rule; nothing already auto-prepared is retroactively changed.

---

### US5 - Track RFQ status and history (P3)

A buyer or owner wants to see, at a glance, every RFQ sent from their tenant, who was asked, who
has responded, and what happened to each — sent, responded, expired with no response, or
converted into a request — mirroring the existing order-tracking and alerts patterns.

**Why this priority**: valuable for accountability and follow-up, but the feature is fully usable
end-to-end (send, respond, compare, prepare) without a dedicated history view; this is a
convenience layer, not a blocking dependency for US1–US4.

**Independent Test**: send RFQs to three different suppliers across two separate requests, let one
expire with no response, and confirm the history view correctly shows all three with distinct,
accurate statuses.

**Acceptance Scenarios**:

1. **Given** RFQs in every status (sent, responded, expired, converted), **When** a member views
   RFQ history, **Then** each shows its current status, the suppliers asked, and — where
   applicable — which purchase request it was converted into.
2. **Given** the same read-scoping already established for every other tenant-scoped list in this
   product, **When** a non-owner/buyer member views history, **Then** they see the same
   creator-plus-oversight scoping already used elsewhere (see FR-016).

### Edge Cases

- What happens when a supplier replies to an RFQ after it has already expired? The response is
  still captured and structured (nothing is silently dropped), but the RFQ's status stays
  "expired" rather than reverting to "responded," and it is not eligible for auto-preparation
  (US4) — only for the manual US3 path.
- What happens when the same supplier is asked in two RFQs at once and replies to the wrong
  thread? Response matching relies on the same reply-threading the existing quotation-inbox
  ingestion already uses; a reply that cannot be matched to an open RFQ falls back to becoming an
  ordinary unsolicited quotation, exactly as it would today.
- What happens when a supplier's reply only quotes some of the requested line items? The response
  is still captured; the comparison view (US3) shows exactly what was quoted and what wasn't, and
  a response missing requested items is never eligible for auto-preparation (US4) even if every
  other condition is met.
- What happens when two responses tie under an active guardrail (e.g., identical price from two
  pre-approved suppliers)? Auto-preparation does not fire on a tie; it falls back to the manual
  US3 path so a human breaks the tie.
- What happens if an owner sets a guardrail's maximum order value below the tenant's own currency
  precision or to zero? The system rejects that guardrail configuration outright rather than
  accepting a value that could never trigger, or worse, always trigger.
- What happens to an in-flight RFQ if the supplier it was sent to is deactivated in the tenant's
  supplier directory afterward? The RFQ and any response already captured remain visible and
  actionable (US3 still works), but no new RFQ can be created against a deactivated supplier.

## Requirements

### Functional Requirements

- **FR-001**: An owner or buyer MUST be able to create an RFQ specifying one or more products,
  quantities, a needed-by date, and one or more recipient suppliers drawn from the tenant's own
  supplier directory.
- **FR-002**: The system MUST refuse to include a recipient supplier that has no on-file contact
  channel, and MUST explain why for that specific recipient without blocking the rest of the RFQ.
- **FR-003**: An RFQ MUST NOT be dispatched until a human (owner or buyer) explicitly sends it;
  drafting and editing an RFQ before send has no external effect.
- **FR-004**: Each dispatched RFQ MUST carry enough structured detail (product identity,
  quantity, needed-by date, any tenant-specified terms) that a supplier can respond without
  needing to contact the buyer first.
- **FR-005**: A supplier's reply to a dispatched RFQ MUST be captured and extracted into a
  structured quotation using the same extraction, confidence-scoring, and mandatory-review-on-
  arithmetic-mismatch pipeline the existing quotation inbox already applies to any other
  quotation (FR-005 of `003-quotation-inbox-extraction`) — RFQ responses receive no exemption from
  that review.
- **FR-006**: A reply that cannot be matched to an open RFQ (wrong thread, unsolicited) MUST fall
  back to the existing general quotation-ingestion path, never be silently dropped.
- **FR-007**: A member MUST be able to compare every structured response to one RFQ side by side,
  reusing the existing offer-comparison capability, scoped to that RFQ.
- **FR-008**: A member MUST be able to manually select one response and prepare a draft purchase
  request from it; the draft MUST enter the existing purchase-request approval workflow
  unchanged, and MUST cite the RFQ response it was prepared from.
- **FR-009**: The system MUST NEVER create, submit, or transmit a purchase order to a supplier as
  a direct result of preparing a request — preparation only ever produces a draft awaiting the
  existing human approval step, with no exception for auto-prepared drafts (FR-011).
- **FR-010**: An owner MUST be able to configure zero or more auto-preparation guardrails, each
  specifying at minimum: a maximum order value, an explicit allow-list of suppliers and/or
  product categories, a minimum number of responses required, and a maximum acceptable price
  variance from the tenant's own recent purchase history for the same product. Auto-preparation
  MUST be off by default for every tenant until an owner explicitly configures and enables at
  least one guardrail.
- **FR-011**: When every condition of an enabled guardrail is met by an RFQ response, the system
  MUST automatically prepare a draft purchase request identical in shape and downstream workflow
  to one prepared manually under US3, and MUST record which guardrail rule triggered it as part
  of the draft's audit trail.
- **FR-012**: When any condition of an active guardrail is not met — including a tie between
  responses, a partially-quoted response, or a response arriving after RFQ expiry — the system
  MUST NOT auto-prepare a request; the response remains available only for the manual US3 action,
  and the buyer MUST be shown why the guardrail did not apply.
- **FR-013**: The system MUST reject an auto-preparation guardrail configuration whose maximum
  order value is zero, negative, or otherwise could never realistically trigger or would always
  trigger regardless of response content.
- **FR-014**: Disabling or tightening a guardrail MUST only affect RFQ responses evaluated after
  the change; a request already auto-prepared under a prior guardrail configuration MUST NOT be
  retroactively altered or withdrawn by that change.
- **FR-015**: Every RFQ, response, and auto-preparation event MUST append an audit event
  (creation, send, response received, request prepared — manual or automatic — and guardrail
  changes), consistent with every other mutation in this product.
- **FR-016**: RFQ read access MUST follow the same tenant-scoped, creator-plus-owner/buyer-
  oversight pattern already established for every other member-facing list and detail view in
  this product (see `analyst_conversation`'s RLS policy for the most recent precedent).
- **FR-017**: A member MUST be able to view the status and history of every RFQ sent from their
  tenant — sent, responded (with response count), expired with no response, or converted into a
  purchase request — scoped per FR-016.
- **FR-018**: Every monetary value in an RFQ, a captured response, and an auto-preparation
  guardrail MUST carry an explicit currency; no cross-currency guardrail comparison or
  auto-preparation is permitted — a response in a different currency than the guardrail's
  configured value always falls back to the manual US3 path.

### Key Entities

- **RFQ (Request for Quotation)**: A tenant-scoped, buyer-authored request for one or more
  products/quantities by a needed-by date, sent to one or more suppliers. Tracks its own status
  (draft, sent, expired, converted) independently of any individual response.
- **RFQRecipient**: One supplier asked within one RFQ — tracks that specific supplier's response
  status separately, since different suppliers on the same RFQ respond (or don't) independently.
- **RFQResponse**: A structured quotation captured from a supplier's reply to a specific RFQ,
  linked to both the RFQ and the underlying quotation record the existing extraction pipeline
  already produces — this entity does not duplicate quotation data, it links an existing
  quotation to the RFQ it answers.
- **AutoPreparationGuardrail**: A tenant-scoped, owner-authored rule set (maximum value, supplier/
  category allow-list, minimum response count, maximum price variance) governing when a response
  may be auto-prepared into a draft purchase request without a human reviewing responses first.
- **AutoPreparationEvent**: An audit-linked record of one instance of a guardrail firing,
  recording which rule triggered, which response it acted on, and which draft purchase request it
  produced — this is what makes an auto-prepared draft distinguishable from a manually-prepared
  one in the approval queue.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A buyer can create and send a structured RFQ to multiple suppliers in under 2
  minutes, without drafting free-text correspondence by hand.
- **SC-002**: 100% of supplier replies to a sent RFQ are captured as structured quotations without
  manual re-entry, using the same extraction pipeline and confidence/review behaviour already
  measured for the general quotation inbox.
- **SC-003**: 0% of auto-prepared draft purchase requests bypass the existing human approval
  step — every one, without exception, awaits an approver's explicit decision before any purchase
  order could ever be sent to a supplier.
- **SC-004**: 100% of auto-prepared drafts are visibly distinguishable from manually-prepared ones
  in the approval queue, with the triggering guardrail rule shown.
- **SC-005**: 0% of auto-preparation events occur for a tenant that has not explicitly configured
  and enabled at least one guardrail.
- **SC-006**: A buyer can compare all responses to an RFQ and prepare a request from the winner in
  under 1 minute once responses have arrived.
- **SC-007**: 0% of RFQ responses reveal or leak another tenant's RFQs, suppliers, or history,
  under automated cross-tenant adversarial testing.

## Out of scope

- Negotiating or counter-offering automatically with a supplier — this release captures and
  compares responses; it does not conduct a back-and-forth negotiation on the tenant's behalf.
- Discovering or inviting new, previously-unknown suppliers — RFQs are sent only to suppliers
  already in the tenant's own supplier directory with an on-file contact channel.
- Sending a purchase order to a supplier, in any circumstance, automatic or manual, as part of
  this release — that remains the existing, unchanged purchase-request-and-order flow, gated by
  the existing human approval step this release deliberately does not touch.
- A dedicated negotiation-brief-style evidence surface for RFQ responses (that already exists,
  separately, for supplier risk in R4.1) — this release's comparison view reuses the existing
  offer-comparison capability, it does not build a new one.
