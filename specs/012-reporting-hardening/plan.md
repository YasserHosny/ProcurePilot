# Implementation Plan: Reporting and Hardening

**Branch**: `012-reporting-hardening` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-reporting-hardening/spec.md`

## Summary

R2.5 completes Phase 2: scheduled reports with a Reports center, per-member weekly digests with
email delivery, hardened exports (CSV, branch filter, row cap, retention, the missing download
endpoint, Arabic PDF), a measured performance and accessibility pass, and the pre-G2 security
review evidence. It reuses the existing `exports` module, `export_job` table, Redis/RQ worker
topology, and alerts/savings/purchase data — adding a scheduler entrypoint and a digest worker to
the existing `apps/api` image rather than new services.

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5.6, Angular 19, PostgreSQL 17
**Primary Dependencies**: FastAPI, Pydantic v2, psycopg, supabase-py, Redis + RQ (existing),
openpyxl, reportlab (existing), Angular Material/CDK, RxJS, @ngx-translate/core
**Storage**: Supabase Postgres with RLS; Supabase Storage private bucket for artifacts; SMTP via
environment configuration for digest delivery
**Testing**: pytest, httpx TestClient, Karma/Jasmine, Playwright, axe-core, timing-based
regression tests, dependency audits
**Target Platform**: ProcurePilot web and API; no new mobile scope in R2.5
**Project Type**: API + web SPA + worker entrypoints inside the existing api deployable
**Performance Goals**: initial bundle ≤ 500 kB raw; zero budget warnings; compare-grid
recalculation < 150 ms; export of 10,000 rows ≤ 60 s; digest generation ≤ 30 s per subscription
**Constraints**: tenant from JWT only for API paths and tenant-pinned queries in workers; money
pairs always include currency; renderer strings from `packages/i18n`; no autonomous purchasing;
artifacts tenant-scoped with RLS; append-only audit
**Scale/Scope**: reporting and hardening for Phase 2 workspaces on top of R2.4 data

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Principle I: every artifact and digest carries source counts, rule version, filter snapshot, and
  explicit-currency values; delivery failures are surfaced, never swallowed.
- Principle II: generation inputs (filters, period, rule version) are snapshotted on the job row;
  rows are reproducible from source data plus the recorded snapshot; artifacts expire rather than
  mutate.
- Principle III: reporting is advisory — no report or digest path creates purchases, approvals,
  orders, payments, or supplier messages; every digest item routes a human to a decision surface.
- Principle IV: no passive dashboard — the Reports center carries download and schedule actions;
  digests carry per-item deep links to acting surfaces.
- Principle V: new tables (`report_schedule`, `digest_subscription`) are tenant-scoped with
  `ENABLE` + `FORCE` RLS, `USING` and `WITH CHECK`; workers without a JWT pin every query to the
  owning tenant by parameter; cross-tenant references resolve as not found; the isolation test is
  extended.
- Principle VI: no new service — the scheduler and digest worker are new entrypoints of the
  existing `apps/api` package, following the `export_worker` precedent recorded in migration
  `20260821000032`; the complexity is tracked below.
- Principle VII: money always carries currency; renderer labels come from `packages/i18n`; Arabic
  PDFs render right-to-left with an embedded Arabic-capable font; web work uses logical
  properties and ships both catalogues.

No constitution violations are planned.

## Project Structure

### Documentation (this feature)

```text
specs/012-reporting-hardening/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- checklists/
|   `-- requirements.md
|-- contracts/
|   `-- reporting-hardening.openapi.yaml
`-- tasks.md
```

### Source Code (repository root)

```text
apps/api/src/procurepilot_api/
|-- modules/reports/
|   |-- schemas.py          # schedule + artifact schemas
|   |-- schedules.py        # schedule CRUD service, due-run claim queries
|   `-- router.py           # /reports/schedules, /reports/artifacts
|-- modules/digests/
|   |-- schemas.py          # subscription + delivery schemas
|   |-- service.py          # subscription CRUD, content assembly
|   |-- renderer.py         # digest rendering (email + in-app payload)
|   `-- router.py           # /digests/subscriptions, /digests/latest
|-- modules/exports/
|   |-- schemas.py          # extended kinds, csv, branch filter, row cap
|   |-- service.py          # extended create, tenant-pinned readers
|   |-- renderers.py        # csv + new kinds + i18n labels + Arabic PDF
|   |-- storage.py          # signed URL creation, retention purge helpers
|   `-- router.py           # + GET /exports/{id}/download
|-- workers/
|   |-- export_worker.py    # extended: scheduled runs, csv, retention
|   |-- report_scheduler.py # new: due-list claim + enqueue loop
|   `-- digest_worker.py    # new: digest render + deliver
|-- config.py               # SMTP, retention, row cap, URL TTL settings
`-- shared/i18n.py          # catalogue loading from packages/i18n

apps/web/src/app/features/reports/
|-- reports-center/         # artifacts + schedules list, download actions
|-- schedule-form/          # create/edit schedule
`-- digest-settings/        # subscription CRUD + delivery status

apps/web/src/app/features/savings/export-savings/   # extended formats/branch

packages/i18n/
|-- en.json                 # reports.*, digests.* namespaces
`-- ar.json

supabase/migrations/
|-- 20260915000001_tenant_reporting_timezone.sql
|-- 20260915000002_report_schedule.sql
|-- 20260915000003_digest_subscription.sql
`-- 20260915000004_export_job_reporting_extensions.sql

.github/workflows/ci.yml    # dependency audit job

docs/operations/pentest-scope.md
docs/quality/r2.5-security-review-record.md
```

**Structure Decision**: Extend the existing `exports` module and `export_job` table for all
artifacts (on demand and scheduled); add `reports` and `digests` modules for their own CRUD
surfaces; add two worker entrypoints in the existing api package; add one CI job. No new
`services/` directory, no new deployable.

## Complexity Tracking

- **Two new worker entrypoints** (`report_scheduler`, `digest_worker`) in the existing api image:
  justified by the RQ topology already established by `export_worker` (migration
  `20260821000032` records the precedent — rendering and scheduling are entrypoints of the api
  package, not new services). The scheduler is single-instance and claim-based
  (`FOR UPDATE SKIP LOCKED`) so at-most-one enqueue per due run needs no distributed lock library.
- **SMTP delivery in the api package**: provider-agnostic SMTP client via environment settings;
  no vendor SDK and no new service. Delivery failures degrade to explicit in-app status, which is
  the constitutionally honest failure mode.
- **Server-side i18n loading from `packages/i18n`**: the api reads the existing catalogue files at
  runtime rather than duplicating labels, keeping one source of truth for user-facing strings
  across web and rendered documents.
- **Bundle reduction by route lazy-loading**: changes routing configuration only; per the
  assumption, no feature is removed.
