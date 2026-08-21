# Feature Specification: Matching and Normalisation

**Feature Branch**: `004-matching-normalisation`
**Created**: 2026-08-21
**Status**: Draft
**Input**: User description: "Chunk 4.4: Matching and Normalisation. Reviewed quotation line items must be matched to catalogue products with calibrated confidence, using a layered pipeline: deterministic keys (GTIN, supplier SKU, alias hit), then pg_trgm lexical similarity, then pgvector semantic similarity, then feature scoring (brand, variant, pack, unit, price plausibility), landing on a calibrated confidence that auto-accepts, auto-rejects, or routes to a human match-resolution queue. A confirmed match or a no-match-create-new-product decision creates or reuses a ProductAlias so the same supplier wording never needs re-matching. Unit and pack normalisation must apply to matched quotation lines so quantities are comparable across suppliers. A landed-cost engine computes total cost per line as a deterministic, versioned, replayable function. Matching precision at auto-accept target 92 percent, human review band target 8 percent, both measured on a held-out labelled benchmark that does not yet exist."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A reviewed quotation's lines are matched automatically (Priority: P1)

Once a buyer has reviewed and confirmed a quotation (chunk 4.3), each of its line items is
automatically compared against the workspace's catalogue. Lines the system can match with high
confidence — because the supplier's wording has been seen before, or a product code matches
exactly — are matched without anyone touching them.

**Why this priority**: This is the entire value of the chunk: turning a reviewed quotation into
comparable, priced lines without manual re-entry. Without automatic matching for the easy cases,
every line becomes manual work and the product delivers no time saving at all.

**Independent Test**: Take a reviewed quotation whose line wording exactly matches a previously
confirmed alias, and confirm the line is matched to the correct product with no human action,
carrying a confidence score and the reason it matched.

**Acceptance Scenarios**:

1. **Given** a reviewed quotation line whose wording exactly matches an existing product alias,
   **When** matching runs, **Then** the line is matched to that alias's product automatically, with
   a confidence score and a stated reason (alias hit).
2. **Given** a reviewed quotation line carrying a GTIN or supplier code that exactly matches a
   product already in the catalogue, **When** matching runs, **Then** the line is matched
   automatically on that deterministic key, without needing similarity scoring at all.
3. **Given** a reviewed quotation line with no exact key match, **When** matching runs, **Then**
   the system still proposes the best candidate(s) it can find using wording and product-attribute
   similarity, each with its own confidence and reason.
4. **Given** a matched line, **When** a workspace member views it, **Then** they can see which
   product it was matched to, at what confidence, and why — not just that it happened.

---

### User Story 2 - A reviewer resolves matches that need a human decision (Priority: P1)

A line's best candidate match is not confident enough to accept automatically. A reviewer opens a
match-resolution queue, sees the candidates ranked with their reasons, and either confirms one,
tells the system it is a different pack size or variant, marks it a compatible alternative, or
says nothing fits and creates a new product. Whatever they decide is remembered.

**Why this priority**: Constitution Principle III requires a human in the loop wherever automation
is not confident — this is that loop for matching specifically. Without it, the product would
either force every uncertain line to a dead end or silently guess, and Principle I forbids a
confident-looking match that is really a guess.

**Independent Test**: Take a line with no strong candidate, open it in the resolution queue, choose
"no match — create new product," and confirm a new catalogue product is created and the line is
matched to it.

**Acceptance Scenarios**:

1. **Given** a line below the auto-accept confidence, **When** a reviewer opens it, **Then** they
   see its ranked candidates side by side with the reason each one scored the way it did.
2. **Given** a reviewer resolving a line, **When** they choose an outcome, **Then** they can say
   the same product, a different pack size, a different variant, a compatible alternative, or no
   match — not just accept or reject.
3. **Given** a reviewer who confirms a match, **When** the decision is saved, **Then** the exact
   supplier wording on that line becomes an alias for the chosen product, so an identical wording
   later resolves automatically per User Story 1.
4. **Given** a reviewer who finds nothing fitting, **When** they choose to create a new product,
   **Then** a new catalogue product is created (reusing the existing product-creation capability)
   and the line is matched to it.
5. **Given** outstanding match-resolution work, **When** a reviewer works through the queue,
   **Then** they can select a candidate and confirm it using the keyboard alone, without the mouse.

---

### User Story 3 - Every matched line shows its true landed cost (Priority: P1)

Once a line is matched, a workspace member can see not just the supplier's unit price but the full
landed cost of that line — price, tax, delivery, and discount combined — computed the same way
every time, on a quantity that is normalised to the same base unit the catalogue already uses.

**Why this priority**: A unit price alone is not a comparable cost, and comparing raw prices across
suppliers is the exact mistake this product exists to prevent. Landed cost is also the first real
test of Constitution Principle II: without a deterministic, versioned, replayable computation here,
nothing downstream (comparison, savings) can be trusted either.

**Independent Test**: Take a matched line with a known unit price, quantity, VAT rate, and delivery
fee, and confirm the displayed landed cost equals the expected calculation exactly, with the rule
version used recorded alongside it.

**Acceptance Scenarios**:

1. **Given** a matched line with a unit price, quantity, tax rate, delivery fee, and discount,
   **When** its landed cost is computed, **Then** the result reflects all of them combined, in the
   line's own currency, never a bare number.
2. **Given** a landed-cost computation, **When** it is stored, **Then** it carries the identifier
   of the rule version used, alongside the raw inputs it was computed from.
3. **Given** a previously computed landed cost and its stored rule version, **When** it is
   recomputed from the same raw inputs and the same rule version, **Then** the result is identical
   — every time, not just usually.
4. **Given** a matched line's quantity in the supplier's own pack size, **When** its landed cost
   and quantity are shown, **Then** they are expressed on the same base unit the catalogue already
   normalises to, so it is comparable to other lines regardless of supplier.

---

### User Story 4 - A landed cost can be explained after the fact (Priority: P2)

Weeks after a quotation was matched and priced, someone asks how a particular line's landed cost
was calculated. The system can show the original inputs, the rule version used, and reproduce the
same figure on demand — without that figure ever having silently changed underneath them.

**Why this priority**: This is the audit half of Principle II. It matters as soon as pricing rules
change at all, but the product delivers its core value (User Stories 1-3) before anyone needs to
look backward, so it can follow rather than block the MVP loop.

**Independent Test**: Change the active landed-cost rule version, then reopen a line priced under
the previous version, and confirm its displayed cost and rule version are unchanged from when it
was first computed.

**Acceptance Scenarios**:

1. **Given** a landed cost computed under an earlier rule version, **When** the active rule version
   later changes, **Then** the earlier computation's stored value and rule version remain exactly
   as they were — nothing is recomputed in place.
2. **Given** any stored landed-cost computation, **When** a workspace member inspects it, **Then**
   they can see every input that fed it and the exact rule version applied.

---

### Edge Cases

- What happens when two or more candidates score similarly and no single one clearly wins? Both are
  presented to the reviewer with their individual reasons; the system does not guess between
  close-scoring candidates.
- What happens when no candidate at all can be found for a line? It still routes to the
  match-resolution queue, offered as a "no match" case with the create-new-product path directly
  available — never a dead end.
- What happens when a matched product is later archived in the catalogue? The historical match
  itself is unaffected — it is a recorded fact, not a live reference that disappears — but the
  workspace should be able to see that the matched product is now archived.
- What happens when a line's tax rate is absent? It is treated as zero tax for that line, not as an
  error; VAT-exempt items are a legitimate case, not a data problem.
- What happens when a line's currency differs from the currency the matched product is usually
  priced in? Landed cost is computed and shown in the line's own currency; no automatic currency
  conversion happens anywhere in this chunk.
- What happens if the same exact supplier wording was previously confirmed as one product, but a
  reviewer now wants to attach it to a different product instead? Out of scope for this chunk —
  correcting or retiring a previously confirmed alias is not covered here; a new, different wording
  can always be resolved independently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST attempt to match every line item of a quotation only once that quotation
  has reached its reviewed, trusted state (chunk 4.3) — never a line from an unreviewed or
  in-progress quotation.
- **FR-002**: System MUST attempt deterministic matching keys first — an exact GTIN match, an exact
  supplier product code match, or an exact hit against a previously confirmed alias for that exact
  wording — before attempting any similarity-based matching.
- **FR-003**: When no deterministic key resolves a line, System MUST propose candidates using
  wording similarity and, where useful, semantic similarity against the catalogue.
- **FR-004**: System MUST combine wording/semantic similarity with product-attribute plausibility
  (brand, variant, pack size, unit, and whether the price is plausible for that product) into a
  single calibrated confidence score per candidate.
- **FR-005**: Every proposed candidate MUST carry both its confidence score and a human-readable
  reason for why it was proposed (for example: alias hit, code match, wording similarity, price
  plausibility) — a confidence number with no reason is not sufficient.
- **FR-006**: System MUST automatically accept a match when its confidence meets or exceeds the
  configured auto-accept threshold, requiring no human action.
- **FR-007**: System MUST route a line to a human match-resolution queue whenever no candidate
  meets the auto-accept threshold, or whenever multiple candidates score closely enough that
  choosing automatically would be a guess.
- **FR-008**: Reviewers MUST be able to resolve a queued line with one of: confirm the top
  candidate, choose a different candidate, mark it a different pack size of the same product, mark
  it a different variant, mark it a compatible alternative, or mark it as no match.
- **FR-009**: When a reviewer marks a line as no match, System MUST let them create a new catalogue
  product directly from that decision, reusing the existing product-creation capability rather than
  requiring a separate trip to the catalogue.
- **FR-010**: Every human match decision MUST create or reuse a product alias tied to the exact
  supplier wording on that line, so that an identical wording resolves automatically via FR-002 the
  next time it appears, without going through similarity scoring again.
- **FR-011**: System MUST expose match-resolution work as its own queue, independent of any single
  quotation's page, filterable and workable across the workspace's outstanding matches.
- **FR-012**: Reviewers MUST be able to select a candidate and confirm a resolution using the
  keyboard alone.
- **FR-013**: For every matched line, System MUST compute its landed cost — unit price times
  quantity, plus tax, plus delivery fee, minus discount — as an amount with an explicit currency,
  never a bare number.
- **FR-014**: Every landed-cost computation MUST store the raw inputs it was computed from together
  with the identifier of the rule version applied.
- **FR-015**: A landed-cost computation MUST be exactly reproducible: recomputing it from its
  stored raw inputs and rule version MUST yield an identical result, verified by automated tests.
- **FR-016**: System MUST record price and cost data bitemporally — the point in time the price or
  cost applies, and the point in time the workspace learned it — as two separate, both-required
  facts.
- **FR-017**: Match and cost outcome history MUST be append-only; a later computation or decision
  MUST NOT destructively overwrite an earlier one.
- **FR-018**: System MUST normalise a matched line's quantity to the same base-unit convention the
  catalogue's pack definitions already use, so quantities are comparable across suppliers
  regardless of how each supplier packages the product.
- **FR-019**: Only workspace members with mutation permission (owner or buyer) MUST be able to
  resolve matches or trigger new-product creation from a match decision; other roles may view
  matches and costs but not change them.
- **FR-020**: A cross-tenant match, alias, or cost record MUST be indistinguishable from one that
  does not exist — never revealed as "forbidden."

### Key Entities

- **MatchCandidate**: One proposed product for one quotation line — the candidate product, its
  confidence score, and the reason it was proposed. Several may exist per line; none are the
  chosen match until one is accepted or confirmed.
- **MatchDecision**: The outcome for one quotation line — which product it resolved to (if any),
  the outcome type (same product, different pack, different variant, compatible alternative, or no
  match), whether it was automatic or human-made, and who made it if a human did.
- **LandedCost**: The priced, normalised result for one matched line — the computed amount and
  currency, the rule version used, the raw inputs it was computed from, and its bitemporal
  valid-time and record-time.
- **ProductAlias** *(existing, extended)*: A confirmed match decision's wording, reused as-is from
  the catalogue chunk — this chunk is a new writer of that same table, not a new entity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A quotation whose lines all resolve with high confidence requires zero manual
  matching effort from the workspace.
- **SC-002**: At least 92% of automatically accepted matches are correct, measured on a held-out
  labelled benchmark.
- **SC-003**: No more than 8% of quotation lines require human match resolution.
- **SC-004**: A reviewer can resolve an ambiguous match using only a few keystrokes, without ever
  needing the mouse.
- **SC-005**: Once a specific supplier wording has been resolved by a human, it never needs review
  again — it always resolves the same way automatically from then on.
- **SC-006**: For any matched line, the landed cost can be explained: which inputs, which rule
  version, and recomputing it gives back the identical figure.
- **SC-007**: Workspace members can see a true landed cost, not just a unit price, for every
  matched line.

## Assumptions

- Matching runs automatically once a quotation reaches its reviewed state (chunk 4.3); it is not a
  separate action a workspace member has to trigger by hand.
- A quotation line's tax amount is derived from its tax rate and its price times quantity; lines
  do not carry a separately extracted tax amount, so this chunk computes one rather than expecting
  it pre-extracted.
- "Other charges" beyond unit price, tax, delivery fee, and discount are not modelled in this
  chunk's landed-cost calculation; if a future need for them arises, the calculation is extended
  rather than reworked, since inputs and rule version are already stored separately by design.
- The auto-accept confidence threshold, like the extraction confidence threshold in chunk 4.3, is a
  configurable value tuned from real data over time, not a fixed number decided in this
  specification.
- No currency conversion happens anywhere in this chunk; a landed cost is always expressed in the
  quotation line's own currency.
- The precision and review-band success criteria (SC-002, SC-003) cannot be verified until a real
  held-out labelled benchmark of product matches exists — this chunk builds the pipeline and the
  measurement machinery honestly labelled as unvalidated until that benchmark exists, the same
  honest-gap situation chunk 4.3 documented for extraction accuracy.

## Out of Scope

- Offer comparison, recommendations, quantity-threshold recalculation, and basket building (a later
  chunk).
- Historical price aggregation — last-paid, average-paid, and similar cross-quotation views (a
  later chunk; this chunk computes one line's cost, not a product's price history).
- Savings verification and the savings ledger (a later chunk).
- Correcting or retiring a previously confirmed alias once it exists.
- Currency conversion of any kind.
