# Feature Specification: Quotation Inbox and Extraction Review

**Feature Branch**: `003-quotation-inbox-extraction`
**Created**: 2026-08-21
**Status**: Draft
**Input**: User description: "Chunk 4.3: Quotation Inbox + Extraction Review — a workspace uploads supplier quotation documents (PDF, and likely image/email-derived text); an AI extraction step reads them into structured line items (product references, quantities, pack sizes, unit prices, currency); a human reviewer confirms or corrects each extracted line, with a confidence score and provenance back to the source document, before anything becomes trusted commercial data feeding the catalogue's suppliers/products and the eventual Smart Compare engine. First chunk to introduce Redis for the extraction worker's job queue."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload a quotation and see it extracted (Priority: P1)

A buyer receives a supplier quotation as a PDF, a scanned image, or a spreadsheet. Instead of
retyping every line into the catalogue by hand, they upload the document to their workspace and,
within a short wait, see it turned into a structured header (supplier, currency, dates, terms) and
a set of line items (description, quantity, pack, unit price), each carrying a visible confidence
indicator.

**Why this priority**: This is the entire reason the chunk exists — without reliable upload and
extraction, there is nothing to review and nothing to feed downstream. It is the MVP slice: a
workspace that can upload and see extraction happen, even before any correction workflow ships,
already proves the ingestion pipeline works.

**Independent Test**: Upload a single-supplier PDF quotation with a known set of line items and
confirm the system produces a document record, a quotation record, and extracted header/line
fields with confidence scores, without the user typing any of the line data themselves.

**Acceptance Scenarios**:

1. **Given** a workspace member with upload permission, **When** they upload a PDF quotation,
   **Then** the file is stored directly (not routed through hand-typed data entry) and a quotation
   record appears in a "processing" state.
2. **Given** an uploaded quotation, **When** extraction completes, **Then** the workspace sees a
   structured header and line list with a confidence value on every extracted field.
3. **Given** a spreadsheet (Excel/CSV) quotation, **When** it is uploaded, **Then** its already-
   structured values are read directly rather than run through image/text extraction, and every
   field is reported at full confidence.
4. **Given** an uploaded file that is not one of the accepted formats, **When** the upload is
   attempted, **Then** it is refused immediately with a clear reason, before any extraction is
   attempted.

---

### User Story 2 - Review, correct, and confirm a quotation (Priority: P1)

A reviewer opens a quotation that has finished extraction. They see the original document and the
extracted fields side by side. Low-confidence or wrong fields are visibly flagged; the reviewer
corrects them, confirms the supplier the quotation belongs to, and confirms the quotation as
reviewed. Only after this confirmation does the quotation's data count as trustworthy enough to
feed anything downstream.

**Why this priority**: Constitution Principle III makes this non-negotiable: automation may
extract, but a human authorises. Extraction without a review-and-confirm step would produce data
nobody has actually vouched for — not a smaller version of this feature, but a different, disallowed
one. This ships in the same increment as User Story 1, not after it.

**Independent Test**: Take a quotation already extracted (from User Story 1's test), open it in the
review screen, deliberately correct at least one field, confirm the quotation, and verify its status
changes to reviewed/accepted and the correction is recorded against that field with who made it and
when.

**Acceptance Scenarios**:

1. **Given** an extracted quotation open for review, **When** the reviewer views it, **Then** the
   source document and the extracted fields are shown side by side, and clicking a field highlights
   its source region in the document.
2. **Given** a field flagged as low-confidence, **When** the reviewer corrects it, **Then** the
   correction replaces the extracted value and is recorded as a human decision distinct from the
   original AI value.
3. **Given** a quotation ready for review, **When** the reviewer works through it, **Then** they can
   move between fields needing attention using the keyboard alone.
4. **Given** a quotation the reviewer has corrected and is satisfied with, **When** they confirm it,
   **Then** its status becomes reviewed, and it is only from this point that the quotation is
   available as trusted data to any other part of the product.
5. **Given** a quotation nobody has reviewed yet, **When** anything else in the product looks for
   trusted supplier pricing, **Then** that quotation's data is not returned.

---

### User Story 3 - Arithmetic mismatches always force review (Priority: P1)

A quotation's extracted line totals do not add up to its stated document total — a transcription
error, a missed discount line, or a genuinely malformed document. Regardless of how confident the
extraction was on the individual fields, the system will not let this quotation be treated as ready
without a human looking at the mismatch.

**Why this priority**: This is the specific, testable form Constitution Principle I takes in this
chunk — evidence over assertion. A confident-looking extraction that doesn't reconcile arithmetically
is not evidence, it's a guess with a badge on it. This guardrail has to exist from the first release
of extraction, not be added once numbers have already gone wrong for someone.

**Independent Test**: Extract a quotation whose line items sum to a different amount than its stated
total and confirm the quotation is forced into review status regardless of individual field
confidence, with the mismatch itself visible to the reviewer.

**Acceptance Scenarios**:

1. **Given** a quotation whose line totals do not reconcile with its document total, **When**
   extraction finishes, **Then** the quotation is placed into mandatory review and cannot be
   confirmed until a reviewer has looked at the discrepancy.
2. **Given** an arithmetic mismatch on a quotation, **When** the reviewer views it, **Then** the
   mismatch itself (not just the individual fields) is shown as something to resolve.

---

### User Story 4 - See when a supplier re-quotes (Priority: P2)

A supplier that already has a quotation on file sends an updated one — new prices, a new expiry
date, corrected terms. The workspace can see the new quotation is a version of the earlier one,
with both remaining visible, rather than the update silently replacing history.

**Why this priority**: Useful and expected once quotations start accumulating, but the product
delivers real value the moment upload-extract-review works even if every quotation is initially
treated as standalone; version linking is a refinement on top of that loop, not a precondition for
it.

**Independent Test**: Upload a quotation for a supplier that already has one on file, and confirm
the new one is linked to the prior version and both remain visible and distinguishable.

**Acceptance Scenarios**:

1. **Given** a supplier with an existing quotation, **When** a new quotation document for the same
   supplier is uploaded and confirmed as a re-quote, **Then** the new quotation is linked to the
   prior one as a newer version.
2. **Given** a quotation with an earlier version, **When** a workspace member views it, **Then**
   they can see and open the prior version rather than it having disappeared.

---

### Edge Cases

- What happens when an uploaded file is corrupted, password-protected, or otherwise unreadable?
  The document is marked as failed to read, distinctly from "pending review," and no extraction
  attempt is charged against it.
- What happens when the primary extraction path is unavailable? A fallback extraction path is used
  so a single provider's outage does not stop the review queue from receiving new work; if both are
  unavailable, the document is queued rather than silently dropped.
- What happens when a reviewer starts correcting a quotation and never finishes? The quotation stays
  in its in-review state indefinitely — nothing times out into being treated as confirmed.
- What happens when the same document is uploaded twice? Both uploads are recorded; duplicate
  detection and merging is not required in this chunk, but nothing is silently overwritten.
- What happens when a quotation mixes more than one currency across its lines? Out of scope for this
  chunk — a quotation is assumed to be denominated in one currency; a document that genuinely mixes
  currencies is flagged as a validation failure requiring review rather than guessed at.
- What happens when extracted numbers use a locale-specific decimal or thousands separator (e.g.,
  `1.234,56` vs `1,234.56`)? The same unambiguous parsing rule already established for catalogue CSV
  import applies: recognised unambiguous formats are parsed correctly, and a genuinely ambiguous
  value is refused into review rather than guessed.
- What happens when a document contains quotations from more than one supplier at once (a combined
  statement)? Out of scope for this chunk — one document is assumed to hold one supplier's
  quotation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Workspace members with upload permission MUST be able to upload a supplier quotation
  document in PDF, image, Excel, or CSV format via a direct-to-storage upload that does not route
  file bytes through hand-entered data.
- **FR-002**: System MUST create a document record for every upload, capturing where it is stored,
  its file type, a content fingerprint, and how it arrived (uploaded directly in this chunk; other
  channels are reserved for later).
- **FR-003**: System MUST create a quotation record linked to its source document, and track that
  quotation through a lifecycle of states from newly uploaded, through extraction, to reviewed and
  confirmed (or refused, if it could never be read).
- **FR-004**: System MUST refuse a file that is not an accepted format immediately, before any
  extraction is attempted, with a clear reason given to the uploader.
- **FR-004a**: System MUST offer downloadable sample quotation files so users can test the
  extraction pipeline without needing a real supplier document.
- **FR-004b**: System MUST allow an authenticated user to download the original uploaded document
  from the quotation review page via a short-lived signed URL. The URL is generated server-side
  using a service-role Supabase Storage client; tenant isolation is enforced by RLS on the
  `document` table before the URL is issued.
- **FR-005**: System MUST extract, for every quotation, a header (at minimum: supplier, currency,
  issue date, and expiry date where present) and one or more line items (at minimum: the original
  wording as it appeared in the document, quantity, pack information, and unit price).
- **FR-006**: System MUST bypass AI-based extraction for inputs that are already structured data
  (Excel, CSV) and read their values directly, reserving AI extraction for documents that require
  reading unstructured text or images (PDF, scanned image).
- **FR-007**: System MUST provide a fallback extraction path for use when the primary path fails or
  is unavailable, so that a single extraction provider's outage does not block new quotations from
  entering the review queue.
- **FR-008**: Every extracted field MUST carry its own confidence score and a reference back to its
  location in the source document — never a single confidence value standing in for an entire
  quotation or an entire line.
- **FR-009**: System MUST record, for every extracted value, how it was produced (the extraction
  method and the specific model or path used), so a value's origin can always be reconstructed later.
- **FR-010**: System MUST validate that a quotation's line totals reconcile with its stated document
  total (where one is present), and force the quotation into mandatory review whenever they do not,
  regardless of the confidence reported on individual fields.
- **FR-011**: System MUST force a quotation into mandatory review whenever any of its fields falls
  below a configured confidence threshold, rather than accepting it silently.
- **FR-012**: System MUST provide a review interface that shows the source document and the
  extracted fields side by side, and highlights a field's source region in the document when it is
  selected.
- **FR-013**: Reviewers MUST be able to correct any extracted field, and a correction MUST be
  recorded as a distinct, attributable human decision rather than overwriting the original
  extracted value in place.
- **FR-014**: Reviewers MUST be able to move between fields needing attention using the keyboard
  alone, without requiring the mouse.
- **FR-015**: As part of reviewing a quotation, the reviewer MUST confirm which existing supplier it
  belongs to (using the workspace's existing supplier records); resolving which catalogue *product*
  each line refers to is out of scope for this chunk and belongs to the matching capability that
  follows it.
- **FR-016**: A quotation's data MUST NOT be usable as trusted commercial data by any other part of
  the product until a human has reviewed and confirmed it.
- **FR-017**: System MUST record who reviewed and confirmed (or corrected) a quotation and when, as
  part of its audit trail.
- **FR-018**: System MUST run extraction as an asynchronous job whose status can be checked, rather
  than requiring the uploader's request to stay open until extraction finishes.
- **FR-019**: System MUST expose outstanding review work as its own queue, independent of any single
  quotation's detail page, so a reviewer can work through everything awaiting attention across the
  workspace, filterable by its status.
- **FR-020**: When a new quotation is uploaded for a supplier that already has one on file and is
  confirmed as an update to it, System MUST link the two as versions of one another, and MUST keep
  the prior version visible rather than replacing it.
- **FR-021**: Every monetary value captured for a quotation (unit price, delivery fee, discount, and
  any other amount) MUST be stored as an amount together with an explicit currency, matching the
  convention already established for the rest of the product — never a bare number.
- **FR-022**: A document that cannot be read at all (corrupted, encrypted, unsupported despite
  passing the initial format check) MUST be marked as failed to read, distinctly from a quotation
  that is merely awaiting review.

### Key Entities

- **Document**: An uploaded file — where it is stored, its type, a content fingerprint, and how it
  arrived. Exists independently of whether it was ever successfully extracted.
- **Quotation**: One supplier's offer, tied to the document it came from, carrying header
  information (supplier, currency, dates, terms) and a lifecycle status. May have a prior version it
  supersedes.
- **QuotationLine**: One line item within a quotation — its original wording as extracted, and the
  structured fields resolved from it (quantity, pack, unit price and other amounts, each with its own
  currency).
- **FieldExtraction**: The provenance record behind one extracted field (on a header or a line) —
  its confidence score, the location in the source document it came from, the method and model
  version that produced it, and, once reviewed, the human correction and reviewer if one occurred.
- **ExtractionJob**: The asynchronous unit of work that turns an uploaded document into a quotation's
  extracted fields, with a status a client can poll.
- **ReviewTask**: One item of outstanding review work, surfaced in the review queue independently of
  any single quotation's page, with its own status and priority.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A workspace member can upload a supplier quotation and see it turned into a structured,
  reviewable set of fields without retyping any line item themselves.
- **SC-002**: At least 90% of extracted fields match the correct value on a held-out benchmark set of
  quotations, with no drop in accuracy from one release to the next.
- **SC-003**: 100% of quotations whose line totals do not reconcile with their stated total are held
  in mandatory review — none are ever presented as ready to use without a human looking at the
  mismatch.
- **SC-004**: A reviewer can find, correct, and confirm every flagged field on a typical single-page
  quotation (around 15-20 lines) well within the time it would take to retype the document from
  scratch.
- **SC-005**: The system's confidence scores are trustworthy: fields it reports at a given confidence
  level are actually correct at close to that rate, not consistently over- or under-confident.
- **SC-006**: Zero quotations ever become usable as trusted commercial data without a recorded human
  review decision attached to them.
- **SC-007**: When a supplier sends a follow-up quotation for one already on file, a workspace member
  can see both the new and prior versions and tell which is current, without the prior one
  disappearing.

## Assumptions

- A quotation is denominated in a single currency; genuinely mixed-currency documents are treated as
  a validation failure requiring review rather than something the system resolves automatically.
- Confirming which catalogue product each quotation line refers to is explicitly out of scope here —
  that is the matching capability the next chunk delivers. This chunk's review step confirms the
  supplier and the correctness of the extracted fields, not the product match.
- The confidence threshold below which a field forces mandatory review is a configurable value
  tuned from real data over time, not a fixed number decided in this specification.
- Uploaded documents may contain another business's confidential commercial terms; retention follows
  the same tenant-isolation guarantees as the rest of the product, and a document is retrievable only
  by the workspace that uploaded it, for as long as that workspace's account remains active.
- Email and API ingestion of quotations are reserved for a later chunk; this chunk covers direct
  upload only, though the document record's design anticipates other arrival channels.

## Out of Scope

- Matching extracted quotation lines to catalogue products, alias learning from reviewer decisions,
  and landed-cost computation (the next chunk).
- Offer comparison, recommendations, and basket building (a later chunk).
- Savings verification and the savings ledger (a later chunk).
- Email or API-based quotation ingestion (a later chunk) — this chunk is upload-only.
- Automatic duplicate-document detection or merging.
- Multi-supplier documents (one document is assumed to carry one supplier's quotation).
