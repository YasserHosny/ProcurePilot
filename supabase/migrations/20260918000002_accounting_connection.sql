-- 20260918000002_accounting_connection.sql — task T004, chunk R3.1 (014-accounting-integration)
--
-- accounting_connection — one workspace's authorized link to one external accounting account
-- (spec: "Accounting Connection"). Exactly one non-disconnected connection per tenant this
-- release; a tenant may disconnect and reconnect, creating a new row each time so a prior
-- account's synced history never merges with a new one (spec edge case).
--
-- access_token/refresh_token hold live OAuth credentials for a third party financial system.
-- RLS is row-scoped, not column-scoped, so "SELECT for any authenticated member" (the connection
-- status visibility FR-002 asks for) would otherwise also expose these secrets to every member
-- who can merely read the tenant's connection status. Column-level GRANTs close that gap:
-- `authenticated` may WRITE the tokens once, at connect time (INSERT only, gated by the
-- owner-only insert policy below, through the normal _authenticated_db path — no service-role
-- carve-out needed for connect), but can never SELECT or UPDATE them afterward. Only
-- `service_role` (the sync worker's own path, T018) ever reads or refreshes an existing token.

create type accounting_provider as enum ('quickbooks');
create type accounting_connection_status as enum ('active', 'needs_reauth', 'disconnected');

create table if not exists accounting_connection (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenant(id) on delete cascade,

  provider          accounting_provider not null,
  realm_id          text not null,
  display_name      text not null,
  access_token      text not null,
  refresh_token     text not null,

  status            accounting_connection_status not null default 'active',
  connected_by      uuid not null,
  connected_at      timestamptz not null default now(),
  last_synced_at    timestamptz,
  disconnected_at   timestamptz,

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  constraint accounting_connection_membership_fkey
    foreign key (tenant_id, connected_by) references membership (tenant_id, id),

  constraint accounting_connection_tenant_id_key unique (tenant_id, id),

  constraint accounting_connection_disconnected_at_only_when_disconnected
    check ((status = 'disconnected') = (disconnected_at is not null))
);

-- At most one non-disconnected connection per tenant at a time (data-model.md).
create unique index if not exists accounting_connection_one_active_per_tenant
  on accounting_connection (tenant_id)
  where status <> 'disconnected';

create index if not exists accounting_connection_tenant_idx
  on accounting_connection (tenant_id, created_at desc);

comment on table accounting_connection is
  'A workspace''s authorized link to one external accounting account (R3.1). Disconnecting never
   deletes the row — history stays queryable. access_token/refresh_token are service_role-only
   columns (see column comment above); every other column is member-readable.
   See specs/014-accounting-integration/data-model.md.';

alter table accounting_connection enable row level security;
alter table accounting_connection force  row level security;

create policy accounting_connection_tenant_select on accounting_connection
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy accounting_connection_owner_insert on accounting_connection
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and connected_by = current_membership_id()
    and current_member_role() = 'owner'
  );

create policy accounting_connection_owner_update on accounting_connection
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  );

-- The sync worker also updates this row (last_synced_at on every sync; status -> 'needs_reauth'
-- on a failed token refresh, FR-002/spec Acceptance Scenario 1.4) — a system-triggered write via
-- the same tenant-scoped `authenticated` session as synced_vendor/synced_bill (see that
-- migration's header), which never carries a member_role claim. `current_member_role() is null`
-- is what distinguishes that worker session from a real member's own session here (every real
-- member session sets member_role; a worker session deliberately never does), so a non-owner
-- member's own session can never satisfy this policy — only the worker's can.
create policy accounting_connection_worker_update on accounting_connection
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  );

-- Column-level split (see file header): `authenticated` never gets access_token/refresh_token
-- in SELECT or UPDATE — only INSERT, for the one-time write at connect time. A refreshed token
-- (research.md R4) is instead written through a literal service_role connection — see
-- sync_service.py's own _service_role_db helper — the one write this feature makes that
-- genuinely needs to bypass RLS rather than act as a tenant-scoped authenticated session,
-- because no authenticated session (member or worker) is ever allowed to see or set a token.
grant select (
  id, tenant_id, provider, realm_id, display_name, status, connected_by, connected_at,
  last_synced_at, disconnected_at, created_at, updated_at
) on accounting_connection to authenticated;

grant insert (
  id, tenant_id, provider, realm_id, display_name, access_token, refresh_token, status,
  connected_by, connected_at
) on accounting_connection to authenticated;

grant update (
  status, disconnected_at, updated_at, last_synced_at
) on accounting_connection to authenticated;

grant select, insert, update on accounting_connection to service_role;
