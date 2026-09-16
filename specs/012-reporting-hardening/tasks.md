---
description: "Task list for Reporting and Hardening (R2.5) implementation"
---

# Tasks: Reporting and Hardening

**Input**: Design documents from `/specs/012-reporting-hardening/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/reporting-hardening.openapi.yaml

**Tests**: Test tasks ARE included and come first in each phase. The constitution and spec require
them: FR-019/SC-002 (isolation), FR-021 (dependency audit), FR-026 (axe-core), FR-025 (timing
regression), FR-022 (recorded security review).

**Organization**: grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1–US5 from spec.md
- Every task names its exact file path

---

## Phase 1: Setup and schema (orchestrator lane)

**Purpose**: the tenant, schedule, subscription, and artifact state everything else sits on.

- [x] T001 Write migration `supabase/migrations/20260915000001_tenant_reporting_timezone.sql`
  adding `tenant.reporting_timezone text not null default 'UTC'` with the IANA-validation comment
  (API validates the value; the database stores it).
- [x] T002 Write migration `supabase/migrations/20260915000002_report_schedule.sql` creating
  `report_schedule` with the `report_schedule_status` enum, the `locale` column (FR-029), unique
  `(tenant_id, created_by_membership_id, kind, format, filters_digest)`, the due-list partial
  index, kind CHECK, and RLS: `ENABLE` + `FORCE`, policies with `USING` and `WITH CHECK`
  (members select; owner/buyer write) per data-model.md.
- [x] T003 Write migration `supabase/migrations/20260915000003_digest_subscription.sql` creating
  `digest_subscription` with the `digest_channel` and `digest_subscription_status` enums, unique
  `(tenant_id, membership_id, kind, filters_digest)`, the due-list partial index, and RLS:
  members manage only their own rows; owners may select all rows in the tenant (visibility only).
- [x] T004 Write migration
  `supabase/migrations/20260915000004_export_job_reporting_extensions.sql` adding
  `schedule_id` (composite FK), `locale`, `rule_version`, `expires_at`, the immutable
  `schedule_snapshot` jsonb (research R13 / security critique finding 7), the `expired` status
  value, the `csv` value for `export_format` (own statement — a CHECK may not reference the new
  value in the same transaction; the kind/format matrix is enforced at the API and contract
  boundary), the kind CHECK for the R2.5 value set, the per-period unique partial index
  `(tenant_id, schedule_id, filters->>'period_start') where schedule_id is not null`, and the
  `(tenant_id, created_at desc)` listing index.
- [x] T005 Write migration
  `supabase/migrations/20260915000005_reporting_reader_functions.sql` defining the four
  authorization-pinned SECURITY DEFINER reader functions (`reporting_savings_for_period`,
  `reporting_purchases_for_period`, `reporting_alert_snapshot`, `reporting_validity_expiring`)
  with `SET search_path` pinned, explicit `tenant_id` parameters, and — where member-specific
  visibility matters — effective `membership_id` and optional `branch_id` parameters validated
  inside the function, per research R5.
- [x] T006 [P] Update `apps/api/scripts/seed.py` to seed, in the demo tenant: one report schedule
  and one digest subscription with `next_run_at` in the past, plus the period data they report on.

**Checkpoint**: migrations apply cleanly; `\d+ report_schedule` shows FORCE RLS and both-policy
shape; the isolation test for the new tables passes.

---

## Phase 2: Contract and test-first foundations (orchestrator lane)

- [x] T007 Write `specs/012-reporting-hardening/contracts/reporting-hardening.openapi.yaml`
  covering: schedules CRUD (`/reports/schedules`), the artifacts cursor list
  (`/reports/artifacts`), the extended `POST /exports` (kinds, csv, branch filter, row-cap
  error), `GET /exports/{id}/download`, digest subscriptions CRUD (`/digests/subscriptions`),
  `GET /digests/latest`, the `reporting_timezone` field on `PATCH /tenant`, and the kind/format
  matrix.
- [x] T008 [P] [US1] Write `apps/api/tests/integration/test_reporting_isolation.py` — the FR-019
  test: two tenants with marker schedules, artifacts, export jobs, and subscriptions; cross-reads
  via API assert not found; the four reader functions are called with tenant A's id and assert
  tenant B's marker rows are invisible; a branch-A/branch-B case asserts a branch-scoped member
  cannot see the other branch's artifacts, digest content, or reader rows; worker hardening cases
  assert tenant/job mismatch payloads and duplicate RQ replay are refused, and that purged
  artifacts invalidate previously issued download links.
- [x] T009 [P] [US1] Write `apps/api/tests/unit/test_report_windows.py` covering the pure
  schedule math: weekly window derivation in the reporting timezone (UTC default, DST boundary
  case), weekday/next-run computation, and per-period idempotency key derivation.
- [x] T010 Write `apps/api/tests/contract/test_reporting_contract.py` validating request and
  response shapes of every new and extended endpoint against the contract from T007.

**Checkpoint**: the contract exists, and the isolation and window tests are red for the right
reason (no module code yet), ready to drive implementation.

---

## Phase 3: User Story 1 — Scheduled reports and a working Reports center (P1)

- [x] T011 [US1] Implement schedule CRUD and window math in
  `apps/api/src/procurepilot_api/modules/reports/schedules.py` and `modules/reports/schemas.py`:
  create/update/pause/resume/delete with duplicate refusal, RBAC (owner/buyer write), filter
  validation against enabled branches/suppliers, locale selection (FR-029), next-run computation,
  and the schedule-survives-creator-deactivation rule — passing T009.
- [x] T012 [US1] Implement `GET/POST/PATCH/DELETE /api/v1/reports/schedules` and
  `GET /api/v1/reports/artifacts` (cursor pagination, limit cap 100, branch-visibility filtering
  for branch-scoped roles per FR-004) in
  `apps/api/src/procurepilot_api/modules/reports/router.py`, with audit events
  `reports.schedule_*` and `reports.export_requested` carrying the FR-011 payload contract.
- [x] T013 [US1] Implement `GET /api/v1/exports/{id}/download` in
  `apps/api/src/procurepilot_api/modules/exports/router.py` and `storage.py`: authenticated
  job lookup (RLS-visible), branch-visibility verification (FR-005), expiring signed URL via the
  documents-module pattern with a bounded environment-configured TTL, audit
  `reports.artifact_downloaded`, and not found for cross-tenant, unauthorised-branch, or purged
  artifacts — closing the Wave 15 audit finding (research R6).
  Wave 15 remediation note: the core endpoint (authenticated lookup, RLS-visible 404s, signed
  URL with `EXPORT_DOWNLOAD_URL_TTL_SECONDS`, `reports.artifact_downloaded` audit,
  integration tests in `apps/api/tests/integration/test_export_download.py`) landed early on
  main with honest `api-specification.md` docs. T013's remainder: branch-visibility
  verification (FR-005, blocked on T014 readers) and purged-artifact/expiry semantics (blocked
  on the T006 retention migration).
- [x] T014 [US1] Extend on-demand exports in `apps/api/src/procurepilot_api/modules/exports/schemas.py`
  and `service.py`: kinds `spend_by_supplier` and `alerts_summary`, `csv` format, the branch filter
  (replacing the `unsupported_in_phase_1` refusal) with branch-visibility validation, the locale
  field (FR-029), the declared column schemas and currency-grouped aggregation from
  data-model.md, and the 10,000-row cap with the structured over-cap refusal (FR-013).
- [x] T015 [US1] Implement the catalogue loader `apps/api/src/procurepilot_api/shared/i18n.py`
  reading `packages/i18n/en.json` and `ar.json` at runtime, and extend
  `apps/api/src/procurepilot_api/modules/exports/renderers.py`: CSV renderer for all kinds
  (UTF-8 BOM prefixed), `spend_by_supplier` and `alerts_summary` renderers with the declared
  business column schemas, labels from the catalogue, structured PDF table layouts with page
  headers, human-usable web evidence links, full header metadata on empty exports, and
  Arabic-capable PDF through the shaping pipeline (`arabic-reshaper` + `python-bidi` added to
  `apps/api/pyproject.toml`, embedded OFL font under
  `apps/api/src/procurepilot_api/assets/fonts/`, right-to-left layout) per research R8.
- [x] T016 [US1] Implement the scheduler entrypoint
  `apps/api/src/procurepilot_api/workers/report_scheduler.py`: tick loop with `--once` flag,
  due-row claim via `FOR UPDATE SKIP LOCKED`, next-run advance in the claimed transaction, RQ
  enqueue with deterministic per-period job ids, the immutable schedule snapshot written at
  enqueue, crash-after-upload recovery, and the retention purge pass with
  `reports.artifact_purged` audit events that invalidate issued links.
- [x] T017 [US1] Extend `apps/api/src/procurepilot_api/workers/export_worker.py` for scheduled
  runs: treat queue payloads as untrusted hints (load the row by id, re-derive tenant and scope
  from the database inside the transaction, refuse mismatches — research R5), schedule-linked
  jobs read their window from the immutable snapshot, use the authorization-pinned reader
  functions, set `locale`, `rule_version`, and `expires_at`, and record `reports.run_*` audit
  events with the FR-011 payload; failed runs leave no completed artifact.
- [x] T018 [US1] Extend `apps/api/src/procurepilot_api/modules/tenants/router.py` so
  `PATCH /api/v1/tenant` accepts `reporting_timezone` (owner-only, IANA-validated; region,
  currency, tax model stay immutable).
- [x] T019 [US1] Write `apps/api/tests/integration/test_report_schedules.py` (CRUD, RBAC
  refusal, pause/resume, duplicate refusal) and `apps/api/tests/integration/test_export_download.py`
  (signed URL, expiry, cross-tenant, unauthorised-branch, and purged not found; CSV BOM presence;
  Arabic PDF shaping assertion on connected glyphs and display order), and extend
  `apps/api/tests/contract/test_reporting_contract.py` coverage for the download flow.
- [x] T020 [P] [US1] Build the Reports center in `apps/web/src/app/features/reports/reports-center/`:
  artifacts list (kind, format, locale, period, status, row count, rule version, summary
  highlight, download action, and per-kind operational deep link — alerts to the inbox,
  savings to the ledger, spend to compare), schedules list with pause/resume, cross-links from
  the savings/export screens, cursor pagination, i18n keys in `packages/i18n/en.json` and
  `ar.json`, logical properties, keyboard-reachable actions.
- [x] T021 [P] [US1] Build the schedule form in `apps/web/src/app/features/reports/schedule-form/`
  (kind, format per the contract matrix, filters, weekday, locale) and extend
  `apps/web/src/app/features/savings/export-savings/` for csv, kinds, the branch filter, and the
  "schedule as weekly report" cross-link pre-populating the schedule form.
- [x] T022 [US1] Write `apps/web/tests/e2e/reporting-hardening.spec.ts`: schedule create →
  scheduler trigger → artifact appears → download → pause stops generation, in English and
  Arabic, plus the keyboard-only Reports center journey in both directions.

**Checkpoint**: US1 is independently demonstrable end to end — a schedule produces a downloadable,
evidence-carrying artifact exactly once per period.

---

## Phase 4: User Story 2 — Weekly actionable digests (P2)

- [x] T023 [US2] Implement digest subscription CRUD and content assembly in
  `apps/api/src/procurepilot_api/modules/digests/service.py` and `schemas.py`: self-service
  subscriptions (a member manages only their own), branch filter, weekly window content from the
  authorization-pinned readers in the FR-009 section order (verified savings hero, pending
  outcome verifications, pending approvals for the subscriber, anomalies, expiring validity),
  each item with deep link and explicit-currency money where applicable, and default provisioning
  of one active subscription on membership acceptance (research R3).
- [x] T024 [US2] Implement the digest renderer and delivery in
  `apps/api/src/procurepilot_api/modules/digests/renderer.py`, the SMTP settings in
  `apps/api/src/procurepilot_api/config.py` (host, port, username, password as `SecretStr`,
  from, tls — no hardcoded fallbacks, `.env.example` placeholders), and the worker
  `apps/api/src/procurepilot_api/workers/digest_worker.py`: multipart render (HTML with
  `dir`/`lang` attributes and email-safe fonts, plus plain text), deliver via SMTP when
  configured with `List-Unsubscribe` headers and a settings footer link, treat queue payloads as
  untrusted hints (research R5), redact credentials from logs and audit detail, record
  `last_delivery_*` and the `digests.delivery_*` audit events with the FR-011 payload, skip
  inactive memberships, and leave an explicit `email_unconfigured` status otherwise (research R7).
- [x] T025 [US2] Implement `GET/POST/PATCH/DELETE /api/v1/digests/subscriptions` and
  `GET /api/v1/digests/latest` (the in-app DigestView) in
  `apps/api/src/procurepilot_api/modules/digests/router.py`.
- [x] T026 [US2] Write `apps/api/tests/integration/test_digests.py`: content matches seeded
  weekly records; delivery success, failure, and unconfigured paths audited; inactive membership
  skipped; cross-tenant subscription ids not found.
- [x] T027 [P] [US2] Build digest settings and the in-app digest view in
  `apps/web/src/app/features/reports/digest-settings/`: subscription CRUD with one-click
  pause/resume, the dismissible onboarding prompt for the default subscription, honest email
  status ("email not configured" state), the rendered digest in the FR-009 information
  architecture with per-item deep links, i18n in both catalogues, keyboard-reachable.
- [x] T028 [US2] Extend `apps/web/tests/e2e/reporting-hardening.spec.ts` with the digest flow:
  subscribe → trigger → in-app digest renders with links → status reflects delivery outcome.

**Checkpoint**: a subscriber receives (or reads in-app) a digest whose every section is
source-backed and actionable, with honest delivery state.

---

## Phase 5: User Story 3+4 — Performance and accessibility pass (P2)

- [x] T029 [P] [US4] Convert feature routes to lazy-loaded routes in
  `apps/web/src/app/app.routes.ts` (and component imports accordingly) so the production build
  reports the initial bundle at or under 500 kB raw with zero budget warnings — measured against
  the Wave 15 baseline (588.35 kB), per research R10.
  Landed early in the Wave 15 remediation (main): routes were already lazy; the real offenders
  were the eagerly-imported Sentry SDK (244.92 kB) and synchronous animations provider — both
  now lazy. Initial bundle 457.79 kB, zero budget warnings.
- [x] T030 [P] [US4] Bring every component style inside its 4 kB budget, refactoring or splitting
  the styles of the components listed in
  `docs/quality/r2.5-performance-accessibility-baseline.md` (team, review-queue,
  resolution-queue, product-intelligence, alerts-inbox, savings-ledger, saving-evidence,
  match-resolution, export-savings, plan-display, home), so the build emits zero SCSS budget
  warnings.
  Landed early in the Wave 15 remediation (main): shared primitives deduplicated into global
  `styles.scss`; oversized components decomposed into real child components (own template +
  class), not `styleUrls` budget evasion; TS-998113/NG8011 warnings also cleared. Zero build
  warnings, 56/56 component styles within budget.
- [x] T031 [US4] Write `apps/web/tests/e2e/compare-grid-performance.spec.ts` asserting
  compare-grid recalculation completes under 150 ms for a seeded basket (constitution gate;
  FR-025), stable against CI noise via repeated-measurement median.
- [x] T032 [US3] Write `apps/api/tests/integration/test_export_generation_budget.py` asserting a
  10,000-row export completes within 60 seconds and an over-cap request is refused with the
  structured error and no storage object (SC-004).
- [x] T033 [US4] Extend the axe-core suite (`pnpm test:a11y`) to the mandatory surface list from
  research R11 in English and Arabic, including the Reports center and digest settings, and add
  the print-stylesheet check for the Reports center.

**Checkpoint**: `pnpm --filter web build` is warning-free; the timing and a11y gates are green in
CI.

---

## Phase 6: User Story 5 — Security review before G2 (P2)

- [x] T034 [US5] Add the dependency-audit job to `.github/workflows/ci.yml`: `pip-audit` over
  `apps/api` and the worker packages, `pnpm audit --prod` over the workspace, blocking on
  high/critical, with the accepted-findings allowlist at
  `docs/operations/dependency-audit-allowlist.txt` (each entry naming owner and reason).
- [x] T035 [US5] Extend `apps/api/src/procurepilot_api/shared/rate_limit.py` and apply limits to
  export creation, schedule mutations, and digest subscription mutations (FR-020): keyed by
  verified tenant and membership claims with IP fallback, caps on active schedules and
  subscriptions per member, and integration tests proving structured 429 responses with no
  queued work.
- [x] T036 [US5] Execute and record the security review in
  `docs/quality/r2.5-security-review-record.md`: RLS policy review for `report_schedule` and
  `digest_subscription` (both-policy shape, FORCE), worker tenant re-derivation and
  authorization-pinned reader review, signed-URL max TTL and private bucket policy review
  (storage path shape, CSV content type, no PII in paths), purge link invalidation, rate-limit
  review, SMTP secret-handling and log-redaction review, audit payload completeness, and a
  re-check that `audit_event` still grants no update or delete — every item passed or carrying an
  owned exception (FR-022).
- [x] T037 [US5] Write the penetration-test scope document
  `docs/operations/pentest-scope.md`: in-scope surfaces, data classifications, environment and
  credentials handling, boundaries and exclusions, per roadmap §10.8 (FR-023).

**Checkpoint**: CI blocks on dependency findings; the security record has no open red items; the
pentest is procurable.

---

## Phase 7: Cross-cutting (orchestrator lane)

- [x] T038 Update `docs/architecture/data-dictionary.md` with `report_schedule`,
  `digest_subscription`, the `tenant`, `export_job`, and reader-function extensions, and the new
  audit events.
- [x] T039 Update `docs/architecture/api-specification.md` from
  `specs/012-reporting-hardening/contracts/reporting-hardening.openapi.yaml`, including the
  previously documented-but-unimplemented download endpoint now matching the implementation.
- [x] T040 Update `docs/user/user-documentation.md` and screenshots for the Reports center,
  schedule form, digest settings, and the export extensions; add the mobile web-only boundary
  note to `docs/user/mobile-app-user-documentation.md` (reporting surfaces are web-only in R2.5;
  digest deep links open web routes).
- [x] T041 Run and record the release gates: `pnpm lint`, `pnpm test:api`, `pnpm test:web`,
  `pnpm test:e2e`, `pnpm test:a11y`, `pnpm test:isolation`, and a warning-free
  `pnpm --filter web build`; record results in this file.
- [x] T042 Update `docs/quality/test-strategy.md` with the R2.5 gates (docs gap audit): the
  compare-grid timing regression and CI-noise strategy, initial-bundle and style-budget gates,
  the mandatory axe surface list in EN and AR, the dependency-audit CI job, rate-limit and
  security-review checks, pentest scope, and the isolation extension for schedules, artifacts,
  subscriptions, and reader functions.

---

## Dependencies

```text
Phase 1 Schema (T001-T006)
    ↓
Phase 2 Contract + test-first (T007-T010)
    ↓
Phase 3 US1 (T011-T022)  ← T011/T012 depend on T002+T007; T020-T022 need T007 stable
    ↓
Phase 4 US2 (T023-T028)  ← reuses the scheduler (T016) and reader functions (T005)
    ↓
Phase 5 Perf/a11y (T029-T033)  ← T033 needs the US1/US2 UI; T029/T030 are independent
    ↓
Phase 6 Security (T034-T037)  ← T035 needs the new routers; T036 needs all code final
    ↓
Phase 7 Cross-cutting (T038-T041)
```

**Story independence**: T029/T030 (bundle and style budgets) can run any time after Phase 2;
T034 (CI audit job) can run in parallel with Phase 3. US2 depends on US1 only for the scheduler
and reader functions, not for the Reports center UI.

---

## Delegation lanes

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator** | migrations, RLS, reader functions, isolation tests, security, gates | Codex in-house | T001–T010, T034–T037, T038–T041 |
| **Backend/API** | reports/digests/exports modules, workers, renderers, API tests | Codex delegate | T011–T019, T023–T026, T032 |
| **Frontend** | Reports center, schedule form, digest UI, perf/a11y pass, e2e | Agy delegate | T020–T022, T027–T031, T033 |

**Lane D-equivalent work is retained by the orchestrator**: the reader functions (T005) and the
RLS migrations (T002–T004) are the R2.5 instances of the tenancy-critical path — a
parameter-pinned function that quietly ignores its `tenant_id` argument passes a casual review
exactly the way a missing `WITH CHECK` does. Their review burden is not delegated.

Lanes touch disjoint paths. Every delegated diff is reviewed against spec.md, plan.md, and the
constitution before it lands. For Agy frontend lanes, if permission prompts block headless
execution, `agy --dangerously-skip-permissions` may be used only with the user's prior standing
approval, with narrow file scope and independent gate reruns.

## Implementation waves

**Wave 16 (foundation + US1 thin slice)**: T001–T010 (orchestrator) + T011, T012, T014 (backend)
+ T020 read-only slice (Agy, after T007 lands).

**Wave 17 (US1 completion + US2)**: T013, T015–T019, T021–T022 (backend + Agy) + T023–T028
(backend + Agy).

**Wave 18 (hardening + close-out)**: T029–T033 (Agy + backend) + T034–T037 (orchestrator) +
T038–T042.

Do not start US2 UI (T027) until the digest content shape is stable in T023–T025.
