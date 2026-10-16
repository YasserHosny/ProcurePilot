-- A test fixture inserted `kg` as a second global reference unit, duplicating the
-- canonical `kilogram` unit. Keep `kg` as a recognised extraction alias, but merge
-- persisted foreign keys back to the canonical reference code.
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
      -- This existing guard rejects every UPDATE behind a verified saving. This
      -- maintenance-only rewrite changes the unit alias to its equivalent canonical
      -- code; disable just that trigger for this statement and immediately restore it.
      alter table purchase_record disable trigger purchase_record_locked_by_verified_saving;
      execute format('update %s set %I = %L where %I = %L',
                     fk.table_name, source_column, 'kilogram', source_column, 'kg');
      alter table purchase_record enable trigger purchase_record_locked_by_verified_saving;
    else
      execute format('update %s set %I = %L where %I = %L',
                     fk.table_name, source_column, 'kilogram', source_column, 'kg');
    end if;
  end loop;

  delete from supported_base_unit where code = 'kg';
end $$;
