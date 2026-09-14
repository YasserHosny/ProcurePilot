# ProcurePilot - Wave 16 Execution Plan (R2.5 foundation + US1 thin slice)

**Written**: 2026-09-14, by the Wave 15 orchestrator, after the R2.5 planning package was drafted
on `codex/wave15-r2-5-planning`.

**Target feature**: `012-reporting-hardening`

**Release**: R2.5 - Reporting + Hardening (final Phase 2 release before G2)

**Mode**: Implementation. Wave 15's planning-only restriction is lifted for the tasks named
below, and only for them.

## 0. Starting point

Wave 15 produced the planning package under `specs/012-reporting-hardening/` (spec, plan,
research, data-model, quickstart, requirements checklist, tasks) plus four critique/baseline
documents. All five scope ambiguities are resolved in research.md R1-R5, R11, R12. Two
assumptions are flagged for the user at the start gate: provider-agnostic SMTP (R7) and the OFL
Arabic typeface (R8).

Wave 16 is the first of three implementation waves defined in
`specs/012-reporting-hardening/tasks.md`:

- **Wave 16** — foundation + US1 thin slice (this plan)
- **Wave 17** — US1 completion + US2 digests
- **Wave 18** — performance/a11y/security hardening + close-out

## 1. Non-negotiables

1. Read `.specify/memory/constitution.md` before writing code.
2. Only the tasks in this plan are implemented. Wave 17/18 tasks are not pulled forward.
3. Tenant isolation is enforced in the database: every new tenant-scoped table ships with
   `ENABLE` + `FORCE` RLS and policies supplying `USING` and `WITH CHECK`, in the same migration.
4. Tenancy comes from the verified JWT claim for API paths; workers pin every query to the owning
   tenant by parameter. Cross-tenant reads return not found.
5. No secrets in the repo; SMTP and TTL settings come from the environment with no hardcoded
   fallback for any secret.
6. Every user-facing string comes from `packages/i18n` (en + ar), including renderer output.
7. Every monetary value carries an explicit currency.
8. `audit_event` stays append-only.
9. No autonomous purchasing; reporting is advisory only.
10. Frontend implementation under `apps/web/src/**` is delegated to Agy when practical and
    independently reviewed by the orchestrator before landing. If headless Agy delegation is
    blocked by permission prompts, `agy --dangerously-skip-permissions` may be used only with the
    user's standing approval, with narrow file scope and gate reruns.
11. Migrations are forward-only, one versioned file per change, never edited after merge.

## 2. Scope for Wave 16

From `specs/012-reporting-hardening/tasks.md`:

1. Phase 1 (T001–T006): tenant reporting timezone, `report_schedule`, `digest_subscription`,
   `export_job` extensions, tenant-pinned reader functions, seed additions.
2. Phase 2 (T007–T010): OpenAPI contract, contract tests, isolation tests, window-math tests.
3. US1 thin slice: T011 (schedule CRUD service + window math), T012 (schedule/artifact routers),
   T014 (on-demand export extensions: kinds, csv, branch filter, row cap), and the read-only
   Reports center slice of T020.

Out of scope for Wave 16: the download endpoint (T013), renderers and Arabic PDF (T015), the
scheduler worker (T016), export worker extensions (T017), tenant PATCH (T018), remaining US1
tests/UI (T019, T021, T022), all of US2 (T023–T028), and all of Phases 5–7.

## 3. Task split

### Orchestrator lane - in-house

**Tasks**: T001–T010 (exact file paths in tasks.md Phase 1 and Phase 2).

**Order**: T001–T005 migrations first (T005's reader functions are the tenancy-critical path and
are written by the orchestrator personally), T006 seed, then T007 contract, then T008–T010 tests.
T008 and T009 are parallelisable with T007.

**Gate commands**:

```bash
pnpm db:migrate
pnpm test:api -- apps/api/tests/integration/test_reporting_isolation.py
pnpm test:api -- apps/api/tests/unit/test_report_windows.py
pnpm test:api -- apps/api/tests/contract/test_reporting_contract.py
```

The isolation and contract tests are expected to be red at the start of the wave (no module code)
and green by its end only if T011/T012 land in the same wave — they do (backend lane below). The
orchestrator lands migrations and contract first so the backend lane never waits.

### Backend/API lane - Codex delegate

**Tasks**: T011, T012, T014.

**File scope**:

- `apps/api/src/procurepilot_api/modules/reports/` (new: `schemas.py`, `schedules.py`, `router.py`)
- `apps/api/src/procurepilot_api/modules/exports/schemas.py`
- `apps/api/src/procurepilot_api/modules/exports/service.py`
- `apps/api/tests/integration/test_report_schedules.py` (T019 lands in Wave 17; the delegate
  writes the slice's tests inside the files above only if instructed — see dispatch brief)

**Brief**: implement against `specs/012-reporting-hardening/contracts/reporting-hardening.openapi.yaml`
and data-model.md; RBAC owner/buyer for schedule writes; cursor pagination limit cap 100; audit
events from data-model.md's list; kind/format matrix enforced at the boundary; branch filter
validated against branch visibility; row cap 10,000 with the structured refusal; no hardcoded
user-facing strings (renderer labels are Wave 17's T015 — API error `message` fields follow the
existing error-envelope conventions).

**Gate commands**:

```bash
pnpm test:api -- apps/api/tests/contract/test_reporting_contract.py
pnpm test:api -- apps/api/tests/integration/test_report_schedules.py
pnpm lint
pnpm test:isolation
```

### Frontend lane - Agy delegate

**Task**: T020, read-only slice only.

**File scope**:

- `apps/web/src/app/features/reports/reports-center/` (new)
- `apps/web/src/app/layout/` (sidebar entry only)
- `apps/web/src/app/app.routes.ts` (route entry only)
- `packages/i18n/en.json`, `packages/i18n/ar.json` (`reports.*` namespace)

**Brief**: artifacts and schedules lists (read-only: no create/pause/download actions yet), cursor
pagination wiring, i18n keys in both catalogues, CSS logical properties, keyboard-reachable
focus order, axe-clean. No other `apps/web/src/**` file may be touched.

**Gate commands**:

```bash
pnpm --filter web build
pnpm test:web
pnpm test:a11y
```

## 4. Branches

- `codex/wave16-r2-5-foundation` — orchestrator (migrations, contract, tests)
- `codex/wave16-r2-5-backend` — backend delegate slice
- `codex/wave16-r2-5-reports-ui` — Agy slice

All three merge to `main` after orchestrator review, in that order (contract before UI review).

## 5. Review protocol

Each lane ends with: files changed, exact gate commands run and their real output, open
questions, and a recommendation. The orchestrator reviews every diff against spec.md, plan.md,
data-model.md, and the constitution before merge, with specific attention to:

1. RLS policy shape on `report_schedule` and `digest_subscription` (both policies, FORCE).
2. Reader functions: every query filtered by the `tenant_id` parameter; `SET search_path` pinned.
3. The per-period unique partial index and its interaction with the claim query.
4. No renderer/UI string outside `packages/i18n`; no bare money values anywhere.

## 6. Wave 17 start criteria

Wave 17 (US1 completion + US2: T013, T015–T019, T021–T022, T023–T028) may start only after:

1. Wave 16 branches are merged to `main` and gates are green there.
2. The user has confirmed the two flagged assumptions (SMTP provider-agnostic design, OFL Arabic
   font) or amended them.
3. The download endpoint design (T013) is re-checked against the documents-module signed-URL
   pattern still current on `main`.

## 7. Known cautions

- `ALTER TYPE export_format ADD VALUE 'csv'` must not be referenced by any CHECK or policy in the
  same migration transaction (T004 note).
- The scheduler does not exist yet in Wave 16; nothing may enqueue scheduled runs. T012's
  artifact list must tolerate `schedule_id` being null everywhere (on-demand jobs only).
- The Reports center must not link downloads yet — the download endpoint is Wave 17 (T013). The
  UI must render `download_url` as absent, not as a dead link (this was `main`'s defect).
- Do not implement US2 digest subscription UI ahead of the stable content shape; T027 stays in
  Wave 17.
- Bundle/style budget work (T029/T030) must not be pulled into the UI slice "while we're in
  there" — it is Wave 18 with its own measurement-verified gates.
