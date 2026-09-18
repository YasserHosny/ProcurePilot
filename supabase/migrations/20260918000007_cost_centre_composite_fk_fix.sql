-- 20260918000007_cost_centre_composite_fk_fix.sql — fixes issue #23
--
-- cost_centre's two composite FKs (chunk R2.0, supabase/migrations/20260822000039_cost_centre.sql)
-- use plain `on delete set null` on a multi-column foreign key. That nulls EVERY referencing
-- column when the trigger fires — including tenant_id, which is `not null` on cost_centre — so
-- deleting the referenced membership or branch fails outright with a not-null violation instead
-- of gracefully clearing the optional reference.
--
-- Same bug pattern found and fixed three times in 013-automated-ingestion and
-- 014-accounting-integration's own new migrations (ingestion_email_log_supplier_fkey,
-- quotation_ingestion_email_fkey, and several R3.1 tables) — cost_centre predates that pattern
-- and was already merged, so it needs its own forward-only migration rather than an in-place
-- edit. PostgreSQL 15+'s column-targeted form fixes this: only the named column is nulled,
-- tenant_id (and the row itself) is left intact. Verified empirically against a real PG17
-- instance for the same fix earlier this session.

alter table cost_centre drop constraint cost_centre_budget_owner_fkey;
alter table cost_centre
  add constraint cost_centre_budget_owner_fkey
    foreign key (tenant_id, budget_owner_membership_id) references membership (tenant_id, id)
    on delete set null (budget_owner_membership_id);

alter table cost_centre drop constraint cost_centre_branch_fkey;
alter table cost_centre
  add constraint cost_centre_branch_fkey
    foreign key (tenant_id, branch_id) references branch (tenant_id, id)
    on delete set null (branch_id);
