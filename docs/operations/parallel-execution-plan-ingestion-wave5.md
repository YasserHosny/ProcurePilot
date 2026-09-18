# ProcurePilot — Ingestion Wave 5 Execution Plan (Frontend)

**Written**: 2026-09-17, following Wave 4's completion and merge onto `013-automated-ingestion`
(commit `ed04a82`).

**Target feature**: `013-automated-ingestion` (R3.0)

**Scope**: `specs/013-automated-ingestion/tasks.md` Phase 5 (T022–T027) + Phase 6 (T028–T029) —
`plan.md`'s own "Wave 5 — Frontend", entirely the Frontend (Agy) lane. This is the first wave in
this feature with real frontend/Agy work; Waves 1–4 were all backend, done in-house or reviewed
in-house after Agy dispatch.

**Mode**: Dispatched to Agy across three sequential phases (not all seven tasks at once — see §4
for why), each task in its own real git clone (`~/agy-clones/`, never a worktree).

---

## 0. Starting point

Waves 1–4 are complete and merged: schema (T001–T007), email ingestion backend (T008–T014),
capture + catalogue import backend (T015–T018), and listing/stats APIs (T019–T021). Nine real
backend endpoints exist and are tested:

| Endpoint | Backend task |
|---|---|
| `GET/PUT /tenants/email-config`, `POST /tenants/email-config/{enable,disable}` | T013 |
| `POST /capture` | T015 |
| `POST /suppliers/{supplier_id}/catalogue-import` | T018 |
| `GET /ingestion/emails` | T019 |
| `GET /suppliers/{supplier_id}/catalogue-imports` | T020 |
| `GET /ingestion/stats` | T021 |

This wave builds the Angular UI against these nine endpoints. No backend changes in this wave.

## 1. Non-negotiables

Every user-facing string comes from `packages/i18n` (en + ar) — no hardcoded copy, checked by
grepping each new component's `.html` for bare text outside a `{{ '...' | translate }}` or
`[attr]="'...' | translate"` binding. RTL: use CSS logical properties (`margin-inline-start`, not
`margin-left`) in every new `.scss` file — test both directions before calling a component done.
The `*appRole` directive (`core/auth/role.directive.ts`) is a **display convenience only**, not a
security control — the server already enforces role checks (T013's owner-only mutations, T015/
T018's owner+buyer writes); never treat hiding a button as sufficient authorization anywhere in
this wave. Tenancy is resolved server-side from every request's JWT already — nothing in this
wave needs to know or pass a tenant id.

## 2. Real findings that reshape tasks.md's literal file list

Two things tasks.md's one-line bullets get wrong versus the actual codebase, found by reading the
real frontend before writing this plan (not assumed from the task list):

1. **T027's named file, `apps/web/src/app/features/ingestion/ingestion.routes.ts`, does not
   match this codebase's routing convention.** Every feature (`reports`, `savings`, `requests`,
   `matching`, ...) registers its routes directly as lazy `loadComponent` entries inside the one
   central `apps/web/src/app/app.routes.ts` — there are no per-feature `.routes.ts` files
   anywhere in the tree (confirmed: `find . -iname "*.routes.ts"` returns only `app.routes.ts`
   itself). T027 adds its five routes to `app.routes.ts`, matching every other feature, not a new
   file.
2. **Navigation is hub-and-spoke, not one sidenav entry per component.** `reports-center` has
   exactly one top-level sidenav entry (`/reports`); `schedule-form` and `digest-settings` are
   sub-pages reached by links *inside* `reports-center`, with no sidenav entries of their own.
   This wave follows the identical pattern rather than adding five new sidenav items: **one**
   sidenav entry, "Ingestion" → `/ingestion` (T026's dashboard), and T022/T023/T024/T025 are
   sub-routes reached via cards/links from that dashboard. Full route list in §3.6.

A third finding, not a convention mismatch but a real scope gap worth flagging rather than
silently inventing a fix for: **T026's "recent activity list" bullet has no single backing
endpoint.** `GET /ingestion/stats` (T021) returns only aggregate counts, not an activity feed.
The only genuine "recent items" endpoint is T019's `GET /ingestion/emails` (tenant-wide,
naturally recent-first). Catalogue imports have no tenant-wide listing — T020's endpoint is
scoped per-supplier (`GET /suppliers/{id}/catalogue-imports`), so there is no way to show "5 most
recent catalogue imports across all suppliers" without a new backend endpoint, which is out of
this wave's scope. **Resolved scope**: the dashboard's recent-activity section shows the 5 most
recent rows from `GET /ingestion/emails` only; it does not attempt to include capture or
catalogue-import activity. Say so directly in the component (a code comment, not a fabricated
data source) rather than leaving a reviewer to wonder why captures/imports never appear there.

## 3. Task scope

### 3.1 T028 — i18n keys (en + ar)

Add one new top-level `ingestion` namespace to both `packages/i18n/en.json` and
`packages/i18n/ar.json`, nested the same way `digests`/`reports` already are (see those two
blocks for the exact structural convention — nested objects per sub-area, not flat dotted keys
inside the JSON itself). Cover every label, button, empty-state, and error message needed by
T022–T026 as specced below — email config (forwarding address, enable/disable, domain allowlist,
daily limit, copy-to-clipboard confirmation), email log (status labels for all six
`IngestionEmailStatus` values: received/processing/completed/failed/duplicate/rejected; filter
labels), capture (file picker, camera capture, supplier selector, upload progress, MIME/size
errors), catalogue import (file picker, supplier selector, progress, results summary, expandable
error row), dashboard (stat card labels, match-rate/extraction-rate labels, recent-activity
section, empty states), and a shared `ingestion.nav` key for the sidenav entry. Also add
`shell.navIngestion` if the sidenav label is sourced from the `shell` namespace instead (match
whichever convention `shell.navSavings`/`shell.navRequests` actually use — check before picking).
Arabic translations must be real Arabic, not machine-transliterated English — match the quality
bar of the existing `digests`/`reports` Arabic entries.

This task runs **first, alone** (see §4) so T022–T026 only ever *reference* existing keys via
`TranslatePipe`/`TranslateService`, never add new ones — avoiding five parallel sessions fighting
over the same two JSON files.

### 3.2 T029 — Ingestion API client

New file `apps/web/src/app/features/ingestion/ingestion-api.ts`, modeled directly on
`apps/web/src/app/features/reports/digest-settings/digests-api.ts`'s shape (`@Injectable({
providedIn: 'root' })`, `inject(HttpClient)`, `environment.apiBaseUrl`, typed request/response
interfaces, one method per endpoint returning `Observable<T>`). Cover all nine endpoints from
§0's table:

- `getEmailConfig(): Observable<TenantEmailConfig>` — `GET /tenants/email-config`
- `updateEmailConfig(payload): Observable<TenantEmailConfig>` — `PUT /tenants/email-config`
- `enableEmailConfig()` / `disableEmailConfig(): Observable<TenantEmailConfig>` — the two
  `POST /tenants/email-config/{enable,disable}`
- `listEmailLogs(params): Observable<IngestionEmailLogList>` — `GET /ingestion/emails` with
  `cursor`, `limit`, `status`, `from_domain`, `date_from`, `date_to` all optional query params
- `submitCapture(file: File, supplierId?: string, notes?: string): Observable<{quotation_id:
  string; status: string}>` — `POST /capture`, **multipart**: build a `FormData`, append `file`
  and the optional fields, `this.http.post(url, formData)` — Angular's `HttpClient` sets the
  multipart boundary itself from a `FormData` body; do not set a `Content-Type` header manually
  (this is not the presign-then-direct-storage-upload pattern `quotation-upload.component.ts`
  uses — capture/catalogue-import are plain multipart POSTs the server itself stores)
- `submitCatalogueImport(supplierId: string, file: File): Observable<CatalogueImportResult>` —
  `POST /suppliers/{supplierId}/catalogue-import`, same `FormData` approach
- `listCatalogueImports(supplierId: string, params): Observable<CatalogueImportSummaryList>` —
  `GET /suppliers/{supplierId}/catalogue-imports`
- `getStats(): Observable<IngestionStats>` — `GET /ingestion/stats`

Every interface field name and type must match the real Pydantic response models exactly (they
are reproduced in full in §3.3–§3.6 below for each consuming component — do not guess field
names). Reuse the existing `ApiError` interface (`core/api/models.ts`) for error typing; do not
redefine it. Do **not** duplicate the existing `ApiService.suppliers()` method (`core/api/
api.service.ts`) for supplier lookups — T024/T025's supplier picker injects the existing
`ApiService`, not a duplicate method on `IngestionApiService`.

This task runs in parallel with T028 (§4) — no shared files between them.

### 3.3 T022 — Email config settings component

Route `/ingestion/email-config`. Files under `apps/web/src/app/features/ingestion/email-config/`.
Fetches `TenantEmailConfig` on init (`{id, forwarding_address, enabled, domain_allowlist:
string[] | null, daily_limit, daily_count, daily_count_date, spf_dkim_required, created_at,
updated_at}`). Displays forwarding address with a copy-to-clipboard button (`navigator.clipboard.
writeText`, snackbar confirmation on success). Enable/disable toggle — **owner only**
(`*appRole="'owner'"`, matching T013's server-side `require_role(*OWNER)` on both endpoints) —
calls `enableEmailConfig()`/`disableEmailConfig()`. Domain allowlist editor: a simple add/remove
chip list, `PUT`s the full `domain_allowlist` array via `updateEmailConfig()` on each change.
Daily limit shown read-only (its own edit form is not requested by this task). Loading and error
states via signals, matching `digest-settings.component.ts`'s pattern exactly (`isLoading`
signal, `error` signal, `translate.instant(...)` for messages, `MatSnackBar` for mutation
feedback).

### 3.4 T023 — Ingestion email log viewer component

Route `/ingestion/email-log`. Files under `apps/web/src/app/features/ingestion/email-log/`.
Paginated table/list of `IngestionEmailLog` rows (`{id, message_id, from_address, from_domain,
subject, received_at, processed_at, status, error_message, attachment_count, quotation_id,
supplier_id, match_method, created_at}`) via `listEmailLogs()`, cursor-paginated ("load more" /
next-page button using `next_cursor`, matching `digests`'s own pagination UX if it has one, else
a simple "load more" button). Status badges: one distinct color/icon per `IngestionEmailStatus`
value (received/processing/completed/failed/duplicate/rejected) — six visually distinct states,
not just two. Supplier attribution: show the matched supplier when `supplier_id` is present (a
name lookup isn't available from this endpoint alone — display the id or, if time allows, use the
existing `ApiService.supplier(id)` lookup; don't block on this). `quotation_id` present → a
router link to `/quotations/:id` (that route already exists). Date range filter (two date
inputs, wired to `date_from`/`date_to`), status filter (a select), from_domain filter (a text
input) — all optional, cleared together by a "reset filters" action.

### 3.5 T024 — Capture upload component

Route `/ingestion/capture`. Files under `apps/web/src/app/features/ingestion/capture/`.
`WRITE_ROLES` only (owner/buyer) — gate the whole route with `roleGuard('owner', 'buyer')` in
`app.routes.ts` (T015's endpoint requires it server-side regardless; gate the route too so a
viewer role doesn't reach a form that will just 403). File picker via `<input type="file"
accept="application/pdf,image/jpeg,image/png,image/heic">`; a second, mobile-oriented affordance
per tasks.md, `<input type="file" accept="image/*" capture="camera">`, for direct camera capture.
Client-side pre-checks before submit (fail fast, matching `quotation-upload.component.ts`'s own
`validateAndSetFile` pattern): reject empty files and files over 10 MB (`CAPTURE_MAX_BYTES`)
with a translated error before ever calling the API — the server re-validates regardless
(constitution: never trust the client), this is only to avoid an avoidable round trip. Optional
supplier selector: inject the existing `ApiService`, call `.suppliers()`, a simple autocomplete
or select. Optional free-text notes field. Upload progress indicator while the `POST /capture`
call is in flight (a spinner is sufficient — `HttpClient` reports upload progress only with
`reportProgress`/`observe: 'events'`, which `submitCapture()` doesn't need to add just for this).
On success, show the returned `quotation_id` with a link to `/quotations/:id` and a "capture
another" reset action.

### 3.6 T025 — Catalogue import component

Route `/ingestion/catalogue-import`. Files under
`apps/web/src/app/features/ingestion/catalogue-import/`. `WRITE_ROLES` only, same role-guard
reasoning as T024. Supplier selector is **required** here (the endpoint is
`/suppliers/{supplier_id}/catalogue-import` — there is no supplier-less variant), so block the
file picker until a supplier is chosen. File picker restricted to `.csv`/`.xlsx`
(`accept=".csv,.xlsx"`), client-side pre-check for empty file and >25 MB
(`CATALOGUE_IMPORT_MAX_BYTES`) before submit, same fail-fast reasoning as T024. Upload +
processing progress (this call can take longer than capture's — it runs matching synchronously
server-side per T017 — show an indeterminate progress state, not a fake determinate bar).
Results display after the call returns: `{id, supplier_id, status, total_rows, imported_rows,
skipped_rows, error_rows, error_details}` — show the four counts prominently, and an expandable
list of `error_details` (`{row, column, error}` per entry) for `error_rows > 0`. A link to
`/ingestion/catalogue-import-history?supplier_id=...` if T023-style history browsing is wanted
here — optional, not required by tasks.md's own bullet list; skip it if it doesn't fit cleanly
rather than inventing a new route.

### 3.7 T026 — Ingestion dashboard component

Route `/ingestion` (the hub — see §2). Files under
`apps/web/src/app/features/ingestion/dashboard/`. Fetches `IngestionStats` (`{
emails_received_today, emails_received_week, emails_received_month, capture_uploads_total,
catalogue_imports_total, supplier_match_rate, extraction_success_rate}`) via `getStats()`. Stat
cards for emails-today, capture uploads, catalogue imports (matching tasks.md's own list — the
week/month figures can appear as secondary text on the same card rather than needing three
separate cards, reviewer's judgment call, just be consistent). Match-rate gauge:
`supplier_match_rate` and `extraction_success_rate` are both `0.0`–`1.0` floats — render as a
percentage (a simple radial/linear gauge component is fine; do not pull in a new charting
library for this — Angular Material has no built-in gauge, a styled `<mat-progress-bar
mode="determinate">` with a percentage label is an acceptable, dependency-free substitute).
Recent activity list: per §2's finding, the 5 most recent rows from `listEmailLogs({limit: 5})`
only — label the section honestly (e.g. "Recent emails", not an unqualified "Recent activity"
that implies captures/imports are included when they are not). Cards/links to the four sub-pages
(`/ingestion/email-config`, `/ingestion/email-log`, `/ingestion/capture`,
`/ingestion/catalogue-import`) — this is the hub, so it is the only component responsible for
surfacing those four as navigable options.

### 3.8 T027 — Routing + navigation

No new file (§2). Add five routes to the guarded-shell `children` array in
`apps/web/src/app/app.routes.ts`, alongside the existing `reports`/`savings`/etc. entries:
`/ingestion` (T026, no extra role guard — any authenticated member can view the dashboard, same
as `/reports`), `/ingestion/email-config` (T022, no extra guard — the component itself gates the
mutating toggle to owner via `*appRole`, matching how `/reports/digest-settings` has no route-
level guard either), `/ingestion/email-log` (T023, no guard), `/ingestion/capture` (T024,
`canActivate: [roleGuard('owner', 'buyer')]`, matching `/quotations/upload`'s own precedent),
`/ingestion/catalogue-import` (T025, same `roleGuard('owner', 'buyer')`). One new sidenav entry
in `apps/web/src/app/layout/shell/shell.component.html`, following the exact `<a mat-list-item
routerLink=... routerLinkActive="active" class="nav-item"><mat-icon>...</mat-icon><span
class="nav-label">{{ '...' | translate }}</span></a>` block shape already used for `/reports`
— pick an appropriate Material icon (`mail` or `inbox` is a reasonable fit, `reports` already
uses `assessment`, `savings` uses `savings` — do not reuse an icon another nav entry already
uses). This is the **only** task that touches `app.routes.ts` or `shell.component.html` in this
wave — runs alone, after all five components from Phase B are merged (§4), specifically to avoid
five parallel sessions all trying to edit the same two files.

## 4. Delegation mechanics — three sequential phases

Unlike Wave 4 (three independent tasks dispatched all at once), this wave has a real dependency
graph tasks.md's own table states explicitly (T022–T026 all depend on T029; T027 depends on
T022–T026) — dispatching all seven at once would guarantee five-way conflicts on
`packages/i18n/*.json`, `ingestion-api.ts`, `app.routes.ts`, and `shell.component.html`
simultaneously. Instead:

**Phase A (parallel, 2 Agy sessions)**: T028 (i18n keys) and T029 (API client) — no shared files
between them, dispatch together, merge both, re-run affected tests before Phase B starts.

**Phase B (parallel, 5 Agy sessions)**: T022, T023, T024, T025, T026 — each a **self-contained
new directory** under `features/ingestion/` with zero file overlap between them (they only
*read* T028's already-merged i18n keys and T029's already-merged API client — neither is a
Phase B session's own file to edit). Genuinely safe to run in parallel and merge in any order.
Each session's brief points at the exact §3.x subsection above plus the concrete existing-
component references named in it (`digest-settings.component.ts`, `quotation-upload.component.ts`,
`reports-center.component.spec.ts`) so a fresh Agy session isn't inventing conventions from
nothing.

**Phase C (solo, 1 Agy session)**: T027 — only after all five Phase B components are merged, so
it can write real `loadComponent` imports pointing at files that actually exist, and add exactly
one sidenav entry without conflicting with anything else touching those two shared files.

Every session, same discipline as Wave 4: real clone under `~/agy-clones/`, own branch off
`013-automated-ingestion` at the commit this plan doc lands on, runs `pnpm --filter web
test:unit` (`ng test --watch=false --browsers=ChromeHeadless`) and `pnpm --filter web lint`
(`ng lint`) before committing, commits locally, does not push. **I re-run both myself** against
the merged state after each phase before starting the next one — never trust a self-report,
same rule as every prior wave.

## 5. Review protocol

1. Grep every new `.html` file for text nodes that aren't behind a `| translate` — a missed
   hardcoded string is the single most likely miss across five parallel sessions each moving
   fast.
2. Confirm `*appRole` gates match the *server's* actual role requirements exactly (owner-only on
   email-config enable/disable per T013; owner+buyer on capture/catalogue-import per T015/T018)
   — a client gate looser than the server is merely a bad UX (a disabled-looking action that
   still 403s), but a gate that's *wrong in the other direction* (hiding something a role
   actually can do) is a real regression worth catching here.
3. Confirm the two multipart upload methods in `ingestion-api.ts` actually send `FormData` (not
   JSON with a base64 file, which would blow past request size limits and doesn't match the
   backend's `await request.form()` parsing).
4. Confirm T027's five new routes and the one sidenav entry don't collide with any existing path
   or already-used Material icon.
5. `pnpm --filter web test:unit` and `pnpm --filter web lint` green across the whole `apps/web`
   tree (not just the new files) after each phase merges — a Phase B session editing only its own
   new directory can still break the global test run if, e.g., it introduces a duplicate
   component selector.
6. Manually smoke-test the golden path in a real browser after Phase C merges (per this session's
   own standing UI-testing discipline) — start the dev server, walk through: dashboard loads →
   email-config toggle → capture upload → catalogue import → email log filtering. This is the
   first UI this feature has ever had; nothing here has been exercised as a human would use it
   yet.

## 6. What comes after

Phase 7 (Testing & Quality) is next per `tasks.md` — E2E tests for the ingestion flows, an a11y
pass (axe-core, zero violations, matching this session's own precedent from Wave 18 of
012-reporting-hardening), and the stage-gate docs. Not scoped in detail here; revisit
`specs/013-automated-ingestion/tasks.md`'s remaining tasks once Wave 5 is merged and smoke-tested.

## 7. Cautions

- Angular's `HttpClient` will NOT auto-set a `Content-Type: multipart/form-data` header
  correctly if a session manually sets one on a `FormData` body — the boundary parameter has to
  come from the browser, not be typed by hand. Leave the header alone entirely.
- The `IngestionEmailStatus`/`SupplierMatchMethod` string literal unions must be copied from the
  backend's real Pydantic `Literal[...]` values (`schemas.py`), not re-derived from tasks.md's
  prose, which doesn't enumerate them.
- Do not add a "cancel" action to the catalogue-import upload once submitted — per T017, the
  server call is synchronous and does the matching pipeline inline; there is no job to cancel,
  and offering a "cancel" button that can't actually stop anything would be misleading.
- `daily_limit`/`daily_count` on `TenantEmailConfig` are read-only display data per T022's own
  scope (no "edit daily limit" form is requested) — don't add a mutation path tasks.md didn't ask
  for.
