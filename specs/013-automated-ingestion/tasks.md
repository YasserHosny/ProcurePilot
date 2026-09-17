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

- [ ] **T015** — API: capture endpoint
  - `POST /api/v1/capture` — multipart/form-data
  - Accept file (image/pdf) + optional supplier_id + optional notes
  - Validate file type and size (10 MB limit)
  - Store file → Supabase Storage
  - Create quotation record (source = 'capture')
  - Queue extraction job
  - Create audit event
  - Return quotation_id + status
  - Rate limiting
  - Unit + integration tests

- [ ] **T016** — Service: catalogue file parser
  - Parse CSV (stdlib csv module)
  - Parse XLSX (openpyxl)
  - Column mapping via alias dictionary (research R6)
  - Row validation (required fields, types, currency presence)
  - Return structured `CatalogueImportData` with valid_rows + error_rows
  - Unit tests with sample files

- [ ] **T017** — Service: catalogue import orchestrator
  - Accept parsed catalogue data + supplier_id + tenant_id
  - Match products against catalogue (call spec 004 matching pipeline)
  - Create/update offers with explicit currency
  - Flag unmatched products as `pending_review`
  - Create `catalogue_imports` record with results
  - Create audit events
  - Integration tests

- [ ] **T018** — API: catalogue import endpoint
  - `POST /api/v1/suppliers/{supplier_id}/catalogue-import` — multipart/form-data
  - Accept CSV or XLSX file (25 MB limit)
  - Validate supplier belongs to tenant
  - Store file → Supabase Storage
  - Call catalogue import orchestrator
  - Return import summary (imported, skipped, errors)
  - Rate limiting
  - Unit + integration tests

## Phase 4 — Backend: Ingestion Listing & Monitoring

- [ ] **T019** — API: ingestion email log listing
  - `GET /api/v1/ingestion/emails` — cursor-paginated list of processed emails
  - Filters: status, from_domain, date range
  - Response includes supplier match info and quotation link
  - Unit + integration tests

- [ ] **T020** — API: catalogue import history
  - `GET /api/v1/suppliers/{supplier_id}/catalogue-imports` — paginated import history
  - Response includes summary stats and error details
  - Unit + integration tests

- [ ] **T021** — API: ingestion dashboard stats
  - `GET /api/v1/ingestion/stats` — aggregate stats
  - Emails received today/week/month, capture uploads, catalogue imports
  - Supplier match rate, extraction success rate
  - Unit tests

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
