-- 20260929000000_composite_tenant_foreign_keys_followup.sql
--
-- Closes the last 6 single-column FKs between tenant-scoped tables that
-- 20260927000001_composite_tenant_foreign_keys.sql deliberately deferred (GitHub issue #7). Same
-- gap and same fix as that migration: a single-column FK only proves the parent row exists in SOME
-- tenant, so a tenant-A row can reference a tenant-B parent while passing its own RLS check. These 6
-- were deferred because their parents (document, match_candidate, match_decision, product_alias)
-- first need `unique (tenant_id, id)` for a composite FK to target.
--
-- Adding that unique constraint cannot fail on existing data: `id` is already each parent's
-- primary key, so (tenant_id, id) is unique by construction. The data-integrity question is the
-- children's: the guard below refuses to proceed if any existing child row already references a
-- parent in another tenant, rather than letting the ADD CONSTRAINT fail half-way or silently
-- "repairing" data. Both local and hosted were checked read-only before this migration was written
-- (2026-09-29): zero such rows.
--
-- Each replacement keeps its original constraint name and ON DELETE action. All six originals are
-- ON UPDATE NO ACTION, MATCH SIMPLE, NOT DEFERRABLE, which are also the defaults below. MATCH
-- SIMPLE matters for the nullable columns (selected_match_candidate_id, alias_id,
-- purchase_record.match_decision_id): a NULL reference still skips the check, exactly as before.

do $$
declare
  rec record;
  bad bigint;
begin
  for rec in
    select * from (values
      ('quotation', 'document_id', 'document'),
      ('match_decision', 'selected_match_candidate_id', 'match_candidate'),
      ('landed_cost', 'match_decision_id', 'match_decision'),
      ('match_resolution_idempotency', 'match_decision_id', 'match_decision'),
      ('purchase_record', 'match_decision_id', 'match_decision'),
      ('match_decision', 'alias_id', 'product_alias')
    ) as t(child_table, col, parent_table)
  loop
    execute format(
      'select count(*) from %I c join %I p on p.id = c.%I where c.tenant_id <> p.tenant_id',
      rec.child_table, rec.parent_table, rec.col
    ) into bad;
    if bad > 0 then
      raise exception '%.% has % row(s) referencing a % row in another tenant; resolve before migrating',
        rec.child_table, rec.col, bad, rec.parent_table;
    end if;
  end loop;
end $$;

alter table document        add constraint document_tenant_id_key        unique (tenant_id, id);
alter table match_candidate add constraint match_candidate_tenant_id_key unique (tenant_id, id);
alter table match_decision  add constraint match_decision_tenant_id_key  unique (tenant_id, id);
alter table product_alias   add constraint product_alias_tenant_id_key   unique (tenant_id, id);

do $$
declare
  rec record;
begin
  for rec in
    select * from (values
      ('quotation', 'quotation_document_id_fkey', 'document_id', 'document', 'ON DELETE CASCADE'),
      ('match_decision', 'match_decision_selected_match_candidate_id_fkey',
        'selected_match_candidate_id', 'match_candidate', ''),
      ('landed_cost', 'landed_cost_match_decision_id_fkey', 'match_decision_id', 'match_decision',
        'ON DELETE CASCADE'),
      ('match_resolution_idempotency', 'match_resolution_idempotency_match_decision_id_fkey',
        'match_decision_id', 'match_decision', 'ON DELETE CASCADE'),
      ('purchase_record', 'purchase_record_match_decision_id_fkey', 'match_decision_id',
        'match_decision', ''),
      ('match_decision', 'match_decision_alias_id_fkey', 'alias_id', 'product_alias', '')
    ) as t(child_table, old_conname, col, parent_table, tail)
  loop
    execute format('alter table %I drop constraint %I', rec.child_table, rec.old_conname);
    execute format(
      'alter table %I add constraint %I foreign key (tenant_id, %I) references %I (tenant_id, id) %s',
      rec.child_table, rec.old_conname, rec.col, rec.parent_table, rec.tail
    );
  end loop;
end $$;
