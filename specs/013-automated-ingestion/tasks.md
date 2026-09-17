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

- [x] **T028** — i18n: add ingestion keys (en + ar) (`packages/i18n/{en,ar}.json`)
  - One new top-level `ingestion` namespace, nested the same way `digests`/`reports` already
    are. Covers every label, button, empty-state, and error message for T022–T026 in one pass,
    landed *before* those five components so five parallel builds never had to touch (and
    conflict on) the same two JSON files. Real, natural Arabic — not transliterated.
  - Ran first, alone, in Wave 5's delegation sequence (see
    `docs/operations/parallel-execution-plan-ingestion-wave5.md` §4).

- [x] **T029** — API service: ingestion API client (`modules/ingestion/ingestion-api.ts` on web)
  - `IngestionApiService`, modeled on `reports/digest-settings/digests-api.ts`'s shape. One
    method per backend endpoint (T013, T015, T018–T021), typed request/response interfaces
    matching the real Pydantic schemas field-for-field. The two upload methods
    (`submitCapture`, `submitCatalogueImport`) build `FormData` and post it directly — no
    `Content-Type` header set by hand, no presign step (unlike `quotation-upload.component.ts`'s
    older flow) — since the backend endpoints are plain multipart POSTs. Reuses the existing
    `ApiError` type rather than redefining it; does not duplicate `ApiService.suppliers()`.
  - Ran alongside T028 (no shared files). Tests: `ingestion-api.spec.ts` (15 tests).

- [x] **T022** — Component: email ingestion settings (`features/ingestion/email-config/`)
  - Tenant email config display, owner-only enable/disable toggle (`*appRole="'owner'"`,
    matching T013's server-side `require_role(*OWNER)`), domain allowlist editor (chip add/
    remove, PUTs the full array), copy-to-clipboard forwarding address, read-only daily limit
    display. Follows `digest-settings.component.ts`'s signal + `TranslateService` pattern.
  - **Real test-infrastructure bug found in review**: spying on `MatSnackBar` via a plain
    `TestBed.configureTestingModule({ providers: [{ provide: MatSnackBar, useValue: spy }] })`
    entry silently does nothing for a standalone component in this Angular setup — `inject(
    MatSnackBar)` still resolves to the real service (confirmed empirically by logging the
    injected instance). The proven fix, used throughout this codebase (e.g.
    `team.component.spec.ts`) but not written down anywhere: `.overrideComponent(YourComponent,
    { set: { providers: [...] } })` instead. Fixed in this component's spec and called out
    explicitly in every subsequent Wave 5 component's dispatch brief so it wasn't rediscovered
    five times.
  - Delegated to Agy; reviewed, independently re-tested, one fix applied before merge.

- [x] **T023** — Component: ingestion email log viewer (`features/ingestion/email-log/`)
  - Cursor-paginated list via `IngestionApiService.listEmailLogs`, six distinct status badges
    (`received`/`processing`/`completed`/`failed`/`duplicate`/`rejected`), supplier/quotation
    links, status/from-domain/date-range filters with reset. Follows `reports-center.component.
    ts`'s listing pattern.
  - Delegated to Agy; reviewed. One minor fix: a pagination test relied only on
    `HttpTestingController.expectNone(...)` with no Jasmine `expect(...)`, which Karma flags as
    "has no expectations" even though it passes — added real assertions alongside it.

- [x] **T024** — Component: capture upload (`features/ingestion/capture/`)
  - File picker (`application/pdf,image/jpeg,image/png,image/heic`) plus a mobile camera-capture
    input (`accept="image/*" capture="camera"`), optional supplier selector (reuses the existing
    `ApiService.suppliers()`, no duplicate lookup logic), optional notes field, client-side
    pre-checks (empty/oversized/unsupported-format) before the round trip. Mirrors
    `quotation-upload.component.ts`'s drag-drop/validate/error-handling UX, but posts directly
    via `IngestionApiService.submitCapture` (no presign step — T015's endpoint is a plain
    multipart POST). Inline error banner, not a snackbar. `*appRole="['owner','buyer']"` display
    gate matching T015's real server-side role requirement.
  - Delegated to Agy; reviewed, independently re-tested, no changes needed.

- [x] **T025** — Component: catalogue import (`features/ingestion/catalogue-import/`)
  - Required supplier selector (the endpoint is per-supplier; file picker stays disabled until
    one is chosen), CSV/XLSX-only picker, client-side pre-checks (empty/oversized/format) before
    submit, indeterminate progress (never a fake determinate percentage — T017's matching runs
    synchronously server-side), results summary (total/imported/skipped/error counts) with an
    expandable per-row error list, "import another" reset. Deliberately has no "cancel" action on
    an in-flight import (there is nothing to cancel — the server call is synchronous).
  - Delegated to Agy; reviewed, independently re-tested, no changes needed.

- [x] **T026** — Component: ingestion dashboard (`features/ingestion/dashboard/`)
  - Stat cards (emails today/week/month, capture uploads, catalogue imports), match-rate and
    extraction-success-rate shown as `<mat-progress-bar mode="determinate">` percentages (no new
    charting library). Recent-activity section deliberately scoped to the 5 most recent
    `listEmailLogs` rows only and labeled "Recent Emails," not an unqualified "Recent Activity"
    — there is no tenant-wide catalogue-import listing endpoint (T020 is per-supplier only), so
    captures/imports genuinely cannot appear there; a code comment says so. Cards link to the
    other four sub-pages (this is the hub — see T027).
  - Delegated to Agy; reviewed, independently re-tested, no changes needed.

- [x] **T027** — Routing + navigation (`app.routes.ts` + `layout/shell/shell.component.html`)
  - **Real finding versus tasks.md's own file list**: this codebase has no per-feature
    `*.routes.ts` files anywhere (`find . -iname "*.routes.ts"` returns only `app.routes.ts`
    itself) — every feature registers lazy `loadComponent` routes directly in one central file.
    Added five routes there instead of creating `features/ingestion/ingestion.routes.ts` as
    tasks.md's bullet suggested. `/ingestion/capture` and `/ingestion/catalogue-import` get
    `canActivate: [roleGuard('owner', 'buyer')]` (matching `/quotations/upload`'s own
    precedent); the other three ingestion routes have no route-level guard, matching
    `/reports`/`/reports/digest-settings`.
  - **Hub-and-spoke navigation**, not one sidenav item per component: a single new entry
    (`inbox` icon, `ingestion.nav` i18n key, matching `reports.nav`'s own per-feature-key
    convention) routes to `/ingestion` only — the other four pages are reached via links from
    the dashboard hub, exactly like `reports-center` → `schedule-form`/`digest-settings` have no
    sidenav entries of their own.
  - Ran solo, after all five Phase 5 components were merged, specifically to avoid five parallel
    sessions all editing these same two shared files.
  - Delegated to Agy; the first dispatch attempt was killed by the host's OOM watchdog while
    running backgrounded — retried in the foreground per this session's own established
    guidance for OOM-prone dispatches, which completed cleanly. Reviewed, independently
    re-tested (436/436), lint and a full production build both clean.

**Known follow-up, not fixed in this wave**: `pnpm --filter web build` warns that all five new
components' `.scss` files exceed the project's 4 KB per-component style budget (by 195 B–1.95 KB
each) — a non-blocking build warning, not an error, and not caught by any test. Five components
built in parallel without visibility into this shared Angular CLI budget. Worth a follow-up pass
to trim shared styles into a common stylesheet rather than tuning five files individually, but
deferred rather than spending another delegation round on pure CSS size right now.

## Phase 7 — Testing & Quality

Wave 6 execution plan: `docs/operations/parallel-execution-plan-ingestion-wave6.md`. Its own
grounding pass found T030–T034 largely already covered by tests written alongside their own
backend tasks in Waves 1–4 (see that doc's §0) — each entry below records only the real,
precisely-scoped gap that was actually closed, not a full suite written from scratch.

- [x] **T030** — Unit tests: email parser (`tests/unit/test_email_parser.py`)
  - The matcher side (domain/address/thread/no-match, cross-tenant) was already fully covered
    by T009's own tests — untouched. Real parser-level gaps closed: body-only/no-attachment
    email, `multipart/alternative` (plain-text preferred over html), RFC 2047 non-ASCII subject
    + non-UTF-8 (`windows-1256`) body charset, malformed/garbage bytes raising `EmailParseError`
    cleanly. Kept the existing programmatic `EmailMessage`-builder pattern rather than adding
    on-disk `.eml` fixtures — a deliberate call, not a default.
  - Delegated to Agy; reviewed, independently re-tested (11/11), no changes needed.

- [x] **T031** — Integration test: the email ingestion worker itself
  (`tests/integration/test_email_ingestion_worker.py`, new file)
  - Deduplication, the unmatched-supplier review path, and the daily rate limit were already
    covered by T011/T014's own tests — untouched. The real, single gap: nothing exercised the
    actual worker's `FOR UPDATE SKIP LOCKED` claim loop end-to-end (every existing test called
    the orchestrator function or webhook handler directly). Five new tests: claim + status
    transition, **real concurrent-claim exclusivity** (two genuine overlapping psycopg
    transactions, no `sleep()`-based race), the success path via `tick()` creating
    document/quotation/extraction_job, retry-to-terminal-`failed` after `max_attempts`, and
    `tenant_id` sourced from the claimed job row even when the payload carries a wrong or
    missing tenant id.
  - Delegated to Agy; reviewed (including the concurrency test's actual mechanics, not just
    that it passed), independently re-tested (5/5), no changes needed.

- [x] **T032** — Integration test: capture endpoint, `image/jpeg` happy path
  (`tests/integration/test_capture_service.py`)
  - Four of five scenarios were already covered by T015's own tests; the one gap was the
    happy-path test only exercising a PDF, not the image case tasks.md also asks for. New test
    mirrors the existing PDF happy path exactly, asserting `document["mime_type"] ==
    "image/jpeg"`.
  - First dispatched to OpenCode (`opencode-go/muse-spark-1.2-contributor-free`, the `simple`
    lane at the time) — both `-free` model variants (`1.2` and `1.3`) failed immediately with a
    generic `"Unexpected server error"`, confirmed independent of the brief by running the raw
    `opencode` CLI directly with a trivial "say hello" prompt. The user's response was to remove
    OpenCode from the fleet entirely (not just retry or swap models) — see the
    `delegate-heavily-to-codex` memory. Re-dispatched to Agy (the `simple` lane's new default);
    reviewed, independently re-tested, no changes needed.

- [x] **T033** — Integration test: catalogue import repeat-call behavior
  (`tests/integration/test_catalogue_import.py`)
  - T033's original acceptance-scenario wording ("offers created", "pending_review", "no
    duplicate offers") describes a design T017 explicitly abandoned during implementation (see
    T017's own entry above) — the four scenarios already tested there are correct for the real
    design and untouched. The one scenario with a real analog under the new design: importing
    the identical file twice. New test proves catalogue_import's own repeat-call behavior is
    sane (two independent, internally consistent reviewed quotations, matching invoked twice
    with two different quotation ids) — it explicitly does **not** prove the real
    `MatchingService`/`landed_cost` pipeline is idempotent on a duplicate price list, since that
    pipeline is faked in this test file by established precedent; that remains a genuine,
    explicitly-flagged open question, not silently resolved either way.
  - Delegated to Cursor (`auto`, the new `mid` lane — no packaged `cursor-delegate` skill yet,
    dispatched by hand via `cursor-agent -p`); reviewed, independently re-tested, no changes
    needed. First use of the Cursor lane on this feature.

- [x] **T034** — Tenant isolation: close the one real gap, extend the canonical surface
  (`tests/integration/test_tenant_isolation.py`)
  - Every ingestion table except `tenant_email_config` already had *some* cross-tenant coverage
    scattered in its own per-endpoint test file (T019/T020/T021) — but none of the four had an
    entry in this codebase's actual canonical isolation surface, the master
    `test_tenant_isolation.py` (its own module docstring tracks every chunk that's extended it;
    its closing `test_rls_is_enabled_and_forced_on_every_tenant_scoped_table` meta-test is a
    hardcoded table allowlist that silently does not check any table missing from it). Added
    `tenant_email_config`, `ingestion_email_log`, `ingestion_jobs`, and `catalogue_imports` to
    both — new `Workspace` fields + `make_workspace()` seed rows, 8 new visibility/cross-tenant-
    write tests, and the meta-test's allowlist. All 83 tests in the file pass, including the
    meta-test now actually verifying RLS enabled+forced on all four (it silently wasn't
    checking them before this).
  - Done in-house, not delegated, per the standing tenancy carve-out.

- [x] **T035** — E2E tests: ingestion flows (`apps/web/tests/e2e/ingestion.spec.ts`)
  - Four flows per `docs/operations/parallel-execution-plan-ingestion-wave7.md` §2: email config
    setup (including the unconfigured-state fix from Wave 6's bug find), capture upload with a
    positive+negative route-guard regression pair (viewer blocked, buyer allowed), catalogue
    import (supplier-gated file picker, real CSV fixture matched exactly by row count), and
    dashboard stats on a genuinely fresh zero-activity workspace.
  - Delegated to Agy; reviewed and independently re-run. My own first re-run hit a real
    infrastructure gap this session hadn't hit before: the running `procurepilot-api`/`-web`
    containers were wired to the **remote hosted** Supabase project (`docker-compose.remote.yml`,
    left over from Agy's own live-walkthrough session), while local E2E setup mints its test
    invitation directly into a **local** `supabase start` Postgres — two different databases, so
    sign-up 404'd. Rebuilt against the local stack instead and hit a second, genuinely subtle gap:
    the API's `SUPABASE_JWT_ISSUER` must equal GoTrue's own literal configured issuer string
    (`http://127.0.0.1:54321/auth/v1`, confirmed by reading `supabase_auth_ProcurePilot`'s real
    env — note this is `127.0.0.1`, not the docker bridge gateway IP the app otherwise reaches
    Supabase through) or every real signed-in session 401s with `invalid_token_claims`, even
    though the anon/service-role keys work fine. Once both were fixed, all 4 flows passed cleanly,
    independently, twice.

- [x] **T036** — a11y: ingestion surfaces (`apps/web/tests/e2e/ingestion-a11y.spec.ts`)
  - axe-core (WCAG 2.1 AA) on all five surfaces in English and Arabic, keyboard-only operability
    of both file-upload components (Tab/Enter reaching and activating the file trigger and the
    remove-file control, with real focus assertions), and an explicit RTL check beyond the axe
    scan (no horizontal scroll, directional-icon mirroring via `.rtl-flip`).
  - Delegated to Agy, with an explicit instruction not to weaken assertions or suppress findings.
    It found 3 real WCAG AA color-contrast violations and correctly left the spec committed with
    those 3 tests failing rather than hiding them: dashboard `.stat-secondary` text (`#94a3b8` on
    white, 2.56:1), and catalogue-import's disabled-dropzone prompt/hint text (3.82:1 and 2.17:1,
    made worse by `opacity: 0.6` on the whole disabled container). Independently re-verified the
    same 3 failures myself before merging the spec as-is.
  - Immediately dispatched a follow-up fix (also Agy) for all 3: replaced the washed-out colors
    with ones that independently compute to >= 4.5:1 (verified both by the dispatch and by me,
    same luminance formula, same results — 4.76:1 / 13.35:1 / 6.92:1), and removed the disabled
    dropzone's blanket `opacity: 0.6` (de-emphasis is now full-contrast text plus a de-emphasized
    icon and `cursor: not-allowed` instead). Rebuilt the live web container with the fix and
    re-ran the full a11y suite plus T035's E2E suite against it: 15/15 and 4/4 pass, zero
    regressions, zero remaining violations.

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
