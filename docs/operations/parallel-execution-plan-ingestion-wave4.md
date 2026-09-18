# ProcurePilot — Ingestion Wave 4 Execution Plan (Monitoring & Listing APIs)

**Written**: 2026-09-17, following Wave 3's completion and merge onto `013-automated-ingestion`
(commit `23b69f2`).

**Target feature**: `013-automated-ingestion` (R3.0)

**Scope**: `specs/013-automated-ingestion/tasks.md` Phase 4, Tasks T019–T021 — `plan.md`'s own
"Wave 4 — Monitoring & Listing APIs", entirely the Backend lane. No new migration, no schema
change: every table this wave reads (`ingestion_email_log`, `catalogue_imports`, `quotation`,
`extraction_job`) already exists with RLS already enabled+forced from Waves 1–3.

**Mode**: Dispatched to Agy, three parallel sessions (one per task), each in its own real git
clone (`~/agy-clones/`, never a linked worktree — Agy's `grep_handler.go` app-root scan fails
inside one). Unlike Waves 1–3 (implemented in-house), this wave's tasks are read-only, bounded,
and follow an established pattern exactly (see §2) — a good fit for delegation with a careful
review pass before merge, not a from-scratch design decision. Tenant-isolation *design* stays
in-house per standing practice; these tasks reuse an already-reviewed RLS boundary rather than
creating a new one, so the risk this delegates is implementation-pattern-matching, not tenancy
design.

---

## 0. Starting point

Wave 3 (T015–T018, capture + catalogue import backend) is complete, tested (1049 passed
backend-wide, only the 2 known pre-existing `azure` failures), and merged to
`013-automated-ingestion`. This wave adds three read-only endpoints so ingestion activity
(inbound emails, catalogue imports, and aggregate stats) is visible through the API before Wave
5 builds the frontend screens that consume them.

## 1. Non-negotiables

Unchanged from every prior wave: tenant isolation enforced in the database (ENABLE+FORCE RLS,
USING+WITH CHECK) — **every query in this wave goes through `_authenticated_db(settings,
member)`**, never a service-role client, so RLS actually applies; tenancy from the verified JWT
claim only; cross-tenant reads resolve not-found, never forbidden (moot for pure list/stat
endpoints scoped to the caller's own tenant, but any lookup-by-id path must still follow it); no
secrets in the repo; `audit_event` append-only (these are reads — no new audit events are
expected or wanted for a `GET`). Cursor pagination, `limit` capped at 100, matching every other
list endpoint in this codebase (`digests/service.py::list_subscriptions` is the reference
implementation — same `_encode_cursor`/`_decode_cursor` offset-in-base64 helpers, same
`order by created_at desc, id desc` + `fetch_limit + 1` has-more trick). **No rate limiting** on
any of these three endpoints — `GET` list endpoints elsewhere in this codebase are never wrapped
in `@mutation_limiter.limit()`, only mutations are; do not invent a new rate-limit setting.

## 2. Task scope

### T019 — Ingestion email log listing

`GET /api/v1/ingestion/emails` — cursor-paginated list of `ingestion_email_log` rows for the
caller's tenant, newest first (`order by received_at desc, id desc`).

Query params: `cursor` (optional), `limit` (1–100, default 50), `status` (optional, one of
`ingestion_email_status`'s six values), `from_domain` (optional, exact match on
`from_domain`), `date_from`/`date_to` (optional, filter on `received_at`).

Response schema **already scaffolded** in `modules/ingestion/schemas.py` from T008 —
`IngestionEmailLog` (all columns of `ingestion_email_log` including `quotation_id`,
`supplier_id`, `match_method` for "supplier match info and quotation link") and
`IngestionEmailLogList` (`items` + `next_cursor`). Do not redefine these; extend only if a
genuinely new field is needed, and say why in the PR description if so.

New file: `modules/ingestion/email_log_service.py` (or add to the existing
`modules/ingestion/service.py` if that reads more naturally alongside `IngestionConfigService`
— either is fine, pick one and be consistent). Wire into `router.py` as a plain `current_member`
dependency (any role — this is a read, not a write; `WRITE_ROLES` from T015/T018 does not apply
here).

Tests: `tests/integration/test_ingestion_email_log_listing.py` — cover: empty list, pagination
(more than one page), each filter independently (status, from_domain, date range), cross-tenant
isolation (a second tenant's rows never appear), and that `quotation_id`/`supplier_id` are
populated correctly when a row has them and `null` when it doesn't (e.g. a `rejected` row from
before any supplier match was attempted).

### T020 — Catalogue import history

`GET /api/v1/suppliers/{supplier_id}/catalogue-imports` — cursor-paginated list of
`catalogue_imports` rows for one supplier, newest first (`order by created_at desc, id desc`).
Validate the supplier belongs to the caller's tenant first (404 on cross-tenant/unknown
`supplier_id`, reusing the exact check `catalogue_import_service.import_catalogue` already does
at its own top — same query, same `NotFoundError(details={"resource": "supplier"})` shape, for
consistency).

Query params: `cursor`, `limit` (1–100, default 50). No filters requested in tasks.md beyond
supplier scoping — do not add ones that weren't asked for.

Response includes "summary stats and error details" per tasks.md — that is already every column
on `catalogue_imports` (`total_rows`, `imported_rows`, `skipped_rows`, `error_rows`,
`error_details` jsonb, `column_mapping` jsonb, `status`, timestamps) — a new Pydantic schema
`CatalogueImportSummary` (single item) + `CatalogueImportSummaryList` (`items` + `next_cursor`)
in `modules/ingestion/schemas.py`, modeled directly on the real table columns (see
`supabase/migrations/20260917000004_catalogue_imports.sql` — read it, don't guess the columns).

New file or extend `catalogue_import_service.py` with a `list_imports(*, member, supplier_id,
cursor, limit)` function alongside `import_catalogue`.

Tests: `tests/integration/test_catalogue_import_history.py` — empty list, pagination, a real
import's row appears with correct summary counts (reuse `import_catalogue` from T017 to seed a
real row rather than hand-inserting one — proves the listing endpoint and the write path agree
on shape), cross-tenant supplier resolves 404.

### T021 — Ingestion dashboard stats

`GET /api/v1/ingestion/stats` — a single aggregate object, no pagination. Tasks.md's own list:
"Emails received today/week/month, capture uploads, catalogue imports. Supplier match rate,
extraction success rate."

Define each precisely against the real schema (do not invent a metric tasks.md didn't ask for):
- `emails_received_today` / `_week` / `_month` — `count(*) from ingestion_email_log where
  tenant_id = ... and received_at >= <window start>`. "Today"/"week"/"month" are tenant-local
  calendar boundaries — reuse whatever helper this codebase already has for tenant-timezone
  window boundaries (check `reports/`/`digests/` modules for a `reporting_timezone`-aware date
  helper before writing a new one; `tenant_context`/`ctx.get("reporting_timezone")` is the
  established pattern per `digests/service.py`'s `_tenant_context` usage).
- `capture_uploads_total` (or scoped to the same today/week/month windows if that reads more
  usefully — pick one and document the choice) — `count(*) from quotation where tenant_id = ...
  and source = 'capture'`.
- `catalogue_imports_total` — `count(*) from catalogue_imports where tenant_id = ...`.
- `supplier_match_rate` — of `ingestion_email_log` rows with `status = 'completed'`, the
  fraction with a non-null `supplier_id` (i.e. `match_method` set). Define the denominator
  precisely (all completed rows, or all received rows?) and say which in a code comment — this
  is a genuine ambiguity in tasks.md's one-line spec, not something to silently pick without
  flagging.
- `extraction_success_rate` — of `extraction_job` rows belonging to ingestion-sourced quotations
  (`quotation.source in ('email', 'capture')`) that have left `queued`/`running`, the fraction
  with `status = 'succeeded'`. Scope this to ingestion-sourced quotations specifically, not every
  `extraction_job` in the tenant (manually-uploaded quotations have extraction jobs too, and
  mixing them in would misrepresent *this feature's* success rate).

New schema `IngestionStats` in `modules/ingestion/schemas.py`. New service function
`get_ingestion_stats(*, member)`. Single `GET` handler, no query params.

Tests (unit-level is what tasks.md asks for, but this needs real rows to compute a rate against
— use the same disposable-Postgres integration test setup as T019/T020, just skip pagination
concerns): zero-activity tenant returns all-zero stats (not a division-by-zero error — 0/0 rate
must resolve to `0.0` or `null`, pick one and be consistent across both rate fields), a tenant
with a mix of matched/unmatched emails and succeeded/failed extractions produces the correct
rates, cross-tenant isolation (another tenant's activity never leaks into the caller's stats).

## 3. Delegation mechanics

Three independent Agy sessions, each given only this document plus pointers to the exact files
to read first (never asked to re-derive the Wave 1–3 findings already written down here and in
`docs/operations/parallel-execution-plan-ingestion-wave3.md`). Each session:
1. Works in its own real clone under `~/agy-clones/`, on its own branch off
   `013-automated-ingestion` at `23b69f2` (`ingestion-wave4-t019`, `-t020`, `-t021`).
2. Implements its one task, including tests, and runs them against the same disposable-Postgres
   recipe used throughout this feature (Docker `pgvector/pgvector:pg17` on port 5433 + the fixed
   Supabase-stand-in SQL + every `supabase/migrations/*.sql` in order — no new migration needed
   this wave, so this is just "apply everything already merged").
3. Runs `ruff check` on its own changed files.
4. Commits locally (does not push) and reports back a summary of what it did, real findings, and
   test results — same "never trust a self-report" discipline as every other wave: **I re-run
   the tests myself against a fresh disposable Postgres before merging any of the three**, then
   `ruff check` the full `apps/api` tree, then the full backend suite once all three are merged
   together (a stats-endpoint test and a listing-endpoint test could plausibly collide on
   fixture/tenant setup if merged carelessly — check for that specifically).

## 4. Review protocol

Unchanged discipline, applied to delegated work specifically:
1. Every query touching `ingestion_email_log`, `catalogue_imports`, `quotation`, or
   `extraction_job` in the three diffs goes through `_authenticated_db` — grep for
   `create_client`/`service_role` in each diff; there should be none (no Storage/service-role
   need for read-only listing/stats).
2. Cross-tenant isolation actually tested, not just implied by `tenant_id = current_tenant_id()`
   RLS existing — each of the three test files needs a real second-tenant assertion.
3. T021's rate definitions match what's written in §2 above exactly (denominator choice,
   0/0 handling) — Agy sessions run in parallel and cannot coordinate with each other, so this is
   the one task most likely to drift from spec without a shared document to anchor it, which is
   exactly why the definitions are spelled out precisely here rather than left to tasks.md's
   one-liner.
4. Full backend suite green (1049+ passed, only the 2 known pre-existing `azure` failures) after
   all three are merged onto `013-automated-ingestion` together.

## 5. What comes after

Wave 5 (T022–T029) is next — the first wave with real Agy/frontend work: i18n keys, an ingestion
API client, and five UI components (email config settings, email log viewer, capture upload,
catalogue import, ingestion dashboard) plus routing/navigation. T029 (ingestion API client)
depends on this wave's three endpoints being real and stable.

## 6. Cautions

- Do not let T021's stats queries scan unbounded ranges without an index — `ingestion_email_log`
  already has `tenant_id, from_domain` and `tenant_id, status` indexes from T001; check whether a
  `tenant_id, received_at` index is needed for the today/week/month windows before assuming the
  existing ones cover it.
- `catalogue_imports.error_details` and `column_mapping` are `jsonb` — return them as-is in the
  response model (`dict`/`list[dict]` typed), don't stringify or re-parse.
- Three parallel Agy sessions editing the same `modules/ingestion/schemas.py` and possibly the
  same `router.py` is a near-guaranteed merge conflict — resolve by hand at merge time, don't let
  one session silently overwrite another's addition. Merge T019 first, then T020, then T021,
  re-running the full ingestion test directory after each merge rather than merging all three and
  debugging the result at once.
