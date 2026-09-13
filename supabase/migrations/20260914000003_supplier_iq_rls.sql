-- 20260914000003_supplier_iq_rls.sql
--
-- RLS for R2.4 Supplier IQ tables. Both tables are tenant-scoped, select-visible to tenant
-- members, and insertable only by owner/buyer roles through authenticated API paths.

create policy supplier_commercial_term_tenant_select on supplier_commercial_term
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy supplier_commercial_term_owner_buyer_insert on supplier_commercial_term
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  );

create policy supplier_scorecard_snapshot_tenant_select on supplier_scorecard_snapshot
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy supplier_scorecard_snapshot_owner_buyer_insert on supplier_scorecard_snapshot
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and (
      computed_by_membership_id is null
      or computed_by_membership_id = current_membership_id()
    )
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert on supplier_commercial_term to authenticated;
grant select, insert on supplier_scorecard_snapshot to authenticated;
grant select, insert, update, delete on supplier_commercial_term to service_role;
grant select, insert, update, delete on supplier_scorecard_snapshot to service_role;
