# ProcurePilot — Ingestion Wave 3 Execution Plan (Capture & Catalogue Import Backend)

**Written**: 2026-09-17, following Wave 2's completion and merge onto `013-automated-ingestion`
(commit `359c687`).

**Target feature**: `013-automated-ingestion` (R3.0)

**Scope**: `specs/013-automated-ingestion/tasks.md` Phase 3, Tasks T015–T018 — `plan.md`'s own
"Wave 3 — Capture & Catalogue Import Backend", entirely the Backend lane (Claude), matching
Wave 2's lane assignment exactly. No frontend or delegate-lane work in this wave (that's Wave 5).

**Mode**: Implementation, in-house (Claude), following Wave 2's own precedent of grounding every
task in the *actual* schema and existing services before writing code, not the planning docs
alone — this wave surfaced two real architectural findings that change the shape of T017/T018
from what tasks.md's bullet list implies. Both are documented below rather than discovered mid-
implementation and patched around.

---

## 0. Starting point

Wave 2 (T008–T014, email ingestion) is complete, tested (1031 passed backend-wide, only the 2
known pre-existing `azure` failures), and merged to `013-automated-ingestion`. Wave 1's schema
(T001–T007, plus the Wave-1-review fixes and Wave 2's own `20260917000008` migration) is in
place. This wave adds mobile capture and supplier catalogue (CSV/XLSX) import — the last two
ingestion channels before Wave 4 (listing/monitoring endpoints) and Wave 5 (frontend).

## 1. Non-negotiables

Unchanged from every prior wave: tenant isolation enforced in the database (ENABLE+FORCE RLS,
USING+WITH CHECK); tenancy from the verified JWT claim only; cross-tenant reads resolve not-found;
no secrets in the repo; every user-facing string from `packages/i18n`; every monetary value
carries an explicit currency; `audit_event` append-only; no autonomous purchasing (a catalogue
import updates *prices offered*, never places an order). Constitution Principle III — "reviewed
is the only trusted state" — is directly load-bearing for this wave's central design decision;
see §2.2.

## 2. Task scope

### T015 — Capture endpoint

`POST /api/v1/capture`, multipart/form-data: `file` (image/pdf, required), `supplier_id`
(optional), `notes` (optional). Per research R5, a dedicated endpoint rather than extending
`POST /quotations` (that endpoint expects a document that already exists via the presign flow;
capture receives raw bytes directly, has no presign step, and needs no "I already know the
structure" branch).

**Design, reusing Wave 2's own established pattern almost verbatim**: unlike email, there is no
external webhook needing async decoupling — the server already holds the file bytes at the point
of the HTTP request — so capture is handled **synchronously within the request handler**, not via
`ingestion_jobs` + a worker:
1. Validate MIME type (`application/pdf`, `image/jpeg`, `image/png`, `image/heic` per R8) and size
   (≤10 MB per R8) — `image/heic` is not in `document.mime_type`'s current CHECK list (only
   pdf/png/jpeg/tiff/csv/xls/xlsx/text-plain as of Wave 2's own migration) and needs widening in
   this wave's migration alongside the source-channel change below.
2. Upload to the existing `quotation-documents` bucket at the existing path shape
   (`tenants/{tenant_id}/quotations/{document_id}/{filename}`) — same reasoning as Wave 2's own
   `_store_primary_document`: the CHECK constraint on `document.storage_path` only allows this
   shape, and there is no functional need for a different one.
3. Insert `document` (`source_channel = 'capture'`, already a valid enum value from Wave 2),
   `quotation` (`status = 'pending'`, `source = 'capture'`, `supplier_id` from the payload if
   given — **not** `'pending_extraction'`, which research R5 names but which does not exist in
   `quotation_status`'s real enum (`pending, extracting, extracted, in_review, reviewed,
   refused`, checked directly); `'pending'` is the same status a manually-uploaded, not-yet-
   reviewed quotation starts in, and is what this pipeline already treats as "awaiting the
   extraction/review cycle").
4. Insert `extraction_job` (`status = 'queued'`) and enqueue via the existing Redis extraction
   queue — identical to Wave 2's `_enqueue_extraction`, factored into a small shared helper
   (`modules/ingestion/extraction.py`) rather than copy-pasted a second time.
5. Audit `capture_uploaded` (success) or `capture_rejected` (refused, for a validation failure).
6. Rate-limited via a new dedicated setting (`RATE_LIMIT_CAPTURE_UPLOAD`), matching T035's own
   per-feature-limit convention — never reuse an unrelated limit.

### T016 — Catalogue file parser

`modules/ingestion/catalogue_parser.py`. Parses CSV (stdlib `csv`) and XLSX (`openpyxl`, already
a dependency) into a `CatalogueImportData(valid_rows, error_rows, column_mapping)` structure, per
research R6's header-name alias dictionary (`product_name`/`name`/`item`/`description` →
`product_name`; `unit_price`/`price`/`rate` → `unit_price`; `unit`/`uom`/`unit_of_measure` →
`unit`; `currency`/`curr` → `currency`; `qty`/`quantity`/`moq` → `minimum_order_quantity`).
Required columns are `product_name` and `unit_price` (R6) — if the file's headers cannot resolve
either one, the whole file is rejected before any row is processed, with a structured error
naming the unrecognised columns and the expected alternatives. Individual row-level problems
(missing value in a required column, an unparseable price, a currency the tenant does not
recognise) go to `error_rows`, not a whole-file rejection.

### T017 — Catalogue import orchestrator

**Real finding, changes this task's actual shape**: research R6/tasks.md's "match products
against catalogue (call spec 004 matching pipeline)... create/update offers with explicit
currency" reads like a direct product-price write. It is not one. Checked directly:
`LandedCostService.compute_for_line_with_client` (the only path that produces an "offer" the
compare/basket-split screens read) requires a real `quotation_line_id` **and** a `match_decision`
already pointing at it — there is no lighter-weight "create an offer from a bare product+price"
entry point anywhere in the codebase. `MatchingService.quotation_matches()` — the actual spec-004
matching entry point — additionally **requires the parent quotation's `status` to already be
`'reviewed'`** (`raise ConflictError` otherwise, checked directly in `service.py`), and
`_create_automatic_decision` calls `LandedCostService.compute_for_line_with_client` itself once a
line auto-matches — the matching pipeline creates the landed cost, not a second step.

**Resolved design** (reuses the existing, tested pipeline exactly as it stands, rather than
duplicating matching/scoring/landed-cost logic a second time for catalogue rows):
1. Insert one `document` row for the catalogue file itself (`source_channel =
   'catalogue_import'` — a new enum value; genuinely a distinct provenance from upload/email/
   capture, not a mislabel of 'upload').
2. Insert **one `quotation`** for the whole import (not one per row) — `supplier_id` from the
   endpoint's path parameter (already known, unlike email/capture), `source = 'catalogue_import'`
   (also new, alongside the same `quotation_source_valid` CHECK widening), and — the load-bearing
   choice — **`status = 'reviewed'`, `reviewed_by` = the importing member, `reviewed_at = now()`
   at creation**, not `'pending'`. This is not a shortcut around Constitution Principle III: the
   owner/buyer submitting a bulk supplier price list *is* the human vouching for its contents,
   exactly as a reviewer vouches for extracted quotation data before matching runs on it — and
   it is the only way to reach `quotation_matches()` at all, since that function refuses anything
   not already `'reviewed'`.
3. Insert one `quotation_line` per valid parsed row — `line_number` (1-based), `original_text` =
   the row's `product_name` value (what the deterministic alias matcher and the embedding
   fallback both key on), `quantity` = `minimum_order_quantity` if mapped else `1`,
   `unit_price_amount`/`unit_price_currency` from the row. No `field_extraction` rows are needed
   (checked: `_line_field`'s GTIN/supplier-code lookup falls through cleanly to `original_text`-
   only matching when no extracted fields exist for a line).
4. Call `MatchingService().quotation_matches(bearer_token=<the request's real bearer token>,
   member=member, quotation_id=quotation_id)` — **synchronously, inside the API request** (see
   T018 below for why), not via `ingestion_jobs`/a worker. This one call does the rest: for each
   line it runs the deterministic matcher, then embedding similarity, auto-creates a
   `match_decision` + `landed_cost` for a clear match, or opens a `match_task` (the existing
   review queue) otherwise — which *is* R6's "flag unmatched products as pending_review," reusing
   the review surface spec 003/004 already built rather than inventing a parallel one.
5. Insert the `catalogue_imports` row with the real outcome counts (`total_rows`,
   `imported_rows` = lines that got an auto-accepted `match_decision`, `skipped_rows` = rows the
   parser itself dropped as duplicates within the file, `error_rows` = parser-level row errors,
   `error_details`, `column_mapping`). Status `'completed'` (or `'failed'` if the whole import
   could not proceed, e.g. required columns unmappable).
6. Audit `catalogue_import_started` at the top and `catalogue_import_completed` /
   `catalogue_import_failed` at the end.

**Why synchronous, not `ingestion_jobs` (which already declares a `'catalogue_import'`
`job_type` value from Wave 1)**: `quotation_matches()` and everything under it authenticates via
`authenticated_client(settings, bearer_token)` — the older Supabase-postgrest-client pattern this
codebase's matching/landed-cost modules use, not the raw-psycopg `_authenticated_db` pattern
Wave 2's ingestion code uses. A background worker has no live bearer token to hand it, and
reaching into `MatchingService`'s private methods to bypass that (to run matching under a
service-role connection instead) would fork and duplicate tested logic rather than reuse it. The
request handler already holds a real, valid bearer token for the calling owner/buyer, so running
synchronously there is the option that reuses the existing pipeline exactly as built. SC-003 (R6:
1,000 rows within 30 seconds) is comfortably inside a normal HTTP request budget, so this is not
a performance compromise. `ingestion_jobs.job_type = 'catalogue_import'` is left declared but
unused by this implementation — flagged here rather than silently ignored, in case a later wave
wants to revisit async processing for very large files.

### T018 — Catalogue import endpoint

`POST /api/v1/suppliers/{supplier_id}/catalogue-import`, multipart/form-data, CSV or XLSX,
≤25 MB (R8). Owner/buyer role (matching T017's `catalogue_imports_owner_buyer_insert` RLS
policy). Validates the named supplier belongs to the caller's tenant before anything else (404,
not 403, on a cross-tenant supplier id). Stores the raw file to `quotation-documents` (reusing
the storage-path convention, not a new bucket), calls T017's orchestrator synchronously, and
returns the `catalogue_imports` row (import summary: imported/skipped/error counts, error
details) directly as the response — not a job id to poll, since there is no async job. Rate-
limited via a new dedicated `RATE_LIMIT_CATALOGUE_IMPORT` setting.

## 3. Migration for this wave

One new forward-only migration, `20260917000009_capture_catalogue_source_and_mime.sql`:
- Widen `document_source_channel` with `'catalogue_import'`.
- Widen `document.mime_type`'s CHECK (currently `document_mime_type_check` after Wave 2's own
  edit) to add `image/heic` (R8, capture) and confirm `application/vnd.ms-excel`/xlsx/csv are
  already present for catalogue files (they are, from the original 20260819000018 migration).
- Widen `quotation_source_valid`'s CHECK to add `'catalogue_import'`.

Verified against a disposable Postgres before landing, same discipline as every prior migration
this session has written.

## 4. Review protocol

Unchanged from every prior wave: never trust a self-report, re-run gates independently. For this
wave specifically:
1. Confirm `quotation_matches()` really does refuse a non-`'reviewed'` quotation (regression-
   proof the load-bearing assumption behind T017's design, not just assert it).
2. Confirm a catalogue row that already matches an existing alias auto-creates a `landed_cost`
   row with the row's own currency, not a hallucinated default.
3. Confirm an ambiguous/unmatched row opens a real `match_task`, and that the existing match-
   resolution queue (spec 004's own screen) can act on it — this wave does not add a second
   review surface.
4. Cross-tenant: a catalogue-import request naming another tenant's `supplier_id` resolves 404.
5. Full backend suite green (1031+ passed, only the 2 known pre-existing failures) before this
   wave is considered done.

## 5. What comes after

Wave 4 (T019–T021: ingestion email-log listing, catalogue-import history, dashboard stats — all
Backend lane, all read-only) is next per `plan.md`. Wave 5 is the first wave with real Agy/
frontend work (T022–T029) — the first point in this feature where "dispatch" means delegating to
another lane rather than Claude doing every task in-house.

## 6. Cautions

- Do not let T017's per-row matching accidentally trust unverified data: every field on a
  synthesized `quotation_line` must come from the parsed catalogue row, never a default that
  could silently misprice something (e.g. no default currency — a row with no resolvable
  currency is a row-level error, not a fallback to the tenant's default currency).
- `image/heic` is real-world common for phone photos (R8) but `python-magic`/libmagic's HEIC
  detection can be inconsistent across libmagic versions — verify the actual sniffed MIME string
  for a real HEIC sample before trusting the content-type-mismatch check on capture uploads.
- Keep `ingestion_job_type = 'catalogue_import'` and `'capture_ingest'` values in mind as
  currently-unused-by-this-implementation, not remove them — a later wave may still want them.
