# Feature Specification: Catalogue and Suppliers

**Feature Branch**: `002-catalogue-suppliers`
**Created**: 2026-08-20
**Status**: Draft
**Input**: User description: "Chunk 4.2 Catalogue + Suppliers (R1.1): product master, supplier profiles, units and pack definitions, CSV import with validation, and product aliases."

## Overview

A business can describe what it buys and who it buys from. Products, the pack sizes they arrive in,
suppliers and their commercial terms — entered by hand or imported in bulk from a spreadsheet.

This is the chunk where ProcurePilot stops being an empty shell and starts holding the customer's
own commercial data. Nothing here compares prices or recommends anything: it builds the vocabulary
that the comparison in chunks 4.4 and 4.5 will be expressed in. A supplier quoting "6 × 5L" and
another quoting "12 × 750ml" cannot be compared until both resolve to the same product measured in
the same base unit, and that resolution is what this chunk makes possible.

It is also the first chunk to store money, which the roadmap treats as a schema decision rather
than a display one.

## Clarifications

### Session 2026-08-20

- **Q: Which roles may create and edit catalogue and supplier records?**
  **A: Owner and buyer write; branch manager, approver and viewer read.** This matches the
  roadmap's persona split — the buyer is the power user whose job is getting the right goods at the
  right price, while the branch manager only requests and receives. Consequence: the catalogue and
  supplier screens need a read-only presentation as well as an editable one, and every mutating
  endpoint in this chunk is guarded to owner and buyer. Letting branch managers write was rejected
  because several people naming the same product differently is precisely the drift that
  normalisation later has to undo.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A buyer builds the product master (Priority: P1)

A buyer records the things their business buys regularly: a name they recognise, the pack it comes
in, and the base unit it should be measured in. They can correct a product later, and retire one
they no longer buy without erasing the history that mentions it.

**Why this priority**: everything downstream is expressed in terms of products. Suppliers quote
against them, extraction matches to them, comparison normalises them. Without the product master
there is nothing to attach a price to.

**Independent Test**: create a product with a pack definition, edit it, archive it, and confirm the
normalised base quantity is shown throughout — testable with no supplier and no import.

**Acceptance Scenarios**:

1. **Given** a signed-in buyer, **When** they create a product with a name, base unit and pack of 6 × 5 litres, **Then** the product is saved and its normalised quantity of 30 litres is displayed.
2. **Given** an existing product, **When** the buyer edits its pack definition, **Then** the normalised quantity updates and the change is recorded as an auditable event.
3. **Given** a product the business no longer buys, **When** the buyer archives it, **Then** it stops appearing in active lists but is not deleted and remains resolvable by anything that references it.
4. **Given** a product, **When** the buyer records a GTIN, **Then** the value is validated for shape and stored; an invalid GTIN is refused with a reason.
5. **Given** two products in the catalogue, **When** the buyer marks one an approved substitute for the other, **Then** the relationship is stored and visible from both.

---

### User Story 2 - A buyer records who they buy from (Priority: P1)

A buyer records each supplier and the terms that determine what an order actually costs: payment
terms, lead time, minimum order value, delivery fee. They mark suppliers preferred or blocked.

**Why this priority**: landed cost is the product's core arithmetic, and it is made of exactly these
terms. A price without the delivery fee and minimum order value attached is not a cost. It is P1
alongside the product master because a catalogue with no suppliers cannot produce a comparison.

**Independent Test**: create a supplier with full commercial terms, change its status, and confirm
the monetary terms are stored with an explicit currency — testable with no products present.

**Acceptance Scenarios**:

1. **Given** a signed-in buyer, **When** they create a supplier with payment terms, lead time, minimum order value and delivery fee, **Then** the supplier is saved and every monetary value carries an explicit currency.
2. **Given** a supplier, **When** the buyer sets its status to blocked, **Then** it is excluded from future purchasing suggestions but its history is retained.
3. **Given** a supplier, **When** the buyer marks it preferred, **Then** that preference is visible wherever the supplier appears.
4. **Given** a supplier with a minimum order value in one currency, **When** the workspace operates in a different currency, **Then** the amount is displayed with its own currency and never silently converted.
5. **Given** a supplier that is referenced by existing records, **When** the buyer attempts to delete it, **Then** the action is refused and archiving is offered instead.

---

### User Story 3 - A buyer imports a catalogue from a spreadsheet (Priority: P2)

Rather than typing hundreds of rows, a buyer uploads the spreadsheet they already keep. The system
checks the whole file before saving anything, and if rows are wrong it says which rows and why, so
the buyer can fix the file and try again.

**Why this priority**: it is the difference between a product a business can adopt in an afternoon
and one that demands a week of data entry. It is P2 because the catalogue can be built by hand
first — but adoption realistically depends on it.

**Independent Test**: upload a file with a mix of valid and invalid rows, confirm nothing is saved,
confirm the error report names each bad row and its problem, then upload a corrected file and
confirm every row is saved.

**Acceptance Scenarios**:

1. **Given** a well-formed file, **When** the buyer uploads it, **Then** they see what will be created before anything is saved, and can confirm or cancel.
2. **Given** a file where some rows are invalid, **When** the buyer uploads it, **Then** **nothing is saved** and the report lists each failing row by its number in the file with a specific reason.
3. **Given** a file whose columns do not match what is expected, **When** the buyer uploads it, **Then** they are told which columns are missing or unrecognised rather than seeing a generic failure.
4. **Given** a file containing a product that already exists, **When** the buyer imports it, **Then** they are told it is a duplicate and can choose to skip or update it, rather than silently creating a second copy.
5. **Given** a file containing amounts written in a different decimal convention, **When** it is imported, **Then** the amounts are interpreted correctly or the row is refused — never misread by a factor of a thousand.
6. **Given** a large file, **When** the buyer uploads it, **Then** they receive progress feedback and the result, rather than an unexplained wait.

---

### User Story 4 - The system learns what suppliers call things (Priority: P3)

A supplier's description of a product rarely matches the buyer's name for it. When someone confirms
that a supplier's wording refers to a particular product, the system remembers that for the
workspace, so the same wording resolves automatically next time.

**Why this priority**: it is the seed of the matching engine that chunk 4.4 depends on. It is P3
here because nothing yet generates supplier descriptions automatically — the value accrues once
document extraction arrives. Building the store now means chunk 4.4 starts with a working memory
rather than an empty one.

**Independent Test**: record an alias for a product, then confirm the same supplier wording resolves
to that product for that workspace and not for any other.

**Acceptance Scenarios**:

1. **Given** a supplier's description of a product, **When** a buyer confirms which product it refers to, **Then** the association is stored for that workspace.
2. **Given** a stored alias, **When** the same description is seen again, **Then** the product is resolved without asking again.
3. **Given** an alias recorded by one business, **When** another business encounters the same wording, **Then** the first business's alias is not used — aliases are private to the workspace that taught them.
4. **Given** an alias that was recorded in error, **When** a buyer removes it, **Then** the wording stops resolving to that product.

---

### Edge Cases

- **A pack definition of zero or negative size** — refused; a pack that contains nothing cannot be normalised, and a negative quantity would corrupt every comparison built on it.
- **A pack whose normalised quantity is fractional** (3 × 0.33 litres) — stored at full precision; rounding here compounds into a wrong saving later.
- **Archiving a product that is an approved substitute for another** — permitted, but the substitute relationship stops being offered while the product is archived.
- **A GTIN that is valid in shape but belongs to a different product** — the system cannot detect this; it is a data-quality matter for the buyer, and the field is advisory rather than a key.
- **Two products in the same workspace with the same name** — permitted with a warning; businesses legitimately buy "gloves" from several suppliers in different specifications.
- **An import file that is empty, or contains only a header row** — reported as such rather than as a successful import of nothing.
- **An import file that is not the expected format at all** (a PDF renamed, a binary) — refused with a clear message before any parsing is attempted.
- **An import that fails partway through saving** — nothing is left half-created; the catalogue is either as it was or as the file described, never in between.
- **A monetary amount with no currency** — refused. There is no default currency for a supplier's terms, and inferring one would produce a plausible, wrong number.
- **A supplier's minimum order value in a currency the workspace does not use** — stored and displayed as given; conversion requires a rate nobody has supplied.

## Requirements *(mandatory)*

### Functional Requirements

**Product master**

- **FR-001**: Users MUST be able to create a product with a name, a base unit, and an optional GTIN, brand and variant.
- **FR-002**: Users MUST be able to define a pack for a product as a count and a unit size, and the system MUST derive and store the normalised base quantity.
- **FR-003**: System MUST refuse a pack count or unit size that is zero, negative, or non-numeric.
- **FR-004**: System MUST preserve the full precision of derived quantities and MUST NOT round them for storage.
- **FR-005**: Users MUST be able to edit a product and its pack definition.
- **FR-006**: Users MUST be able to archive a product, and the system MUST NOT delete it. Archived products MUST remain resolvable by records that reference them.
- **FR-007**: Users MUST be able to record approved substitutes between products in the same workspace.
- **FR-008**: System MUST validate the shape of a GTIN when one is supplied and refuse an invalid one with a stated reason.
- **FR-009**: System MUST maintain a shared canonical product layer distinct from each workspace's own naming, so that a workspace's names and preferences never leak to another workspace.

**Suppliers**

- **FR-010**: Users MUST be able to create a supplier with a name, payment terms, lead time in days, minimum order value, and delivery fee.
- **FR-011**: System MUST store every monetary value with an explicit currency and MUST refuse an amount presented without one.
- **FR-012**: System MUST NOT convert between currencies. Amounts MUST be displayed in the currency they were entered in.
- **FR-013**: Users MUST be able to set a supplier's status to active, preferred, or blocked.
- **FR-014**: System MUST refuse deletion of a supplier that is referenced by other records, and MUST offer archiving instead.
- **FR-015**: Users MUST be able to nominate a preferred supplier for a product.

**CSV import**

- **FR-016**: Users MUST be able to upload a delimited file to create products or suppliers in bulk.
- **FR-017**: System MUST validate the entire file before saving anything, and MUST save either all valid rows or none — never a partial import.
- **FR-018**: System MUST report each failing row by its line number in the uploaded file, with a specific reason for that row.
- **FR-019**: System MUST report missing or unrecognised columns distinctly from row-level errors.
- **FR-020**: System MUST show the user what will be created and require confirmation before saving.
- **FR-021**: System MUST detect rows that duplicate existing records and MUST let the user choose to skip or update rather than silently creating duplicates.
- **FR-022**: System MUST interpret decimal separators unambiguously and MUST refuse a row whose numeric value cannot be read with certainty.
- **FR-023**: System MUST refuse a file that is not of an accepted type before attempting to parse it.
- **FR-024**: System MUST report an empty file, or one containing only headers, as such.

**Aliases**

- **FR-025**: Users MUST be able to record that a supplier's description refers to a particular product in their workspace.
- **FR-026**: System MUST resolve a previously recorded description to its product without asking again.
- **FR-027**: System MUST keep aliases private to the workspace that recorded them.
- **FR-028**: Users MUST be able to remove an alias.

**Cross-cutting**

- **FR-029**: Every record created in this chunk MUST belong to exactly one workspace and MUST be protected by the same database-enforced isolation as existing data.
- **FR-030**: Every creation, edit, archive and import MUST be recorded as an auditable event.
- **FR-031**: All user-facing text introduced by this chunk MUST come from the shared English and Arabic catalogue and MUST render correctly right-to-left.
- **FR-032**: System MUST permit only owners and buyers to create, edit or archive catalogue and supplier records, and MUST enforce this server-side.
- **FR-033**: System MUST allow branch managers, approvers and viewers to read catalogue and supplier records.
- **FR-034**: System MUST NOT present a mutating action to a role that may not perform it — as a display courtesy in addition to server enforcement, never instead of it.

### Key Entities

- **Canonical Product**: the shared, workspace-independent identity of a product — brand, name, variant, GTIN, base unit. Exists so that cross-workspace benchmarking remains possible later without leaking workspace data now.
- **Workspace Product**: a workspace's own view of a canonical product — the name they use, their preferred supplier, their approved substitutes. This is what a buyer sees and edits.
- **Pack Definition**: how a workspace product arrives — a count, a unit size, and the derived base quantity that makes offers comparable.
- **Supplier**: a business the workspace buys from, with the commercial terms that determine landed cost: payment terms, lead time, minimum order value, delivery fee, status, and a reliability score computed later from recorded outcomes.
- **Product Alias**: a supplier's wording mapped to a workspace product, private to the workspace that recorded it.
- **Import Job**: one upload — its file, its validation outcome, the rows it created, and the errors it reported. Retained so an import can be explained after the fact.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A buyer can create a product with a pack definition and see its normalised quantity in under 90 seconds without assistance.
- **SC-002**: A buyer can import a 200-row catalogue file and receive either a complete import or a full error report in under 60 seconds.
- **SC-003**: 100% of rows rejected during an import are reported with their line number and a specific reason.
- **SC-004**: 0% of imports leave the catalogue partially updated, verified by automated test.
- **SC-005**: In 100% of automated cross-workspace attempts, no product, supplier or alias belonging to another workspace is returned or revealed.
- **SC-006**: 100% of stored monetary values carry an explicit currency, verified by automated check against the schema.
- **SC-007**: Normalised quantities are reproducible: recomputing from the stored pack definition yields an identical value in 100% of cases.
- **SC-008**: All catalogue and supplier screens pass an automated WCAG 2.1 AA check with zero violations, in both languages.
- **SC-009**: 100% of mutating catalogue and supplier actions are refused for branch manager, approver and viewer, verified by automated test for every role.

## Assumptions

- **Import format**: comma-delimited text with a header row, as exported by common spreadsheet tools. Native spreadsheet binaries are out of scope for this chunk.
- **Base units** are drawn from a fixed, data-held set (litre, millilitre, kilogram, gram, each) rather than free text, because normalisation across arbitrary unit names is not decidable.
- **Reliability score** is a column populated from recorded outcomes in a later chunk; nothing computes it here.
- **The canonical product layer is populated by the workspace's own entries** in this chunk. No external product database is consulted.
- **Aliases are recorded by hand** in this chunk. Nothing generates them automatically until document extraction arrives in chunk 4.3.
- **No prices are stored against products.** Supplier terms are stored; per-product pricing arrives with offers in chunk 4.4.
- **Archiving, not deletion**, is the pattern throughout, consistent with the audit obligations already established.
- **Money follows the existing shared type** — amount plus explicit currency, amount held as a decimal rather than a float.

## Dependencies

- The tenancy, identity and role model delivered in chunk 4.1, including database-enforced workspace isolation and the audit event trail.
- The shared money type and the reference tables of supported currencies established in chunk 4.1.
- The English and Arabic catalogue and right-to-left support delivered in chunk 4.1.
- `docs/architecture/data-dictionary.md` for field-level definitions of the entities above.

## Out of Scope

- Prices, offers, quotations and any comparison between suppliers (chunks 4.3–4.5)
- Document upload, extraction, or the review queue (chunk 4.3)
- Automatic product matching and confidence scoring (chunk 4.4)
- The landed-cost engine (chunk 4.4)
- Purchase requests, approvals and budgets (Phase 2)
- Any external product or GTIN database lookup
- Currency conversion of any kind
