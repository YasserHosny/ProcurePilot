-- 20261120000100_feedback_api_role.sql — spec 025 hardening (PPS-223), from the 2026-11-20
-- debate-review of the merged feature (findings F1, F2, F3, D1).
--
-- The problem: the API and PostgREST both reached the feedback tables as `authenticated`, so a
-- member's or operator's own access token could call PostgREST directly and skip everything the
-- API enforces — the submit cooldown, server-set timestamps, the upload flow that ties a stored
-- file to its submission, and the audit events on every operator read and change (ADR-027).
--
-- The fix: a dedicated role, `feedback_app`, that only the API can become.
--   * It is a member of `authenticated`, so it keeps every other privilege and RLS policy the API
--     relies on (tenant, membership, audit functions, ...).
--   * The feedback tables' grants and policies move from `authenticated` to `feedback_app`, so a
--     token used directly against PostgREST gets "permission denied" on them.
--   * PostgREST's login role (`authenticator`) can only switch into roles it is a member of
--     (anon, authenticated, service_role). `feedback_app` is never granted to it, so no token —
--     whatever its `role` claim says — can reach this role. Only the API's own DATABASE_URL
--     connection (`postgres`) can `set role feedback_app`.
--
-- Also in this migration:
--   * F1: an attachment's storage path must sit under ITS OWN submission's folder, not just the
--     workspace's, so an attachment row cannot point at another submission's private file.
--   * F2: reading, withdrawing and attaching to one's own feedback require live membership, not
--     only a matching tenant and user in the token.
--   * F3: `created_at` is always the database's own time for rows the API inserts, so it cannot
--     be set to delay the 12-month retention purge.

-- ---------------------------------------------------------------------------
-- The role
-- ---------------------------------------------------------------------------
do $$
begin
  create role feedback_app nologin;
exception when duplicate_object then null;
end
$$;

comment on role feedback_app is
  'The API''s own role for the feedback tables (spec 025). Member of authenticated; never granted
   to authenticator, so PostgREST cannot reach it. 20261120000100.';

grant authenticated to feedback_app;
-- The connection user the API and workers log in as must be able to `set role feedback_app`.
grant feedback_app to postgres;

-- ---------------------------------------------------------------------------
-- feedback_submission: grants and policies move to feedback_app
-- ---------------------------------------------------------------------------
revoke all on feedback_submission from authenticated;

grant select (
  id, tenant_id, submitter_user_id, submitter_membership_id, submitter_name, submitter_email,
  member_role, text_content, category, status, page_path, app_version, locale, is_demo,
  idempotency_key, created_at, status_changed_at, status_changed_by
) on feedback_submission to feedback_app;
grant insert, delete on feedback_submission to feedback_app;
grant update (status, labels, status_changed_at, status_changed_by)
  on feedback_submission to feedback_app;

drop policy feedback_select_own_or_owner on feedback_submission;
create policy feedback_select_own_or_owner on feedback_submission
  for select to feedback_app
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() is not null
    and (submitter_user_id = current_user_id() or current_membership_role() = 'owner')
  );

drop policy feedback_select_operator on feedback_submission;
create policy feedback_select_operator on feedback_submission
  for select to feedback_app
  using (is_platform_operator());

drop policy feedback_insert_member on feedback_submission;
create policy feedback_insert_member on feedback_submission
  for insert to feedback_app
  with check (
    tenant_id = current_tenant_id()
    and submitter_user_id = current_user_id()
    and current_membership_role() is not null
    and member_role = current_membership_role()::text
    and is_demo = (select t.is_demo from tenant t where t.id = tenant_id)
    and status = 'new'
    and labels = '{}'
    and status_changed_at is null
    and status_changed_by is null
  );

drop policy feedback_update_operator on feedback_submission;
create policy feedback_update_operator on feedback_submission
  for update to feedback_app
  using (is_platform_operator())
  with check (is_platform_operator());

drop policy feedback_delete_own_new on feedback_submission;
create policy feedback_delete_own_new on feedback_submission
  for delete to feedback_app
  using (
    tenant_id = current_tenant_id()
    and current_membership_role() is not null
    and submitter_user_id = current_user_id()
    and status = 'new'
  );

-- F3: the API never sends created_at; this makes sure nothing it inserts can either.
create or replace function feedback_submission_server_created_at()
returns trigger
language plpgsql
as $$
begin
  if current_user = 'feedback_app' then
    new.created_at := now();
  end if;
  return new;
end;
$$;

create trigger feedback_submission_server_created_at
  before insert on feedback_submission
  for each row execute function feedback_submission_server_created_at();

-- ---------------------------------------------------------------------------
-- feedback_attachment
-- ---------------------------------------------------------------------------
revoke all on feedback_attachment from authenticated;
grant select, insert on feedback_attachment to feedback_app;

drop policy feedback_attachment_select on feedback_attachment;
create policy feedback_attachment_select on feedback_attachment
  for select to feedback_app
  using (
    (
      tenant_id = current_tenant_id()
      and exists (
        select 1 from feedback_submission s
        where s.id = feedback_attachment.submission_id
          and s.tenant_id = feedback_attachment.tenant_id
      )
    )
    or is_platform_operator()
  );

drop policy feedback_attachment_insert on feedback_attachment;
create policy feedback_attachment_insert on feedback_attachment
  for insert to feedback_app
  with check (
    tenant_id = current_tenant_id()
    and current_membership_role() is not null
    and exists (
      select 1 from feedback_submission s
      where s.id = feedback_attachment.submission_id
        and s.tenant_id = feedback_attachment.tenant_id
        and s.submitter_user_id = current_user_id()
    )
  );

-- F1: bind the stored file to its own submission. The API writes
-- tenants/<tenant>/feedback/<submission>/<uuid>/<name>, so every existing row already conforms.
alter table feedback_attachment drop constraint feedback_attachment_path;
alter table feedback_attachment add constraint feedback_attachment_path check (
  storage_path like 'tenants/' || tenant_id::text || '/feedback/' || submission_id::text || '/%'
);

-- ---------------------------------------------------------------------------
-- Operator read helpers: API-only too (D1). Through PostgREST an operator's token could otherwise
-- read internal labels and workspace names with no audit event.
-- ---------------------------------------------------------------------------
revoke execute on function feedback_operator_labels(uuid) from authenticated;
grant  execute on function feedback_operator_labels(uuid) to feedback_app;

revoke execute on function operator_tenant_names(uuid[]) from authenticated;
grant  execute on function operator_tenant_names(uuid[]) to feedback_app;
