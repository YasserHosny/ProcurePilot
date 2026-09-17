# Tasks: Automated Ingestion

**Feature**: 013-automated-ingestion
**Created**: 2026-09-17
**Status**: Draft

## Phase 1 — Data Model & Infrastructure (Foundation)

- [x] **T001** — Migration: `ingestion_email_log` table + RLS + indexes
  - Create table with all columns from data-model.md
  - ENABLE + FORCE RLS with `USING` and `WITH CHECK`
  - Unique constraint on `(tenant_id, message_id)`
  - File: `supabase/migrations/20260917000001_ingestion_email_log.sql`

- [x] **T002** — Migration: `ingestion_jobs` table + RLS + indexes
  - Create table with `FOR UPDATE SKIP LOCKED` pattern support
  - ENABLE + FORCE RLS
  - Partial index on `(status, created_at) WHERE status = 'pending'`
  - File: `supabase/migrations/20260917000002_ingestion_jobs.sql`

- [x] **T003** — Migration: `tenant_email_config` table + RLS + indexes
  - Create table with unique constraints on `tenant_id` and `forwarding_address`
  - ENABLE + FORCE RLS
  - File: `supabase/migrations/20260917000003_tenant_email_config.sql`

- [x] **T004** — Migration: `catalogue_imports` table + RLS + indexes
  - Create table
  - ENABLE + FORCE RLS
  - File: `supabase/migrations/20260917000004_catalogue_imports.sql`

- [x] **T005** — Migration: `quotations` add `source` + `ingestion_email_id` columns
  - Add `source` column with default `'upload'`
  - Backfill existing rows
  - Add `ingestion_email_id` FK
  - File: `supabase/migrations/20260917000005_quotations_source.sql`

- [x] **T006** — Migration: `suppliers` add `email_domains` column
  - Add `email_domains text[]` with GIN index
  - File: `supabase/migrations/20260917000006_suppliers_email_domains.sql`

- [x] **T007** — Migration: `ingestion-raw` storage bucket + RLS
  - Create bucket for raw email storage
  - Tenant-scoped RLS policy
  - File: `supabase/migrations/20260917000007_ingestion_storage.sql`

## Phase 2 — Backend: Email Ingestion

- [x] **T008** — Module: `modules/ingestion/__init__.py`, router, schemas
  - `modules/ingestion/schemas.py`, `router.py` wired into `main.py`

- [x] **T009** — Service: supplier domain matcher (`modules/ingestion/matcher.py`)
  - R3 assumes a `supplier_contacts` table for the "address" signal that does not exist
    anywhere in this codebase (checked directly). Implemented instead as address MEMORY:
    has this exact From address matched a supplier before, for this tenant
    (`match_supplier_by_address_history`) — delivers the same stated purpose ("higher
    specificity than domain for a shared domain like gmail.com") with no schema change.
  - Cascading order per R3's Decision line: address history → domain → thread → unmatched.
  - Tests: `tests/integration/test_ingestion_matcher.py` (5 tests, including cross-tenant
    isolation) — integration rather than pure-unit, since the logic is mostly SQL.

- [x] **T010** — Service: email parser (`modules/ingestion/email_parser.py`)
  - stdlib `email` + `python-magic` per R2. `content_type_mismatch` flags a disguised
    attachment for the orchestrator to reject.
  - Tests: `tests/unit/test_email_parser.py` (7 tests).

- [x] **T011** — Service: email ingestion orchestrator (`modules/ingestion/orchestrator.py`)
  - Real schema gaps found and resolved during implementation (not assumed from spec docs):
    (a) `quotation.document_id` is a single required FK with no join table, so one quotation
    can only ever have one primary document — every attachment still gets its own `document`
    row, but only the first is wired to a quotation and queued for extraction (a genuine,
    flagged product-scope gap versus the full "each attachment linked to the same quotation"
    acceptance scenario, not a bug in this code); (b) `document.storage_path`'s CHECK only
    allowed `tenants/%/quotations/%`, so ingested documents reuse that exact path shape
    rather than data-model.md's proposed (incompatible) `{tenant_id}/ingestion/email/...`
    shape; (c) `document.mime_type`'s CHECK had no text/plain, which acceptance scenario 5
    (text-only email) requires — widened via `20260917000008_document_mime_type_text_plain.sql`.
  - Unmatched suppliers get a `review_task` (reusing the generic `review_required` reason —
    no reason value names "supplier unmatched" specifically).
  - Tests: `tests/integration/test_ingestion_orchestrator.py` (4 tests: matched, unmatched,
    no-attachment/body-as-document, duplicate message-id).

- [x] **T012** — Worker: email ingestion worker (`workers/email_ingestion_worker.py`)
  - Same `FOR UPDATE SKIP LOCKED` shape as report_scheduler/export_worker/digest_worker;
    tenant_id read from the claimed job row, never the payload (same untrusted-payload
    discipline). Retry up to `max_attempts` (3), then terminal `failed`.
  - No dedicated worker-level test file; covered indirectly via the orchestrator tests
    (`process_inbound_email` is exactly what the worker calls per claimed job).

- [x] **T013** — API: tenant email config endpoints (`modules/ingestion/service.py` + `router.py`)
  - `GET`/`PUT /tenants/email-config`, `POST /tenants/email-config/{enable,disable}`. `PUT`
    upserts (no separate "create" task existed) — `forwarding_address` is server-derived from
    `{tenant.slug}@{INGESTION_EMAIL_DOMAIN}`, not client-supplied.
  - Rate-limited via the established `mutation_limiter` (T035, 012-reporting-hardening)
    pattern — new dedicated setting `RATE_LIMIT_INGESTION_CONFIG_MUTATION`, not reused from
    an unrelated feature's limit.
  - Tests: `tests/integration/test_ingestion_email_config.py` (5 tests, including RBAC).

- [x] **T014** — Webhook: inbound-email endpoint (`modules/ingestion/router.py` + `webhook_security.py`)
  - R1's own "pending implementation spike" (SES vs Mailgun undecided) resolved by an
    `INGESTION_EMAIL_PROVIDER` setting (`stub` default / `mailgun` / `ses`), mirroring
    `EXTRACTION_PROVIDER_MODE`'s stub/real split rather than committing to one provider SDK
    before that decision is made. Mailgun's HMAC-SHA256 signature verification is fully
    implemented (no SDK, no network call). `stub`/`ses` modes verify an interim shared secret
    instead of a real SNS certificate-chain check — full SNS verification is real, separate
    follow-up work once SES vs Mailgun is actually decided, not something to fake as done.
  - Every rejection path (unknown recipient, disabled, domain not allowlisted, daily limit
    reached, oversized) returns the same `202` as success (R10: no existence/state leak from
    the response) rather than the task list's literal "429 for rate limited," which would
    leak that the address exists and has its own limit.
  - Tests: `tests/integration/test_ingestion_webhook.py` (5 tests).

## Phase 3 — Backend: Capture & Catalogue Import

- [x] **T015** — API: capture endpoint (`modules/ingestion/capture_service.py` + `router.py`)
  - `POST /capture` — multipart/form-data (`file`, optional `supplier_id`/`notes`). Synchronous
    in the request (research R5) — unlike email, there is no external step to decouple from,
    the server already has the file bytes. Mirrors the manual-upload flow's own
    document+quotation+extraction_job creation (source = `capture`, status = `pending`)
    rather than routing through `ingestion_jobs`. `enqueue_extraction` factored out of
    `orchestrator.py` into a new shared `modules/ingestion/extraction.py` so capture and email
    share one Redis-enqueue implementation.
  - File type validated via `python-magic` MIME sniffing (`application/pdf`, `image/jpeg`,
    `image/png`, `image/heic`), not the client-supplied filename/extension. `image/heic` and
    a new `document.mime_type` CHECK value added for phone-camera uploads
    (`20260917000009_capture_catalogue_source_and_mime.sql`). No persisted column exists for
    free-text `notes` on `quotation` yet — carried in the audit trail rather than silently
    dropped.
  - Tests: `tests/integration/test_capture_service.py` (5 tests: happy path with queued
    extraction, no-supplier capture, oversized file, unsupported MIME, cross-tenant/unknown
    supplier).

- [x] **T016** — Service: catalogue file parser (`modules/ingestion/catalogue_parser.py`)
  - CSV (stdlib `csv`) and XLSX (`openpyxl`, `read_only=True`) via one shared row model.
    Alias dictionary per research R6. `currency` added to the required-column set beyond R6's
    own explicit list — constitution non-negotiable 6 (every monetary value has an explicit
    currency) makes a missing currency column a whole-file rejection, not a per-row default.
  - Per-row errors (bad type, missing value, etc.) are collected without rejecting the whole
    file; only a missing/unmappable required column rejects the whole file.
  - Tests: `tests/unit/test_catalogue_parser.py` (8 tests: canonical headers, alias
    resolution, missing-required-column and missing-currency whole-file rejection, mixed
    per-row errors, 1-based row numbering, XLSX numeric cells, empty file).

- [x] **T017** — Service: catalogue import orchestrator (`modules/ingestion/catalogue_import_service.py`)
  - Real finding that reshapes this task versus its own summary above: `MatchingService.
    quotation_matches()` (the actual spec-004 matching entry point) refuses any quotation
    whose status is not already `reviewed`, and itself creates the `landed_cost` row for every
    line it auto-matches — there is no lighter "create an offer from a bare product+price"
    path to call instead. So this synthesizes **one `quotation` per import** (not one per row,
    and not one `offer`/`landed_cost` per row directly) with status `reviewed` set at
    creation — the importing owner/buyer is the human vouching for the bulk price list, the
    same role a reviewer plays for extracted data — and one `quotation_line` per valid row,
    then calls the existing, tested matching pipeline exactly as a real reviewed quotation
    would. Runs synchronously inside the request (not via the `ingestion_jobs`/
    `catalogue_import` worker type Wave 1 already declared but leaves unused) because
    `quotation_matches()` authenticates with the caller's real bearer token, which a
    background worker does not have; SC-003 (1,000 rows in 30s) fits an HTTP request budget.
    Full reasoning: `docs/operations/parallel-execution-plan-ingestion-wave3.md` §2.
  - A row with an unsupported currency is a per-row error (FK violation on
    `supported_currency`, caught via a psycopg SAVEPOINT per row), not a whole-import failure;
    an import with zero importable rows records `status = 'failed'` and skips matching
    entirely.
  - Tests mock `MatchingService.quotation_matches` itself (asserting it is called with the
    right bearer token and quotation id) rather than exercising it end-to-end — it talks to
    Postgres via the older postgrest-client architecture that the disposable-Postgres-only
    test environment does not provide, matching this codebase's own precedent
    (`test_matching_routing.py` tests `MatchingService`'s internals in its own suite).
  - Tests: `tests/integration/test_catalogue_import.py` (5 tests: one line per row + matching
    invoked, per-row bad-currency error, all-rows-bad-currency skips matching, unmappable
    required column records a failed import, cross-tenant supplier resolves not-found).

- [x] **T018** — API: catalogue import endpoint (`modules/ingestion/router.py`)
  - `POST /suppliers/{supplier_id}/catalogue-import` — multipart/form-data, CSV or XLSX only
    (25 MB limit via `CATALOGUE_IMPORT_MAX_BYTES`). Owner/buyer role, matching T017's
    `catalogue_imports_owner_buyer_insert` RLS policy. Returns the completed import summary
    directly — there is no async job id to poll, since T017 runs synchronously.
  - Covered by T017's service-level integration tests (`import_catalogue` is exactly what
    this endpoint calls); no separate TestClient-level HTTP test was added for the router
    wiring itself.

## Phase 4 — Backend: Ingestion Listing & Monitoring

- [x] **T019** — API: ingestion email log listing (`modules/ingestion/email_log_service.py` + `router.py`)
  - `GET /ingestion/emails`, cursor-paginated (`_encode_cursor`/`_decode_cursor` offset pattern
    from `digests/service.py`), `order by received_at desc, id desc`. Filters: `status`,
    `from_domain` (exact match), `date_from`/`date_to` (accepts a bare `YYYY-MM-DD` or a full
    ISO datetime; a bare date is widened to the full local day). Reuses the `IngestionEmailLog`/
    `IngestionEmailLogList` schemas already scaffolded in T008 — no changes needed. Every query
    through `_authenticated_db`, no service-role client.
  - Delegated to Agy (`docs/operations/parallel-execution-plan-ingestion-wave4.md`); reviewed
    and independently re-tested before merge, no changes needed.
  - Tests: `tests/integration/test_ingestion_email_log_listing.py` (9 tests: empty list,
    multi-page pagination, invalid cursor, each filter independently, cross-tenant isolation,
    populated vs. null `quotation_id`/`supplier_id`, buyer+owner RBAC).

- [x] **T020** — API: catalogue import history (`catalogue_import_service.py` + `router.py`)
  - `GET /suppliers/{supplier_id}/catalogue-imports`, cursor-paginated, same pattern as T019.
    Validates the supplier belongs to the caller's tenant first, reusing `import_catalogue`'s
    own check (same query, same `NotFoundError` shape). New `CatalogueImportSummary`/
    `CatalogueImportSummaryList` schemas modeled directly on `catalogue_imports`'s real columns.
  - Delegated to Agy; reviewed and independently re-tested before merge, no changes needed.
  - Tests: `tests/integration/test_catalogue_import_history.py` (5 tests: empty list,
    pagination, a real import seeded via T017's `import_catalogue` appears with correct summary
    counts, cross-tenant supplier resolves 404, supplier scoping within the same tenant).

- [x] **T021** — API: ingestion dashboard stats (`modules/ingestion/stats_service.py` + `router.py`)
  - `GET /ingestion/stats` — single aggregate, no pagination. `emails_received_today/_week/
    _month` use tenant-local calendar boundaries (`reporting_timezone` from `tenant`, ISO week
    starting Monday). `supplier_match_rate` = (`ingestion_email_log` rows with `status =
    'completed'` and a non-null `supplier_id`) / (rows with `status = 'completed'`).
    `extraction_success_rate` = (`extraction_job` rows for `quotation.source in ('email',
    'capture')` with `status = 'succeeded'`) / (same scope, `status not in ('queued',
    'running')`). Both rates resolve to `0.0` on a zero denominator, never a division error.
    These two definitions were ambiguous in this task's own one-line spec — pinned precisely in
    `docs/operations/parallel-execution-plan-ingestion-wave4.md` §2 before implementation so
    they wouldn't drift.
  - Delegated to Agy; reviewed before merge. One real finding: the first implementation imported
    `digests/service.py`'s private (`_`-prefixed) `_tenant_context` helper cross-module — CLAUDE.md:
    "cross-module access goes through defined interfaces, not shared internal state." Fixed by
    inlining the one-column `reporting_timezone` lookup this endpoint actually needs, rather than
    reusing a helper that also fetches locale fields it doesn't.
  - Tests: `tests/integration/test_ingestion_stats.py` (6 tests: zero-activity tenant returns
    all-zero stats with `0.0` rates, a seeded mix of matched/unmatched emails and succeeded/failed
    extraction jobs produces hand-verified exact rates, cross-tenant isolation, tenant-timezone
    window derivation, the HTTP endpoint itself, calendar-window unit boundaries).

## Phase 5 — Frontend: Email Config & Ingestion Views

- [ ] **T022** — Component: email ingestion settings
  - Tenant email config display (forwarding address, enabled state)
  - Enable/disable toggle (owner only)
  - Domain allowlist editor
  - Daily limit display
  - Copy-to-clipboard for forwarding address
  - i18n (en + ar)
  - File: `apps/web/src/app/features/ingestion/email-config/`

- [ ] **T023** — Component: ingestion email log viewer
  - Paginated list of processed emails
  - Status badges, supplier attribution, quotation links
  - Date range filter
  - i18n (en + ar)
  - File: `apps/web/src/app/features/ingestion/email-log/`

- [ ] **T024** — Component: capture upload
  - File picker for image/PDF
  - Camera integration (via `<input type="file" accept="image/*" capture="camera">`)
  - Optional supplier selector
  - Upload progress indicator
  - i18n (en + ar)
  - File: `apps/web/src/app/features/ingestion/capture/`

- [ ] **T025** — Component: catalogue import
  - File picker for CSV/XLSX
  - Supplier selector
  - Upload + processing progress
  - Import results display (imported, skipped, errors)
  - Error details expandable list
  - i18n (en + ar)
  - File: `apps/web/src/app/features/ingestion/catalogue-import/`

- [ ] **T026** — Component: ingestion dashboard
  - Stats cards: emails today, captures, imports
  - Match rate gauge
  - Recent activity list
  - i18n (en + ar)
  - File: `apps/web/src/app/features/ingestion/dashboard/`

- [ ] **T027** — Routing: ingestion feature module
  - Add ingestion routes to app routing
  - Navigation menu entry
  - Role guards (owner/buyer)
  - File: `apps/web/src/app/features/ingestion/ingestion.routes.ts`

## Phase 6 — i18n & API Service Layer (Frontend)

- [ ] **T028** — i18n: add ingestion keys (en + ar)
  - All labels for email config, capture, catalogue import, dashboard
  - Error messages
  - Status labels
  - Files: `packages/i18n/en.json`, `packages/i18n/ar.json`

- [ ] **T029** — API service: ingestion API client
  - Typed API calls for all ingestion endpoints
  - Error handling with structured error mapping
  - File: `apps/web/src/app/features/ingestion/ingestion-api.ts`

## Phase 7 — Testing & Quality

- [ ] **T030** — Unit tests: email parser + supplier matcher
  - Sample .eml files as fixtures
  - Domain match, address match, thread match, no-match scenarios
  - MIME type verification edge cases

- [ ] **T031** — Integration tests: email ingestion end-to-end
  - Webhook → job → worker → quotation + documents + extraction job
  - Deduplication test
  - Rate limit test
  - Unmatched supplier → review queue test

- [ ] **T032** — Integration tests: capture endpoint
  - Upload image → quotation + extraction job
  - Upload PDF → same flow
  - File too large → rejection
  - Unsupported type → rejection

- [ ] **T033** — Integration tests: catalogue import
  - CSV with known products → offers created
  - XLSX with unknown products → pending_review
  - Invalid rows → error report
  - Second import → price update, no duplicate offers

- [ ] **T034** — Tenant isolation tests
  - Cross-tenant email log access → not found
  - Cross-tenant capture → not found
  - Cross-tenant catalogue import → not found
  - Email to disabled tenant → bounce

- [ ] **T035** — E2E tests: ingestion flows
  - Email config setup (Playwright)
  - Capture upload flow (Playwright)
  - Catalogue import flow (Playwright)
  - Dashboard stats display

- [ ] **T036** — a11y: ingestion surfaces
  - axe-core scan on all ingestion components
  - Keyboard navigation for file upload
  - RTL layout verification

## Phase 8 — Documentation & Close-Out

- [ ] **T037** — API specification: add ingestion endpoints
  - `docs/architecture/api-specification.md` — R3.0 section
  - All new endpoints documented

- [ ] **T038** — Data dictionary: add ingestion entities
  - `docs/architecture/data-dictionary.md` — new tables, columns, events
  - All new audit events documented

- [ ] **T039** — User documentation: ingestion features
  - `docs/user/user-documentation.md` — email forwarding, capture, catalogue import
  - Mobile documentation update

- [ ] **T040** — Test strategy: R3.0 section
  - `docs/quality/test-strategy.md` — ingestion test coverage
  - Worker reliability, deduplication, rate limiting

- [ ] **T041** — OpenAPI contract update
  - `specs/013-automated-ingestion/contracts/automated-ingestion.openapi.yaml`
  - All new endpoints with request/response schemas

- [ ] **T042** — Security review: ingestion surfaces
  - Webhook signature verification
  - File upload validation (type sniffing, size limits)
  - Rate limiting on all ingestion endpoints
  - Tenant isolation in worker jobs
  - Anti-abuse measures
