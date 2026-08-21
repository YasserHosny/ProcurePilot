-- 20260821000034_value_proof_rls.sql
--
-- Isolation for every table this chunk adds, in ONE file — same discipline as migrations 0016,
-- 0021, 0027, and 0029 for chunks 4.2-4.5.
--
-- Four tables are uniformly tenant-scoped. `plan` is the deliberate shared-reference exception,
-- written out rather than generated, exactly mirroring canonical_product's rule (0016): readable
-- by anyone signed in, writable only by the service role.

do $$
declare t text;
begin
  foreach t in array array[
    'purchase_record', 'saving_record', 'export_job', 'billing_account'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('alter table %I force  row level security', t);
    execute format($f$
      create policy tenant_isolation on %I
        for all to authenticated
        using      (tenant_id = current_tenant_id())
        with check  (tenant_id = current_tenant_id())
    $f$, t);
    execute format('grant select, insert, update, delete on %I to authenticated', t);
    execute format('grant select, insert, update, delete on %I to service_role', t);
  end loop;
end $$;

-- ---------------------------------------------------------------------------
-- plan — the deliberate exception, no tenant_id, mirrors canonical_product_read exactly.
-- ---------------------------------------------------------------------------
alter table plan enable row level security;
alter table plan force  row level security;

create policy plan_read on plan
  for select to authenticated using (true);

-- No insert, update or delete policy for authenticated. Absence of a policy is the denial.
grant select on plan to authenticated;
grant select, insert, update on plan to service_role;

comment on policy plan_read on plan is
  'Shared product-tier definitions: readable by every workspace, writable by none of them
   directly. The uniform tenant_isolation policy cannot apply because there is no tenant_id —
   see research.md R5, mirrors canonical_product_read from 20260819000016_catalogue_rls.sql.';
