# Quickstart: Reporting and Hardening

This quickstart describes the intended R2.5 validation path once tasks are implemented.

## 1. Apply migrations and seed

```bash
pnpm db:migrate
pnpm db:seed
```

Seed data must include verified savings and purchase records across two periods, at least one
branch, alert conditions triggering each anomaly kind, offers whose validity ends within seven
days, and one demo report schedule and digest subscription whose `next_run_at` is in the past.

## 2. Configure email delivery (or verify honest absence)

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` in the
environment to deliver digests by email, or leave them unset and verify the in-app digest with an
explicit "email not configured" status.

## 3. Run the scheduler once and verify scheduled generation

```bash
docker compose up --build api web redis export-worker report-scheduler digest-worker
docker compose exec report-scheduler python -m procurepilot_api.workers.report_scheduler --once
```

Expected: one artifact per due schedule and one digest per due subscription; a second `--once`
run produces no duplicates.

## 4. Run API checks

```bash
pnpm test:api -- apps/api/tests/contract/test_reporting_contract.py
pnpm test:api -- apps/api/tests/integration/test_reporting_isolation.py
pnpm test:api -- apps/api/tests/integration/test_report_schedules.py
pnpm test:api -- apps/api/tests/integration/test_export_download.py
pnpm test:api -- apps/api/tests/integration/test_digests.py
pnpm test:isolation
```

Expected: contract, schedule, download, digest, and isolation tests pass; cross-tenant references
return not found; tenant-pinned reader functions see only their tenant.

## 5. Run web, a11y, and performance checks

```bash
pnpm --filter web build
pnpm test:web
pnpm test:e2e -- apps/web/tests/e2e/reporting-hardening.spec.ts
pnpm test:a11y
```

Expected: production build with zero budget warnings (initial bundle ≤ 500 kB raw); Reports
center and digest settings work in English and Arabic with zero automated WCAG 2.1 AA violations;
keyboard-only journeys pass in both directions; the compare-grid recalculation regression test
reports under 150 ms.

## 6. Manual smoke

1. Open the Reports center from the sidebar.
2. Create a weekly savings-ledger schedule for the coming weekday; pause and resume it.
3. Trigger the scheduler (or wait for the cadence); refresh the Reports center.
4. Download the artifact as XLSX and as CSV; confirm explicit currency columns and row counts.
5. Request an on-demand spend-by-supplier export filtered by branch; download it.
6. Open digest settings; subscribe; trigger the digest; follow each deep link.
7. Switch the workspace locale to Arabic; regenerate a PDF; confirm right-to-left, catalogue
   labels, and legible Arabic text.
8. Verify an over-cap export request is refused with a structured error.

No step should create a purchase, approval, order, payment, or supplier message.
