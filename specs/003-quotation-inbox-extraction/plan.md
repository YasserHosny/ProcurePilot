# Implementation Plan: Quotation Inbox and Extraction Review

**Branch**: `003-quotation-inbox-extraction` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-quotation-inbox-extraction/spec.md`

## Summary

A workspace uploads a supplier quotation (PDF, image, Excel, or CSV) via a presigned direct-to-
storage upload. Structured formats are parsed directly; PDFs and images go through an extraction
worker (Bedrock primary, Azure Document Intelligence fallback) that returns a header and line items,
each field carrying its own confidence and a pointer back to its source location. Arithmetic
mismatches and sub-threshold confidence force the quotation into a review queue, where a human
corrects fields side by side with the source document and confirms the quotation — only after which
its data counts as trustworthy. This is the first chunk with an asynchronous job (extraction) and
therefore the first to need Redis and a genuinely separate service, both pre-authorised by the
constitution for exactly this purpose.

## Technical Context

**Language/Version**: unchanged — Python 3.12 (`apps/api` and the new `services/extraction-worker`),
TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged from chunks 4.1–4.2 for `apps/api`, plus a Redis client
(`redis-py`) for the job queue and a storage client for presigned Supabase Storage URLs.
`services/extraction-worker` is a new Python deployable: an AWS Bedrock SDK client (Claude 3 Haiku)
as the primary extraction path, an Azure Document Intelligence client as fallback, and the stdlib
`csv`/`openpyxl`-equivalent for structured-format bypass. No new frontend dependency.

**Storage**: Supabase Postgres 17 (unchanged) for `document`, `quotation`, `quotation_line`,
`field_extraction`, `extraction_job`, `review_task`. Supabase Storage for the uploaded files
themselves (bucket already created in chunk 4.1, unused until now). **Redis** enters the stack here
for the first time — the extraction job queue — per research R7 in `specs/001-platform-foundation/research.md`.

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core (unchanged). New for
this chunk: an AI evaluation harness under `ml/evals/` against a held-out labelled benchmark
(`ml/benchmarks/`), run on model or prompt change, never on data used to tune the extractor —
per the constitution's Quality Gates.

**Target Platform**: unchanged — Linux containers, evergreen browsers. `services/extraction-worker`
runs as its own container, invoked via the Redis-backed job queue rather than synchronously in the
request path.

**Project Type**: Angular SPA + FastAPI modular monolith, **plus the first genuinely separate
service** (`services/extraction-worker`) — pre-authorised in Constitution Principle VI: "Only the
extraction worker and the optimiser are pre-authorised for extraction when load justifies it."

**Performance Goals**: extraction field accuracy ≥90% on the held-out benchmark, with no regression
release over release (constitution Quality Gates); a reviewer clears a typical single-page quotation
well within manual retyping time (SC-004).

**Constraints**: every extracted field carries its own confidence and source-region provenance, not
an aggregate (Principle I; corrects an earlier data-dictionary placeholder — see Complexity Tracking
and `research.md`); arithmetic mismatches and sub-threshold confidence always force review, with no
override path that skips it (Principle III); nothing becomes trusted commercial data before a
recorded human confirmation (SC-006); WCAG 2.1 AA in both languages for the review screen.

**Scale/Scope**: pilot-sized — tens of quotations per workspace per week, documents in the low tens
of pages, review queues sized for a single reviewer working through them within a day. Three new
`apps/api` modules (`documents`, `quotations`, `extraction`) plus a shared `jobs` module, one new
external service, and roughly 2 new screens (upload + review queue, quotation detail/review).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design | Post-design |
|---|---|---|---|---|
| **I. Evidence Over Assertion** | **Yes — the first real test of this principle** | Every extracted field, not just every quotation, must carry its own confidence, source location, extraction method, and model version, plus the reviewing human once one intervenes. The chunk 4.1 data-dictionary's tentative `QuotationLine.confidence` (a single aggregate decimal) undercounts this and must not be built as drafted — see `data-model.md`. | ⏳ Design must produce a per-field provenance record, not a per-line aggregate | ✅ PASS — `field_extraction` is its own table, one row per field on a header or line, carrying `confidence`, `source_page`/`source_region`, `extraction_method`, `model_version`, and separate `corrected_value`/`corrected_by`/`corrected_at`. The aggregate-confidence placeholder is explicitly superseded, not carried forward (`data-model.md` R5, `research.md`). |
| **II. Deterministic, Replayable Normalisation** | No | No landed-cost computation in this chunk — that is chunk 4.4. Extraction is not a normalisation function in this principle's sense (it reads a document, it does not compute a cost from stored rules), so replay-determinism does not apply here yet. | ✅ N/A | ✅ N/A |
| **III. Human Authority Over Automation** | **Yes — the second real test of this principle** | Extraction, however confident, never becomes trusted data on its own. Arithmetic mismatches and sub-threshold confidence force mandatory review with no bypass. The review queue is a first-class state machine (its own statuses, not just a filter on quotations), matching the constitution's explicit instruction that "human review is an architectural concept, not a screen." | ⏳ Design must model `ReviewTask` as its own resource, not a computed view | ✅ PASS — `review_task` is a standalone table (own `status`/`priority`/`reason`, queryable via `GET /review-tasks` independent of any one quotation). `quotation.status` only reaches `reviewed` — the one trusted state — through an explicit `POST /confirm` that 409s while arithmetic mismatch, sub-threshold fields, or an unconfirmed supplier remain outstanding. |
| **IV. Every Insight Ends in an Action** | Partially | The review queue is itself the action surface — every extracted quotation leads somewhere (confirm or correct), never a passive report. No dashboard ships in this chunk. | ✅ PASS | ✅ PASS |
| **V. Tenant Isolation by Construction** | **Yes** | `document`, `quotation`, `quotation_line`, `field_extraction`, `extraction_job`, and `review_task` are all tenant-scoped and need `tenant_id` + RLS `ENABLED`/`FORCED`, following the uniform pattern from chunks 4.1–4.2. Uploaded files themselves must be retrievable only by the uploading tenant — this is a Supabase Storage policy question, not only a Postgres one, and needs the same rigor. | ⏳ Storage bucket policy is new territory; must be designed, not assumed | ✅ PASS — all six tables get the uniform `ENABLE`+`FORCE`+`USING`+`WITH CHECK` policy (`data-model.md` §Row-level security), and the underlying Storage object gets a *second*, independent boundary: a private bucket with tenant-prefixed paths and Storage policies comparing the path's tenant segment and the owning `document` row to the caller's JWT claim (`research.md` R8) — a readable `document` row must not imply a public object URL. |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes — this chunk's real complexity item** | `services/extraction-worker` is a genuinely new deployable. The constitution pre-authorises exactly this service, but "when load justifies it" still needs a stated reason: AI extraction calls (Bedrock/Azure DI) are slow (seconds to tens of seconds) and call third-party APIs with their own availability and cost profile — running them synchronously inside `apps/api`'s request path would tie up API workers and make a fallback-provider retry impossible to do cleanly. Redis is new too, purely as the job queue backing this one asynchronous flow — not a general cache yet. Both are addressed in Complexity Tracking below. | ⏳ Must document in Complexity Tracking, not merely cite pre-authorisation | ⚠️ PASS with justification — see Complexity Tracking. The queue design stays deliberately boring (Redis + RQ, chosen over Celery specifically to avoid growing a distributed workflow system for one queue and one worker type — `research.md` R4); Postgres's `extraction_job` row, not Redis, is the durable, user-facing source of truth. |
| **VII. Money, Tax, Language from the Schema Up** | Yes | Every quotation line amount (unit price, delivery fee, discount) is an amount+currency pair, matching chunk 4.2's `Money` convention exactly — no new money shape. Locale-sensitive decimal parsing reuses the same unambiguous-parse-or-refuse rule already tested for CSV import. All review-screen strings come from `packages/i18n`, both languages, RTL-tested. | ✅ PASS | ✅ PASS — `contracts/quotation-inbox.openapi.yaml` reuses chunk 4.2's exact `Money` schema (decimal-string amount, three-letter currency, never a bare number) for `unit_price`, `delivery_fee`, `discount`, and `stated_total`. Arithmetic-mismatch tolerance is one minor currency unit using exact `Decimal` arithmetic, never float (`research.md` R6). |

**Workflow gates**: specification precedes code ✅ (spec approved, all checklist items pass, zero
clarification markers); stage gates ✅ (this is Phase 1 chunk 4.3, G1 is the gate ahead); delegated
work reviewed ✅ (planned — every delegated diff reviewed against this plan and the constitution
before it lands, same discipline as chunk 4.2).

## Project Structure

### Documentation (this feature)

```text
specs/003-quotation-inbox-extraction/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── quotation-inbox.openapi.yaml
├── checklists/
│   └── requirements.md  # passing
└── tasks.md              # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
apps/api/
├── src/procurepilot_api/modules/
│   ├── documents/        # upload presigns, document metadata, storage URIs
│   ├── quotations/        # quotation lifecycle, versioning
│   ├── extraction/        # orchestrates the extraction worker; stores results + confidence
│   └── jobs/              # shared async job resource: status, polling
├── migrations/ → supabase/migrations/  (versioned SQL, this chunk's tables + RLS)
└── tests/{unit,integration,contract}/

services/extraction-worker/   # first code in this placeholder directory (chunk 4.1 anticipated it)
├── src/                       # Bedrock primary, Azure DI fallback, structured-format bypass,
│                               # arithmetic/locale validation layer
└── tests/

apps/web/
└── src/app/features/quotations/
    ├── upload/                # drag-and-drop upload, format/progress states
    ├── review-queue/          # cross-quotation review queue, filterable
    └── quotation-review/      # side-by-side document + fields, inline correction, keyboard flow

packages/
└── i18n/                      # quotation.* namespace, en + ar, kept at parity
```

**Structure Decision**: Same modular monolith plus the one pre-authorised new service. `documents`,
`quotations`, `extraction`, and `jobs` land inside `apps/api` per `engineering-spec.md` §2.1 — they
are request/response and orchestration concerns, not the extraction work itself. The extraction work
proper (calling Bedrock/Azure DI, running the validation layer) lives in
`services/extraction-worker`, the placeholder directory chunk 4.1 already created for exactly this
purpose (see `specs/001-platform-foundation/plan.md` Complexity Tracking).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| New deployable: `services/extraction-worker` | AI extraction calls (Bedrock, with Azure DI fallback) run seconds to tens of seconds and depend on a third-party API's own availability. Running this inline inside an `apps/api` request would hold a web worker hostage per document and make a clean fallback-provider retry impossible without also blocking the caller. The constitution names this exact service as pre-authorised ("when load justifies it") — the load reason is latency and third-party dependency isolation, not raw request volume. | Running extraction synchronously in `apps/api` was rejected: it couples the API's availability to two external AI providers' latency and uptime, and a provider failover would have to happen within a single HTTP request's timeout budget instead of a retryable background job. |
| New infrastructure dependency: Redis | Backs the extraction job queue — `apps/api` enqueues a job, `services/extraction-worker` consumes it, and the `jobs` module exposes pollable status back to the client. This is the first asynchronous flow in the product; nothing before it needed a durable queue. | An in-process queue (as used for chunk 4.1's rate limiting) was rejected: it does not survive an API process restart mid-extraction, and would silently lose a job a reviewer is waiting on — unacceptable for a workflow the constitution requires to have "its own state machine, SLAs, and metrics." Already flagged and deferred to exactly this chunk in `specs/001-platform-foundation/research.md` R7. |
