-- 20260913000005_quality_issue_photo_storage.sql — task T005, chunk R2.3 (Mobile Approvals and
-- Delivery Receipt)
--
-- The Supabase Storage side of quality-issue-photo isolation, mirroring
-- 20260819000020_quotation_storage.sql exactly (specs/010-mobile-approvals-receipt/research.md
-- R3) — this project's one existing precedent for "a tenant-scoped file that must not be readable
-- across tenants even with a guessed path". A separate bucket, not a shared one: these are an
-- unrelated document type with an unrelated lifecycle to quotation documents.
--
-- Paths are allocated by the server under
-- tenants/{tenant_id}/quality-issues/{issue_id}/{filename} — the client never supplies
-- tenant_id, and a readable delivery_quality_issue_photo row must not imply a public object URL.

insert into storage.buckets (id, name, public, file_size_limit)
values ('quality-issue-photos', 'quality-issue-photos', false, 10485760)
on conflict (id) do nothing;

-- storage.objects already ships with RLS enabled and forced by Supabase; only policies are added
-- here. storage.foldername(name) splits the object path on '/' — index 1 (0-based) is the
-- tenant segment of tenants/{tenant_id}/quality-issues/...

create policy quality_issue_photos_tenant_isolation
  on storage.objects
  for all
  to authenticated
  using (
    bucket_id = 'quality-issue-photos'
    and current_tenant_id() is not null
    and (storage.foldername(name))[2] = current_tenant_id()::text
  )
  with check (
    bucket_id = 'quality-issue-photos'
    and current_tenant_id() is not null
    and (storage.foldername(name))[2] = current_tenant_id()::text
  );

comment on policy quality_issue_photos_tenant_isolation on storage.objects is
  'Second isolation boundary for delivery quality-issue photos, alongside
   delivery_quality_issue_photo table RLS — see
   specs/010-mobile-approvals-receipt/research.md R3. A member of tenant A cannot retrieve or
   overwrite a tenant B object even with a known or guessed path.';
