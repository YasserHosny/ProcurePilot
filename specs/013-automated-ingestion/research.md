# Research: Automated Ingestion

**Feature**: 013-automated-ingestion
**Created**: 2026-09-17
**Status**: Draft

## R1: Email Receiving Infrastructure

### Question
Which email receiving service should ProcurePilot use for inbound tenant email addresses?

### Options Evaluated

| Option | Model | Pros | Cons |
|---|---|---|---|
| **AWS SES Inbound** | SES receives on MX → SNS → SQS → worker | Push-based, serverless, no polling, proven scale, integrates with S3 for raw storage | AWS-specific, requires domain verification, S3 intermediate storage |
| **Mailgun Routes** | Mailgun receives → HTTP webhook to API | Simple webhook model, good deliverability reputation, built-in parsing | Vendor lock-in to Mailgun, webhook reliability depends on API uptime, per-message cost |
| **IMAP Polling** | Poll a mailbox on a schedule | Works with any email provider, simple to understand | Polling delay (seconds to minutes), connection pooling complexity, credential management, pull-based |
| **Postfix + Dovecot (self-hosted)** | Run own MTA | Full control, no vendor dependency | Operational burden, deliverability reputation, security surface area |

### Recommendation
**AWS SES Inbound** — push-based model eliminates polling delay, SQS provides durable queuing
with at-least-once delivery, and the infrastructure is already in the AWS ecosystem (the
roadmap's §10.3 recommends AWS Bedrock for document AI). Raw emails can be stored in S3 as a
replay log before processing.

**Fallback**: Mailgun Routes as a simpler alternative if SES Inbound's setup complexity is
disproportionate to current scale. Both are evaluated as production-ready.

### Decision
Pending implementation spike. Start with SES Inbound; fall back to Mailgun if domain
verification or SQS integration proves blocking within the first sprint.

---

## R2: Email Parsing and Attachment Extraction

### Question
How should the worker parse inbound emails and extract attachments?

### Evaluation
Python's `email` standard library (`email.message.EmailMessage`) handles MIME parsing, multipart
traversal, attachment extraction, header decoding, and charset handling. No third-party library
needed for parsing.

For MIME type detection of attachments: `python-magic` (libmagic wrapper) provides reliable
content-type sniffing independent of declared MIME headers.

### Recommendation
- Use `email.message_from_bytes` (stdlib) for parsing.
- Use `python-magic` for content-type verification.
- Store attachments with both declared and detected MIME type for audit.
- Reject attachments where detected type does not match declared type (defence against disguised
  executables).

### Decision
Use stdlib `email` parser + `python-magic`. No new heavy dependencies.

---

## R3: Supplier Identification from Email

### Question
How should the system identify which supplier sent an email?

### Evaluation
Three signals, in priority order:

1. **Sender domain match**: Extract domain from `From:` header. Look up in
   `supplier_contacts.email_domain` (existing table). This is the highest-confidence automatic
   match.
2. **Sender address match**: Exact match on `supplier_contacts.email`. Higher specificity than
   domain for suppliers sharing a generic domain (e.g., `@gmail.com`).
3. **Thread context**: If `In-Reply-To` or `References` headers match a previously processed
   email that was already linked to a supplier, inherit the supplier link. Useful for reply
   chains.

If no signal matches, mark the quotation as `supplier_unmatched` and route to the review queue.

### Recommendation
Implement all three signals as a cascading matcher. The review queue for unmatched suppliers
already exists (spec 003). No new AI or ML model needed — this is deterministic domain/address
lookup + thread following.

### Decision
Cascading deterministic match: address → domain → thread. Unmatched → review queue.

---

## R4: Message Deduplication

### Question
How should the system prevent duplicate quotations from the same email?

### Evaluation
RFC 5322 `Message-ID` is globally unique per email. Store processed Message-IDs per tenant in a
deduplication table. Before creating a quotation, check if the Message-ID exists for the tenant.

Edge cases:
- Some email clients generate duplicate Message-IDs for forwarded copies. This is acceptable:
  the forwarded copy should not create a duplicate.
- If a user manually forwards the same email to two different tenant addresses, each tenant
  gets its own record — deduplication is per-tenant.

### Recommendation
- Add `ingestion_email_log` table with unique constraint on `(tenant_id, message_id)`.
- Check before processing; skip with audit event if duplicate.
- Retain the raw email reference for replay.

### Decision
Per-tenant Message-ID deduplication via unique constraint.

---

## R5: Capture Endpoint Design

### Question
Should the mobile capture flow use a dedicated endpoint or extend the existing quotation upload?

### Evaluation
The existing `POST /api/v1/quotations` endpoint expects structured metadata (supplier, products,
prices). The capture flow is fundamentally different: it receives a raw file and optional
metadata, then relies on extraction to produce structure.

### Recommendation
**Dedicated `POST /api/v1/capture` endpoint** — accepts `multipart/form-data` with:
- `file` (required): image or PDF
- `supplier_id` (optional): UUID if the buyer knows the supplier
- `notes` (optional): free-text context

Returns the created quotation ID and extraction status. The quotation starts in
`status = 'pending_extraction'`.

This separates the "I have structured data" flow from the "I have a photo, figure it out" flow
at the API boundary, avoiding conditional complexity in the existing endpoint.

### Decision
Dedicated `/capture` endpoint with minimal metadata. Reuses existing extraction pipeline.

---

## R6: Catalogue Import Column Mapping

### Question
How should the system map CSV/XLSX columns to the canonical product schema?

### Evaluation
Options:
1. **Fixed column positions**: Fragile, breaks with any column reorder.
2. **Header name matching**: Flexible, case-insensitive fuzzy match on header names.
3. **Manual column mapping UI**: Most flexible, highest friction.

### Recommendation
**Header name matching** with a predefined alias dictionary:
- `product_name` / `name` / `item` / `description` → `product_name`
- `unit_price` / `price` / `rate` → `unit_price`
- `unit` / `uom` / `unit_of_measure` → `unit`
- `currency` / `curr` → `currency`
- `qty` / `quantity` / `moq` → `minimum_order_quantity`

If a required column (`product_name`, `unit_price`) cannot be mapped, reject the file with a
structured error listing unrecognised columns and expected alternatives.

Future: manual mapping UI in a later release if customer demand requires it.

### Decision
Header-name matching with alias dictionary. Reject on unmappable required columns.

---

## R7: Redis for Job Queue (Deferred)

### Question
Should ingestion workers use Redis-backed queues (RQ) or the current database-backed approach?

### Evaluation
The current architecture uses `FOR UPDATE SKIP LOCKED` on Postgres for worker coordination
(report_scheduler, digest_worker, export_worker). This works reliably at current scale.

Redis was previously deferred (spec 001, research R7; AGENTS.md notes "No Redis yet — deferred
to chunk 4.3"). Adding Redis specifically for ingestion would introduce a new infrastructure
dependency that the rest of the system doesn't use.

### Recommendation
**Continue with database-backed queuing for R3.0.** Use `FOR UPDATE SKIP LOCKED` on an
`ingestion_jobs` table, matching the established pattern. Revisit Redis when:
- Throughput exceeds what a single Postgres connection pool can handle (>1,000 jobs/minute)
- Multiple independent worker types need different queue semantics

### Decision
Database-backed queue. Redis remains deferred.

---

## R8: File Size and Type Limits

### Question
What limits should apply to ingested files?

### Evaluation
- Supabase Storage default upload limit: 50 MB (configurable).
- Typical quotation PDF: 50 KB – 2 MB.
- Typical photo: 2 – 8 MB (HEIC/JPEG).
- Typical catalogue CSV: 50 KB – 5 MB.
- Typical supplier price list XLSX: 100 KB – 15 MB.

Extraction pipeline performance degrades significantly above 10 MB per document.

### Recommendation

| Context | Size limit | Rationale |
|---|---|---|
| Single email attachment | 10 MB | Extraction performance |
| Total email (all attachments) | 50 MB | Supabase Storage default |
| Capture upload | 10 MB | Mobile upload performance on 3G |
| Catalogue import | 25 MB | Large XLSX sheets with embedded images |

Accepted MIME types:
- Email attachments: `application/pdf`, `image/jpeg`, `image/png`, `image/heic`,
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `text/csv`
- Capture: `application/pdf`, `image/jpeg`, `image/png`, `image/heic`
- Catalogue: `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### Decision
Limits as tabled. Reject unsupported types at the boundary with structured error.

---

## R9: WhatsApp Business API (Deferred Evaluation)

### Question
Should R3.0 include direct WhatsApp Business API integration?

### Evaluation
WhatsApp Business API requires:
1. Meta Business Verification (weeks of process time).
2. WhatsApp Business Account + phone number.
3. Webhook infrastructure for incoming messages.
4. Compliance with Meta's commerce policies.
5. Per-conversation pricing ($0.005–$0.08 depending on category and region).

The manual capture flow (User Story 2) achieves the core value proposition — getting a photo of
a WhatsApp quotation into the system — without any of this infrastructure. The buyer opens the
ProcurePilot app, photographs or shares the file, and uploads it.

### Recommendation
**Defer direct WhatsApp API to R3.x+.** The capture endpoint handles the immediate need.
Evaluate WhatsApp API when:
- 50+ tenants actively request automated WhatsApp capture.
- The manual capture flow proves to be a retention bottleneck.
- Meta Business Verification is completed for unrelated reasons.

### Decision
Deferred. Manual capture covers 80% of value at 10% of complexity, per integration principle #1.

---

## R10: Email Domain Verification and Anti-Abuse

### Question
How should the system prevent abuse of tenant forwarding addresses?

### Evaluation
Risks:
- Spam: tenant address receives unsolicited email.
- Spoofing: attacker sends email pretending to be a supplier.
- Volume abuse: flood of emails to fill storage.
- Cross-tenant: guessing another tenant's address.

### Recommendation
1. **Rate limiting**: max 100 emails/day per tenant address. Excess emails bounced.
2. **Attachment size enforcement**: at SES/Mailgun level before hitting the worker.
3. **Domain allowlist (optional)**: tenants can restrict accepted sender domains to their
   registered supplier domains.
4. **SPF/DKIM/DMARC checking**: verify sender authenticity before accepting.
5. **Cross-tenant**: tenant slug in address is the only identifying information. Standard
   bounce for unknown addresses — no existence leak.

### Decision
Rate limits + optional domain allowlist + SPF/DKIM verification. Detailed implementation in
data model.
