# ProcurePilot — Test Strategy & Test Plan

> How ProcurePilot will be tested across the pyramid, with special attention to AI accuracy and financial correctness.

---

## 1. Strategy

| Layer | Tool | Responsibility | When |
|---|---|---|---|
| Unit | pytest 8.3 + pytest-asyncio (backend, Python 3.12), Karma 6.4 / Jasmine 5.6 (frontend) | Functions, services, components, validators | Every PR |
| Integration | pytest + httpx TestClient | API endpoints, DB queries, auth middleware | Every PR |
| Tenant isolation | pytest (`pnpm test:isolation` = `apps/api/tests/integration/test_tenant_isolation.py`) | Forced RLS, cross-tenant 404 | Every PR (`Tenant isolation` job) |
| E2E | Playwright ^1.60 | Critical user journeys on web | Every PR, six shards (`docs/operations/ci-pipeline.md`) |
| Mobile E2E | `flutter test` (`apps/mobile/test/`, including `integration/`) | Request, approval, delivery flows | Before store release (not in CI) |
| AI eval | Custom harness + benchmark datasets | Extraction and matching accuracy | Every model/prompt change |
| Performance | Locust / k6 | Latency, throughput, concurrent extraction | Before G1 and G2 |
| Security | OWASP ZAP + penetration test | OWASP Top 10, auth, RLS | P1 ongoing + third-party at end P2 |
| Accessibility | axe-core (`@axe-core/playwright` ^4.14; `pnpm test:a11y` runs the `@a11y`-tagged Playwright tests) / Lighthouse | WCAG 2.1 AA | Every PR that touches the web app, and every push to `main` |

## 2. Test Environments

- **Local:** `docker compose up` services against the hosted Supabase (`docs/operations/local-dev.md`).
  `docker-compose.yml` has no Supabase or Postgres service; a local Supabase stack, when a test
  needs one (as the E2E suite does), comes from `supabase start`.
- **CI:** ephemeral containers spun up by GitHub Actions, each E2E shard with its own Supabase CLI
  stack, Redis, API, extraction worker and web app.
- **Staging/demo:** Bunny Magic Containers at `https://procurepilot.iron-sys.com` (API under
  `/api/v1`), with the hosted demo tenants (`docs/gtm/demo-tenant/README.md`).
- **Production:** not live yet; the pilot app is planned at `pilot.iron-sys.com`
  (`docs/operations/pilot-environment-plan.md`). Feature flags will protect new capabilities.

## 3. Unit / Integration Test Targets

### Backend
- Pydantic schema validation for every request/response model.
- Tenant isolation: queries fail without `tenant_id` and pass with RLS.
- Auth middleware rejects expired/revoked tokens.
- Landed-cost engine: deterministic outputs per rule version.
- Matching pipeline: alias hits, GTIN hits, lexical/semantic candidates, confidence thresholds.

### Frontend
- Form validation with Zod schemas.
- Component rendering for review queue, compare grid, savings ledger.
- HTTP services retry and error handling.

### Mobile
- Offline draft persistence and sync.
- Barcode scan to product lookup.
- Approval action with idempotency.

## 4. AI Evaluation Plan

### Extraction
- **Dataset:** 300+ labelled quotation line items, versioned per release.
- **Metrics:** field-level accuracy, document-level exact match, arithmetic-validation pass rate, cost per document.
- **Gate:** ≥ 90% field-level accuracy on priority fields; no regression versus previous baseline.

### Matching
- **Dataset:** 500+ labelled product-match pairs, including hard negatives.
- **Metrics:** precision at auto-accept, recall, review-band size, alias hit rate.
- **Gate:** ≥ 92% precision at auto-accept; review-band ≤ 8%.

### Calibration
- Expected calibration error (ECE) on confidence scores.
- Confidence must match observed accuracy within 5% per bucket.
- **Status (2026-11-19):** match-score calibration is not feasible yet. Hosted has far fewer than
  the 500+ labelled match decisions the matching gate needs, and `ml/evals/product_matching/`
  reports that rather than a calibrated score. Keep it that way until the benchmark exists. The
  extraction harness (`ml/evals/quotation_extraction/`) likewise has no real held-out benchmark yet.

## 5. E2E Scenarios

### Web
1. Self-onboard → upload quotation → review extraction → confirm matches → see Smart Compare → record purchase → verify saving in ledger.
2. CSV import catalogue → upload quotation → extraction uses catalogue aliases.
3. Invite team member → assign role → verify RBAC limits.

### Mobile
1. Branch manager creates request → approver receives push → approves → buyer records order → branch confirms delivery.
   *(2026-11-19: the "receives push" step cannot pass yet; server-side push delivery is a stub
   with no FCM/APNs credentials, so every send is recorded as not delivered. Runbook §3.5.)*
2. Offline draft → sync on reconnect → no duplicate request.

## 6. Performance Targets

- Dashboard FCP < 1.5 s.
- Compare grid recalculation < 150 ms.
- Extraction p95 < 45 s per document.
- 99th percentile API latency < 500 ms for read endpoints.

## 7. Responsibilities

- **Engineering lead:** unit/integration/E2E infrastructure.
- **AI lead:** eval datasets, harness, and gates.
- **Product designer:** accessibility and UX acceptance.
- **Founder:** prioritises E2E scenarios based on pilot feedback.

## 8. Responsive & RTL Testing

All UI changes must be verified at three viewport widths:

| Tier | Width | Key checks |
|---|---|---|
| Mobile | < 600px | Single-column layout, no horizontal scrollbar, reduced padding |
| Tablet | 600–959px | Intermediate layouts, flex-wrap correct |
| Desktop | ≥ 960px | Multi-column grids, side-by-side panels |

RTL verification: switch locale to Arabic and confirm:
- Logical properties flip correctly (margins, paddings).
- Text alignment reverses.
- Navigation and action buttons reorder.
- No text clipping or overflow.

## 9. Production Smoke Testing

After every deployment, run the end-to-end flow on the live production URL:

1. Sign in or sign up.
2. Upload a real document (not stub mode) → verify extraction provenance shows the expected
   AI provider (not `stub-provider-v1`).
3. Review and confirm the quotation.
4. Verify the review queue, Smart Compare, and savings flows.
5. Resize the browser to mobile width and verify responsive layout.

This catches issues that local tests cannot: misconfigured container env vars (e.g.
`EXTRACTION_PROVIDER_MODE` still set to `stub`), cross-app Redis connectivity failures,
and GHCR image pull issues.

## 10. R2.5 Hardening & Release Gates

Release R2.5 (`012-reporting-hardening`) introduces formal performance, accessibility, security, and tenant-isolation gates before the G2 stage gate:

### 10.1 Compare-Grid Timing Regression & CI-Noise Strategy
- **Gate:** Compare-grid recalculation under 150 ms (constitution Principle V, FR-025, SC-006).
- **CI-Noise Mitigation:** To eliminate false positives from runner load spikes, Playwright test `compare-grid-performance.spec.ts` computes the median of 7 consecutive quantity recalculation samples rendered entirely inside the browser DOM via `performance.now()`.
- **Target:** Median recalculation time < 150 ms for a 25-offer comparison grid.

### 10.2 Initial Bundle & Component Style Budgets
- **Initial Bundle Budget:** Raw initial bundle must remain ≤ 500 kB (Wave 15 baseline was 588 kB; lazy routes + lazy Sentry SDK achieved 457.79 kB).
- **Component Style Budget:** Strict ≤ 4 kB SCSS limit per component stylesheet (`styleUrl` single, no evasion via `styleUrls` array). Monitored via Angular CLI build budgets in `angular.json`.

### 10.3 Accessibility (axe-core) Mandatory Surfaces
- **Automated Gate (`pnpm test:a11y`):** Zero WCAG 2.1 AA violations across both English (LTR) and Arabic (RTL) for all primary user journeys:
  - Sign-in / Sign-up
  - Dashboard & Home
  - Product Catalogue & Supplier management
  - Quotation Upload & Review
  - Smart Compare & Basket Split
  - Alerts Inbox & Savings Ledger
  - Reports Center (`/reports`) & Digest Settings (`/reports/digest-settings`)
- **Keyboard Navigation:** Full bidirectional Tab/Shift+Tab navigation traversable through all interactive elements on data tables, banner toolbars, and forms.
- **Print Coverage:** Reports Center includes `@media print` coverage ensuring artifact tables print without UI chrome.

### 10.4 Dependency Audit CI Gate
- **Automated Check:** `.github/workflows/ci.yml` runs `pip-audit` across all Python environments (`apps/api`, worker services) and `pnpm audit --prod` across web workspaces.
- **Enforcement:** Blocks CI on any unallowlisted High or Critical vulnerability.
- **Allowlist (`docs/operations/dependency-audit-allowlist.txt`):** Every accepted finding must carry an assigned owner and explicit rationale (e.g. upstream framework constraint, non-exploitable transitive dependency).

### 10.5 Rate Limiting & Resource Caps
- **Endpoint Limits:** Export creation, report schedule mutations, and digest subscription mutations enforce tenant+membership claim rate limits with client IP fallbacks (FR-020).
- **Standing Caps:** Active schedules and digest subscriptions enforce strict per-member cardinality limits (422 structured error) preventing unbounded daemon job accumulation.

### 10.6 Security Review & Penetration Test Readiness
- **Internal Security Review (`docs/quality/r2.5-security-review-record.md`):** Evidence-based verification covering RLS policy shapes (`ENABLE` + `FORCE`), worker tenant re-derivation from DB state, reader-function authorization pins, storage bucket policies (`exports`), signed-URL max TTLs, and append-only audit enforcement.
- **Third-Party Penetration Test Scope (`docs/operations/pentest-scope.md`):** Formal procurement-ready scope document establishing in-scope boundaries, data classification, and test environments for third-party adversarial testing at the G2 gate.

### 10.7 Tenancy & Isolation Extension
- **Automated Isolation Tests (`pnpm test:isolation`):** Verified RLS policies across `report_schedule`, `digest_subscription`, `export_job`, and Supabase Storage `exports` bucket.
- **Cross-Tenant Guarantees:** Any cross-tenant or unauthorized-branch access resolves to HTTP 404 (Not Found), never HTTP 403 (Forbidden), avoiding existence leakage.

## 11. R3.0 Automated Ingestion Hardening & Verification Gates

Release R3.0 (`013-automated-ingestion`) introduces multi-channel ingestion (inbound email forwarding, document capture, and supplier catalogue import) backed by asynchronous workers. Verification gates enforce database-level concurrency safety, strict deduplication, anti-abuse rate limits, and failure recovery:

### 11.1 Worker Reliability & Concurrency Claims
- **Claim Pattern (`FOR UPDATE SKIP LOCKED`):** The email ingestion background daemon (`apps/api/src/procurepilot_api/workers/email_ingestion_worker.py`) polls `ingestion_jobs` for pending `email_ingest` jobs using `FOR UPDATE SKIP LOCKED`. Claimed rows are locked and transitioned to `status = 'processing'` with `locked_by = 'email_ingestion_worker'`. Following established worker security discipline (export and digest workers), `tenant_id` is re-derived strictly from the claimed database row, never trusted from the job payload.
- **Exclusivity Proof:** Integration test `test_concurrency_skip_locked_prevents_duplicate_claims` in `apps/api/tests/integration/test_email_ingestion_worker.py` proves claim exclusivity using two real, overlapping `psycopg` transactions (`conn_a` and `conn_b`). While Connection A holds the claim lock uncommitted, Connection B executes the exact same query; Connection B skips the locked row and returns an empty claim list (`claimed_b == []`), verifying that concurrent workers cannot double-claim or race on pending jobs.
- **Retry & Terminal Failure:** When processing raises an unhandled exception, `_mark_job_failed()` increments `attempts`. If `new_attempts < max_attempts`, the job reverts to `pending` with `locked_by = None` and `last_error` recorded. When `attempts >= max_attempts`, the job transitions to terminal `failed` with `completed_at = now()`.
- **Failure Proof:** Integration test `test_failure_retry_and_terminal_failed_status` in `apps/api/tests/integration/test_email_ingestion_worker.py` verifies this lifecycle with `max_attempts = 3`. Attempts 1 and 2 return the job to `pending`, attempt 3 transitions the job to terminal `failed`, and a subsequent worker tick ignores the failed job without retrying (`claimed == 0`).

### 11.2 Inbound Email Deduplication
- **Database Constraint:** `supabase/migrations/20260917000001_ingestion_email_log.sql` defines `constraint ingestion_email_log_tenant_message_id_key unique (tenant_id, message_id)`. This enforces RFC 5322 Message-ID uniqueness scoped per tenant, preventing replayed or redelivered emails from triggering duplicate ingestion pipelines.
- **Deduplication Proof:** Integration test `test_duplicate_message_id_is_skipped_without_creating_a_second_quotation` in `apps/api/tests/integration/test_ingestion_orchestrator.py` processes an email with an identical `message_id` twice. The first call succeeds (`status: "completed"`), while the second immediately returns `status: "duplicate"` with the message ID. The database confirms that `ingestion_email_log` retains exactly 1 record and no second quotation or extraction job is created.

### 11.3 Rate Limiting & Quota Controls
- **Tenant Daily Email Limit:** Each tenant's ingestion volume is capped via `tenant_email_config.daily_limit` against rolling usage `daily_count`.
- **Quota Rejection Proof:** Integration test `test_daily_limit_reached_refuses_without_queueing` in `apps/api/tests/integration/test_ingestion_webhook.py` verifies that when `daily_count >= daily_limit`, inbound webhook calls return HTTP `202 Accepted` (complying with R10 anti-probing and no-existence-leak requirements) but refuse processing without enqueuing any job (`count(*) from ingestion_jobs` is 0).
- **Endpoint Limits (`apps/api/src/procurepilot_api/config.py`):** Ingestion mutation endpoints enforce verified tenant+membership claim rate limits, with IP fallbacks:
  - Ingestion configuration mutations: `rate_limit_ingestion_config_mutation` (`RATE_LIMIT_INGESTION_CONFIG_MUTATION`, default `30/minute`).
  - Inbound email webhook: `rate_limit_inbound_email_webhook` (`RATE_LIMIT_INBOUND_EMAIL_WEBHOOK`, default `60/minute`).
  - Document capture uploads: `rate_limit_capture_upload` (`RATE_LIMIT_CAPTURE_UPLOAD`, default `30/minute`).
  - Catalogue imports: `rate_limit_catalogue_import` (`RATE_LIMIT_CATALOGUE_IMPORT`, default `10/minute`).

### 11.4 Known Coverage Gap: Catalogue Re-Import Matching Pipeline Idempotency
- **Sanity Proof:** Integration test `test_importing_the_same_file_twice_creates_two_independent_quotations` in `apps/api/tests/integration/test_catalogue_import.py` verifies that `catalogue_import`'s own repeat-call behavior is sane. Importing the identical CSV file twice creates two distinct quotations (`first["id"] != second["id"]`), two separate `catalogue_imports` audit records, and triggers matching invocation for each quotation.
- **Coverage Gap:** In `test_catalogue_import.py`, `MatchingService.quotation_matches()` is stubbed via the `_fake_matching` fixture because the full matching pipeline relies on the legacy PostgREST client architecture rather than the disposable PostgreSQL test harness (as documented in `_fake_matching`'s fixture docstring). Consequently, whether the real `MatchingService` and landed-cost pipeline behaves idempotently when processing duplicate catalogue imports remains untested and is flagged as an open question for a future test wave.

## 12. End-to-End Conventions (added 2026-10-18)

These come from flaky or misleading E2E runs fixed in October 2026 (PRs #77, #78, #85, #93). CI's shape —
docs-only skip, six shards, accessibility split — is in `docs/operations/ci-pipeline.md`.

- **Run one spec** with `pnpm --filter web exec playwright test <spec>`. `pnpm --filter web test:e2e -- <spec>`
  silently runs the whole suite.
- **Selects with async options:** open a `mat-select` with `openAsyncSelect` from
  `apps/web/tests/e2e/support/select.ts`. Material ignores a click while the select has no options, so a plain
  `click()` can do nothing; the helper retries until the select's own `aria-expanded` is `true` and an option is
  visible.
- **Language:** a user's language is stored on the server and follows them into later tests. An `ensureEnglish`
  helper must always choose English and then assert `html[dir="ltr"]` and `html[lang="en"]` (as in
  `approval-queue.spec.ts`). Checking `dir` first and skipping the switch races the app applying the saved
  language. Eight specs still use the older conditional check: `accounting`, `accounting-a11y`, `analyst-a11y`,
  `ingestion`, `organisation-a11y`, `pos`, `purchase-request-submission`, `requests-a11y`.
- **Dialogs and accessibility scans:** wait for the dialog's open animation to finish before running axe — a visible
  dialog can still be fading in, and colour contrast is then measured on half-faded colours (see
  `waitForDialogSettled` in `organisation-a11y.spec.ts`).
- **No fixed sleeps:** wait on a condition (`expect(...)`, `expect(async () => ...).toPass()`), not
  `waitForTimeout`.
- **Documentation screenshots** are regenerated by `.github/workflows/docs-screenshots.yml` and compared with
  `scripts/docs_screenshots_diff.py`: an image fails if more than 1% of its pixels differ in brightness by more than
  24 levels, if its size changed, or if it was added or removed. The flow that produces them must fail loudly
  rather than fall back to whatever data exists.
- **Hosted walkthrough:** passing suites are not enough for a user-facing release; walk it through on the hosted
  environment in English and Arabic (roadmap §6.3). The October 2026 demo build found 20 defects the suites had
  passed.

## 13. In-App Feedback (spec `025-user-feedback`)

Feedback is the one feature that deliberately crosses workspaces (platform operators, ADR-027), so its
tests are weighted towards the database boundary. Integration tests need `TEST_DATABASE_URL` pointing at
a Postgres with the spec 025 migrations applied and are skipped without it; storage, mail and, where
noted, the audit writer are in-memory fakes, while row-level security, the unique indexes and the
forward-only status trigger are always real.

### 13.1 API unit tests (`apps/api/tests/unit/`, no database)
- `test_feedback_validation.py`: files are judged by content (libmagic), never by name; count (422),
  size (413) and type (415) limits; audio-only WebM and MP4 recorder output accepted, the same
  containers with a video track refused. Fixtures from real Chrome, Safari and Firefox recordings are in
  `apps/api/tests/fixtures/feedback/` (see its `README.md`).
- `test_feedback_context.py`: page path from a same-origin `Referer` only; language from
  `Accept-Language`, falling back to the workspace default.
- `test_feedback_status_machine.py`: the API's forward-only pre-check and label rules (409
  `feedback.invalid_transition`).
- `test_feedback_storage.py`: tenant-prefixed object paths, signed URLs and deletes.
- `test_feedback_digest_renderer.py`: digest content in English and Arabic, no email address.
- `test_current_operator.py`: operator access needs the live `platform_operator` row; the token claim
  alone is not enough; non-operators get 404.
- `test_platform_operator_cli_parsing.py`: CLI arguments and email normalisation.

### 13.2 Contract tests (`apps/api/tests/contract/test_feedback_contract.py`)
The member and owner endpoints through the real app and router with the service mocked: status and
error codes, client-supplied workspace, user, role and demo values ignored, a second voice message
refused, `limit` capped at 100, the owner-only inbox answering 404 to other roles, and drift tests
comparing the live OpenAPI document with `specs/025-user-feedback/contracts/feedback.openapi.yaml`.
The `/platform/feedback` routes are covered over HTTP in `test_feedback_operator.py` (below), not here.

### 13.3 Integration tests (`apps/api/tests/integration/`)
- **`test_feedback_isolation.py` (schema-level isolation, the hard gate).** Runs as the real
  `authenticated` and `anon` roles with JWT claims: both tables have RLS enabled and forced; no
  cross-workspace read, insert, attach, update or delete; own-or-owner visibility; no member can change
  status, labels or any other column, or insert a forged row; a tenant cannot select `labels` and
  `feedback_operator_labels()` returns null to tenants; withdrawal only while `new`; operator reach and
  forward-only status; `status_changed_*` cannot be forged; a revoked operator has no access;
  `platform_operator` is unreachable by clients.
- `test_tenant_isolation.py` (`pnpm test:isolation`) includes `feedback_submission` and
  `feedback_attachment` in its forced-RLS set and workspace fixture.
- `test_feedback_operator.py`: what the database lets an operator do (read every workspace; change
  status and labels only, forward only; no other tenant table; nothing once revoked; digest functions
  touch the caller's row only; workspace names for operators only), then the HTTP routes (404 for
  non-operators on every route, one aggregate audit event per list, per-submission audit events,
  revocation on the next request).
- `test_feedback.py`: submit for every role with server-set context, cooldown, idempotent replay
  (including parallel requests with one key), all-or-nothing uploads, audio, withdrawal and the
  withdraw-versus-status-change race.
- `test_feedback_rbac.py` and `test_feedback_visibility.py`: who sees what through the service, the
  owner inbox, attachment URLs, no labels in any tenant payload, visibility after a member is removed.
- `test_feedback_audit_cross_tenant.py`: the T058 gate spike. The audit writer's server-side form can
  file an operator event under another workspace; a member session still cannot.
- `test_feedback_retention.py` and `test_feedback_worker.py`: 12-month purge with objects first, orphan
  sweep, and the operator digest (one per day, watermark, opt-in only, Arabic, retry after a failed
  send).
- `test_auth_hook_operator_claim.py` and `test_platform_operator_cli.py`: the UI-hint claim and the
  grant, revoke and list commands with their audit events.

### 13.4 Web unit tests (Karma + Jasmine)
- `features/feedback/`: `attachment-rules.spec.ts` (client-side type, size and count checks before any
  upload), `audio-recorder.service.spec.ts` (2-minute auto-stop, unsupported and denied microphone),
  `feedback-draft.store.spec.ts` (draft kept across a closed dialog or an expired session, cleared for
  another member), `feedback-api.spec.ts`, `feedback-widget/feedback-dialog.component.spec.ts` and
  `feedback-widget.component.spec.ts`, `feedback-attachment/feedback-attachment.component.spec.ts`,
  `my-feedback/my-feedback.component.spec.ts`, `workspace-feedback/workspace-feedback.component.spec.ts`.
- `features/platform/feedback-triage/`: `feedback-triage.component.spec.ts`,
  `feedback-detail/feedback-detail.component.spec.ts`, `platform-feedback-api.spec.ts`.
- `core/auth/operator.guard.spec.ts`, `app.routes.spec.ts` and `layout/shell/shell.component.spec.ts`
  (widget mounted in the shell, nav entries by role, the operator entry only for operators).

### 13.5 End-to-end and accessibility (Playwright)
- `apps/web/tests/e2e/feedback.spec.ts` (T078): submit from the widget, the submitter's own list, the
  owner's read-only inbox, operator triage, withdrawal.
- `apps/web/tests/e2e/feedback-a11y.spec.ts` (T079, tagged `@a11y`, so part of `pnpm test:a11y`): zero
  axe violations for the widget, both lists and the triage view in English and Arabic (SC-007). The
  360 px check in both reading directions is manual.

## 14. Open Decisions

1. Which Flutter testing framework (integration tests vs. Maestro).
2. Whether to add synthetic data generation for performance testing.
3. Real `MatchingService` idempotency on duplicate catalogue imports: catalogue import repeat-call sanity is proven in `test_catalogue_import.py`, but real matching and landed-cost pipeline behavior on re-import remains untested because `MatchingService` is faked in integration tests (see §11.4).
