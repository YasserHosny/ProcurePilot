-- 20260819000020_quotation_storage.sql — task T010
--
-- The Supabase Storage side of quotation-document isolation.
--
-- Postgres RLS on `document` protects the METADATA row. It says nothing about the file bytes
-- sitting in Storage — a leaked or guessed object path would bypass table RLS entirely if the
-- bucket itself had no policy. Uploaded quotations may carry another business's confidential
-- pricing, so this is a second, independent isolation boundary, not a formality.
--
-- Paths are allocated by the server under `tenants/{tenant_id}/quotations/{document_id}/{filename}`
-- (see research.md R1, R8) — the client never supplies tenant_id, and a readable `document` row
-- must not imply a public object URL.

insert into storage.buckets (id, name, public, file_size_limit)
values ('quotation-documents', 'quotation-documents', false, 52428800)
on conflict (id) do nothing;

-- storage.objects already ships with RLS enabled and forced by Supabase; only policies are added
-- here. `storage.foldername(name)` splits the object path on '/' — index 1 (0-based) is the
-- tenant segment of `tenants/{tenant_id}/quotations/...`.

create policy quotation_documents_tenant_isolation
  on storage.objects
  for all
  to authenticated
  using (
    bucket_id = 'quotation-documents'
    and current_tenant_id() is not null
    and (storage.foldername(name))[2] = current_tenant_id()::text
  )
  with check (
    bucket_id = 'quotation-documents'
    and current_tenant_id() is not null
    and (storage.foldername(name))[2] = current_tenant_id()::text
  );

grant select, insert, update, delete on storage.objects to authenticated;

comment on policy quotation_documents_tenant_isolation on storage.objects is
  'Second isolation boundary for quotation source files, alongside document table RLS — see
   specs/003-quotation-inbox-extraction/research.md R8. A member of tenant A cannot retrieve or
   overwrite a tenant B object even with a known or guessed path.';
