-- 20260819000011_catalogue_units.sql — task T001
--
-- Base units are a FIXED, data-held set, not free text. Normalising arbitrary unit names is not
-- decidable — "L", "ltr", "litre", "Litre" and "liter" are the same thing to a person and five
-- different strings to a database — and the entire comparison engine in chunk 4.4 rests on this
-- being right. Widening the set is an insert or an is_enabled flip, never a migration.

create table if not exists supported_base_unit (
  code       text primary key,
  label_en   text not null,
  label_ar   text not null,
  -- Only units of the same dimension are comparable. Litres and kilograms describe different
  -- physical quantities, and a comparison across them would be arithmetic without meaning.
  dimension  text not null check (dimension in ('volume', 'mass', 'count')),
  is_enabled boolean not null default true,
  created_at timestamptz not null default now()
);

insert into supported_base_unit (code, label_en, label_ar, dimension) values
  ('litre',      'Litre',      'لتر',      'volume'),
  ('millilitre', 'Millilitre', 'مليلتر',   'volume'),
  ('kilogram',   'Kilogram',   'كيلوجرام', 'mass'),
  ('gram',       'Gram',       'جرام',     'mass'),
  ('each',       'Each',       'وحدة',     'count')
on conflict (code) do nothing;

alter table supported_base_unit enable row level security;

-- Readable by anyone signed in; writes are service-role only, which needs no policy because the
-- service role bypasses RLS. Absence of a write policy IS the denial.
create policy base_unit_read on supported_base_unit
  for select to anon, authenticated using (true);

grant select on supported_base_unit to anon, authenticated;
