# Feature Specification: Smart Compare + Intelligence

**Feature Branch**: `005-smart-compare-intelligence`
**Created**: 2026-08-21
**Status**: Draft
**Input**: User description: "Chunk 4.5 Smart Compare and Intelligence: offers compare endpoint with recommendation scorer, product price-history intelligence view, Smart Compare grid, basic two-supplier basket optimisation via a new services/optimiser using OR-Tools, and an actionable alerts inbox v1"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A buyer compares supplier offers for one product (Priority: P1)

A buyer needs to decide which supplier to order a specific product from, at a specific quantity.
They open the product's compare screen and see every eligible supplier's true landed cost side by
side — not just the sticker price — with one offer clearly recommended, backed by a plain-language
reason, a confidence level, and any risk (for example, a price that expires soon). Changing the
quantity updates every offer's total instantly.

**Why this priority**: This is the chunk's core value proposition — comparable, trustworthy
purchasing decisions — and depends only on chunk 4.4's already-matched, already-costed quotation
lines. Nothing else in this chunk can be demonstrated without it.

**Independent Test**: Can be fully tested by opening the compare screen for a product with two or
more supplier offers on file, confirming the landed cost, recommendation, evidence, and confidence
are all shown, and confirming that changing the quantity field updates every row without a page
reload.

**Acceptance Scenarios**:

1. **Given** a product with three supplier offers of differing landed cost, **When** the buyer
   opens its compare screen at a quantity of 10, **Then** all three offers are listed with their
   landed cost at that quantity, the lowest-cost eligible offer is visually highlighted as
   recommended, and the recommendation shows its evidence, a confidence level, and a validity
   window.
2. **Given** the compare screen is open, **When** the buyer changes the quantity, **Then** every
   offer's landed cost recalculates and the recommendation is re-evaluated without a full page
   reload.
3. **Given** a recommended offer's price is valid only for one more day, **When** the buyer views
   the recommendation, **Then** a risk note states the price's validity window explicitly.
4. **Given** a product has no supplier offers on file yet, **When** the buyer opens its compare
   screen, **Then** they see a clear empty state, not an error or a blank table.

---

### User Story 2 - A buyer sees a product's price history and buying context (Priority: P1)

Before ordering, a buyer wants to know whether today's price is actually good. They open a
product's intelligence view and see a chart of what they've paid over time, per supplier, alongside
the last price paid, the average price paid over a recent rolling window, and the best price ever
recorded — all computed from the workspace's own purchase history, not a new or separate ledger.

**Why this priority**: Historical context is what turns "here is a number" into "here is why you
should trust this number," directly serving Constitution Principle I (evidence over assertion) and
this chunk's core "smart" framing. It is independently valuable even before the recommendation
scorer or basket optimiser exist.

**Independent Test**: Can be fully tested by opening the intelligence view for a product with at
least two historical landed-cost records from different dates and confirming the chart, last-paid,
average-paid, and best-price figures all match what those historical records actually show.

**Acceptance Scenarios**:

1. **Given** a product has landed-cost history from three different quotations over the last six
   months, **When** the buyer opens its intelligence view, **Then** a chart shows a point or series
   per supplier over time, and "last paid," "average paid (rolling window)," and "best price" cards
   show figures that are traceable back to those specific historical records.
2. **Given** a product has no purchase history yet, **When** the buyer opens its intelligence view,
   **Then** they see a clear empty state explaining that history builds up as quotations are
   matched and costed, not an error.

---

### User Story 3 - A buyer splits one basket across two suppliers (Priority: P2)

A buyer has a short list of products and quantities they need and wants to know whether splitting
the order across two particular suppliers, rather than buying everything from one, saves money once
minimum-order and delivery considerations are respected. They submit the basket and, shortly after,
see a recommended split between the two suppliers and the expected total cost.

**Why this priority**: This is the first real use of a dedicated optimisation engine and delivers
clear value, but it is scoped to exactly two suppliers and a plain minimum-cost objective — a
deliberately narrow slice of the full basket-optimisation vision, appropriately lower priority than
the P1 stories that make every other product decision trustworthy first.

**Independent Test**: Can be fully tested by submitting a basket of two or more products, each with
offers from the same two named suppliers, and confirming a completed allocation appears shortly
after submission with a lower or equal total cost than buying everything from either supplier
alone.

**Acceptance Scenarios**:

1. **Given** a basket of three products each with offers from Supplier A and Supplier B, **When**
   the buyer submits the basket for a two-supplier split, **Then** they can see the split is in
   progress, and once complete, see a recommended per-supplier allocation and its expected total
   landed cost.
2. **Given** a basket where splitting does not actually reduce cost versus a single supplier,
   **When** the split completes, **Then** the result plainly recommends buying everything from the
   single cheaper supplier rather than forcing an artificial split.
3. **Given** a basket item has no offer from either of the two chosen suppliers, **When** the buyer
   submits the basket, **Then** they are told which item cannot be allocated, before or instead of
   receiving an incomplete silent result.

---

### User Story 4 - A buyer sees what needs their attention without hunting for it (Priority: P2)

Rather than re-checking every product's compare screen, a buyer opens an alerts inbox and sees a
short list of things that actually need a decision now — a recommended price about to expire, a
previously preferred supplier's offer disappearing, or an unusually large price swing versus
history — and can dismiss or act on each one.

**Why this priority**: This is the chunk's "every insight ends in an action" surface (Constitution
Principle IV), but it depends on the compare and intelligence data already existing from P1, so it
is sequenced after them.

**Independent Test**: Can be fully tested by creating conditions that should raise each alert type
(an expiring recommended price, a disappeared preferred-supplier offer, a large price swing) and
confirming each appears in the inbox and can be dismissed.

**Acceptance Scenarios**:

1. **Given** a recommended offer's price expires within a configured warning window, **When** the
   buyer opens the alerts inbox, **Then** an alert for that product appears explaining the
   expiring price.
2. **Given** a buyer dismisses an alert, **When** they reopen the inbox, **Then** that alert no
   longer appears.
3. **Given** no alert conditions currently exist for the workspace, **When** the buyer opens the
   inbox, **Then** they see a clear empty state, not an error.

---

### Edge Cases

- What happens when a product's only supplier offer's price has already expired (`valid_to` in the
  past)? It must not be silently treated as still valid; the compare screen must show it as expired
  and exclude it from being the recommended offer.
- What happens when two supplier offers tie exactly on landed cost? A deterministic tie-break (for
  example, higher match confidence, then better lead time) must be applied and disclosed as part of
  the recommendation's evidence, not decided arbitrarily.
- What happens when the two-supplier basket split has no feasible allocation at all (for example,
  neither supplier can supply a required product)? The system must report which product(s) blocked
  a feasible solution rather than returning an empty or partial allocation silently.
- What happens when a workspace has zero purchase history for every product? Every screen in this
  chunk (compare, intelligence, alerts) must degrade to a clear, friendly empty state rather than
  erroring, since this is the state every new workspace starts in.
- What happens when the alerts inbox's underlying conditions change between page loads (for
  example, a price that was expiring is now actually expired)? The alert should update to reflect
  current reality on next load, not persist a stale description.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list every eligible supplier offer for a given product at a given
  required quantity, each showing its landed cost, normalised unit price, lead time, a reliability
  signal, a stock signal, and the match confidence of the underlying product match — reusing chunk
  4.4's landed-cost computation and match records, never recomputing landed cost independently.
- **FR-002**: System MUST exclude, or clearly mark as expired, any offer whose price validity
  window has already passed at the time of comparison.
- **FR-003**: System MUST recommend exactly one offer per comparison (when at least one eligible
  offer exists), with a structured evidence breakdown (what made this the recommended offer),
  a calibrated confidence, an explicit risk note when one applies, and the recommendation's
  validity window — never a bare "recommended" label with no reasoning surfaced.
- **FR-004**: System MUST recalculate every offer's landed cost and re-evaluate the recommendation
  when the required quantity changes, without requiring a new page load.
- **FR-005**: System MUST apply a documented, deterministic tie-break rule when two or more offers
  are equally recommendable, and that tie-break rule must itself appear in the evidence shown to
  the buyer.
- **FR-006**: System MUST show, per product, a price history over time per supplier, derived
  entirely from that workspace's own existing landed-cost records — no new, separate source of
  price truth is introduced by this chunk.
- **FR-007**: System MUST show, per product, the last price paid, an average price paid over a
  rolling window, and the best (lowest) price paid on record, each computed from that same
  historical data and each traceable back to the specific record(s) behind it.
- **FR-008**: System MUST allow a buyer to submit a basket of products and required quantities,
  restricted in this chunk to exactly two named suppliers, for a minimum-cost allocation split
  between them.
- **FR-009**: System MUST treat a basket split as a tracked, asynchronous unit of work with an
  observable status (for example, pending, running, completed, failed) rather than a synchronous
  call that blocks the buyer, consistent with this project's existing pattern for longer-running
  work (chunk 4.3's extraction jobs).
- **FR-010**: System MUST report which product(s), if any, prevent a feasible two-supplier
  allocation, rather than returning an empty or silently partial result.
- **FR-011**: System MUST NOT apply minimum-order-value, delivery-tier, branch, budget, or
  preference-weight constraints to the two-supplier split in this chunk; it optimises for lowest
  total landed cost across exactly two suppliers only. Full basket optimisation with those
  constraints is out of scope for this chunk (see Out of Scope).
- **FR-012**: System MUST surface an alerts inbox listing conditions needing the buyer's attention:
  at minimum, a recommended offer's price nearing expiry, a previously preferred supplier's offer
  disappearing from the eligible set, and a price swing beyond a configured threshold versus
  historical average.
- **FR-013**: Users MUST be able to dismiss an individual alert, after which it no longer appears
  unless the underlying condition recurs.
- **FR-014**: System MUST re-evaluate alert conditions against current data on each inbox load,
  rather than persisting a stale description of a condition that has since changed.
- **FR-015**: System MUST express every monetary value in this chunk (offers, landed cost,
  recommendations, basket allocations, price history) as an explicit amount-and-currency pair,
  never a bare number, matching the convention already established in chunks 4.2–4.4.
- **FR-016**: System MUST show every screen introduced by this chunk (compare, intelligence,
  alerts, basket result) in both of the workspace's supported languages, right-to-left included,
  using this project's existing translation catalogue convention — no hardcoded strings.
- **FR-017**: System MUST NOT expose data from another tenant's workspace through any endpoint or
  screen introduced by this chunk; a cross-tenant reference MUST behave as not found, never as
  forbidden, matching this project's existing tenant-isolation convention.
- **FR-018**: System MUST restrict basket-split submission to roles already permitted to act on
  purchasing decisions (owner, buyer); other roles may view compare, intelligence, and alerts
  screens but not submit a basket split.

### Key Entities

- **Offer**: A supplier's current, comparable position for one product at one quantity — landed
  cost, normalised unit price, lead time, reliability signal, stock signal, match confidence, and
  the price's validity window. Derived from existing matched, costed quotation lines; not a new
  system of record for price.
- **Recommendation**: The outcome of comparing a product's offers at a given quantity — the chosen
  offer, its evidence breakdown, confidence, risk note, and validity window. Computed at request
  time from current offers and history; not stored as a standing decision (a buyer's actual
  purchase choice, if captured, belongs to chunk 4.6's savings ledger, not this chunk).
- **PriceHistoryPoint**: A single historical landed-cost fact for a product from a specific
  supplier at a specific point in time, used to build the intelligence view's chart and summary
  figures. Derived entirely from existing landed-cost records, not a new source of truth.
- **BasketSplitJob**: A tracked, asynchronous request to allocate a basket of products and
  quantities across exactly two named suppliers at minimum cost, with an observable status and,
  once complete, a resulting allocation and expected total cost (or a report of which items
  blocked a feasible solution).
- **Alert**: A single actionable condition surfaced to a buyer — its kind (expiring price,
  disappeared preferred offer, price swing), the product and evidence it concerns, and whether it
  has been dismissed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A buyer can see a fully reasoned recommendation — landed cost, evidence, confidence,
  and risk — for any product with at least one supplier offer, without leaving the compare screen.
- **SC-002**: Changing the required quantity on the compare screen updates every visible offer and
  the recommendation in under 150 milliseconds, so the interaction feels instantaneous rather than
  like a page reload.
- **SC-003**: A product's price-history view accurately reflects that workspace's own purchase
  history with no discrepancy between the displayed "last paid"/"average paid"/"best price" figures
  and the underlying records they are computed from.
- **SC-004**: A two-supplier basket split reaches a completed status (or an explicit, actionable
  "no feasible allocation" report) without requiring the buyer to refresh the page manually to find
  out.
- **SC-005**: Every alert a buyer sees corresponds to a real, currently-true condition in their
  workspace's own data — no alert persists once its underlying condition has resolved.
- **SC-006**: 80% of recommended offers are accepted by the buyer without a manual override —
  this specific target cannot be measured honestly until real historical buyer decisions exist to
  compare against (see Assumptions); it is recorded here as the target this chunk is building
  toward, not a claim this chunk can validate today.

## Assumptions

- **Recommendation-acceptance measurement (SC-006)** cannot be validated in this chunk: there is no
  real buyer-decision history yet, the same honest-gap situation chunk 4.3's extraction-accuracy
  target and chunk 4.4's matching-precision target were already in. The recommendation scorer and
  its evidence output are built and testable on synthetic/fixture data; the 80%-acceptance figure
  itself is deferred to chunk 4.6, when outcome capture exists to measure it against.
- **The 150ms recalculation budget (SC-002) is a client-side interaction budget**, not a new
  server round-trip per keystroke: a product's set of offers is fetched once when the compare
  screen opens, and landed cost is already a pure function of quantity plus stored per-unit inputs
  (chunk 4.4), so recalculating every visible offer as the quantity changes is arithmetic the
  client already has everything it needs for. Requiring a server round-trip on every quantity
  change would make the 150ms budget dependent on network conditions this project does not control.
- **The two-supplier basket split names its two suppliers by the buyer's own choice** at submission
  time (for example, "split this basket between my two lowest-cost eligible suppliers" or two the
  buyer names explicitly) rather than the system silently choosing which two suppliers to consider
  out of an arbitrarily large set — full any-N-supplier optimisation is explicitly out of scope
  (see Out of Scope).
- **"Reliability" and "stock" signals shown per offer** reuse whatever supplier-level reliability
  and stock fields already exist from chunk 4.2's supplier record; this chunk does not introduce a
  new reliability-scoring or inventory-tracking system.
- **A recommended offer's "risk note"** is a plain-language surfacing of a small, fixed set of
  known risk conditions (price expiring soon; recommended offer's confidence below a high-trust
  threshold) rather than an open-ended risk-detection system.

## Out of Scope

- The savings ledger, outcome capture, and Excel/PDF export (chunk 4.6, F22–F24, US-010, US-011).
- Purchase requests, approval routing, branches, cost centres, budgets, and the policy engine
  (Phase 2, F25–F28) — this project's CLAUDE.md explicitly defers all Phase 2 features.
- Full basket optimisation across an arbitrary number of suppliers with minimum-order values,
  delivery tiers, branch/budget constraints, and preference weights (the full scope of F21) — this
  chunk ships only the minimum-cost, exactly-two-supplier version described above.
- The "Create request" and "Record purchase" actions sketched alongside the Smart Compare grid
  mockup — both depend on entities this chunk does not build (purchase requests belong to Phase 2;
  recording an actual purchase belongs to chunk 4.6's outcome capture) and are represented as
  disabled or omitted in this chunk's actual screen, not wired to real functionality.
- A learned or feedback-tuned recommendation ranking model — this chunk's recommendation scorer is
  a first-version weighted score with calibrated thresholds, per `engineering-spec.md` §5.2; a
  learned ranking model based on outcome feedback is explicitly future work in that same document.
- Any currency conversion — recommendations and comparisons only ever compare offers already in a
  common currency; cross-currency comparison is not part of this chunk.
