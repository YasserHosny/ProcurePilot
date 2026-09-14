# ProcurePilot - Wave 15 Execution Plan (R2.5 planning and readiness)

**Written**: 2026-09-14, by Codex orchestrator, after R2.4 Supplier IQ / compare / basket fixes
were merged to `main` at `1ec1aa0`.

**Target feature**: `012-reporting-hardening`

**Release**: R2.5 - Reporting + Hardening

**Mode**: Planning and audit only. Do not implement product code in this wave.

## 0. Starting point

R2.4 (`011-optimisation-supplier-iq`) is complete in the task file and merged to `main`.
It added advanced basket optimisation, Supplier IQ scorecards, Supplier IQ recommendation
evidence, anomaly detection v1, E2E/a11y coverage, and user/architecture docs.

R2.5 is the last Phase 2 roadmap chunk before the G2 gate. Per the roadmap, its scope is:

- Scheduled reports
- Digests
- Exports
- Performance tuning
- Accessibility pass
- Security review

Because the constitution requires specification before implementation, Wave 15 creates and
reviews the R2.5 planning package and records the hardening audit scope. It must not add
scheduled-report code, notification jobs, export endpoints, UI screens, or database migrations.

## 1. Non-negotiables

These apply to every lane:

1. Read `.specify/memory/constitution.md` before writing.
2. No implementation code in this wave. Planning docs, audit reports, and task lists only.
3. No Phase 3 integration work. Email ingestion, accounting/POS integrations, public APIs,
   connector framework, and data-freshness engine remain out of scope until G2 is passed.
4. No autonomous purchasing. Reports and digests may recommend review actions only.
5. Any planned report/export containing monetary values must preserve explicit currency.
6. Any planned user-facing text must be assigned to `packages/i18n` in future implementation tasks.
7. Any planned tenant-scoped persistence must include RLS `ENABLE` + `FORCE`, `USING`, and
   `WITH CHECK`, with tenancy resolved only from verified JWT claims.
8. Future frontend implementation under `apps/web/src/**` should be delegated to Agy when
   practical and independently reviewed before landing.
9. If headless Agy delegation is blocked by permission prompts, future delegation plans may use
   `agy --dangerously-skip-permissions` only after explicit user approval, with narrow file scope
   and independent gate reruns.

## 2. Scope for Wave 15

Wave 15 produces the planning and evidence needed to safely start R2.5 implementation later:

1. R2.5 Speckit package under `specs/012-reporting-hardening/`.
2. Cross-model critique reports for reporting, exports, accessibility, security, and performance.
3. A concrete task list split into implementation waves with no file-scope overlap.
4. A release-readiness baseline for the current `main` branch.
5. An explicit G2 evidence checklist showing what can be measured now and what remains product
   telemetry rather than code.

## 3. Task split

### Orchestrator lane - Codex

**File scope**:

- `specs/012-reporting-hardening/spec.md`
- `specs/012-reporting-hardening/plan.md`
- `specs/012-reporting-hardening/research.md`
- `specs/012-reporting-hardening/data-model.md`
- `specs/012-reporting-hardening/quickstart.md`
- `specs/012-reporting-hardening/checklists/requirements.md`
- `specs/012-reporting-hardening/tasks.md`
- `docs/operations/parallel-execution-plan-wave16.md`

**Work**:

1. Draft the R2.5 spec from the roadmap scope.
2. Resolve ambiguity before tasks are written:
   - Are scheduled reports email-only, in-app-only, downloadable-only, or a combination?
   - Which report formats are in scope for R2.5: CSV, PDF, XLSX, or all three?
   - Are digests tenant-wide, per user, per branch, or role-specific?
   - Which surfaces are mandatory for the accessibility pass?
   - Which security scan depth is required before G2?
3. Write research decisions for scheduling, digest scope, export formats, retention, auditability,
   performance budgets, and accessibility/security gates.
4. Write data-model and contract plans only if R2.5 needs new tables or endpoints.
5. Write `tasks.md` with test-first tasks and exact file scopes.
6. Write Wave 16 implementation plan after `tasks.md` exists.

**Gate commands**:

```bash
rg -n "T[O]DO|T[B]D|implement [l]ater|fill in detail[s]" specs/012-reporting-hardening docs/operations/parallel-execution-plan-wave16.md
python3 - <<'PY'
from pathlib import Path
required = [
    "spec.md",
    "plan.md",
    "research.md",
    "data-model.md",
    "quickstart.md",
    "tasks.md",
    "checklists/requirements.md",
]
base = Path("specs/012-reporting-hardening")
missing = [name for name in required if not (base / name).exists()]
if missing:
    raise SystemExit(f"missing: {missing}")
print("R2.5 planning package present")
PY
```

### Product critique lane - Agy

**File scope**:

- `docs/quality/r2.5-reporting-hardening-product-critique-agy.md`

**Work**:

Ask Agy to critique the planned R2.5 user experience, especially:

1. Whether scheduled reports and digests end in clear user actions.
2. Whether exports are operationally useful after printing and sharing.
3. Whether reporting risks becoming a passive dashboard, which violates the constitution.
4. Whether Arabic/RTL reporting and printable layouts are accounted for.
5. Whether existing docs screenshots and workflows expose gaps R2.5 should harden.

**Dispatch note**:

Use Agy for critique only in this wave. If Agy needs to inspect `apps/web/src/**`, keep it
read-only in the prompt. If normal headless mode is blocked by permission prompts, use
`agy --dangerously-skip-permissions` only with the user's prior standing approval and record that
choice in the critique file.

**Gate commands**:

```bash
test -s docs/quality/r2.5-reporting-hardening-product-critique-agy.md
rg -n "action|RTL|export|digest|report|accessibility|recommendation" docs/quality/r2.5-reporting-hardening-product-critique-agy.md
```

### Security and compliance critique lane - Codex Security

**File scope**:

- `docs/quality/r2.5-security-hardening-critique.md`

**Work**:

Run a planning-level security review, not code fixes. Cover:

1. Report/export tenant-isolation risks.
2. Scheduled job impersonation and service-role boundaries.
3. Audit events needed for report generation, schedule changes, export downloads, and digest
   delivery attempts.
4. Secret-handling risks for email delivery or storage.
5. Abuse/rate-limit risks for bulk exports.
6. Append-only and retention requirements.

**Gate commands**:

```bash
test -s docs/quality/r2.5-security-hardening-critique.md
rg -n "tenant|RLS|audit|secret|service-role|export|schedule|retention" docs/quality/r2.5-security-hardening-critique.md
```

### Performance and accessibility critique lane - OpenCode or Codex

**File scope**:

- `docs/quality/r2.5-performance-accessibility-baseline.md`

**Work**:

Produce an audit baseline from the current app. Do not change code. Record:

1. Existing Angular build warnings and style budget warnings.
2. Existing high-value pages for a11y regression coverage.
3. Candidate performance budgets for R2.5 reports and exports.
4. Screenshot/documentation risks for print and mobile readability.
5. Which current warnings are pre-existing and which should become R2.5 tasks.

**Gate commands**:

```bash
pnpm --filter web build
pnpm --filter web lint
test -s docs/quality/r2.5-performance-accessibility-baseline.md
```

### Documentation audit lane - Agy or Codex

**File scope**:

- `docs/quality/r2.5-docs-gap-audit.md`

**Work**:

Review `docs/user/user-documentation.md`, `docs/user/mobile-app-user-documentation.md`,
`docs/architecture/api-specification.md`, `docs/architecture/data-dictionary.md`, and
`docs/quality/test-strategy.md` for R2.5 readiness. Record gaps only; do not update those docs
until R2.5 implementation is scoped.

**Gate commands**:

```bash
test -s docs/quality/r2.5-docs-gap-audit.md
rg -n "report|digest|export|accessibility|security|performance|G2" docs/quality/r2.5-docs-gap-audit.md
```

## 4. Branches

- Planning branch: `codex/wave15-r2-5-planning`
- Optional critique branches if delegated work lands separately:
  - `codex/wave15-r2-5-agy-critique`
  - `codex/wave15-r2-5-security-critique`
  - `codex/wave15-r2-5-performance-a11y-baseline`
  - `codex/wave15-r2-5-docs-audit`

Merge all Wave 15 planning outputs to `main` before any R2.5 implementation starts.

## 5. Review protocol

Each lane must end with:

1. Files changed.
2. Exact gate commands run.
3. Actual pass/fail output summary.
4. Open questions.
5. Recommendation for Wave 16.

The orchestrator reviews every critique and reconciles contradictions in
`specs/012-reporting-hardening/research.md` or `tasks.md`. Do not leave competing instructions
across critique files and task files.

## 6. Wave 16 start criteria

Wave 16 may start only after:

1. `specs/012-reporting-hardening/tasks.md` exists and has no placeholders.
2. Product, security, performance/accessibility, and docs critiques are complete.
3. The orchestrator has converted accepted critique findings into tasks.
4. `main` contains the Wave 15 planning package.
5. The user confirms implementation can start.

Expected Wave 16 shape:

- Orchestrator: migrations, RLS, audit-event contract, release-gate ownership.
- Backend/API delegate: report/export schemas, read endpoints, schedule mutation endpoints, tests.
- Worker delegate: scheduled digest/report generation job if approved by R2.5 plan.
- Frontend delegate - Agy: report/export UI, digest settings UI, i18n, a11y and print-friendly
  rendering.
- QA lane: Playwright, axe, performance, and documentation screenshot automation.

## 7. Known cautions

- Do not build dashboards that only describe historical data. Each reporting surface must include
  a concrete next action, evidence, confidence, and validity where applicable.
- Do not introduce email ingestion or external accounting/POS integration under the reporting
  label; those are Phase 3 roadmap items.
- Do not rely on application filtering for report rows. Any persisted report/export/digest state
  must be tenant-scoped and protected by RLS.
- Do not store generated files in a public bucket unless the plan explicitly proves tenant-safe
  access, expiry, and audit.
- Do not export money without currency, source references, and rule-version context.
- Do not claim G2 is passed from code tests alone. G2 requires product telemetry: workflow
  origination, mobile adoption, and retention.
