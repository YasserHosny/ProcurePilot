# ProcurePilot — Wave 18 Execution Plan (Hardening + Close-out)

**Written**: 2026-09-16, following the successful completion and verification of Wave 17 on `main`
(latest commit `33f8bee`, a chain of test/schema-alignment fixes on top of the US1/US2 landing).

**Target feature**: `012-reporting-hardening`

**Release**: R2.5 — Reporting + Hardening (final Phase 2 release before the **G2** gate)

**Mode**: Implementation + documentation close-out. This is the wave `specs/012-reporting-
hardening/tasks.md` itself names **"Wave 18 (hardening + close-out)"** in its own "Implementation
waves" section — it is not new scope invented for this session, it is the plan's own next step.

---

## 0. Starting point

Wave 16 (foundation + US1 thin slice) and Wave 17 (US1 completion + US2 weekly digests) are both
complete and merged to `main`. Per `specs/012-reporting-hardening/tasks.md`:

- Phase 1 Schema (T001–T006): done.
- Phase 2 Contract + test-first (T007–T010): done.
- Phase 3 US1 Scheduled reports (T011–T022): done.
- Phase 4 US2 Weekly digests (T023–T028): done.
- Phase 5 Perf/a11y (T029–T033): **T029 and T030 already landed early**, during the Wave 15
  remediation pass (lazy routes + Sentry-SDK lazy-load got the initial bundle to 457.79 kB;
  component-style decomposition got every component under its 4 kB SCSS budget). **T031–T033
  remain.**
- Phase 6 Security (T034–T037): **not started.**
- Phase 7 Cross-cutting (T038–T042): **not started.**

This wave closes Phase 5 and completes Phases 6–7 — the entire remaining scope of
`012-reporting-hardening`. When it lands, R2.5 is done and the roadmap's G2 gate criteria (§10.8,
line 1223: "R2.4 optimiser + supplier IQ, R2.5 hardening") become checkable.

---

## 1. Non-negotiables

Unchanged from every prior wave — restated because Phase 6 of this wave is a security review and
must not be treated as a formality:

1. Read `.specify/memory/constitution.md` before writing code.
2. Tenant isolation is enforced in the database: RLS `ENABLE`+`FORCE`, `USING`+`WITH CHECK` on
   every tenant-scoped table; a reader function that ignores its pinned `tenant_id` argument is
   exactly as dangerous as a missing `WITH CHECK` and gets the same scrutiny.
3. Tenancy comes from the verified JWT claim; cross-tenant reads return "not found", never
   "forbidden".
4. No secrets in the repo. SMTP credentials, signed-URL secrets: env-only, redacted in logs.
5. Every user-facing string from `packages/i18n` (en + ar).
6. Every monetary value carries an explicit currency.
7. `audit_event` is append-only — the security review (T036) explicitly re-checks this holds for
   every new R2.5 audit event type.
8. No autonomous purchasing.
9. Never touch, stage, commit, or discard files outside this feature's own scope. Check
   `git status` for peer-uncommitted files before and after every merge (0 at the time this plan
   was written — confirm unchanged).

---

## 2. Task Scope

### Phase 5 remainder — Performance & accessibility (Tasks T031, T032, T033)

- **T031** `apps/web/tests/e2e/compare-grid-performance.spec.ts` — compare-grid recalculation
  under 150 ms for a seeded basket (constitution gate, FR-025), stable against CI noise via
  repeated-measurement median (the project's established fix for the recurring compare-grid
  timing/CI-noise problem — see `docs/quality/test-strategy.md`).
- **T032** `apps/api/tests/integration/test_export_generation_budget.py` — a 10,000-row export
  completes within 60s; an over-cap request is refused with the structured error and **no storage
  object is created** (SC-004).
- **T033** Extend `pnpm test:a11y` (axe-core) to the mandatory surface list from research R11, in
  English **and** Arabic, including the Reports center and digest settings; add the print-
  stylesheet check for the Reports center.

### Phase 6 — Security review before G2 (Tasks T034, T035, T036, T037)

- **T034** Dependency-audit CI job: `pip-audit` over `apps/api` + worker packages, `pnpm audit
  --prod` over the workspace, blocking on high/critical, with an owned allowlist at
  `docs/operations/dependency-audit-allowlist.txt`.
- **T035** Rate limiting on export creation, schedule mutations, digest subscription mutations
  (FR-020) in `apps/api/src/procurepilot_api/shared/rate_limit.py` — keyed by verified tenant +
  membership with IP fallback, caps on active schedules/subscriptions per member, integration
  tests proving structured 429s with **no queued work** left behind.
- **T036** Execute and record `docs/quality/r2.5-security-review-record.md`: RLS policy review for
  `report_schedule`/`digest_subscription`, worker tenant re-derivation, signed-URL TTL + bucket
  policy, purge-link invalidation, rate-limit review, SMTP secret handling + log redaction, audit
  payload completeness, `audit_event` append-only re-check (FR-022).
- **T037** `docs/operations/pentest-scope.md` — in-scope surfaces, data classifications,
  environment/credentials handling, boundaries and exclusions (roadmap §10.8, FR-023).

### Phase 7 — Cross-cutting close-out (Tasks T038–T042)

- **T038** `docs/architecture/data-dictionary.md` — `report_schedule`, `digest_subscription`, the
  `tenant` and `export_job` extensions, reader functions, new audit events.
- **T039** `docs/architecture/api-specification.md` from `specs/012-reporting-hardening/contracts/
  reporting-hardening.openapi.yaml`, including the download endpoint that was previously
  documented-but-unimplemented, now matching the real implementation.
- **T040** `docs/user/user-documentation.md` + screenshots for Reports center, schedule form,
  digest settings, export extensions; the mobile web-only boundary note in
  `docs/user/mobile-app-user-documentation.md` (reporting is web-only in R2.5; digest deep links
  open web routes).
- **T041** Run and record the full release gates: `pnpm lint`, `pnpm test:api`, `pnpm test:web`,
  `pnpm test:e2e`, `pnpm test:a11y`, `pnpm test:isolation`, warning-free `pnpm --filter web
  build`; record results in `tasks.md`.
- **T042** `docs/quality/test-strategy.md` — the R2.5 gates: compare-grid timing/CI-noise
  strategy, bundle/style-budget gates, mandatory axe surface list (EN+AR), dependency-audit CI
  job, rate-limit/security-review checks, pentest scope, isolation extension for schedules,
  artifacts, subscriptions, reader functions.

**Dependencies** (per tasks.md): T031/T032 are independent of each other and of T033. T035 needs
the routers already in `main` (they are). T036 needs all Phase 5/6 code final — it runs **last**,
after T031–T035. T038–T041 need everything above final. T042 is the true last task.

---

## 3. Lane Allocation & Task Split

`specs/012-reporting-hardening/tasks.md`'s own Delegation-lanes table assigns Phase 6 and Phase 7
to the **orchestrator**, not a delegate lane — security review and cross-cutting close-out carry
the same review burden as tenancy work and are not delegated by default (mirrors
`tenancy-work-stays-in-house`). Current fleet lanes (`~/.config/delegate-skills/config.json`,
2026-09-16): `complex`/`feature` → claude, `tests`/`ui` → agy (effort high), `simple` → opencode.
Codex is paused until 2026-09-19 12:09 and is not used this wave.

### Lane 1: Frontend/E2E (Agy — `ui` lane)
- **Tasks**: T031, T033
- **Why Agy**: both are frontend-surface Playwright/axe work — "Agy for all FE tasks" per the
  current lane config; T032 is backend pytest and does not fit this lane despite being adjacent
  in the phase.
- **Environment**: a fresh `git clone` under `~/agy-clones/wave18-r2-5-perf-a11y` (never a linked
  `git worktree add` — see `agy-fails-in-linked-git-worktree.md`), with local `git config
  user.name`/`user.email` set explicitly.
- **Key files**:
  - `apps/web/tests/e2e/compare-grid-performance.spec.ts` (new)
  - `apps/web/tests/e2e/reporting-hardening.spec.ts` or a new a11y-focused spec (extend `pnpm
    test:a11y` coverage — check whether axe-core surfaces are enumerated in a Playwright spec or a
    dedicated config list before choosing where to add the Reports-center/digest-settings/print
    checks)
  - `packages/i18n/en.json` / `ar.json` only if new copy is needed for the print stylesheet
- **Gates**:
  ```bash
  pnpm --filter web exec playwright test compare-grid-performance.spec.ts
  pnpm test:a11y
  pnpm lint
  ```
- **Do not touch**: anything under `apps/api/`, `.github/workflows/`, or `docs/quality/`.

### Lane 2 (in-house, Claude): everything else — T032, T034–T037, T038–T042

Per the plan's own lane table this is orchestrator-owned work: security review, dependency-audit
CI wiring, rate limiting, and the full cross-cutting documentation/gate close-out. Given Codex's
pause and that this is the bulk of the wave's genuinely sensitive surface (RLS review, secret
handling, CI blocking rules, the final full-suite gate run), it stays in-house rather than being
split further.

- **Key files**:
  - `apps/api/tests/integration/test_export_generation_budget.py` (new, T032)
  - `.github/workflows/ci.yml` (T034)
  - `apps/api/src/procurepilot_api/shared/rate_limit.py` + its integration tests (T035)
  - `docs/quality/r2.5-security-review-record.md` (new, T036)
  - `docs/operations/dependency-audit-allowlist.txt` (new, T034) and `docs/operations/pentest-
    scope.md` (new, T037)
  - `docs/architecture/data-dictionary.md`, `docs/architecture/api-specification.md`,
    `docs/user/user-documentation.md`, `docs/user/mobile-app-user-documentation.md`,
    `docs/quality/test-strategy.md` (T038–T040, T042)
  - `specs/012-reporting-hardening/tasks.md` itself (record T041's gate results, check off boxes)

---

## 4. Review Protocol

Before merging any lane into `main`:
1. **RLS & tenancy**: no cross-tenant leak; 404 not 403 on cross-tenant/unauthorized-branch reads.
2. **Worker hardening**: workers re-derive tenant/membership from the DB row, never trust raw
   queue payload arguments (T035's rate-limit tests must prove no queued work survives a 429).
3. **Security review (T036) is evidence-based**: every checklist item cites the actual migration,
   policy, or code path reviewed — not a self-report. Same standard as every prior wave: never
   trust an implementer's own "done" claim, re-run gates independently.
4. **Docs match code**: T038–T040 are checked against the real, current implementation (mirrors
   the Wave 13 T037 practice of live-verifying a route path before documenting it), not against
   the spec's original intent if the two have diverged.
5. Clean lints, clean unit tests, zero accessibility violations, peer-uncommitted-file count
   unchanged before/after every merge.

---

## 5. What comes after

T042 is the last task in `specs/012-reporting-hardening/tasks.md` — when this wave lands, R2.5 is
complete and the roadmap's G2 gate (workflow-origination ≥70%, mobile adoption target met,
retention ≥90%, per roadmap line 216/1223) becomes evaluable. The next step after this wave is
**not** a further wave of `012-reporting-hardening` — it is either evidencing the G2 gate, or,
mirroring the Phase 0→1 precedent (`2026-08-22`, gate overridden to proceed into build work
anyway), a user decision on whether to proceed into Phase 3 scope before G2 evidence is gathered.
Do not start any Phase 3 work without that decision.

---

## 6. Cautions

- Codex is paused until 2026-09-19 12:09 — do not dispatch to it before then.
- T036 (security review) and T037 (pentest scope) must run **after** T034/T035 land, since the
  review covers the rate-limiting and dependency-audit surfaces those tasks add.
- T041's full gate run is the last verification step before T042; do not write T042's test-
  strategy update from assumption — run the gates first, record actual results.
- This is very likely the **last wave of Phase 2** — treat T041/T042 with the same rigor as any
  other release-closing gate run in this project's history, not as routine documentation.
