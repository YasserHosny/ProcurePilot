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

- [ ] **T008** — Module: `modules/ingestion/__init__.py`, router, schemas
  - Create ingestion module skeleton
  - Pydantic schemas for email log, job, tenant email config
  - Router stub with OpenAPI tags

- [ ] **T009** — Service: supplier domain matcher
  - `match_supplier_by_address(tenant_id, email)` → supplier_id or None
  - `match_supplier_by_domain(tenant_id, domain)` → supplier_id or None
  - `match_supplier_by_thread(tenant_id, in_reply_to, references)` → supplier_id or None
  - Cascading match function combining all three
  - Unit tests

- [ ] **T010** — Service: email parser
  - Parse raw email bytes → structured `InboundEmail` model
  - Extract: from, subject, message_id, in_reply_to, references, body_text, attachments
  - Each attachment: filename, content_type, size_bytes, content
  - MIME type verification with `python-magic`
  - Unit tests with sample .eml files

- [ ] **T011** — Service: email ingestion orchestrator
  - Accept parsed email + tenant_id
  - Deduplication check (message_id)
  - Supplier identification (cascading match)
  - Create quotation record (source = 'email')
  - Store attachments → Supabase Storage
  - Queue extraction jobs
  - Create audit events
  - Update ingestion_email_log
  - Integration tests

- [ ] **T012** — Worker: email ingestion worker
  - Poll `ingestion_jobs` where `job_type = 'email_ingest'` using `FOR UPDATE SKIP LOCKED`
  - Fetch raw email from S3/Storage
  - Call email parser → email ingestion orchestrator
  - Handle retries (max 3 attempts)
  - Error handling and dead-letter logging
  - Integration tests

- [ ] **T013** — API: tenant email config endpoints
  - `GET /api/v1/tenants/email-config` — get current config
  - `PUT /api/v1/tenants/email-config` — update config (owner only)
  - `POST /api/v1/tenants/email-config/enable` — enable forwarding
  - `POST /api/v1/tenants/email-config/disable` — disable forwarding
  - Rate limiting (SlowAPI)
  - Unit + integration tests

- [ ] **T014** — Webhook: SES/Mailgun inbound endpoint
  - `POST /api/v1/webhooks/inbound-email` — receives SES SNS notification or Mailgun webhook
  - Validate webhook signature (SES SNS signature verification or Mailgun API key)
  - Store raw email → `ingestion-raw` bucket
  - Create `ingestion_jobs` record with `job_type = 'email_ingest'`
  - Update `tenant_email_config.daily_count`
  - Rate limit check against `daily_limit`
  - Return appropriate HTTP status (200 for accepted, 429 for rate limited)
  - Integration tests

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
