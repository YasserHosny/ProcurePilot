-- 20260916000001_exports_storage.sql — Wave 18 T036 (012-reporting-hardening security review)
--
-- The Supabase Storage side of export-artifact isolation. `ExportService`/`ExportStorage`
-- (apps/api/src/procurepilot_api/modules/exports/) have referenced `settings.supabase_exports_
-- bucket` (default 'exports') since Wave 16, and export downloads have been protected by
-- short-lived signed URLs since T005/Wave 16 — but no migration ever created the bucket itself
-- or a storage.objects policy for it, unlike every other tenant-scoped bucket in this codebase
-- (quotation-documents: 20260819000020, quality-issue-photos: 20260913000005). A fresh
-- environment applying every migration in order would have no 'exports' bucket at all, and even
-- once created by hand, the bucket would have had no second isolation boundary beyond the
-- signed-URL check in ExportService.create_download_url — exactly the gap
-- 20260819000020's own comment warns about: "a leaked or guessed object path would bypass table
-- RLS entirely if the bucket itself had no policy."
--
-- Paths are allocated by ExportStorage.upload() as `{tenant_id}/savings/{job_id}.{format}` —
-- NOT the `tenants/{tenant_id}/...` shape the other two buckets use, so the tenant segment is
-- storage.foldername(name)'s first (1-indexed) element here, not its second.

insert into storage.buckets (id, name, public, file_size_limit)
values ('exports', 'exports', false, 52428800)
on conflict (id) do nothing;

-- storage.objects already ships with RLS enabled and forced by Supabase; only the policy is
-- added here.

create policy exports_tenant_isolation
  on storage.objects
  for all
  to authenticated
  using (
    bucket_id = 'exports'
    and current_tenant_id() is not null
    and (storage.foldername(name))[1] = current_tenant_id()::text
  )
  with check (
    bucket_id = 'exports'
    and current_tenant_id() is not null
    and (storage.foldername(name))[1] = current_tenant_id()::text
  );

comment on policy exports_tenant_isolation on storage.objects is
  'Second isolation boundary for generated export artifacts, alongside the signed-URL check in
   ExportService.create_download_url and export_job RLS — see 20260819000020_quotation_storage.sql
   for the original precedent this mirrors. A member of tenant A cannot retrieve or overwrite a
   tenant B export object even with a known or guessed path. The worker and API both connect with
   the service-role key for storage operations (service_role already has storage.objects access
   granted by Supabase by default), so this policy is a defense-in-depth backstop covering any
   future code path that reaches Storage as the authenticated role instead.';
