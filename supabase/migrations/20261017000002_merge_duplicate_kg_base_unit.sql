-- A test fixture inserted `kg` as a second global reference unit, duplicating the
-- canonical `kilogram` unit. Merge persisted foreign keys back to the canonical code and drop
-- the duplicate row. `kg` stays a recognised INPUT alias (normalised to `kilogram` before any
-- FK write — see procurepilot_api.modules.catalogue.units and the extraction worker's
-- _UNIT_ALIASES), so nothing may write the literal `kg` after this migration.
--
-- Atomicity: the whole migration runs in one transaction (Supabase CLI wraps each file), and
-- the DO block below is a single statement, so a failure anywhere rolls everything back —
-- including a trigger that was disabled mid-block (ALTER TABLE ... DISABLE TRIGGER is
-- transactional DDL in Postgres).
insert into supported_base_unit (code, label_en, label_ar, dimension, is_enabled)
values ('kilogram', 'Kilogram', 'كيلوجرام', 'mass', true)
on conflict (code) do nothing;

do $$
declare
  fk record;
  source_column text;
begin
  if not exists (select 1 from supported_base_unit where code = 'kg') then
    return;
  end if;

  for fk in
    select conrelid::regclass as table_name, conkey[1] as attnum
    from pg_constraint
    where contype = 'f' and confrelid = 'supported_base_unit'::regclass
  loop
    select attname into source_column
    from pg_attribute
    where attrelid = fk.table_name and attnum = fk.attnum;

    if fk.table_name = 'purchase_record'::regclass then
      -- purchase_record_locked_by_verified_saving rejects every UPDATE behind a verified
      -- saving. Only touch that financial-integrity guard when there is actually a 'kg'
      -- purchase_record to rewrite; an environment without one never disables it.
      if exists (select 1 from purchase_record where base_unit = 'kg') then
        alter table purchase_record disable trigger purchase_record_locked_by_verified_saving;
        update purchase_record set base_unit = 'kilogram' where base_unit = 'kg';
        alter table purchase_record enable trigger purchase_record_locked_by_verified_saving;
      end if;
    else
      execute format('update %s set %I = %L where %I = %L',
                     fk.table_name, source_column, 'kilogram', source_column, 'kg');
    end if;
  end loop;

  delete from supported_base_unit where code = 'kg';
end $$;
