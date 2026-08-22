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

## Constitution Check — re-run against delivered code (T069)

Run at the close of chunk 4.3, against what was built, verified directly against a real local
Supabase Postgres (all migrations through `20260819000021` applied), a real Redis queue, a real
`services/extraction-worker` process in its own isolated virtual environment, and a real browser
walkthrough of the actual running stack — not accepted from either delegate's self-report.

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Evidence Over Assertion** | ✅ PASS | `field_extraction` is its own table, one row per field on a header or line — confirmed live: a real CSV extraction produced 9 separate provenance rows (2 lines × 3 fields + 4 header fields), each carrying its own `confidence`, `extraction_method`, `model_version`, and `source_page`/`source_region`, with `corrected_value`/`corrected_by`/`corrected_at` left null until a human actually intervenes. No aggregate confidence anywhere. |
| **II. Deterministic, Replayable Normalisation** | ✅ N/A | Unchanged — no landed-cost computation in this chunk. |
| **III. Human Authority Over Automation** | ✅ PASS | Verified live end-to-end: an extraction with a genuine arithmetic mismatch (line items summing to £130.00 against a stated £120.00) was automatically placed `in_review` with a `review_task` (`reason=arithmetic_mismatch`, `priority=high`); `POST /confirm` correctly refused with 409 first for the missing supplier, then again for the unresolved mismatch, in the right order; only after both were resolved did the quotation reach `reviewed` — the one trusted status — with `reviewed_by`/`reviewed_at` recorded. |
| **IV. Every Insight Ends in an Action** | ✅ PASS | Unchanged from pre-design — the review queue is the action surface. |
| **V. Tenant Isolation by Construction** | ✅ PASS | Queried directly: all six tenant-scoped tables (`document`, `quotation`, `quotation_line`, `field_extraction`, `extraction_job`, `review_task`) show RLS `ENABLED` and `FORCED` — `True/True` on every row. `test_tenant_isolation.py` (T063) exercises real cross-workspace reads/writes on all six under a real JWT claim, **plus** a real `storage.objects` insert/select proving the second isolation boundary: a member of workspace alpha cannot read workspace beta's uploaded file even given its exact storage path. 29/29 isolation tests pass. |
| **VI. Modular Monolith Until Scale Demands Otherwise** | ⚠️ PASS with justification | See Complexity Tracking above — unchanged in substance, but the delivered code initially violated its own spirit: a first backend pass had `services/extraction-worker` importing `apps/api`'s `csv_import.parse_decimal` directly, which crashed the worker on every job in a real isolated deployment (RQ reported it as `AttributeError: module has no attribute 'worker'`, masking the real `ModuleNotFoundError`). Fixed by duplicating the one small pure function into the worker's own package rather than sharing import-time state across the two deployables — re-verified in a clean venv containing only the worker's own declared dependencies. |
| **VII. Money, Tax, Language from the Schema Up** | ✅ PASS | Every quotation line amount uses the chunk 4.2 `Money` convention exactly, confirmed live (`unit_price: {amount, currency}` for both lines). Arithmetic mismatch tolerance uses exact `Decimal` arithmetic reusing the existing catalogue parser, not a second implementation with its own drift risk. |

**Workflow gates**: delegated work reviewed ✅ — backend (Codex), frontend (Antigravity), and docs
(Codex) lanes were dispatched in parallel; every diff was re-verified against a live local Postgres,
a live Redis queue, a live worker process, and a live browser session rather than accepted from
self-reports. Real, load-bearing gaps surfaced only by this — not by either delegate's own sandbox,
which lacked the infrastructure to find them:

- **A stuck-quotation bug**: the extraction-enqueue endpoint wrote `quotation.status = 'extracting'`
  and created an `extraction_job` row *before* pushing the job to Redis; when the Redis push failed,
  neither write was rolled back, permanently stranding the quotation (unextractable and unable to
  accept a new extraction attempt, with no recovery path in the API). Fixed to compensate on
  enqueue failure: mark the job `failed` with a clear reason and restore the quotation's prior
  status.
- **A worker import bug**: covered under Principle VI above.
- **Eight inert placeholder tests**: the backend lane's first pass replaced every DB-backed
  integration test (T017–T022, T038–T042, T054, T058) with a file whose entire body was
  `pytest.skip(...)` — none of them ever ran, regardless of `TEST_DATABASE_URL`. Replaced with real
  assertions against a real database in the delta round.
- **A test-helper role-privilege bug**: the new `quotation_helpers.py`'s reference-data setup
  (`supported_base_unit`) needed superuser privilege but ran after the cursor had already switched
  to `authenticated` role in a prior fixture call within the same connection — the same class of bug
  fixed in chunk 4.2's `catalogue_helpers.py`. Fixed the same way: reset role immediately before the
  privileged insert, restore it after.
- **A test double's JSON-encoding bug**: the fake Supabase-REST-over-psycopg test client only
  wrapped `dict`/`list` payload values in `Jsonb(...)`, not scalars destined for `jsonb` columns —
  a plain string written to `corrected_value` produced invalid JSON. Fixed by naming the known
  `jsonb` columns explicitly in the adapter.
- **A frontend persistence bug, found only by driving the actual browser against the actual
  running API**: selecting a supplier on the review screen with no other field correction never
  reached the backend — `confirmQuotation()` only PATCHed the supplier alongside pending
  corrections, so a supplier-only change was silently dropped and every confirm attempt 409'd with
  `supplier_not_confirmed` forever. Neither Karma's mocked API nor the backend's own tests could see
  this, because it is purely a coordination bug between two independently-built lanes reading the
  same contract differently. Fixed the trigger condition to also cover a changed, unsaved supplier
  selection; added a regression test for both the changed-supplier and already-saved-supplier cases.

### Quality gates

| Gate | Threshold | Status |
|---|---|---|
| Cross-tenant isolation | Proven on every change | ✅ 29/29, including the Storage-object boundary, against a real database |
| Per-field evidence (Principle I) | Confidence + provenance per field, not per line/quotation | ✅ Verified live: 9 `field_extraction` rows from one 2-line CSV |
| Arithmetic mismatch forces review (SC-003) | 100% held in mandatory review | ✅ Verified live: a genuine £10 mismatch produced a high-priority `review_task`, and `POST /confirm` 409'd until it was resolved |
| Human confirmation gates trust (SC-006) | Zero quotations trusted without it | ✅ Verified live end-to-end: upload → extract → mismatch detected → supplier confirmed → mismatch resolved → `POST /confirm` succeeded → `status = reviewed`, `reviewed_by`/`reviewed_at` recorded |
| Structured-format bypass (FR-006) | No LLM call for CSV/Excel | ✅ Verified live: `extraction_method = structured_parse`, `model_version = structured-quotation-parser-v1` on every field |
| Backend test suite | All passing | ✅ 266 passed, 1 skipped (unrelated, pre-existing), ruff clean, against a real local Postgres — confirmed idempotent on repeat runs |
| Worker test suite | All passing, in isolation | ✅ 5 passed, ruff clean, in a venv containing only the worker's own declared dependencies (no `apps/api` on the path) |
| Frontend test suite | All passing | ✅ 62 passed (61 + 1 new regression test), `ng lint` clean, i18n 573/573 exact parity |
| Live end-to-end walkthrough | Human-eye pass through the running app | ✅ Real signup-derived session, real upload, real async extraction via a real Redis-backed worker, real arithmetic-mismatch detection, real 409 refusals in the correct order, real confirmation — all against the actually-running stack, not mocks |

### The honest gaps

- **T066's AI evaluation harness cannot honestly report the ≥90% field-accuracy or calibration
  gates**, because there are no real Bedrock/Azure Document Intelligence credentials yet and no real
  held-out benchmark dataset — this chunk runs entirely on a stub extraction provider by explicit,
  user-approved decision (see spec.md's Assumptions). The harness machinery itself (accuracy,
  document-exact-match, arithmetic pass rate, cost, ECE calculation) is built and runs, clearly
  labelled `gate_status=not_validated_stub_provider_no_held_out_benchmark`, so nobody mistakes
  mechanical correctness for a real accuracy claim.
- **No router/service-level test asserts `test_quotation_trusted_data.py`'s premise beyond a
  documented no-op** — there is genuinely no downstream consumer of `reviewed` quotations yet
  (chunk 4.4's matching pipeline is that consumer), so there is nothing else to assert until that
  chunk exists.
- **Re-quote versioning (US4, P2)** was verified through backend tests and Karma, but not through
  the live browser walkthrough — the walkthrough focused on the P1 MVP loop (upload, extract,
  mismatch, confirm), which is where the constitutional non-negotiables live.
