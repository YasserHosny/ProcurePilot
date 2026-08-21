-- 20260821000029_basket_split_alert_dismissal_rls.sql
--
-- Isolation for both tables this chunk adds, in ONE file — same discipline as migrations 0016,
-- 0021, and 0027 for chunks 4.2-4.4.
--
-- No other table needs a new policy this chunk: offers, recommendations, price history, and live
-- alert conditions are computed at request time from already-isolated workspace_product, supplier,
-- match_decision, and landed_cost rows, protected by their own existing policies.

do $$
declare t text;
begin
  foreach t in array array[
    'basket_split_job', 'alert_dismissal'
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
