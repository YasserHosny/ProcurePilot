# Feature Specification: Split an RFQ Between Suppliers and Turn the Split Into Purchase Requests

**Feature Branch**: `024-rfq-basket-split`
**Created**: 2026-10-28
**Status**: Draft. Owner decision 2026-10-28: a split's requests are approved as one group (Q2).
**Tracking**: Jira PPS-96 (plan ID P-66), from the round-1 UX audit PPS-89: findings R1-H2 and R1-L6
(and the split half of R1-H4) in `docs/quality/ux-audits/2026-10-28-round-1/README.md`
**Input**: From an RFQ's Responses, the buyer asks for the cheapest split of the RFQ between the
suppliers who replied. The split is pre-filled from the RFQ's lines and priced from those replies. From
the split's result, the buyer prepares one draft purchase request per supplier, each priced from that
supplier's reply and linked to the RFQ. The approver approves or rejects the split as one.

## Why now

In round 1 (2026-10-28) the basket split found the round's best answer. Rice and flour from الذهبي and
oil and sugar from الوفرة came to SAR 4,063, which is SAR 74 below the cheaper single supplier (SAR 4,137).
Nothing could be done with that answer:

- The result page offers only "Rerun" and "Start New". No step turns it into purchase requests, so the
  buyer has to prepare the single-supplier request instead and lose the saving.
- Basket Split isn't connected to the RFQ. The buyer re-keyed the RFQ's 4 products and quantities
  (about 14 clicks), and each "Add Item" defaulted to rice × 10.
- The split prices each product from the supplier's latest known price for it, which may come from a
  quote other than this RFQ's replies.
- An RFQ can become only one purchase request today (it is marked converted after the first one), so a
  two-supplier outcome has no path at all.
- The page title says "exactly two suppliers" next to "Add Supplier (2–10)", and pack hints overlap the
  label of the next row.

The split is the step where ProcurePilot shows the saving it promises. A saving that can't be ordered
doesn't count.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Split this RFQ from its Responses (Priority: P1)

On RFQ Details › Responses, once at least two replies are reviewed and fully matched, the buyer sees
"Split between suppliers". It opens the split already filled in with the RFQ's products and quantities
and the suppliers who replied. The split uses the prices in those replies. The buyer runs it and sees the
split total, the saving against the best single supplier, and which supplier gets which line.

**Why this priority**: without it, the split is a separate tool that doesn't know about the round, and
its prices may not be the ones the suppliers just quoted.

**Independent Test**: take an RFQ for four products with two reviewed, fully matched replies. Choose
"Split between suppliers" and run it without editing anything. The result matches a hand calculation
from the two quotes: for round 1, SAR 4,063, saving SAR 74 against الوفرة at SAR 4,137.

**Acceptance Scenarios**:

1. **Given** an RFQ with two or more reviewed, fully matched, non-refused replies, **When** the buyer
   opens Responses, **Then** "Split between suppliers" is offered next to the single-supplier "Prepare
   request" actions.
2. **Given** fewer than two such replies, **When** the buyer opens Responses, **Then** the action is
   shown disabled with the reason ("Needs two matched replies", plus "Match N lines" when lines are
   unmatched).
3. **Given** the buyer opens the split from the RFQ, **Then** products, quantities and suppliers are
   filled in from the RFQ and its replies, and the page names the RFQ it came from.
4. **Given** a supplier's reply doesn't quote one of the RFQ's products, **When** the split runs,
   **Then** that product is only allocated to suppliers who quoted it, and the result says which
   supplier didn't quote it.
5. **Given** replies in two different currencies, **When** the buyer opens Responses, **Then** the split
   is not offered, and the reason ("Replies are in different currencies") is shown.
6. **Given** the split is run from the RFQ, **Then** every price it uses comes from that supplier's reply
   to this RFQ, never from another quote.

---

### User Story 2 - Prepare one request per supplier from the split (Priority: P1)

On the split's result, the buyer chooses "Prepare 2 requests". They give the delivery branch and
required-by date once, as they do for a single request. The system creates one draft purchase request per
supplier in the split. Each request holds that supplier's lines at that supplier's quoted prices and is
linked to that supplier's reply. The RFQ is then marked converted, and the buyer lands on a summary
listing both requests.

**Why this priority**: this is the step that turns the round's saving into orders. It is the core of
PPS-96.

**Independent Test**: from the round-1 split, prepare the requests. Two draft requests exist. The
الذهبي one has rice and flour (SAR 2,773) and the الوفرة one has oil and sugar (SAR 1,290). Each names
its supplier and links to the RFQ, and the RFQ shows "Converted" with both requests.

**Acceptance Scenarios**:

1. **Given** a split result allocating lines to N suppliers, **When** the buyer prepares requests,
   **Then** exactly N draft requests are created, one per supplier, each with only that supplier's
   lines at that supplier's quoted pack prices.
2. **Given** the requests are being prepared, **When** any one of them can't be created, **Then** none
   is created and the RFQ stays as it was.
3. **Given** the buyer double-clicks or retries after a timeout, **When** the preparation repeats,
   **Then** the same N requests are returned and no duplicates are created.
4. **Given** the RFQ was already converted (by a single-supplier request or an earlier split), **When**
   the buyer tries to prepare from a split, **Then** they are told it is already converted and shown the
   existing request or requests.
5. **Given** the split result is older than the newest reply to the RFQ (a reply arrived or was
   re-reviewed after the split ran), **When** the buyer tries to prepare, **Then** they are asked to rerun
   the split first.
6. **Given** the split gives every line to one supplier, **When** the buyer prepares, **Then** a single
   request is created. This is the same as "Prepare request" for that reply.

---

### User Story 3 - The split is approved as one (Priority: P1)

The split's requests reach the approver as one item in the Approval Queue: "Split from RFQ … · 2
requests · SAR 4,063 · saves SAR 74 against the best single supplier". Expanding it shows each request,
with its supplier, lines and total. The approver approves or rejects the split as a whole, with one
decision and one reason (owner decision Q2). The approver for the split is the one whose threshold
covers the split's combined total, so splitting a purchase can never route it below the approval it
would otherwise need.

**Why this priority**: R1-H4 found the approver decides without knowing the alternatives. Approving
half a split makes no sense on its own: if the الوفرة half is rejected, the الذهبي half is no longer the
cheapest choice. Routing on the combined total also closes the classic split-purchase loophole.

**Independent Test**: prepare the round-1 split for a branch whose approval threshold changes between
SAR 2,000 and SAR 5,000. The queue shows one item, routed to the approver for SAR 4,063, not to the
lower-threshold approver either half would reach alone. Approving it approves both requests. On a
second split, rejecting it rejects both with the same reason.

**Acceptance Scenarios**:

1. **Given** a split's requests are submitted, **When** the approver opens the Approval Queue, **Then**
   the split appears once, with its RFQ, request count, combined total and saving, and expands to its
   requests.
2. **Given** the approver approves the split, **Then** every request in it is approved at the same
   moment, by the same approver, and each can then become a purchase order.
3. **Given** the approver rejects the split with a reason, **Then** every request in it is rejected with
   that reason, and the buyer sees the split rejected on the RFQ.
4. **Given** branch approval thresholds, **When** a split is submitted, **Then** its approver is chosen
   by the split's combined total, not by each request's own total.
5. **Given** a request that belongs to a split, **When** anyone tries to approve, reject, withdraw or
   submit it on its own, **Then** they are refused and pointed to the split.
6. **Given** a request from a split shown anywhere outside the queue (request page, requests list,
   purchase order), **Then** it shows its split context (RFQ, "1 of N", split total) and links to its
   sibling requests.
7. **Given** a split exceeds a request's branch budget, **When** it is shown to the approver, **Then**
   each request's budget status is visible on the split, as for a single request today.

---

### User Story 4 - Basket Split used on its own is clearer (Priority: P3)

Used outside an RFQ, the Basket Split page says what it does without contradicting itself. A new item
row starts empty rather than as rice × 10, and pack hints don't overlap the next row.

**Why this priority**: these are cosmetic-to-minor issues (R1-L6), but they sit on the page this feature
sends buyers to.

**Acceptance Scenarios**:

1. **Given** the Basket Split page, **Then** the title and the supplier-count control agree (2 to 10
   suppliers).
2. **Given** the buyer adds an item, **Then** the new row has no product and no quantity until the buyer
   picks them.
3. **Given** a product with a pack hint on a narrow screen (≤ 600 px) and in Arabic, **Then** the hint
   doesn't overlap the next row's label.

### Edge Cases

- **A supplier who refused or whose reply was deleted** is not part of the split.
- **A reply with unmatched lines** stops the split from being offered until it is matched (023 makes this
  rare). The reason links to Match Resolution for that quote.
- **Quantities that a supplier's pack or tier rules can't meet exactly** are handled as the split already
  does today. The request takes the quantity the split allocated, in the purchasing pack (ADR-020).
- **Minimum order or delivery fee** that makes a supplier's share uneconomic is part of the split's
  existing landed-cost calculation, and the result shows it.
- **A supplier's reply has expired** (its expiry date is past) when the buyer prepares. The buyer is
  warned, and that supplier's request is still created only if the buyer confirms.
- **The guardrail auto-preparation (ADR-019)** prepares a single request from the cheapest qualifying
  reply. It never prepares a split. Once the RFQ is converted, a split can no longer be prepared, and the
  reverse also holds.
- **Budget**: each request is checked against its branch budget on its own, as today. The summary after
  preparation and the split in the Approval Queue show each request's budget status.
- **Delegation**: an approver's active delegation applies to the split as a whole, as it does to a
  single request.
- **Withdrawing**: the buyer withdraws the split as a whole, never one of its requests.
- **After approval**: each request becomes its own purchase order (one supplier per order). Creating
  one order doesn't affect the other.
- **Roles**: only roles allowed to prepare a request from an RFQ (the RFQ write roles today) can prepare a
  split. Others see the split read-only.
- **Tenant isolation**: the split, its requests and their links stay inside the tenant. A link to another
  tenant's RFQ answers "not found".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: RFQ Details › Responses MUST offer "Split between suppliers" when at least two non-refused
  replies are reviewed, fully matched and in one currency. Otherwise it MUST show the action disabled
  with the specific reason.
- **FR-002**: A split started from an RFQ MUST be pre-filled with the RFQ's products and quantities and
  the suppliers who replied, and MUST record which RFQ it was run for.
- **FR-003**: A split run for an RFQ MUST price each supplier and product only from that supplier's reply
  to that RFQ. If a supplier's reply doesn't quote a product, the split MUST treat that product as not
  offered by that supplier.
- **FR-004**: The split result MUST show the split total, each single-supplier total, and the saving
  against the best single-supplier total, all in the reply currency.
- **FR-005**: From a split run for an RFQ, an authorised buyer MUST be able to prepare purchase requests
  by giving the branch and required-by date once. The default required-by date is the RFQ's needed-by
  date.
- **FR-006**: Preparing from a split MUST create one draft purchase request per supplier with a non-empty
  allocation. Each request MUST hold only that supplier's allocated lines, at the pack price from that
  supplier's reply, and MUST be linked to that supplier's reply.
- **FR-007**: Preparing from a split MUST be all-or-nothing and idempotent. A repeat with the same intent
  MUST return the same requests.
- **FR-008**: An RFQ MUST be converted by exactly one preparation, either one single-supplier request or
  one split. After conversion, the RFQ MUST list every request it produced.
- **FR-009**: Preparation MUST be refused, with a prompt to rerun, when any reply used by the split has
  changed since the split ran.
- **FR-010**: A split's requests MUST be submitted, approved, rejected and withdrawn only as one group
  (owner decision Q2). A decision on the group MUST apply to every request in it at once, with one
  approver, one time and, for a rejection, one reason. An action on a single request of a split MUST be
  refused.
- **FR-011**: The approver for a split MUST be chosen by the split's combined total under the branch's
  approval thresholds, never by the total of an individual request.
- **FR-012**: The Approval Queue MUST show a split as one item (RFQ, request count, combined total,
  saving, budget status per request) that expands to its requests.
- **FR-013**: A request created from a split MUST show, wherever it is shown, the split context: RFQ,
  position among its siblings, split total, saving and links to the sibling requests.
- **FR-014**: Every split preparation MUST be audited with the RFQ, the split, the replies used and the
  requests created.
- **FR-015**: The standalone Basket Split page MUST NOT contradict itself on supplier count. New item
  rows MUST start empty, and pack hints MUST NOT overlap adjacent fields in LTR, RTL or at 600 px and
  below.
- **FR-016**: All new user-facing copy MUST exist in English and Arabic. Money MUST carry its currency
  and use the shared money format.

### Key Entities

- **RFQ**: as today. Its terminal "converted" state can now point to several requests produced by one
  split.
- **Basket split (run)**: as today, plus the RFQ it was run for (if any) and the replies it priced from.
- **Split preparation**: the single act of turning a split into requests. It records the split, the
  requests created and who prepared them. It is what makes a repeat return the same requests.
- **Purchase request**: as today (one supplier's lines, linked to one RFQ reply). It now optionally
  belongs to a split preparation, which gives it siblings, and then follows the group's approval
  state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Replaying round 1, the buyer goes from RFQ Responses to two draft requests worth SAR 4,063
  in at most 4 actions: open split, run, prepare, confirm branch and date. Today this path doesn't exist,
  and setting up the split alone took about 14 clicks.
- **SC-002**: Every price on a request prepared from a split equals the corresponding price in that
  supplier's reply to the RFQ, in 100 % of test cases.
- **SC-003**: Retrying a preparation never creates a duplicate request, and a failed preparation leaves
  no partial set of requests.
- **SC-004**: An approver clears a split with one decision, and every request in it ends in the same
  state, in 100 % of test cases.
- **SC-005**: No split is ever routed to a lower approval threshold than its combined total requires.
- **SC-006**: An RFQ never ends up with both a single-supplier request and a split, even when the two
  are prepared at the same moment.

## Assumptions

- The split engine (the existing basket optimiser) stays as it is: same solver and landed-cost rules.
  This feature changes its inputs (the RFQ's replies) and what can be done with its result.
- Replies must be fully matched before a split is offered. Spec 023 is what makes that cheap, but 024
  doesn't depend on 023 to work.
- Approval of a single request is unchanged. Group approval applies only to requests from a split.
  After approval, each request becomes a purchase order as today, and a purchase order still has one
  supplier.
- The split's saving is shown, not yet recorded in the savings ledger. Recording savings from the round
  is R1-M12, a separate item.

## Out of scope

- Splitting across replies in different currencies (currency conversion for comparison).
- Splitting a single line's quantity between suppliers, beyond what the optimiser already does today.
- Automatic preparation of a split by a guardrail.
- Changes to purchase-order creation beyond what PPS-97 already covers (supplier and source shown).
