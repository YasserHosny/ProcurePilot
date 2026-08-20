-- 0003_tenancy.sql — task T013
--
-- The tenancy core, exactly per specs/001-platform-foundation/data-model.md.
-- RLS policies are applied separately in 0004_rls.sql; this file is structure only.

-- ---------------------------------------------------------------------------
-- Enumerations
-- ---------------------------------------------------------------------------
do $$ begin
  create type member_role as enum ('owner', 'buyer', 'branch_manager', 'approver', 'viewer');
exception when duplicate_object then null; end $$;

do $$ begin
  create type membership_status as enum ('active', 'removed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type platform_invitation_status as enum ('pending', 'spent', 'revoked', 'expired');
exception when duplicate_object then null; end $$;

do $$ begin
  create type member_invitation_status as enum ('pending', 'accepted', 'revoked', 'expired');
exception when duplicate_object then null; end $$;

do $$ begin
  create type audit_outcome as enum ('success', 'refused');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- platform_invitation — admits a business to the pilot (FR-033, FR-034)
--
-- Created BEFORE tenant, because a tenant references the invitation that produced it.
-- Not tenant-scoped: it exists before any workspace does. Service role only.
-- Only the HASH of the token is stored: a database read must not yield a usable invitation.
-- ---------------------------------------------------------------------------
create table if not exists platform_invitation (
  id          uuid primary key default gen_random_uuid(),
  email       text not null,
  token_hash  text not null unique,
  expires_at  timestamptz not null,
  status      platform_invitation_status not null default 'pending',
  spent_at    timestamptz,
  created_at  timestamptz not null default now(),

  -- A spent invitation must record when; an unspent one must not claim to have been spent.
  constraint platform_invitation_spent_at_consistent
    check ((status = 'spent') = (spent_at is not null))
);

create index if not exists platform_invitation_email_idx  on platform_invitation (lower(email));
create index if not exists platform_invitation_status_idx on platform_invitation (status)
  where status = 'pending';

-- ---------------------------------------------------------------------------
-- tenant — the workspace, and the isolation boundary for everything else
-- ---------------------------------------------------------------------------
create table if not exists tenant (
  id                     uuid primary key default gen_random_uuid(),
  name                   text not null check (char_length(name) between 1 and 200),
  slug                   text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$'),

  -- Collected at sign-up. No default: FR-031 forbids inferring any of these three.
  region                 text not null references supported_region(code),
  currency               text not null references supported_currency(code),
  tax_model              text not null references supported_tax_model(code),

  default_locale         text not null default 'en' check (default_locale in ('en', 'ar')),
  platform_invitation_id uuid not null unique references platform_invitation(id),
  created_at             timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- membership — a person's participation in ONE workspace
-- ---------------------------------------------------------------------------
create table if not exists membership (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenant(id) on delete cascade,
  user_id             uuid not null references auth.users(id) on delete cascade,
  email               text not null,
  role                member_role not null,
  mfa_enabled         boolean not null default false,
  preferred_locale    text check (preferred_locale in ('en', 'ar')),
  is_active_workspace boolean not null default false,
  status              membership_status not null default 'active',
  created_at          timestamptz not null default now(),

  constraint membership_one_per_person_per_tenant unique (tenant_id, user_id)
);

-- Exactly one active workspace per person (research R3): the tenant_id claim must be unambiguous.
create unique index if not exists membership_one_active_workspace_idx
  on membership (user_id) where is_active_workspace;

create index if not exists membership_tenant_idx on membership (tenant_id);
create index if not exists membership_user_idx   on membership (user_id);

-- Deliberately NOT a unique constraint on owners: a workspace may have several. The rule is a
-- cardinality MINIMUM (>= 1 active owner), which no unique constraint can express — it is
-- enforced by trigger in 0005_owner_guard.sql.

-- ---------------------------------------------------------------------------
-- member_invitation — admits a person to an EXISTING workspace (FR-009, FR-010)
-- ---------------------------------------------------------------------------
create table if not exists member_invitation (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenant(id) on delete cascade,
  email       text not null,
  role        member_role not null,
  token_hash  text not null unique,
  invited_by  uuid not null references membership(id),
  expires_at  timestamptz not null,
  status      member_invitation_status not null default 'pending',
  created_at  timestamptz not null default now()
);

-- One open invitation per address per workspace; re-inviting requires revoking or expiring first.
create unique index if not exists member_invitation_one_pending_idx
  on member_invitation (tenant_id, lower(email)) where status = 'pending';

create index if not exists member_invitation_tenant_idx on member_invitation (tenant_id);

-- ---------------------------------------------------------------------------
-- audit_event — append-only security and membership history (FR-006, FR-014)
--
-- The first instance of the event-sourced pattern Constitution Principle II requires of outcome
-- data in later chunks. Append-only is enforced by the absence of update/delete policies AND by
-- an explicit revoke in 0004_rls.sql.
-- ---------------------------------------------------------------------------
create table if not exists audit_event (
  id                   bigint generated always as identity primary key,
  tenant_id            uuid references tenant(id) on delete cascade,   -- null: pre-workspace events
  actor_membership_id  uuid references membership(id) on delete set null,
  actor_email          text,          -- preserved even after the membership is removed
  action               text not null, -- e.g. 'member.invited', 'auth.failed', 'tenant.created'
  target               jsonb,
  outcome              audit_outcome not null,
  trace_id             text,
  occurred_at          timestamptz not null default now()
);

create index if not exists audit_event_tenant_time_idx on audit_event (tenant_id, occurred_at desc);
create index if not exists audit_event_action_idx      on audit_event (action);

comment on table audit_event is
  'Append-only. No UPDATE or DELETE is permitted to any role, including service. Never stores credentials.';
