# Feature Specification: Replies to an RFQ Match Against the RFQ's Own Lines

**Feature Branch**: `023-rfq-aware-matching`
**Created**: 2026-10-28
**Status**: Draft. Owner decision 2026-10-28: an RFQ match that fits exactly one RFQ line is accepted automatically (Q1).
**Tracking**: Jira PPS-95 (plan ID P-65), from the round-1 UX audit PPS-89: findings R1-H1, R1-M5, R1-M9
and R1-L2 in `docs/quality/ux-audits/2026-10-28-round-1/README.md`
**Input**: When a quotation is a supplier's reply to an RFQ, match its lines against the lines that RFQ
asked for (product, pack, quantity, position) before searching the whole catalogue. Explain the match
as "your RFQ line …", not as a raw score. Learn a confirmed wording once, for every open line that uses
it. Keep the pack the supplier printed, so pack is a real signal.

## Why now

In round 1 (2026-10-28) two suppliers replied to the same RFQ. That RFQ named the exact four products,
their packs and their quantities. Even so, 4 of the 8 quoted lines went to manual matching. The right
product was ranked first but scored 28 % and 34 %, shown in red.

- Matching never reads the RFQ a quote answers. It searches the whole catalogue as if the quote had
  arrived unprompted.
- The score breakdown shows brand, variant, pack, pack size and price at a flat 50 %, plus
  "Semantic: Not available". These are signals the system never measured, presented as evidence.
- Extraction left the pack column (العبوة) empty although the PDF had one, so pack could not help.
- The buyer confirmed «دقيق» for the first supplier. The identical «دقيق» line from the second supplier
  stayed in the queue a minute later.

This is the largest shortcut left in round 1. The RFQ already holds the answer to most of these matching
questions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lines of an RFQ reply arrive matched to the RFQ's products (Priority: P1)

A buyer sends an RFQ for four products to two suppliers. Each supplier replies with a quote. The buyer
reviews and authorizes each quote. Every quoted line that clearly answers one of the RFQ's lines is
matched to that RFQ line's product automatically, and labelled "Your RFQ line 2 · دقيق فاخر (كيس 10 كجم) × 8".
No confirmation is needed (owner decision Q1). Lines that don't clearly answer an RFQ line go through
normal matching, so a human sees every case where the reply and the RFQ disagree.

**Why this priority**: it removes most of the manual matching in an RFQ round, which round 1 measured as
the slowest step. It also makes the Responses comparison usable without a detour to Match Resolution.

**Independent Test**: create an RFQ for four products and send it to two suppliers. Record one reply per
supplier whose line text differs from the catalogue names but which quotes the same products in the same
order and packs. Authorize both quotes. All eight lines are matched to the RFQ's products with the RFQ
explanation, and none reaches the Match Resolution queue.

**Acceptance Scenarios**:

1. **Given** an RFQ with lines A, B, C, D and a reply quoting four lines, **When** the reply is
   authorized, **Then** each quoted line that answers exactly one RFQ line is matched to that line's
   product automatically, with the reason "matched from your RFQ".
2. **Given** a quoted line whose text could answer two of the RFQ's lines (for example «زيت» when the RFQ
   asked for two oils), **When** matching runs, **Then** the line is not matched from the RFQ. It goes
   to Match Resolution with both RFQ lines offered first, each labelled with its RFQ line number.
3. **Given** a reply that adds a product the RFQ didn't ask for, **When** matching runs, **Then** that
   line goes through normal catalogue matching and is labelled "Not in your RFQ".
4. **Given** a reply quoting a different pack from the RFQ line (a 5 kg bag where the RFQ asked for
   10 kg), **When** matching runs, **Then** the line is not matched from the RFQ automatically. It is
   offered with the warning "Pack differs from your RFQ (10 kg asked, 5 kg quoted)".
5. **Given** a quotation that answers no RFQ (uploaded by hand or emailed unprompted), **When** matching
   runs, **Then** behaviour is unchanged from today.
6. **Given** a reply's lines are matched from the RFQ, **When** the buyer opens the RFQ's Responses, **Then** those
   lines appear under the RFQ's product names in the RFQ's order, with no "Match N lines" prompt.
7. **Given** a line matched from the RFQ, **When** the buyer opens the quote's matches, **Then** it is
   listed among the automatic matches with its RFQ line, and the buyer can correct it.
8. **Given** a line matched from the RFQ that is not yet on a purchase request, **When** the buyer
   corrects it to another product, **Then** the correction replaces the match, both are kept in the
   audit trail, and the line's landed cost and the RFQ comparison update.

---

### User Story 2 - The match explanation shows what was measured (Priority: P2)

A buyer opens a line in Match Resolution. The explanation says why the candidate is offered, using only
signals the system actually measured: "Your RFQ line 2", "Same wording as confirmed before", "Name 82 %
similar", "Pack matches (10 kg)". A signal that wasn't measured is not shown as a number. The confidence
colour reflects the evidence: a candidate backed by the RFQ isn't drawn in alarm red.

**Why this priority**: the buyer must be able to trust or overrule the proposal quickly. Today's
placeholder breakdown teaches the buyer to ignore the explanation altogether.

**Independent Test**: open a line proposed from the RFQ and a line proposed by name similarity only.
The first shows the RFQ line reference and no 50 % placeholders. The second shows its similarity and
leaves the unmeasured signals out.

**Acceptance Scenarios**:

1. **Given** a candidate offered from the RFQ, **When** the buyer views it, **Then** the explanation
   leads with "Your RFQ line N · product · pack × quantity".
2. **Given** a signal the system did not measure for this line (for example brand or price), **When**
   the breakdown is shown, **Then** that signal is omitted or marked "not checked", never shown as 50 %.
3. **Given** a candidate whose only evidence is name similarity below the review threshold, **When** it
   is shown, **Then** it keeps today's low-confidence styling.

---

### User Story 3 - One confirmation of a wording clears every open line that uses it (Priority: P2)

The buyer confirms that «دقيق» from supplier A is "دقيق فاخر (كيس 10 كجم)". Supplier B's open line with
the same wording is matched at that moment and leaves the queue, the same way a new line with that
wording would be.

**Why this priority**: within one RFQ round, two suppliers often use the same wording. Confirming it
twice is busywork.

**Independent Test**: authorize two quotes that each contain an unmatched line with the same text.
Confirm one. The other leaves the queue without being opened, and its decision is recorded as learned
from the first.

**Acceptance Scenarios**:

1. **Given** two open lines with the same wording (after normalising spaces, letter case and Unicode
   forms), **When** the buyer confirms one and the wording is learned, **Then** the other is matched to
   the same product and leaves the queue.
2. **Given** an open line whose wording only resembles the learned one (for example «دقيق فاخر» against
   «دقيق»), **When** the wording is learned, **Then** that line is not matched by the learning. It
   stays in the queue.
3. **Given** the buyer learned a wording by mistake, **When** they correct the original match,
   **Then** the lines matched through that wording are listed so they can be re-checked.

---

### User Story 4 - The pack the supplier printed is kept (Priority: P3)

A supplier's PDF has a pack column, for example «كيس 10 كجم» or "Carton 12 × 1 L". Extraction captures
it into the line's pack details, so matching and the RFQ comparison can use it.

**Why this priority**: pack is the strongest cheap signal for telling products apart, and it decides
whether an RFQ match can be accepted (Story 1, scenario 4). Story 1 still works without it, but more
lines would need a human.

**Independent Test**: extract the two round-1 PDFs (الذهبي `DH-26-1252`, الوفرة `WF/2026/0781`; they are
not in the repo yet, and planning adds them as extraction fixtures). Every line's pack details hold the
pack printed in the العبوة column.

**Acceptance Scenarios**:

1. **Given** a quote with a pack column in Arabic or English, **When** it is extracted, **Then** each
   line's pack count, unit size and unit are filled in and shown in Quotation Review.
2. **Given** a pack the extractor can't read with confidence, **When** it is extracted, **Then** the pack
   field is flagged for review, not left silently empty.

### Edge Cases

- **Same product on two RFQ lines.** An RFQ may not repeat a product (PPS-91 enforces this from now on).
  Older RFQs may still contain a repeated product. A line that answers either one is not matched from
  the RFQ.
- **Quote lines in a different order from the RFQ.** Position is supporting evidence only. Product and
  pack decide the match, so a reordered reply still matches.
- **Quantity differs from the RFQ.** The supplier quotes 6 where the RFQ asked for 8. The line still
  matches the product, and the quantity difference is shown on the Responses comparison. Quantity never
  blocks a product match.
- **Supplier substitutes a brand or grade.** The text names a different brand from the RFQ's product.
  It is not matched from the RFQ, and the line goes through normal matching labelled "Possible
  substitute for RFQ line N".
- **RFQ edited after sending.** Matching uses the RFQ as the supplier received it. Sent RFQs can't be
  edited today, so this only needs a guard.
- **An RFQ product archived since sending.** It is not proposed. The line goes through normal matching.
- **Correction after a request was prepared.** The line is on a purchase request, so the match is
  locked (FR-005). The buyer withdraws the request first.
- **Quote re-authorized after correcting its extraction.** RFQ matching re-runs only for lines that have
  no decision yet. Decisions already confirmed stay as they are.
- **Guardrail-driven auto-preparation (ADR-019).** RFQ matches create match decisions like any other, so
  the guardrail evaluation is enqueued exactly as today. The settled-response-set rule is unchanged.
- **Tenant isolation.** RFQ lines are read only within the quotation's own tenant.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When matching a quotation linked to an RFQ response, the system MUST first compare each
  quoted line with that RFQ's lines, before any catalogue-wide search.
- **FR-002**: A quoted line MUST count as answering an RFQ line only when exactly one RFQ line fits it.
  A fit means the line's wording plausibly names that line's product and the quoted pack is the same as
  the RFQ line's pack. When the pack is missing, wording alone decides (FR-006). If zero or several RFQ
  lines fit, the line falls back to normal matching, with any fitting RFQ lines offered first.
- **FR-003**: A line that answers an RFQ line MUST be matched to that line's product automatically,
  with no human confirmation (owner decision Q1). The match is recorded as automatic, with "matched from
  your RFQ" and the RFQ line number as its reason. It MUST be listed with the quote's automatic
  matches.
- **FR-004**: A line matched from the RFQ MUST NOT teach the system its wording. Only a human
  confirmation or correction teaches a wording (FR-011), so one supplier's wording learned through an
  RFQ can't match other suppliers' lines outside an RFQ.
- **FR-005**: An authorised buyer MUST be able to correct a match decision, automatic or human, on a
  line that is not yet on a purchase request. The correction supersedes the earlier decision, and both
  stay in the audit trail. Everything derived from the match (landed cost, the RFQ comparison, the
  guardrail evaluation under ADR-019) MUST follow the corrected decision. A line already on a purchase
  request can't be corrected. The buyer is told which request holds it.
  Today a line has exactly one decision and a second one is refused, so this is new capability that
  automatic RFQ acceptance makes necessary.
- **FR-006**: A quoted line without pack details MAY answer an RFQ line on wording alone only when its
  wording is closer to that RFQ line's product than to any other product in the RFQ by a clear margin.
  The margin is set in planning against the round-1 data.
- **FR-007**: A quoted line whose pack differs from the fitting RFQ line MUST NOT be matched from the
  RFQ. It MUST show the RFQ's pack next to the quoted pack.
- **FR-008**: Every decision made through the RFQ MUST be audited with the RFQ, the RFQ line and the
  quotation line, and MUST be distinguishable in reports from catalogue-search decisions.
- **FR-009**: The match explanation MUST show only signals that were measured for that line. An
  unmeasured signal MUST NOT be shown as a percentage.
- **FR-010**: A candidate proposed from the RFQ MUST lead its explanation with the RFQ line reference
  (number, product, pack and quantity). It MUST NOT be styled as low confidence on account of a
  similarity score.
- **FR-011**: When a confirmed match teaches the system a wording, every other open line in the tenant
  with the same normalised wording MUST be matched to that product and removed from the queue. Each is
  recorded as learned from the confirming decision. Lines that only resemble the wording are not
  affected.
- **FR-012**: Correcting a decision that taught a wording MUST list the lines matched through that
  wording since, so the buyer can review them.
- **FR-013**: Extraction MUST capture a printed pack (count, unit size, unit) for each line when the
  document has one. It MUST flag the pack for review when the pack is present but unreadable.
- **FR-014**: Quotations that answer no RFQ MUST match exactly as they do today (FR-009 to FR-013 still
  apply to them).
- **FR-015**: All new user-facing copy MUST exist in English and Arabic.

### Key Entities

- **RFQ line**: what the buyer asked for: a catalogue product (which carries its purchasing pack), a
  quantity and a position. It is read-only for this feature.
- **RFQ response**: links a supplier's quotation to the RFQ recipient it answers. This link already
  exists and is how a quotation knows its RFQ.
- **Match proposal / decision**: as today, plus the evidence that it came from the RFQ (the RFQ line
  answered) or from a learned wording (the decision that taught it).
- **Learned wording (alias)**: as today. It now also resolves lines that were already open when it was
  learned.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a replay of round 1 (same RFQ, same two PDFs), every one of the 8 lines is matched to
  the right product, and no line needs a catalogue search.
- **SC-002**: A 4-line RFQ reply whose lines all fit the RFQ needs no matching action from the buyer.
  Round 1 took 4 resolutions plus navigation.
- **SC-003**: No quoted line is matched from the RFQ to a product the supplier didn't quote. The
  substitute, pack-differs and ambiguous-wording test cases all go to a human.
- **SC-004**: No match explanation shows a percentage for a signal that was not measured.
- **SC-005**: When two suppliers send the same wording, the buyer confirms it once.
- **SC-006**: Matching for quotes that answer no RFQ is unchanged. The existing matching evaluation
  (`ml/evals/product_matching`) gives the same precision and recall before and after.

## Assumptions

- Matching still runs after a human authorizes the quotation (ADR-019: human data review stays in the
  loop). This feature changes what matching proposes, not when it runs.
- Match-score calibration is still not feasible: hosted has too few human decisions (CLAUDE.md, spec
  004 R5/R10). The RFQ fit is therefore a rule (exactly one fitting line, same pack), not a tuned
  probability. The owner accepted it as deterministic evidence on 2026-10-28 (Q1). It sits alongside
  barcode, supplier code and learned wording, the only automatic acceptances spec 004 allowed so far.
  Similarity-only matches are still never accepted automatically.
- "Same wording" means equal after Unicode NFKC normalisation, case folding and whitespace collapse.
  This is the rule the exact-name bulk confirm already uses.
- Quantity is in the purchasing pack on both sides (ADR-020), so packs compare directly.

## Out of scope

- Basket split from an RFQ and turning a split into requests: spec 024 (PPS-96).
- Changing when matching runs, or matching before human review of the extraction.
- Brand, variant and price-plausibility signals. They are hidden while unmeasured, not built here.
- Recording savings from the RFQ round (R1-M12).
