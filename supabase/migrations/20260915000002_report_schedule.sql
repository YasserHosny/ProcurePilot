-- 20260915000002_report_schedule.sql — task T002, chunk R2.5 (012-reporting-hardening)
--
-- report_schedule — a member-owned recurring report definition (spec FR-001/FR-002). The
-- scheduler (T016, Wave 17) claims due rows off the partial index and enqueues an export_job
-- per period; this row is configuration, NOT outcome history — deleting it never deletes
-- artifacts (export_job rows remain, self-describing via schedule_snapshot).
--
-- Isolation follows the R2.4 supplier_iq pattern exactly: tenant-scoped, select for members,
-- owner/buyer write. There is no branch-scoping on schedules themselves: a schedule's filters
-- may name a branch, and the BRANCH filter value is validated against the caller's branch
-- visibility at the API layer (T011) — the same "authorisation in one place" division R2.1
-- established for purchase_request.

create type report_schedule_status as enum ('active', 'paused');

create table if not exists report_schedule (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  created_by_membership_id   uuid not null,

  kind                       text not null,
  format                     export_format not null,
  filters                    jsonb not null,
  filters_digest             text not null,

  weekday                    smallint not null,
  status                     report_schedule_status not null default 'active',
  next_run_at                timestamptz not null,
  last_run_at                timestamptz,
  rule_version               text not null default '',

  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint report_schedule_membership_fkey
    foreign key (tenant_id, created_by_membership_id) references membership (tenant_id, id),

  -- Composite-key pattern (20260822000036): tenant-scoped children reference this table as
  -- (tenant_id, id) so a wrong-tenant parent id can never satisfy the FK.
  constraint report_schedule_tenant_id_key unique (tenant_id, id),

  -- One schedule per member per kind/format/filters combination (data-model.md). The API
  -- computes filters_digest as the sha256 of the canonical filters JSON; the unique key turns
  -- a duplicate create into an honest refusal instead of a silent second schedule.
  constraint report_schedule_owner_unique
    unique (tenant_id, created_by_membership_id, kind, format, filters_digest),

  constraint report_schedule_weekday_range check (weekday between 0 and 6),
  constraint report_schedule_kind_r25
    check (kind in ('savings_ledger', 'spend_by_supplier', 'alerts_summary'))
  -- Deliberately NO (kind, format) CHECK: export_format gains 'csv' in
  -- 20260915000004 and a CHECK in this file could not honestly validate the matrix until
  -- then; the kind/format matrix stays enforced at the API and contract boundary
  -- (data-model.md, research R2).
);

create index if not exists report_schedule_tenant_idx
  on report_schedule (tenant_id, created_by_membership_id, created_at desc);

-- The scheduler's due-list claim (T016): FOR UPDATE SKIP LOCKED over due active rows.
create index if not exists report_schedule_due_idx
  on report_schedule (next_run_at)
  where status = 'active';

comment on table report_schedule is
  'A member-owned recurring report definition (R2.5). Configuration, not history: delete removes
   the schedule, never its artifacts — export_job.schedule_snapshot keeps generated artifacts
   self-describing. Windows derive from tenant.reporting_timezone. See
   specs/012-reporting-hardening/data-model.md.';

alter table report_schedule enable row level security;
alter table report_schedule force  row level security;

create policy report_schedule_tenant_select on report_schedule
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy report_schedule_owner_buyer_insert on report_schedule
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by_membership_id = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  );

create policy report_schedule_owner_buyer_update on report_schedule
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

-- Hard delete is the retirement path for schedules (data-model.md): a schedule is
-- configuration, not outcome; artifacts survive deletion via schedule_snapshot.
create policy report_schedule_owner_buyer_delete on report_schedule
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert, update, delete on report_schedule to authenticated;
grant select, insert, update, delete on report_schedule to service_role;
