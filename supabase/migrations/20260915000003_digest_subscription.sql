-- 20260915000003_digest_subscription.sql — task T003, chunk R2.5 (012-reporting-hardening)
--
-- digest_subscription — a per-member weekly digest definition (spec FR-008, research R1:
-- per-member, never tenant-wide, so an owner is not pushed a branch buyer's digest). The
-- member owns the row; the owner can SEE all rows in the tenant for visibility but never
-- modify them — the first table in the schema whose RLS splits read visibility from write
-- ownership this way, because a digest is the only entity whose owner is a person, not a
-- workspace.
--
-- Provisioning (one active subscription per new membership, in-app channel by default) is a
-- service behaviour on top of this table (Wave 17, T024) — the table does not force it.

create type digest_channel as enum ('email', 'in_app');
create type digest_subscription_status as enum ('active', 'paused');

create table if not exists digest_subscription (
  id                     uuid primary key default gen_random_uuid(),
  tenant_id              uuid not null references tenant(id) on delete cascade,
  membership_id          uuid not null,

  kind                   text not null default 'weekly_digest',
  locale                 text not null default 'en',
  filters                jsonb not null default '{}'::jsonb,
  filters_digest         text not null,

  channel                digest_channel not null default 'in_app',
  status                 digest_subscription_status not null default 'active',

  next_run_at            timestamptz not null,
  last_delivery_at       timestamptz,
  last_delivery_status   text,

  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),

  constraint digest_subscription_membership_fkey
    foreign key (tenant_id, membership_id) references membership (tenant_id, id),

  constraint digest_subscription_owner_unique
    unique (tenant_id, membership_id, kind, filters_digest),

  constraint digest_subscription_kind_r25 check (kind = 'weekly_digest'),
  constraint digest_subscription_locale check (locale in ('en', 'ar')),
  constraint digest_subscription_last_delivery_status
    check (last_delivery_status is null or last_delivery_status in ('succeeded', 'failed', 'email_unconfigured'))
);

create index if not exists digest_subscription_tenant_idx
  on digest_subscription (tenant_id, membership_id, created_at desc);

-- The digest scheduler's due-list claim (Wave 17): active rows due now, plus the skip rule
-- for subscriptions whose membership is no longer active (data-model.md).
create index if not exists digest_subscription_due_idx
  on digest_subscription (next_run_at)
  where status = 'active';

comment on table digest_subscription is
  'A per-member weekly digest definition (R2.5). Member-owned rows; owners may select all rows
   in the tenant for visibility only. locale drives the digest render language (FR-029);
   filters carry the optional branch_id. See specs/012-reporting-hardening/data-model.md.';

alter table digest_subscription enable row level security;
alter table digest_subscription force  row level security;

-- Members see only their own rows; owners see every row in the tenant (visibility, not
-- control — data-model.md). The OR shape keeps a de-activated membership able to read its
-- own rows while the scheduler skips it (status filter is the scheduler's concern).
create policy digest_subscription_member_select on digest_subscription
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and (membership_id = current_membership_id() or current_member_role() = 'owner')
  );

create policy digest_subscription_member_insert on digest_subscription
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and membership_id = current_membership_id()
  );

create policy digest_subscription_member_update on digest_subscription
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and membership_id = current_membership_id()
  )
  with check (
    tenant_id = current_tenant_id()
    and membership_id = current_membership_id()
  );

create policy digest_subscription_member_delete on digest_subscription
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and membership_id = current_membership_id()
  );

grant select, insert, update, delete on digest_subscription to authenticated;
grant select, insert, update, delete on digest_subscription to service_role;
