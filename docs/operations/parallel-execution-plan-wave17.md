# ProcurePilot — Wave 17 Execution Plan (US1 Completion + US2 Weekly Actionable Digests)

**Written**: 2026-09-16, following the successful completion and verification of Wave 16 on `main`.

**Target feature**: `012-reporting-hardening`

**Release**: R2.5 — Reporting + Hardening (final Phase 2 release before G2)

**Mode**: Implementation.

---

## 0. Starting point

Wave 16 is complete and merged to `main` with 100% passing gates (CI run #35031402198).
The foundations are in place:
- Migrations T001–T005 and seed demo data (T006).
- Contract definition and test-first foundations (T007–T010).
- Schedules CRUD service, window math, and router (T011, T012).
- Extended exports schemas, branch filters, row-cap refusal (T014).
- Read-only Reports center UI slice (T020).

Both start-gate assumptions are confirmed by the user:
1. **Email / SMTP Architecture (R7)**: Standard provider-agnostic SMTP via environment variables
   (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS`, `SMTP_FROM`) with graceful
   degradation to an explicit `email_unconfigured` state when unset (in-app digest viewing remains
   fully functional).
2. **Arabic PDF Shaping & Font (R8)**: Embedded Noto Naskh Arabic (OFL) typeface in
   `apps/api/src/procurepilot_api/assets/fonts/` alongside `arabic-reshaper` and `python-bidi` for
   proper bidirectional Arabic text rendering in ReportLab PDFs.

---

## 1. Non-negotiables

1. Read `.specify/memory/constitution.md` before writing code.
2. Tenant isolation is enforced in the database: every new table/function enforces RLS or pinned
   `tenant_id` parameters.
3. Tenancy comes from the verified JWT claim; cross-tenant reads return "not found", never
   "forbidden" (do not leak existence).
4. No secrets in the repo; SMTP credentials use `SecretStr` and come from environment variables.
5. Every user-facing string comes from `packages/i18n` (en + ar), including report headers and
   email copy.
6. Every monetary value carries an explicit currency.
7. `audit_event` stays append-only.
8. No autonomous purchasing; reporting and digests are advisory only.
9. Frontend implementation under `apps/web/src/**` is delegated to Agy when practical and
   independently reviewed by the orchestrator before landing.
10. Style budget: one stylesheet per component via `styleUrl` (single), under 4 kB.

---

## 2. Scope for Wave 17

Wave 17 delivers the functional core of R2.5 across two user stories:

### User Story 1 Completion (Tasks T013, T015, T016, T017, T018, T019, T021, T022)
- **T013**: Download endpoint (`GET /api/v1/exports/{id}/download`) branch-visibility verification
  and expired/purged status handling.
- **T015**: Runtime i18n loader (`shared/i18n.py`), UTF-8 BOM CSV rendering, declared column schemas
  for `spend_by_supplier` and `alerts_summary`, and Arabic-capable PDF generation (Noto Naskh Arabic,
  `arabic-reshaper`, `python-bidi`).
- **T016**: Background report scheduler worker (`workers/report_scheduler.py`) with `--once` flag,
  `FOR UPDATE SKIP LOCKED` claim loop, deterministic RQ job enqueue, immutable snapshot recording,
  and retention purge pass.
- **T017**: Export worker extensions (`workers/export_worker.py`) for scheduled runs with untrusted
  payload re-derivation, authorization-pinned reader functions, and audit logging.
- **T018**: `PATCH /api/v1/tenant` supporting `reporting_timezone` (owner-only, IANA validated).
- **T019**: Integration tests for report schedules, downloads, and Arabic PDF shaping.
- **T021**: Schedule create form (`/reports/schedule-form`) and Export Savings cross-link.
- **T022**: End-to-end Playwright tests for the scheduled report lifecycle.

### User Story 2: Weekly Actionable Digests (Tasks T023, T024, T025, T026, T027, T028)
- **T023**: Digest subscription CRUD service and content assembly in FR-009 information
  architecture (verified savings hero, pending outcome verifications, pending approvals, anomalies,
  expiring validity), plus default subscription provisioning on member accept.
- **T024**: Digest renderer (multipart HTML + plain text with RTL `dir`/`lang`), SMTP delivery worker
  (`workers/digest_worker.py`), credential redaction, and `email_unconfigured` handling.
- **T025**: Digest router (`/api/v1/digests/subscriptions`, `/api/v1/digests/latest`).
- **T026**: Digest integration tests (`tests/integration/test_digests.py`).
- **T027**: In-app digest view & subscription settings UI (`/reports/digest-settings`).
- **T028**: End-to-end Playwright tests for weekly digest flow.

---

## 3. Lane Allocation & Task Split

### Lane 1: Backend Core & Renderers (Orchestrator Lane)
- **Tasks**: T013, T015, T016, T017, T018, T019
- **Branch**: `codex/wave17-r2-5-us1-backend`
- **Key Files**:
  - `apps/api/pyproject.toml` (add `arabic-reshaper`, `python-bidi`)
  - `apps/api/src/procurepilot_api/assets/fonts/` (Noto Naskh Arabic font)
  - `apps/api/src/procurepilot_api/shared/i18n.py`
  - `apps/api/src/procurepilot_api/modules/exports/renderers.py`
  - `apps/api/src/procurepilot_api/modules/exports/router.py`
  - `apps/api/src/procurepilot_api/modules/tenants/router.py`
  - `apps/api/src/procurepilot_api/workers/report_scheduler.py`
  - `apps/api/src/procurepilot_api/workers/export_worker.py`
  - `apps/api/tests/integration/test_report_schedules.py`
  - `apps/api/tests/integration/test_export_download.py`
- **Gates**:
  ```bash
  pnpm test:api -- apps/api/tests/unit/
  pnpm test:api -- apps/api/tests/integration/test_report_schedules.py
  pnpm test:api -- apps/api/tests/integration/test_export_download.py
  pnpm test:isolation
  pnpm lint
  ```

### Lane 2: Backend Digests (Delegate Lane)
- **Tasks**: T023, T024, T025, T026
- **Branch**: `codex/wave17-r2-5-us2-digests-backend`
- **Key Files**:
  - `apps/api/src/procurepilot_api/config.py` (SMTP settings)
  - `apps/api/src/procurepilot_api/modules/digests/schemas.py`
  - `apps/api/src/procurepilot_api/modules/digests/service.py`
  - `apps/api/src/procurepilot_api/modules/digests/renderer.py`
  - `apps/api/src/procurepilot_api/modules/digests/router.py`
  - `apps/api/src/procurepilot_api/workers/digest_worker.py`
  - `apps/api/tests/integration/test_digests.py`
- **Gates**:
  ```bash
  pnpm test:api -- apps/api/tests/integration/test_digests.py
  pnpm test:isolation
  pnpm lint
  ```

### Lane 3: Frontend Reports & Digests UI (Agy Lane)
- **Tasks**: T021, T027
- **Branch**: `codex/wave17-r2-5-ui`
- **Key Files**:
  - `apps/web/src/app/features/reports/schedule-form/`
  - `apps/web/src/app/features/reports/digest-settings/`
  - `apps/web/src/app/features/savings/export-savings/`
  - `packages/i18n/en.json` & `ar.json`
- **Gates**:
  ```bash
  pnpm --filter web build
  pnpm test:web
  pnpm test:a11y
  pnpm lint
  ```

### Lane 4: E2E Integration & Close-out
- **Tasks**: T022, T028
- **Files**: `apps/web/tests/e2e/reporting-hardening.spec.ts`
- **Gates**:
  ```bash
  pnpm test:e2e -- tests/e2e/reporting-hardening.spec.ts
  pnpm test
  ```

---

## 4. Review Protocol

Before merging each lane into `main`:
1. RLS & Tenancy: Verify that no cross-tenant information is leaked (404 on cross-tenant and
   unauthorized-branch queries).
2. Worker Hardening: Workers must re-derive tenant and membership from the database row, never
   trusting raw queue payload arguments.
3. Typography & RTL: Verify proper Arabic glyph connection and right-to-left layout in generated PDFs
   and emails.
4. Clean lints, clean unit tests, zero accessibility violations.
