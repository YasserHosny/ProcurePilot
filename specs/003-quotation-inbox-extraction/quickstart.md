# Quickstart: Quotation Inbox and Extraction Review

**Feature**: 003-quotation-inbox-extraction | **Date**: 2026-08-21

Assumes chunks 4.1 and 4.2 are already working. Start there if auth, tenancy, seed data, catalogue
or suppliers are not running yet:

- [`../001-platform-foundation/quickstart.md`](../001-platform-foundation/quickstart.md)
- [`../002-catalogue-suppliers/quickstart.md`](../002-catalogue-suppliers/quickstart.md)

This chunk adds Redis and `services/extraction-worker` to the same local compose stack at
implementation time. This quickstart documents that dependency; it does not add compose changes.

---

## 1. Bring the stack up

```bash
docker compose up --build
pnpm db:migrate
pnpm db:seed
```

For this chunk, the compose stack must include:

- the existing API, web app and local Supabase services
- a Redis container for the extraction queue
- `services/extraction-worker`, connected to Redis, Supabase Postgres and Supabase Storage

If Redis is absent, quotation upload can create records but extraction jobs cannot run.

## 2. Sign in as a role that may review

Upload, extraction, correction and confirmation are **owner or buyer only**. Branch manager,
approver and viewer accounts may inspect quotation records but should not see mutation controls.
That is the same role split chunk 4.2 uses.

## 3. Upload a quotation document

In the web app: Quotations -> Upload. Select a PDF, image, Excel file or CSV.

The API call is `POST /api/v1/documents/presign`. It creates a `document` row and returns a
Supabase Storage upload target. The browser then uploads the bytes directly to Storage; the file
does not pass through FastAPI.

After upload completes, the web app calls `POST /api/v1/quotations` with the `document_id`. The new
quotation starts in `pending`.

## 4. Run extraction

Trigger extraction from the quotation screen or call:

```bash
POST /api/v1/quotations/{quotation_id}/extract
```

The response is a `Job` resource. Poll:

```bash
GET /api/v1/jobs/{job_id}
```

Structured CSV/Excel files should be parsed deterministically by the worker. PDF and image files
use Bedrock Claude 3 Haiku first and Azure Document Intelligence only on provider/contract failure.

When the job succeeds, the quotation contains header fields, lines, and one `field_extraction` row
per extracted field. Each field has its own confidence, source page/region, method and model
version.

## 5. Review and correct

Open the review queue:

```bash
GET /api/v1/review-tasks?status=open&limit=50
```

Then open a quotation:

```bash
GET /api/v1/quotations/{quotation_id}
```

The review screen should show the source document beside extracted fields. Selecting a field should
highlight its `source_region`. Low confidence fields and arithmetic mismatches keep the quotation in
review until a human resolves them.

Corrections go through:

```bash
PATCH /api/v1/quotations/{quotation_id}
```

The patch records `corrected_value`, `corrected_by` and `corrected_at` on the relevant
`field_extraction` row. It does not overwrite the original extracted value.

## 6. Confirm the quotation

Once the reviewer has confirmed the supplier and resolved required fields:

```bash
POST /api/v1/quotations/{quotation_id}/confirm
```

The quotation becomes `reviewed`. Only this state is trusted commercial data for later matching,
comparison or savings work. `extracted` is not trusted.

If the supplier sent an update to an existing quotation, pass `previous_quotation_id` at confirm
time so both versions remain visible.

## 7. Verify the guarantees

```bash
# Cross-workspace isolation, extended to documents, quotations, jobs and review tasks
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres pnpm test:isolation

# API contracts and extraction/review workflows
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres pnpm test:api

# Web review flow, keyboard navigation and accessibility
pnpm test:web
pnpm test:e2e
pnpm test:a11y
```

The AI evaluation harness for this chunk lives under `ml/evals/` at implementation time and runs on
every model or prompt change. It must report field-level accuracy, document exact match,
arithmetic-validation pass rate, cost per document and Expected Calibration Error against the
versioned held-out benchmark under `ml/benchmarks/`.

## Common problems

**The upload is refused immediately.** The MIME type is not one of PDF, image, Excel or CSV. That
happens before extraction by design.

**The job stays queued.** Redis or `services/extraction-worker` is not running, or the worker cannot
connect to the same queue as `apps/api`.

**A spreadsheet field has no AI model name.** Correct. Structured files bypass the LLM and record
`extraction_method = structured_parse` with a parser/rule version.

**A number like `1,234` is refused.** That value is ambiguous across decimal conventions. Use an
unambiguous form such as `1234`, `1234.00` or `1,234.00`.

**A quotation extracted cleanly but still needs review.** Arithmetic mismatch, missing supplier
confirmation or any field below the configured threshold forces review. A high confidence score
does not authorize data; the human confirmation does.

## What is deliberately absent

- Matching quotation lines to catalogue products
- Alias learning from reviewer decisions
- Landed-cost computation
- Offer comparison, basket building and recommendations
- Savings verification or savings ledger entries
- Email or API ingestion
- Duplicate-document merging
