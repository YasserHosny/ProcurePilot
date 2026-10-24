-- Saudi workspace reference data; mirror these rows in apps/api/scripts/seed.py.

insert into supported_region (code, label_en, label_ar) values
  ('SA', 'Saudi Arabia', 'المملكة العربية السعودية')
on conflict (code) do nothing;

insert into supported_currency (code, label_en, label_ar, minor_units) values
  ('SAR', 'Saudi Riyal', 'ريال سعودي', 2)
on conflict (code) do nothing;

insert into supported_tax_model (code, label_en, label_ar, region_code) values
  ('sa_vat_standard', 'Saudi VAT (standard)', 'ضريبة القيمة المضافة بالسعودية', 'SA')
on conflict (code) do nothing;
