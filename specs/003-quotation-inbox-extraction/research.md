# Phase 0 Research: Quotation Inbox and Extraction Review

**Feature**: 003-quotation-inbox-extraction | **Date**: 2026-08-21

Chunk 4.1 settled tenancy, auth and the platform stack. Chunk 4.2 settled catalogue money and
decimal parsing conventions. This document resolves only what quotation upload, extraction,
review and the first background job add.

---

## R1 - Presigned direct-to-storage upload

**Decision**: `apps/api` owns a `documents` module endpoint that validates the requested file
metadata, creates a tenant-scoped `document` row, and returns a short-lived Supabase Storage
presigned upload target. The client uploads bytes directly to Supabase Storage using that target,
then creates a `quotation` linked to the `document`.

**Rationale**: FR-001 requires direct-to-storage upload. The API must still be the authority for
tenant scope, accepted MIME types, storage path allocation, content hash recording and document
identity. Keeping file bytes out of the API request path avoids tying FastAPI worker capacity to
large uploads while preserving the database record every later state transition depends on.

Storage paths are allocated by the server under a tenant prefix, for example
`tenants/{tenant_id}/quotations/{document_id}/{filename}`. The client never supplies `tenant_id`,
and the path is not treated as an authorization boundary by itself; it is backed by Storage policy
and the tenant-scoped `document` row.

**Alternatives considered**:
- *Multipart upload through `apps/api`* - simpler to reason about, but contradicts FR-001 and
  makes the API carry large file transfer load that Supabase Storage already handles.
- *Client writes to any path and reports it afterward* - fast, but the client would control tenancy
  placement and could create orphaned files. Rejected by Principle V.
- *Create the quotation before upload succeeds* - would expose review or extraction states for a
  file that might never exist. The `document` can exist at presign time; `quotation` starts only
  once the client has completed upload and posts the document id.

---

## R2 - Extraction provider and fallback

**Decision**: use AWS Bedrock Claude 3 Haiku as the primary unstructured extraction path, with
Azure Document Intelligence as fallback when the Bedrock call is unavailable, times out, returns
invalid schema, or fails parse validation before any useful result can be stored.

**Rationale**: engineering-spec §2.2 already names Bedrock primary and Azure DI fallback. A single
provider creates a hard outage path for the review queue. A primary/fallback pair lets extraction
remain available when one provider fails, while still recording `extraction_method` and
`model_version` per field so downstream users can reconstruct how each value was produced.

Fallback is not used to "vote" between providers in this chunk. It is triggered by operational or
contract failure: provider timeout, rate limit exhaustion, transport error, invalid JSON/schema,
unreadable OCR output, or a provider-specific error. Arithmetic mismatch and low field confidence
do not trigger provider fallback by themselves; they are valid extraction outcomes that force human
review.

**Alternatives considered**:
- *Bedrock only* - lower implementation cost, but one provider outage blocks every new quotation
  from entering review.
- *Azure DI only* - strong for stable form layouts, weaker for arbitrary supplier quotation prose
  and line formats; also gives up the planned Bedrock structured JSON path.
- *Call both providers for every document* - useful for later evaluation, too expensive and slow
  for the MVP path. It also complicates reviewer evidence by creating competing originals.

---

## R3 - Structured-format bypass

**Decision**: Excel and CSV inputs bypass LLM extraction entirely. The extraction worker parses
them deterministically, maps recognized columns to quotation header and line fields, and records
their provenance with `extraction_method = structured_parse` and confidence `1.0000` for values
that parse unambiguously.

**Rationale**: FR-006 is explicit: structured files are already machine-readable. Sending them to
an LLM would add cost, latency and non-determinism while making tests less precise. Deterministic
parsing also reuses the decimal-separator discipline established in chunk 4.2: unambiguous values
parse; ambiguous numeric values are refused into review rather than guessed.

**Alternatives considered**:
- *Normalize every file through the LLM for one implementation path* - superficially simpler, but
  lower accuracy and higher cost for the easiest inputs.
- *Accept spreadsheet values without provenance rows* - contradicts FR-008 and FR-009. A
  deterministic parse is still an extraction method and must be auditable per field.

---

## R4 - Redis job queue

**Decision**: use Redis with Python RQ (`rq`) for the first job queue: `apps/api` writes an
`extraction_job` row and enqueues a small payload containing `job_id`, `tenant_id`, `quotation_id`
and `document_id`; `services/extraction-worker` consumes the queue, updates the job row, and stores
results.

**Rationale**: this is the first background job in the product and should stay boring. RQ matches a
Python FastAPI plus Python worker split, uses Redis directly, has a clear worker model, and avoids
Celery's broker/result-backend configuration surface. The database remains the durable user-facing
job state; Redis is only the delivery mechanism.

The queue payload is deliberately minimal and never contains extracted commercial data or file
bytes. Workers load the document and quotation records through the same tenant-scoped database
model before processing.

**Alternatives considered**:
- *Simple Redis list with custom `BLPOP` loop* - less dependency surface, but quickly grows custom
  retry, visibility-timeout and failure bookkeeping. RQ supplies these primitives without turning
  the project into a distributed workflow system.
- *Celery* - capable, but too broad for one queue and one worker type at pilot scale.
- *In-process FastAPI background tasks* - lost on process restart and couples extraction latency to
  the API process. Rejected by the plan's Complexity Tracking.

---

## R5 - Per-field provenance and corrections

**Decision**: store provenance in a separate `field_extraction` row for each extracted field on a
quotation header or quotation line. Each row records the target entity, target field, original
extracted value, confidence, source page/region, extraction method, model version, and optional
human correction metadata.

**Rationale**: FR-008 and Constitution Principle I require confidence and source location for
every field, never a single aggregate confidence for a line or quotation. This explicitly corrects
the tentative aggregate `QuotationLine.confidence` shape from the earlier data-dictionary sketch.
Corrections are separate facts: the original extracted value stays stored, and the human correction
is attributed with `corrected_value`, `corrected_by` and `corrected_at`.

**Alternatives considered**:
- *`confidence` columns on `quotation` and `quotation_line`* - cannot answer which field was weak,
  where it came from, or which model produced it. Rejected by FR-008.
- *JSON blob of all provenance on a quotation* - easy to append, hard to query for review queues,
  calibration and audit. Provenance is first-class data, not metadata.
- *Overwrite extracted values during review* - loses the evidence trail. Rejected by FR-013.

---

## R6 - Arithmetic validation and locale parsing

**Decision**: arithmetic validation runs after extraction/parsing and before review-task creation.
For each line with enough numeric inputs, compute:

`line_total = (quantity * unit_price) - discount + delivery_fee`

using exact decimal arithmetic, only within one currency. If a stated document total is present,
compare the sum of computable line totals to the stated total. A mismatch is any difference greater
than the configured monetary tolerance, initially one minor unit for the quotation currency
(`0.01` for two-decimal currencies), and it forces review.

Locale-sensitive decimal parsing reuses chunk 4.2's rule: when both `.` and `,` are present, the
last separator is the decimal point; when exactly one comma and no dot appears in a fractional-looking
position that is ambiguous, the value is refused into review rather than guessed.

**Rationale**: FR-010 and User Story 3 need a precise definition of mismatch. Exact `Decimal`
arithmetic plus a currency-specific one-minor-unit tolerance avoids false positives from display
rounding while refusing real discrepancies. Mixed-currency documents are out of scope and become
validation failures requiring review, not conversion problems.

**Alternatives considered**:
- *Zero tolerance* - mathematically pure, but rejects normal supplier documents that round each
  displayed line independently.
- *Percentage tolerance* - inappropriate for invoices and quotations: a large quotation could hide
  a meaningful absolute error.
- *Locale inferred from workspace* - suppliers export files in their own locale, not necessarily
  the buyer's. Guessing silently is the failure mode Principle VII forbids.

---

## R7 - Confidence threshold and calibration

**Decision**: use a configurable extraction confidence threshold, read from environment-backed
settings and recorded with the extraction run. Any field below the active threshold creates or keeps
a `review_task` open. Calibration is verified by the AI eval harness using Expected Calibration
Error (ECE), with confidence buckets required to match observed accuracy within 5%.

**Rationale**: FR-011 says the threshold is configurable rather than fixed in the spec. The
threshold is a routing control, not a trust guarantee. Trust comes from the benchmark gate in
docs/quality/test-strategy.md §4: at least 90% field-level accuracy on a held-out labelled set and
confidence calibration that is close to observed correctness.

The eval harness must report field-level accuracy, document exact match, arithmetic-validation pass
rate, cost per document and ECE for every model or prompt change. Tuning data and held-out benchmark
data remain separate.

**Alternatives considered**:
- *Hard-code a single threshold in the database* - difficult to tune as real data arrives and
  cannot be changed without a migration.
- *Accept high-confidence fields without review automatically* - still not enough to make a
  quotation trusted. FR-016 requires human confirmation before downstream use.
- *Aggregate confidence at quotation level* - hides poorly calibrated fields and violates FR-008.

---

## R8 - Storage bucket tenant isolation

**Decision**: create a dedicated Supabase Storage bucket for quotation source documents with
policies that permit access only when the object path's tenant segment matches the caller's
verified `tenant_id` claim and the corresponding tenant-scoped `document` row belongs to that
tenant. `document` table RLS and Storage policy are both required.

**Rationale**: uploaded quotation files contain confidential supplier pricing. Postgres RLS protects
the metadata row but not the blob by itself. Supabase Storage needs its own policy so a member of
tenant A cannot retrieve a tenant B object by guessing or obtaining its path. The presign endpoint
therefore mints paths only under the current tenant and short-lived URLs only for a document row the
caller can access.

**Alternatives considered**:
- *Private bucket plus service-role downloads proxied through `apps/api`* - secure but routes large
  file downloads through the API and tempts broader service-role use in request paths.
- *Rely on unguessable object names* - not an authorization model. A leaked URL or path would
  bypass tenant isolation.
- *One bucket per tenant* - strong isolation but operationally noisy for pilot scale; policies on a
  tenant-prefixed path give the same enforcement shape with fewer moving parts.

---

## Summary of decisions

| # | Question | Decision |
|---|---|---|
| R1 | Upload flow | API creates document + presign; client uploads directly to Supabase Storage |
| R2 | Provider path | Bedrock Claude 3 Haiku primary, Azure DI fallback on operational/contract failure |
| R3 | Structured files | CSV/Excel deterministic parse, no LLM |
| R4 | Queue | Redis + RQ; database remains source of user-facing job state |
| R5 | Provenance | One `field_extraction` row per field; corrections are distinct facts |
| R6 | Arithmetic | Decimal arithmetic; one-minor-unit tolerance; ambiguous locale numbers refused |
| R7 | Thresholds | Configured confidence threshold plus ECE calibration gate |
| R8 | File isolation | Tenant-prefixed Storage path plus Storage policy and `document` RLS |

**No NEEDS CLARIFICATION items remain.**
