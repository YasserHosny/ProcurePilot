# Feature Specification: Requests + Approvals

**Feature Branch**: `008-requests-approvals`
**Created**: 2026-08-23
**Status**: Draft
**Input**: User description: "Release R2.1 Requests + Approvals (Phase 2, web only): purchase
request creation with branch and cost-centre assignment, approval routing with threshold rules
(amount-based, branch-scoped approver resolution) and delegation, budget check at request
submission time against the R2.0 budget definitions (informational overlap-style warning when a
request would exceed the remaining budget for its scope, not a hard block — consistent with how
R2.0's budget overlap_warning already works), a full audit log entry on every request submission,
approval, rejection, and override, and an approval queue screen where an approver sees requests
awaiting their decision with full context (requester, branch, cost centre, lines, required-by
date, budget status). This is the workflow layer R2.0's organisation model (branches, cost
centres, budgets, branch-scoped roles) was built to support, and is itself the web-only foundation
R2.2/R2.3 mobile approvals depend on. Explicitly OUT of scope for this release: the mobile app
entirely (R2.2-R2.3), the advanced basket optimiser, supplier performance intelligence/scorecards,
anomaly detection, scheduled reports and email digests, and the broader policy engine
(preferred/blocked suppliers, spend limits beyond simple budget check, exception justification
workflows) — those are later Phase 2 releases (R2.4-R2.5) per the roadmap. Draft sketches already
exist and should be treated as a non-binding starting point, not a locked contract:
docs/architecture/data-dictionary.md's 'PurchaseRequest'/'ApprovalStep' placeholder entities, and
docs/architecture/api-specification.md's 'Requests & Approvals (Phase 2)' sketch (POST /requests,
POST /requests/{id}/approve, POST /requests/{id}/reject, GET /approvals/pending)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Buyer submits a purchase request (Priority: P1)

A buyer (or any requesting member) puts together a purchase request: which branch and cost
centre it is for, when it is needed by, and the line items and quantities wanted. Submitting it
moves it out of their own drafts and into the approval pipeline, where it becomes visible to
whoever is responsible for deciding on it.

**Why this priority**: Nothing else in this release has a subject without a request existing
first. It is the entry point to the whole workflow this chunk delivers.

**Independent Test**: Can be fully tested by a buyer creating a request naming a branch, cost
centre, required-by date, and at least one line, submitting it, and confirming it appears with
status "submitted" and the correct requester, branch, and cost centre attached — independent of
who eventually approves it or what the routing/budget logic decides.

**Acceptance Scenarios**:

1. **Given** a buyer on the new-request screen, **When** they fill in branch, cost centre,
   required-by date, and one or more lines and submit, **Then** the request is created with
   status "submitted" and appears in their own request list.
2. **Given** a request still in draft, **When** the buyer saves without submitting, **Then** the
   request persists as "draft" and is not yet visible to any approver.
3. **Given** a submitted request, **When** the buyer views it again, **Then** they see its current
   status and, once decided, the approver's comment.

---

### User Story 2 - Approver decides on a request from the approval queue (Priority: P1)

An approver opens their approval queue and sees every request currently awaiting their decision,
each with enough context — requester, branch, cost centre, lines, required-by date, and budget
status — to decide without hunting for information elsewhere. They approve or reject, optionally
with a comment, and the decision is immediately reflected back to the requester.

**Why this priority**: A request that can be submitted but never decided on delivers no value —
this is the other half of the minimum useful loop, and is tested independently of how routing
picked this particular approver (a request can be seeded directly for this story's own tests).

**Independent Test**: Can be fully tested by seeding a submitted request routed to a given
approver, having that approver open their queue, and approving or rejecting it with a comment —
confirming the request's status changes accordingly and the requester can see the outcome.

**Acceptance Scenarios**:

1. **Given** a submitted request routed to them, **When** an approver opens their approval queue,
   **Then** they see the request listed with requester, branch, cost centre, lines, required-by
   date, and budget status, without navigating elsewhere.
2. **Given** a request in their queue, **When** the approver approves it with a comment,
   **Then** the request's status becomes "approved", the comment is stored, and the request no
   longer appears in the approver's pending queue.
3. **Given** a request in their queue, **When** the approver rejects it with a comment, **Then**
   the request's status becomes "rejected", the comment is stored and visible to the requester,
   and the request no longer appears in the pending queue.
4. **Given** a request awaiting a specific approver's decision, **When** a different member who is
   not that approver (and not an owner) attempts to approve or reject it, **Then** the system
   refuses the action.

---

### User Story 3 - Threshold-based routing sends a request to the right approver, with delegation for cover (Priority: P2)

An owner defines threshold rules — for example, requests under a set amount route to the branch's
own approver, larger ones route to a more senior approver or the owner. When a request is
submitted, the system resolves which approver(s) it belongs in front of using the request's total
value, its branch, and those rules. An approver who is going to be unavailable can delegate their
pending decisions to another eligible approver for a period, so requests do not stall waiting for
someone who is out.

**Why this priority**: Routing and delegation make the approval step correct and resilient rather
than a single hard-coded reviewer, but the underlying submit-then-decide loop (User Stories 1–2)
already delivers a usable workflow without them — this refines who ends up in the queue, not
whether the queue exists.

**Independent Test**: Can be fully tested by defining two threshold tiers with different target
approvers, submitting requests at values that land in each tier, and confirming each lands in the
correct approver's queue; and separately, by having an approver delegate to a colleague and
confirming a newly submitted request appears in the delegate's queue instead for the delegation's
duration.

**Acceptance Scenarios**:

1. **Given** an owner has defined a threshold rule ("requests up to £500 route to the branch
   approver, above that to the owner"), **When** a request under £500 is submitted for that
   branch, **Then** it routes to the branch's approver.
2. **Given** the same threshold rule, **When** a request over £500 is submitted, **Then** it
   routes to the owner instead.
3. **Given** an approver sets up a delegation to a named colleague for a date range, **When** a
   request that would have routed to them is submitted within that range, **Then** it appears in
   the delegate's queue, and the original approver's own queue does not gain it.
4. **Given** a branch has no approver assigned at all, **When** a request for that branch is
   submitted, **Then** it escalates to the owner rather than being routed nowhere.

---

### User Story 4 - Requester and approver see budget status before a decision is made (Priority: P2)

Before submitting, and again when an approver is reviewing, the system shows how a request's
value compares to the remaining budget for its scope (whichever of organisation, branch, or cost
centre the applicable R2.0 budget targets) for the current period — with a clear warning if
approving would exceed it. This is informational: it never blocks submission or approval, it only
makes the financial consequence visible before someone commits to it.

**Why this priority**: Budgets already exist from R2.0 with no spend tracked against them yet;
surfacing that comparison is valuable but the workflow functions correctly (Stories 1–2) even
before this visibility is added, since nothing here is a hard gate.

**Independent Test**: Can be fully tested by defining a budget for a scope, submitting a request
against that scope whose value is within the remaining budget and confirming no warning appears,
then submitting one that would exceed it and confirming a clear warning appears on both the
requester's view and the approver's queue — with the request still submittable and decidable
either way.

**Acceptance Scenarios**:

1. **Given** a branch budget with remaining headroom greater than a request's value, **When**
   the request is submitted, **Then** no budget warning appears anywhere for that request.
2. **Given** a branch budget with less remaining headroom than a request's value, **When** the
   request is submitted, **Then** a warning showing the remaining budget and the request's value
   appears on the request and in the approver's queue, and the request can still be submitted and
   approved.
3. **Given** a request's scope has no budget defined at all, **When** it is submitted, **Then**
   no budget status is shown for it (there is nothing to compare against), and nothing about
   submission or approval is affected.

---

### Edge Cases

- What happens when a request's branch or cost centre is deactivated/archived after submission but
  before a decision is made? The request keeps its original assignment and remains decidable — a
  branch closing down does not retroactively invalidate requests already in flight.
- What happens when a requester wants to change their mind after submitting? They can withdraw a
  request that has not yet been decided, moving it to a "withdrawn" status; they cannot edit a
  submitted request in place, since an approver may already be reviewing what they saw.
- What happens when a request is rejected and the requester wants to try again? They create a new
  request (optionally copying the rejected one's details); a rejected request is never reopened or
  resubmitted, so the audit trail of what was decided and why stays intact.
- What happens when more than one threshold tier or delegation could plausibly apply to the same
  request at the same time? The most specific rule wins (a branch-specific rule over a
  tenant-wide default; an active delegation over the original assignee), and this resolution is
  deterministic, not first-match-wins on an arbitrary rule order.
- What happens when an approver is deleted or removed from the workspace with requests still
  pending their decision? Those requests escalate to the owner, the same fallback as a branch with
  no approver at all, rather than being stuck forever.
- What happens if a request has zero lines? The system does not allow submission of a request with
  no lines — a request must name at least one item to be a purchase request at all.
- What happens when a requester does not know the current price of a line item at request time (the
  common case — pricing is usually discovered later via quotations)? The system estimates each
  line's value from the product's own most recent known price rather than requiring the requester
  to guess, so routing and budget checks always have a number to work with.
- What happens when a line's product has no price history at all (never quoted before)? That line
  contributes zero to the request's estimated value, and the request is marked as having an
  incomplete estimate wherever its value is shown — informational only, never blocking submission,
  routing, or approval.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow a member to create a purchase request naming a branch, an
  optional cost centre, a required-by date, and one or more lines (each a product/quantity/note),
  and to save it as a draft before submitting.
- **FR-002**: System MUST allow a requester to submit a draft request, moving it from "draft" to
  "submitted" and making it visible to whichever approver(s) it routes to.
- **FR-003**: System MUST reject submission of a request with zero lines.
- **FR-004**: System MUST allow a requester to withdraw their own request at any point before a
  decision is recorded, and MUST NOT allow editing a request once it has been submitted.
- **FR-005**: System MUST provide an approval queue showing every request currently awaiting the
  signed-in approver's decision, each with requester, branch, cost centre, lines, required-by
  date, and budget status (when applicable) visible without further navigation.
- **FR-006**: System MUST allow an approver to approve or reject a request in their queue, each
  optionally with a comment, and MUST require an explicit decision by a human member for every
  request — no request may become approved without a recorded human decision, consistent with the
  product's no-autonomous-purchasing rule.
- **FR-007**: System MUST refuse an approve/reject action from any member other than the request's
  currently-resolved approver (or an owner acting as the standing override), the same way the
  product already refuses actions outside a member's role and scope elsewhere.
- **FR-008**: System MUST allow an owner to define threshold rules that resolve which approver a
  submitted request routes to, based on the request's total value and its branch, with a
  most-specific-rule-wins resolution when more than one rule could apply.
- **FR-009**: System MUST escalate a request to the owner when no threshold rule resolves an
  approver for it — including a branch with no approver assigned, and an approver who has been
  removed from the workspace with requests still pending their decision.
- **FR-010**: System MUST allow an approver to delegate their pending and future approval
  decisions to another eligible approver for an explicit date range, and MUST route any request
  that would otherwise land in the delegator's queue to the delegate instead for that range.
- **FR-011**: System MUST compare a submitted request's value against the remaining amount of
  whichever R2.0 budget applies to its scope (organisation, branch, or cost centre) for the
  current period, and surface a clear, informational warning wherever the request is visible when
  it would exceed that remaining amount — never blocking submission or approval because of it.
- **FR-012**: System MUST show no budget status for a request whose scope has no applicable budget
  defined, rather than a misleading zero or a blocking state.
- **FR-013**: System MUST record every request submission, withdrawal, approval, rejection, and
  routing escalation in the existing append-only audit log, consistent with how every other
  administrative action in the product is already audited.
- **FR-014**: System MUST scope every requests/approvals screen to the signed-in member's role and
  branch assignment established in R2.0: a member holding a branch-scoped role sees only requests
  for their own branch(es); an owner sees every request in the tenant.
- **FR-015**: System MUST estimate each request line's value from the product's most recently known
  price rather than requiring the requester to supply one, summing lines into the request's total
  estimated value used for routing (FR-008) and budget comparison (FR-011); a line whose product
  has no known price contributes zero and the request MUST be marked as having an incomplete
  estimate wherever its value is shown, without blocking submission, routing, or approval.

### Key Entities

- **Purchase Request**: A requester's ask to buy something, scoped to a branch and optionally a
  cost centre, with a required-by date and one or more lines. Moves through
  draft → submitted → (approved | rejected | withdrawn). Carries a total estimated value (FR-015)
  used for routing and budget comparison. The subject every approval, threshold rule, and budget
  check in this release acts on.
- **Purchase Request Line**: One item and quantity (with an optional note) within a purchase
  request, plus its estimated unit value drawn from the product's own price history (FR-015); a
  request's total estimated value for routing and budget-check purposes is the sum of its lines.
- **Approval Step**: The record of a single decision (or pending decision) on a request — which
  approver it is assigned to, its status (pending, approved, rejected), any comment, and when it
  was decided. Produced by routing at submission time.
- **Threshold Rule**: An owner-defined rule mapping a request-value range and an optional branch
  scope to the approver a matching request should route to. Resolved most-specific-first when more
  than one rule could apply to the same request.
- **Approval Delegation**: A time-bounded handoff of one approver's pending and incoming decisions
  to another eligible approver, so an absence does not stall the requests that would have routed
  to them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A requester can create, fill in, and submit a purchase request in under 3 minutes
  without external help.
- **SC-002**: An approver can see every context field needed to decide on a request (requester,
  branch, cost centre, lines, required-by date, budget status) without leaving the approval queue
  screen, for 100% of requests in their queue.
- **SC-003**: 100% of requests route to a resolvable approver — either a threshold-matched
  approver, an active delegate, or the owner as fallback — with none left unroutable.
- **SC-004**: 100% of request submissions, withdrawals, approvals, rejections, and routing
  escalations appear in the audit log with the correct actor, action, and target.
- **SC-005**: Zero purchase requests reach "approved" status without an explicit, recorded human
  decision.
