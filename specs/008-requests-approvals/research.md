# Phase 0 Research: Requests + Approvals

## R1 — Branch-scoped RLS extends verbatim to the four new branch-relevant tables

**Decision**: `purchase_request`, `purchase_request_line`, `approval_step`, and
`approval_delegation` reuse R2.0's exact `current_membership_id()`/`current_member_role()`
RESTRICTIVE-policy mechanism (`specs/007-organisation-model/research.md` R1), scoped by each
request's `branch_id`. `threshold_rule` is tenant-wide configuration (owner-managed, like
`budget` at org-wide scope) and needs only ordinary tenant-isolation RLS, not a branch-scoped
RESTRICTIVE layer — a branch manager does not need to see the routing rules to use the product,
only the outcome (which approver a request lands with).

**Rationale**: R2.0 already built and proved this exact mechanism specifically so later releases
would not need a new one (plan.md's Summary and research.md both say so explicitly). Re-deriving
it here would violate the constitution's own guidance against unjustified complexity (Principle
VI) — there is no new isolation axis in this chunk, only new tables sitting on the existing one.

**Alternatives considered**: None seriously — R2.0's mechanism was purpose-built for exactly this
reuse. The only real decision was confirming `threshold_rule` does NOT need branch-scoped RLS
(rejected extending it there: threshold rules are administrative configuration an owner manages
tenant-wide, not a document requesters/approvers browse row-by-row, so there is nothing to leak by
branch).

## R2 — Request value estimation: source, provenance, and freeze timing

**Decision**: Each `purchase_request_line` estimates its own value at line-save time by reusing
the existing price-history mechanism (`apps/api/src/procurepilot_api/modules/offers/price_history.py`'s
`price_history_summary()` and its `last_paid` metric) for the line's `workspace_product_id`: the
most recent `landed_cost` row reachable via `match_decision.matched_workspace_product_id` for that
product, normalised to the product's base unit exactly as `PriceHistoryPoint` already does. The
line stores `estimated_unit_price_amount`, `estimated_unit_price_currency`, and
`estimated_unit_price_source_landed_cost_id` (nullable). While a request is still a draft, this
estimate is recomputed live every time a line changes (so the requester sees a current number
while composing). The moment the request is submitted, every line's estimate is captured as-is —
`estimated_at` is stamped, and nothing about a submitted request's lines is recomputed again, even
if the underlying price history changes afterward. A request's total estimated value (used for
routing and budget comparison) is the sum of its lines' captured estimates once submitted, or the
live sum while still a draft.

A line whose product has no reachable `landed_cost` row at all gets a null estimate and
contributes zero to the total; the request is marked `has_incomplete_estimate = true` wherever its
value is shown (request detail, approval queue row), so nobody mistakes a genuinely-zero-value
request for one that simply has unknown pricing.

**Rationale**: Reuses infrastructure the product already has and already trusts (Principle I —
the estimate carries the same provenance `PriceHistoryPoint` already carries, not a new unaudited
number), rather than inventing a second pricing mechanism. Freezing at submission time satisfies
Principle II directly: an approver's decision must remain explicable against what they actually
saw, and a routing decision or budget-check result that silently changed after the fact — because
someone later paid a different price for the same product — would make historical approval
decisions retroactively unexplainable, exactly what bitemporal/append-only outcome history is
designed to prevent.

**Alternatives considered**:
- *Require the requester to enter an expected unit price manually.* Rejected: the product's core
  differentiator is that it already knows historical pricing better than a requester typing from
  memory would — asking them to guess when the system has better data is a worse product, and
  spec.md's edge case explicitly calls out that requesters usually do not know current pricing.
- *Recompute the estimate live from current price history every time a submitted request is
  viewed.* Rejected: this is exactly what Principle II prohibits for outcome history — an
  approver's decision context must not silently drift out from under an already-recorded decision.
- *Sum multi-currency line estimates into one blended request total by converting to a single
  currency.* Rejected for this release: the product has no currency-conversion mechanism anywhere
  yet (R2.0's research.md R3 and the constitution both treat currency conversion as explicitly out
  of scope), and PR #2's own confirmed cross-currency comparison bugs (GitHub issue #5) are a
  direct warning against introducing implicit conversion here. Simplification adopted: a request's
  lines are expected to share one currency in the common case (the product's tenant-default
  currency); if a request's lines genuinely span currencies, its total estimated value is reported
  per-currency rather than blended, and threshold/budget comparison uses the single-currency total
  when there is one, falling back to "no comparison, incomplete estimate" when there is not. This
  is a deliberate simplification, not a silent gap — real multi-currency requests are expected to
  be rare in the pilot-sized scope this chunk targets.

## R3 — Threshold-based routing, most-specific-wins resolution, delegation, and owner fallback

**Decision**: `threshold_rule` rows each declare an amount range (`min_amount`, nullable
`max_amount`) and an optional `branch_id` (null = tenant-wide default). At submission time, routing
resolves the approver for a request in one deterministic pass, implemented as a pure function
(`resolve_approver(request_value, branch_id, rules, delegations) -> membership_id`) with no
database write of its own:

1. Filter `threshold_rule` rows whose amount range contains the request's total estimated value.
2. Among those, prefer a rule with a matching `branch_id` over a tenant-wide (`branch_id is null`)
   rule — most-specific-wins, exactly as spec.md's edge case requires.
3. If more than one rule at the same specificity still matches (an owner configuration mistake,
   e.g. two overlapping branch-specific ranges), the narrowest amount range wins as the
   tie-breaker, deterministically, not first-row-in-arbitrary-order.
4. If no rule resolves an approver at all — or the resolved approver's membership has been removed
   from the workspace, or the resolved approver has no active delegation covering themselves but is
   simply absent — the request escalates to the tenant's owner.
5. Once an approver (or the owner via escalation) is resolved, `approval_delegation` is checked:
   an active delegation (today's date within `[starts_on, ends_on]`) for that specific approver
   redirects the assignment to the named delegate instead. Delegation is checked AFTER threshold
   resolution, not instead of it, so a delegation is scoped to "whatever this approver would have
   received," not a separate routing dimension of its own.

This function runs once, at submission time, and its result is captured onto the created
`approval_step` row (`assigned_membership_id`) — not re-resolved later. A request already routed
to someone does not silently re-route if the owner adds a new threshold rule the next day.

**Rationale**: A pure function with no DB write is directly and cheaply unit-testable (unlike
R2.0's audit-writer gap, which needed a live HTTP round-trip because the class it belonged to had
no injectable seam) — this chunk deliberately keeps the routing decision as a pure function of its
inputs precisely so it can be proven correct with ordinary unit tests, no live-verification
workaround needed. Capturing the result onto `approval_step` at submission time is the same
freeze-don't-silently-recompute discipline as R2's value estimation, for the same Principle II
reason: routing that could silently change after submission would make "why did this land in my
queue" unanswerable after the fact.

**Alternatives considered**:
- *Re-resolve routing live every time a pending request is viewed, rather than capturing it at
  submission.* Rejected: same Principle II concern as R2 — a request already sitting in someone's
  queue must not silently jump to a different approver's queue because a rule changed underneath
  it, which would be confusing and unauditable.
- *First-matching-rule-in-declared-order, rather than most-specific-wins.* Rejected: spec.md's
  edge case explicitly calls for deterministic most-specific resolution, not an ordering the owner
  has to manage carefully to get right — an accidentally-reordered rule list should not silently
  change routing outcomes.
- *Model delegation as a second, independent routing table checked in place of threshold rules.*
  Rejected: delegation is a property of an approver ("while I'm away, my decisions go to X"), not
  an alternative way to resolve the SAME question threshold rules already answer — layering it on
  top of the threshold-resolved assignee (step 5 above) keeps the two concerns cleanly separable
  and independently testable, matching how the spec's User Story 3 already frames delegation as
  "cover," not "a second, competing rule engine."

## R4 — Audit action naming, extending R2.0's convention

**Decision**: This chunk's audit actions follow the existing `<module>.<entity>_<verb>` shape
established in R2.0 (`organisation.branch_created`, `member.branch_role_assignment_created`, …):
`requests.purchase_request_submitted`, `requests.purchase_request_withdrawn`,
`requests.approval_step_approved`, `requests.approval_step_rejected`,
`requests.approval_step_escalated` (routing fell through to the owner), and
`requests.threshold_rule_created`/`updated`/`deleted` for the owner-configuration side.

**Rationale**: Consistency with the exact naming convention R2.0 established and proved works
(T046's audit-coverage test follows this same shape), rather than inventing a new one for this
chunk. `approval_step_escalated` is its own distinct action (not folded into `_submitted`) because
FR-013 and SC-004 both require routing escalations to be independently auditable — an owner
needs to be able to see, after the fact, which requests reached them only because nobody else was
configured to receive them, as distinct from requests that were always meant for the owner.

**Alternatives considered**:
- *Fold escalation into the submission audit event as a field, not its own action.* Rejected:
  R2.0's audit convention treats every distinct thing-that-happened as its own action string, not
  a flag buried in another event's payload, and escalation is exactly the kind of thing an owner
  would want to search/filter on independently (SC-004 requires escalations to be auditable in
  their own right).
