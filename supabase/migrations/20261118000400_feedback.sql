-- 20261118000400_feedback.sql — spec 025 (in-app user feedback), task T010.
--
-- feedback_submission and feedback_attachment: what a workspace member sent from inside the app,
-- who sent it, where, and on which build. Constitution Principle V: isolation is enforced here, by
-- the database. Both tables carry tenant_id with ENABLE + FORCE row level security; every policy
-- that writes has USING and WITH CHECK.
--
-- Who may do what:
--   * any active member inserts their own submission (and attachments for it) in their workspace;
--   * a member reads their own submissions; a workspace owner reads all of the workspace's;
--   * a platform operator (is_platform_operator(), 20261118000200) reads every workspace's and is
--     the only role that updates anything, and then only status and labels (forward-only);
--   * a member may withdraw (delete) their own submission while it is still `new`.
-- Authorisation decisions use the LIVE membership lookup current_membership_role(), not the JWT's
-- member_role claim, so a removed or demoted member loses access on their next statement.
--
-- Operator labels are never shown to tenants (FR-014). That is enforced in the API response
-- model; the table-level SELECT below does not hide the column.

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
do $$
begin
  create type feedback_status as enum ('new', 'reviewed', 'resolved');
exception when duplicate_object then null;
end
$$;

do $$
begin
  create type feedback_category as enum ('bug', 'idea', 'question', 'other');
exception when duplicate_object then null;
end
$$;

do $$
begin
  create type feedback_attachment_kind as enum ('image', 'audio');
exception when duplicate_object then null;
end
$$;

-- ---------------------------------------------------------------------------
-- Label validity: at most 10 labels, each 1 to 40 characters, none null.
-- A CHECK cannot contain a subquery, so the per-element rule lives in an immutable function.
-- ---------------------------------------------------------------------------
create or replace function feedback_labels_valid(p_labels text[])
returns boolean
language sql
immutable
parallel safe
set search_path = pg_catalog
as $$
  select p_labels is not null
     and cardinality(p_labels) <= 10
     and not exists (
       select 1 from unnest(p_labels) as l
       where l is null or char_length(l) not between 1 and 40
     );
$$;

revoke execute on function feedback_labels_valid(text[]) from public, anon;
grant  execute on function feedback_labels_valid(text[]) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- feedback_submission
-- ---------------------------------------------------------------------------
create table feedback_submission (
  id                       uuid primary key default gen_random_uuid(),
  tenant_id                uuid not null references tenant (id) on delete cascade,
  submitter_user_id        uuid not null,
  submitter_membership_id  uuid null,
  submitter_name           text not null,
  submitter_email          text not null,
  member_role              text not null
    check (member_role in ('owner', 'buyer', 'branch_manager', 'approver', 'viewer')),
  text_content             text not null
    check (char_length(text_content) between 1 and 2000 and btrim(text_content) <> ''),
  category                 feedback_category null,
  status                   feedback_status not null default 'new',
  labels                   text[] not null default '{}'
    check (feedback_labels_valid(labels)),
  page_path                text not null check (char_length(page_path) <= 2000),
  app_version              text not null,
  locale                   text not null check (locale in ('en', 'ar')),
  is_demo                  boolean not null,
  idempotency_key          uuid not null,
  created_at               timestamptz not null default now(),
  status_changed_at        timestamptz null,
  status_changed_by        uuid null,
  constraint feedback_submission_tenant_id_key unique (tenant_id, id),
  constraint feedback_submission_idempotency_key unique (tenant_id, idempotency_key),
  -- Composite FK: the membership must belong to the same tenant. Only the membership column is
  -- nulled when the membership is deleted (tenant_id is NOT NULL).
  constraint feedback_submission_membership_fk
    foreign key (tenant_id, submitter_membership_id)
    references membership (tenant_id, id) on delete set null (submitter_membership_id)
);

comment on table feedback_submission is
  'In-app feedback from a workspace member (spec 025). Tenant-scoped, forced RLS. Status moves
   forward only and only an operator may change status or labels. 20261118000400.';
comment on column feedback_submission.labels is
  'Operator-only triage labels. Never exposed to submitters or owners (FR-014).';
comment on column feedback_submission.is_demo is
  'tenant.is_demo at submit time; later changes to the tenant do not rewrite history.';

create index feedback_submission_tenant_created_idx
  on feedback_submission (tenant_id, created_at desc);
-- Own list and the per-submitter cooldown lookup.
create index feedback_submission_submitter_created_idx
  on feedback_submission (tenant_id, submitter_user_id, created_at desc);
create index feedback_submission_status_created_idx
  on feedback_submission (status, created_at desc);
create index feedback_submission_category_idx
  on feedback_submission (category);
-- Retention purge.
create index feedback_submission_created_idx
  on feedback_submission (created_at);

-- ---------------------------------------------------------------------------
-- State machine and column restriction.
--
--   new -> reviewed -> resolved
--   new ------------> resolved
--
-- No backward moves, and no change to any column except status, labels, status_changed_at and
-- status_changed_by (plus submitter_membership_id to null, the FK's delete action). The two
-- status_changed_* columns are written by this trigger, never by the caller: a caller-supplied
-- value is overwritten. Applies to every role, service role included.
-- ---------------------------------------------------------------------------
create or replace function feedback_submission_guard()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  -- submitter_membership_id may only go to null: that is the membership FK's
  -- `on delete set null (submitter_membership_id)` action when the member's membership is deleted.
  if (to_jsonb(new) - array['status', 'labels', 'status_changed_at', 'status_changed_by',
                            'submitter_membership_id'])
     is distinct from
     (to_jsonb(old) - array['status', 'labels', 'status_changed_at', 'status_changed_by',
                            'submitter_membership_id'])
     or (new.submitter_membership_id is distinct from old.submitter_membership_id
         and new.submitter_membership_id is not null) then
    raise exception 'feedback_submission: only status and labels may change'
      using errcode = 'check_violation';
  end if;

  if new.status is distinct from old.status then
    if not (
         (old.status = 'new'      and new.status in ('reviewed', 'resolved'))
      or (old.status = 'reviewed' and new.status = 'resolved')
    ) then
      raise exception 'feedback_submission: status cannot move from % to %', old.status, new.status
        using errcode = 'check_violation';
    end if;
    new.status_changed_at := now();
    -- Null for a server-side caller with no JWT claims (service role, postgres).
    new.status_changed_by := nullif(
      nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub', ''
    )::uuid;
  else
    new.status_changed_at := old.status_changed_at;
    new.status_changed_by := old.status_changed_by;
  end if;

  return new;
end;
$$;

create trigger feedback_submission_guard
  before update on feedback_submission
  for each row execute function feedback_submission_guard();

-- ---------------------------------------------------------------------------
-- RLS — ENABLE + FORCE, USING and WITH CHECK
-- ---------------------------------------------------------------------------
alter table feedback_submission enable row level security;
alter table feedback_submission force  row level security;

create policy feedback_select_own_or_owner on feedback_submission
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (submitter_user_id = current_user_id() or current_membership_role() = 'owner')
  );

create policy feedback_select_operator on feedback_submission
  for select to authenticated
  using (is_platform_operator());

-- The row must describe the caller truthfully: their own user id, their live role, their
-- workspace's demo flag, a fresh `new` status with no labels and no status history.
create policy feedback_insert_member on feedback_submission
  for insert to authenticated
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

create policy feedback_update_operator on feedback_submission
  for update to authenticated
  using (is_platform_operator())
  with check (is_platform_operator());

create policy feedback_delete_own_new on feedback_submission
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and submitter_user_id = current_user_id()
    and status = 'new'
  );

-- Members hold the column grant but no update policy applies to them, so their updates change
-- nothing. Column-level, so the trigger's immutable columns are not even grantable.
revoke all on feedback_submission from public, anon, authenticated;
grant select, insert, delete on feedback_submission to authenticated;
grant update (status, labels, status_changed_at, status_changed_by)
  on feedback_submission to authenticated;
grant select, insert, update, delete on feedback_submission to service_role;

-- ---------------------------------------------------------------------------
-- feedback_attachment
-- ---------------------------------------------------------------------------
create table feedback_attachment (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null,
  submission_id  uuid not null,
  kind           feedback_attachment_kind not null,
  storage_path   text not null,
  content_type   text not null,
  size_bytes     integer not null,
  display_order  smallint not null,
  created_at     timestamptz not null default now(),
  -- Composite FK: an attachment can only hang off a submission of its own tenant.
  constraint feedback_attachment_submission_fk
    foreign key (tenant_id, submission_id)
    references feedback_submission (tenant_id, id) on delete cascade,
  constraint feedback_attachment_order_unique unique (submission_id, kind, display_order),
  constraint feedback_attachment_order_range check (display_order between 0 and 4),
  constraint feedback_attachment_audio_order check (kind <> 'audio' or display_order = 0),
  constraint feedback_attachment_size check (
    size_bytes > 0
    and ((kind = 'image' and size_bytes <= 5242880)
      or (kind = 'audio' and size_bytes <= 10485760))
  ),
  constraint feedback_attachment_path check (
    storage_path like 'tenants/' || tenant_id::text || '/feedback/%'
  )
);

comment on table feedback_attachment is
  'Image or voice-note attached to a feedback_submission (spec 025). At most 5 images
   (display_order 0-4) and 1 audio per submission. Tenant-scoped, forced RLS. 20261118000400.';

-- At most one audio per submission.
create unique index feedback_attachment_one_audio_idx
  on feedback_attachment (submission_id) where kind = 'audio';
create index feedback_attachment_submission_idx
  on feedback_attachment (tenant_id, submission_id);

alter table feedback_attachment enable row level security;
alter table feedback_attachment force  row level security;

-- Visibility follows the parent submission: the sub-select runs under feedback_submission's own
-- RLS, so an attachment is visible exactly when its submission is (own, owner, or operator).
create policy feedback_attachment_select on feedback_attachment
  for select to authenticated
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

-- Only the submission's own submitter, in the same workspace, adds attachments.
create policy feedback_attachment_insert on feedback_attachment
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and exists (
      select 1 from feedback_submission s
      where s.id = feedback_attachment.submission_id
        and s.tenant_id = feedback_attachment.tenant_id
        and s.submitter_user_id = current_user_id()
    )
  );

-- No update policy and no update grant. No client delete policy: rows go away by cascade when the
-- submission is withdrawn or purged, or by service_role.
revoke all on feedback_attachment from public, anon, authenticated;
grant select, insert on feedback_attachment to authenticated;
grant select, insert, update, delete on feedback_attachment to service_role;
