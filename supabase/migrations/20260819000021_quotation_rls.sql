-- 20260819000021_quotation_rls.sql — task T011
--
-- Isolation for every table this chunk adds, in ONE file — same discipline as migration 0016 for
-- chunk 4.2: the rules for a chunk should be readable in one place, because a missing policy is
-- invisible when policies are scattered across the migrations that created the tables.
--
-- All six tables here are uniformly tenant-scoped — unlike chunk 4.2, there is no shared-spine
-- exception in this chunk (no canonical_product equivalent): every entity a quotation touches
-- belongs to exactly one workspace.

do $$
declare t text;
begin
  foreach t in array array[
    'document', 'quotation', 'quotation_line', 'field_extraction', 'extraction_job', 'review_task'
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
