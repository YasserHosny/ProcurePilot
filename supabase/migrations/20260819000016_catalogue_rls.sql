-- 20260819000016_catalogue_rls.sql — task T006
--
-- Isolation for every table this chunk adds, in ONE file.
--
-- Deliberately not spread across the five migrations that create the tables: the rules for a chunk
-- should be readable in one place rather than reconstructed from five, because a missing policy is
-- invisible when the policies are scattered.
--
-- Three details carry the guarantee, and all three are load-bearing (see migration 0004 for the
-- full reasoning — it is unchanged here):
--   1. ENABLE  — turns policies on for ordinary roles
--   2. FORCE   — applies them to the table OWNER too, which is the role migrations run as
--   3. USING and WITH CHECK — reads and writes respectively; USING alone lets a member insert a
--      row carrying another workspace's tenant_id which they then cannot see

-- ---------------------------------------------------------------------------
-- Tenant-scoped tables: the uniform pattern
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'workspace_product', 'pack_definition', 'product_substitute',
    'supplier', 'product_alias', 'import_job'
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
-- canonical_product — the deliberate exception
--
-- Shared across workspaces, so there is no tenant_id to compare and the uniform policy above
-- cannot apply. Its rule is different and is therefore written out rather than generated:
-- readable by anyone signed in, writable only by the service role, which the application uses
-- inside the same transaction that creates the workspace_product referencing it.
--
-- The table holds no workspace-identifying data — brand, name, variant, GTIN, base unit. That is
-- what makes sharing it safe, and it is the thing to re-check if this table ever gains a column.
-- ---------------------------------------------------------------------------
alter table canonical_product enable row level security;
alter table canonical_product force  row level security;

create policy canonical_product_read on canonical_product
  for select to authenticated using (true);

-- No insert, update or delete policy for authenticated. Absence of a policy is the denial.
grant select on canonical_product to authenticated;
grant select, insert, update on canonical_product to service_role;

grant select on supported_base_unit to service_role;

comment on policy canonical_product_read on canonical_product is
  'Shared spine: readable by every workspace, writable by none of them directly. The uniform
   tenant_isolation policy cannot apply because there is no tenant_id — see research.md R5.';
