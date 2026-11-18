-- 20261118000500_feedback_storage.sql — spec 025 (in-app user feedback), task T011.
--
-- Supabase Storage side of feedback attachments. Private bucket, 10 MiB object limit (the larger
-- of the 5 MiB image and 10 MiB audio caps; the API enforces the per-kind limit).
--
-- Paths are allocated by the server under tenants/{tenant_id}/feedback/{submission_id}/{filename},
-- so index 2 of storage.foldername(name) (1-based, as in the quotation and quality-issue buckets)
-- is the tenant segment.
--
-- Unlike those buckets this one is INSERT-ONLY for clients: a member may upload into their own
-- workspace's prefix and nothing else. There is no select, update or delete policy, so reads,
-- deletes and signed URLs run through the API with the service-role client after the row-level
-- access check on feedback_attachment. A guessed path is therefore unreadable even within the
-- member's own workspace.

insert into storage.buckets (id, name, public, file_size_limit)
values ('feedback-attachments', 'feedback-attachments', false, 10485760)
on conflict (id) do nothing;

create policy feedback_attachments_tenant_insert
  on storage.objects
  for insert
  to authenticated
  with check (
    bucket_id = 'feedback-attachments'
    and current_tenant_id() is not null
    and (storage.foldername(name))[2] = current_tenant_id()::text
  );

-- storage.objects already grants authenticated the table privileges (see
-- 20260819000020_quotation_storage.sql); with no select/update/delete policy for this bucket,
-- those operations match no rows.

comment on policy feedback_attachments_tenant_insert on storage.objects is
  'Insert-only tenant-prefix policy for feedback attachments (spec 025). No client select,
   update or delete: reads and deletes go through the API with the service-role client.
   20261118000500.';
