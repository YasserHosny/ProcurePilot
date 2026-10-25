-- Ireland workspace reference data; mirror these rows in apps/api/scripts/seed.py.

insert into supported_region (code, label_en, label_ar) values
  ('IE', 'Ireland', 'أيرلندا')
on conflict (code) do nothing;

insert into supported_currency (code, label_en, label_ar, minor_units) values
  ('EUR', 'Euro', 'يورو', 2)
on conflict (code) do nothing;

insert into supported_tax_model (code, label_en, label_ar, region_code) values
  ('ie_vat_standard', 'Irish VAT (standard)', 'ضريبة القيمة المضافة بأيرلندا', 'IE')
on conflict (code) do nothing;
