-- 20260918000001_purchase_record_composite_key.sql — task T003, chunk R3.1 (014-accounting-integration)
--
-- purchase_record predates the composite-key-FK convention established in 011/012/013
-- (supplier_commercial_term, supplier_scorecard_snapshot, ingestion_email_log, report_schedule,
-- etc.): every cross-module FK into a tenant-scoped table pins to that table's own
-- (tenant_id, id) unique key, never a bare id, so a cross-tenant reference can never be inserted
-- even from a service-role path that bypasses RLS. purchase_bill_match (T007) is the first thing
-- to reference purchase_record from outside its own module, so this gap has to close now.
--
-- Pure additive constraint on an existing unique column (id is already the primary key) — no
-- backfill, no data migration, cannot fail against existing rows.

alter table purchase_record
  add constraint purchase_record_tenant_id_key unique (tenant_id, id);
