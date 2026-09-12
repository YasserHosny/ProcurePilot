-- 20260912000004_low_stock_report_review_fixes.sql
--
-- Two fixes to 20260912000002_low_stock_report.sql found by automated PR review
-- (chatgpt-codex-connector, PR #15) and confirmed on 2026-09-12 — migrations are forward-only,
-- so this corrects the prior file rather than editing it.
--
-- 1. The original grant gave `authenticated` UPDATE and DELETE on low_stock_report. Combined
--    with the tenant-isolation policy's `FOR ALL`, that let any tenant member modify or delete
--    any low-stock report they could see — contradicting the insert-only contract in
--    specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml ("Insert-only (FR-006)") and this
--    table's own migration comment ("Insert-only; no PATCH/DELETE surface this release"). Narrow
--    `authenticated` to what the API surface actually exposes: SELECT and INSERT.
-- 2. `count_remaining` had no floor. The API contract only accepts an unsigned value
--    (`^\d+(\.\d{1,6})?$`), but nothing stopped a direct insert (or a future write path) from
--    persisting a negative one — an impossible inventory fact. Add the same style of check the
--    sibling `purchase_request_line.quantity` column already uses, adjusted for nullability.

revoke update, delete on low_stock_report from authenticated;

alter table low_stock_report
  add constraint low_stock_report_count_remaining_check
  check (count_remaining is null or count_remaining >= 0);
