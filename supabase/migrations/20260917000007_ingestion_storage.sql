-- 20260917000007_ingestion_storage.sql — task T007, chunk R3.0 (013-automated-ingestion)
--
-- Storage bucket and policies for raw email payloads and ingestion artifacts.
--
-- The raw inbound email (.eml / MIME bytes) is stored in 'ingestion-raw' bucket under
-- `{tenant_id}/raw-email/{message_id}` for audit, compliance, and deterministic replay.
-- Access is restricted to authenticated users within the same tenant, mirroring the
-- established pattern from 20260916000001_exports_storage.sql.

insert into storage.buckets (id, name, public, file_size_limit)
values ('ingestion-raw', 'ingestion-raw', false, 52428800)
on conflict (id) do nothing;

create policy ingestion_raw_tenant_isolation
  on storage.objects
  for all
  to authenticated
  using (
    bucket_id = 'ingestion-raw'
    and current_tenant_id() is not null
    and (storage.foldername(name))[1] = current_tenant_id()::text
  )
  with check (
    bucket_id = 'ingestion-raw'
    and current_tenant_id() is not null
    and (storage.foldername(name))[1] = current_tenant_id()::text
  );

comment on policy ingestion_raw_tenant_isolation on storage.objects is
  'Tenant isolation for raw inbound email payloads in the ingestion-raw bucket (R3.0). Ensures
   raw emails can only be accessed or replayed within the tenant boundary.';
