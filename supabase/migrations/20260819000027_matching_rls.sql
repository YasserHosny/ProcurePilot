-- 20260819000027_matching_rls.sql — task T010
--
-- Isolation for every table this chunk adds, in ONE file — same discipline as migrations 0016 and
-- 0021 for chunks 4.2 and 4.3.
--
-- All four tables here are uniformly tenant-scoped. The two new embedding columns added in
-- migration 0026 need no separate policy: `tenant_name_embedding` is just another column on the
-- already tenant-isolated `workspace_product` table, and `canonical_embedding` is just another
-- column on the already-shared `canonical_product` table — the existing canonical_product_read
-- policy from migration 0016 already covers it, by design (see research.md R4: the embedding is
-- safe to share only because it is derived exclusively from fields canonical_product already
-- legitimately holds).

do $$
declare t text;
begin
  foreach t in array array[
    'match_candidate', 'match_task', 'match_decision', 'landed_cost'
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
