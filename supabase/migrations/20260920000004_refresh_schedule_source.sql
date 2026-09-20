-- Link refresh intent to the latest completed supplier catalogue upload.
-- Refresh jobs remain reviewable ingestion work; no price history is overwritten here.

alter table offer_refresh_schedule
  add column if not exists source_import_id uuid;

alter table offer_refresh_schedule
  add constraint offer_refresh_schedule_source_import_fkey
  foreign key (tenant_id, source_import_id)
  references catalogue_imports (tenant_id, id)
  on delete set null;

create index if not exists offer_refresh_schedule_source_import_idx
  on offer_refresh_schedule (tenant_id, source_import_id)
  where source_import_id is not null;
