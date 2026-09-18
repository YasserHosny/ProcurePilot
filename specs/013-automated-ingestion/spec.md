# Feature Specification: Automated Ingestion

**Feature Branch**: `013-automated-ingestion`
**Created**: 2026-09-17
**Status**: Draft
**Input**: Roadmap R3.0 (M15 – M16): "Email ingestion + supplier catalogue refresh". Roadmap §8.1
Phase 3 scope: "Email ingestion: dedicated per-tenant forwarding address; automatic supplier
identification; attachment extraction; thread-to-quotation linking". Roadmap §8.3 Integration
Principle #1: "CSV and email before APIs". This is the first Phase 3 release, following the G2
stage gate (ADR-016).

## User Scenarios & Testing *(mandatory)*

### User Story 1 – Receive quotations by email forwarding (Priority: P1)

A buyer configures a tenant-specific email forwarding address. When a supplier sends a quotation
by email to that address — or the buyer forwards a supplier's email — ProcurePilot identifies the
supplier from the sender or thread context, extracts document attachments (PDF, image, XLSX),
creates a quotation record linked to the identified supplier, and queues the attachments for
extraction. The buyer sees the new quotation in the inbox within minutes, with supplier
attribution and extraction status visible.

**Why this priority**: Email forwarding is the first named R3.0 scope item. The roadmap's
integration principle #1 requires email before APIs. Manual file upload is the current ceiling
on data inflow; email forwarding removes the user from the critical path for every quotation
that arrives by email, which is the dominant channel for the target segment.

**Independent Test**: Configure a tenant email address. Send an email with a PDF attachment from
a known supplier's email domain. Verify: the quotation record is created, the supplier is
identified, the attachment is stored in Supabase Storage, an extraction job is queued, and the
quotation appears in the inbox. Then send the same email again and verify deduplication prevents
a second quotation.

**Acceptance Scenarios**:

1. **Given** a tenant with a configured forwarding address and a registered supplier with
   domain `acme.com`, **When** an email from `sales@acme.com` arrives with a PDF attachment,
   **Then** a quotation is created linked to that supplier, the PDF is stored, and an extraction
   job is queued.
2. **Given** an email with multiple attachments (PDF + XLSX), **When** it is processed, **Then**
   each attachment produces a separate document record linked to the same quotation.
3. **Given** an email from an unrecognised sender domain, **When** it is processed, **Then** the
   quotation is created with supplier marked as `unmatched` and a review-queue item is created
   for manual supplier assignment.
4. **Given** the same email Message-ID is received twice, **When** the second copy arrives,
   **Then** it is discarded without creating a duplicate quotation, and a deduplication event
   is logged.
5. **Given** an email with no attachments (text-only quotation), **When** it is processed,
   **Then** a quotation is created with the email body stored as the primary source document
   and queued for text extraction.

---

### User Story 2 – Capture quotations via WhatsApp photo (Priority: P2)

A buyer photographs a physical quotation or takes a screenshot of a WhatsApp message containing
prices. They upload the image or PDF through a mobile-friendly capture flow. ProcurePilot stores
the original, creates a quotation record, and queues the image for OCR-based extraction. The
buyer can optionally tag the supplier at capture time or let ProcurePilot suggest one from the
extracted content.

**Why this priority**: WhatsApp is the dominant supplier communication channel for SMEs in the
target market. Buyers receive quotations as photos, screenshots, and voice-note-adjacent PDFs in
WhatsApp. The capture flow is the lowest-friction path from a phone screen to a structured
quotation.

**Independent Test**: Upload a photograph of a printed quotation via the mobile capture endpoint.
Verify: the image is stored, a quotation record exists with `source = 'capture'`, an extraction
job is queued, and the quotation appears in the inbox. Upload a WhatsApp-forwarded PDF and
verify the same flow works for document types beyond images.

**Acceptance Scenarios**:

1. **Given** a buyer with a camera phone, **When** they photograph a quotation and upload it
   through the capture endpoint with an optional supplier tag, **Then** the image is stored, a
   quotation is created with `source = 'capture'`, and extraction is queued.
2. **Given** a PDF forwarded from WhatsApp, **When** it is uploaded through the same capture
   endpoint, **Then** the flow works identically to a photographed quotation.
3. **Given** an uploaded image, **When** the buyer does not tag a supplier, **Then** the quotation
   is created with supplier `unmatched` and appears in the review queue for supplier assignment.
4. **Given** an upload exceeding the file size limit (10 MB), **When** the request is submitted,
   **Then** it is rejected with a structured error naming the limit.

---

### User Story 3 – Refresh supplier catalogue from scheduled import (Priority: P2)

A buyer or owner uploads a supplier's full price list (CSV or XLSX). ProcurePilot ingests the
file, maps columns to the canonical product schema, creates or updates offers with validity
dates, and flags new products for review. The import can be repeated — the latest file replaces
stale pricing and the update is audited.

**Why this priority**: "Supplier catalogue refresh" is the second named R3.0 theme item.
Suppliers typically send periodic price lists. An import flow that processes these files into
structured offers eliminates per-item data entry.

**Independent Test**: Upload a CSV with 50 product rows, including known and unknown SKUs.
Verify: known products are matched to existing catalogue entries, unknown products are flagged
for review, offers are created with explicit currency and validity, and a second upload of the
same file does not create duplicate offers.

**Acceptance Scenarios**:

1. **Given** a CSV with a header row mapping to `product_name`, `unit`, `unit_price`, `currency`,
   **When** the file is uploaded for a supplier, **Then** offers are created for each valid row
   with explicit currency.
2. **Given** a row with an unrecognised product, **When** the import processes it, **Then** a
   candidate product is created with `status = 'pending_review'` and linked to the offer.
3. **Given** a second upload of the same supplier's price list with updated prices, **When** it
   is processed, **Then** existing offers' prices are superseded (the old price is retained in
   history) and an audit event records the refresh.
4. **Given** a file with invalid rows (missing required fields), **When** it is processed,
   **Then** valid rows are imported and invalid rows are collected in a structured error report
   returned to the caller.

---

### Edge Cases

- If an email attachment is corrupted or an unsupported MIME type, the document is stored as-is
  with `extraction_status = 'unsupported'` and the quotation remains with no extracted data,
  available for manual entry.
- If the email inbound worker crashes mid-processing, the message remains unacknowledged in the
  queue and is retried. Partially created records are cleaned up or completed on retry.
- If two emails from the same supplier arrive within seconds, each receives its own quotation
  record — deduplication applies only on identical Message-ID, not on supplier proximity.
- If a capture upload is interrupted (partial upload), the storage write is atomic (Supabase
  Storage guarantees) and no quotation record is created for a missing file.
- If a catalogue import file is empty (headers only), the import completes with zero rows
  processed, zero errors, and an explicit empty result — no silent skip.
- If a forwarding address is disabled for a tenant, incoming emails are rejected at the SMTP
  level (bounce) and are not stored.
- If a cross-tenant email address is guessed, the response is a standard bounce — no existence
  leak.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide per-tenant forwarding email addresses in the format
  `{tenant_slug}@ingest.procurepilot.com`, configurable by an owner.
- **FR-002**: System MUST process inbound emails: extract sender, subject, Message-ID,
  In-Reply-To, body text, and all attachments.
- **FR-003**: System MUST identify the supplier from the sender's email domain by matching
  against registered supplier contact emails and domains.
- **FR-004**: System MUST create a quotation record for each processed inbound email, linked to
  the identified supplier (or `unmatched`), with `source = 'email'`.
- **FR-005**: System MUST store each attachment in Supabase Storage under the tenant's document
  bucket, scoped by `tenant_id/ingestion/{quotation_id}/`.
- **FR-006**: System MUST queue each stored attachment for the existing extraction pipeline
  (spec 003).
- **FR-007**: System MUST deduplicate inbound emails by Message-ID per tenant.
- **FR-008**: System MUST provide a mobile-friendly capture endpoint (`POST /api/v1/capture`)
  accepting image (JPEG, PNG, HEIC) and PDF uploads with optional supplier ID.
- **FR-009**: System MUST create a quotation record for each capture upload with
  `source = 'capture'`.
- **FR-010**: System MUST provide a catalogue import endpoint
  (`POST /api/v1/suppliers/{id}/catalogue-import`) accepting CSV and XLSX files.
- **FR-011**: System MUST match imported product rows against the existing catalogue using
  the matching pipeline (spec 004).
- **FR-012**: System MUST create offers from matched catalogue rows with explicit currency
  and validity dates.
- **FR-013**: System MUST flag unmatched products as `pending_review`.
- **FR-014**: System MUST audit every ingestion event: email received, capture uploaded,
  catalogue imported, supplier matched, supplier unmatched, extraction queued.
- **FR-015**: System MUST enforce file size limits: 10 MB per attachment, 50 MB per email,
  25 MB per catalogue import file.

### Non-Functional Requirements

- **NFR-001**: Email processing latency MUST be under 60 seconds from receipt to quotation
  visible in inbox (excluding extraction time).
- **NFR-002**: Capture upload MUST respond within 3 seconds on a 3G connection for a 5 MB image.
- **NFR-003**: Catalogue import of 1,000 rows MUST complete within 30 seconds.
- **NFR-004**: All ingestion endpoints MUST enforce tenant isolation via RLS — no email, capture,
  or import data is accessible cross-tenant.
- **NFR-005**: Inbound email processing MUST be idempotent per Message-ID.
- **NFR-006**: The system MUST handle at least 100 inbound emails per tenant per day without
  backpressure.
- **NFR-007**: All stored documents MUST be encrypted at rest (Supabase Storage default).

### Out of Scope

- Real-time WhatsApp Business API integration (deferred to a later R3.x release; this release
  covers the manual capture flow only).
- Voice note transcription.
- Automatic reply to suppliers acknowledging receipt.
- Email sending from the tenant's forwarding address (inbound only).
- Full ERP connector framework (R3.4).
- Three-way match (R3.3).

## Architecture Notes

### Email Ingestion Pipeline

```
Supplier email
  → SES Inbound / Mailgun Routes
    → SNS → SQS queue
      → Ingestion Worker (Python, runs in API process or sidecar)
        → Identify supplier (domain match)
        → Create quotation record
        → Store attachments → Supabase Storage
        → Queue extraction jobs → existing extraction pipeline
        → Audit event
```

### Capture Flow

```
Mobile device (camera / file picker)
  → POST /api/v1/capture (multipart/form-data)
    → Validate file (type, size)
    → Store file → Supabase Storage
    → Create quotation record (source = 'capture')
    → Queue extraction job
    → Audit event
    → Return quotation ID + status
```

### Catalogue Import Flow

```
CSV / XLSX upload
  → POST /api/v1/suppliers/{id}/catalogue-import
    → Parse file (csv / openpyxl)
    → Validate columns + rows
    → Match products → existing matching pipeline
    → Create / update offers
    → Flag unmatched products
    → Audit event
    → Return import summary (imported, skipped, errors)
```

### Key Design Decisions

1. **SES Inbound over IMAP polling**: SES Inbound + SQS is push-based, serverless, and avoids
   polling delays. IMAP polling requires credentials management, connection pooling, and
   introduces unnecessary latency. Research doc evaluates both.
2. **Capture endpoint over WhatsApp Business API**: The API requires Meta business verification,
   ongoing fees, and webhook infrastructure. Manual capture via the mobile app's camera
   achieves 80% of the value at 10% of the complexity, per integration principle #1.
3. **Reuse existing extraction and matching pipelines**: No new AI infrastructure — FR-006 and
   FR-011 feed into specs 003 and 004 respectively.
4. **Tenant slug in email address**: Uses the existing `tenant.slug` unique constraint. Avoids
   a separate address-allocation system.

## Dependencies

- **Spec 003** (Quotation Inbox & Extraction): extraction pipeline for queued documents.
- **Spec 004** (Matching & Normalisation): product matching for catalogue import.
- **Supabase Storage**: document storage with tenant-scoped RLS.
- **AWS SES Inbound / Mailgun**: email receiving infrastructure (research doc evaluates options).
- **AWS SQS or equivalent**: message queue for inbound email processing.
