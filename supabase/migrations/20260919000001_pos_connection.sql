-- 20260919000001_pos_connection.sql — task T004, chunk R3.2 (015-pos-inventory-integration)
--
-- pos_connection — one workspace's authorized link to one external POS/inventory account
-- (spec: "POS Connection"). Exactly one non-disconnected connection per tenant this release; a
-- tenant may disconnect and reconnect, always creating a new row (never reactivating the old
-- one) so connection history stays queryable as its own audit trail (FR-010) — see
-- research.md R8 for why the *signal* table below deliberately does NOT key off this row's id.
--
-- access_token/refresh_token hold live OAuth credentials for a third-party POS system. RLS is
-- row-scoped, not column-scoped, so "SELECT for any authenticated member" (the connection status
-- visibility FR-001 asks for) would otherwise also expose these secrets to every member who can
-- merely read the tenant's connection status. Column-level GRANTs close that gap, identical to
-- accounting_connection's own precedent (20260918000002): `authenticated` may WRITE the tokens
-- once, at connect time (INSERT only, gated by the owner-only insert policy below), but can never
-- SELECT or UPDATE them afterward. Only `service_role` (the sync worker's token-refresh path)
-- ever reads or refreshes an existing token.

create type pos_provider as enum ('square');
create type pos_connection_status as enum ('active', 'needs_reauth', 'disconnected');

create table if not exists pos_connection (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,

  provider              pos_provider not null,
  external_account_id   text not null,
  external_account_name text not null,
  access_token          text not null,
  refresh_token         text not null,

  status                pos_connection_status not null default 'active',
  connected_by          uuid not null,
  connected_at          timestamptz not null default now(),
  last_synced_at        timestamptz,
  disconnected_at       timestamptz,

  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  constraint pos_connection_membership_fkey
    foreign key (tenant_id, connected_by) references membership (tenant_id, id),

  constraint pos_connection_tenant_id_key unique (tenant_id, id),

  constraint pos_connection_disconnected_at_only_when_disconnected
    check ((status = 'disconnected') = (disconnected_at is not null))
);

-- At most one non-disconnected connection per tenant at a time (data-model.md).
create unique index if not exists pos_connection_one_active_per_tenant
  on pos_connection (tenant_id)
  where disconnected_at is null;

create index if not exists pos_connection_tenant_idx
  on pos_connection (tenant_id, created_at desc);

comment on table pos_connection is
  'A workspace''s authorized link to one external POS/inventory account (R3.2). Disconnecting
   never deletes the row — history stays queryable, and a reconnect always inserts a new row
   rather than reactivating this one (research.md R8). access_token/refresh_token are
   service_role-only columns (see column comment above); every other column is member-readable.
   See specs/015-pos-inventory-integration/data-model.md.';

alter table pos_connection enable row level security;
alter table pos_connection force  row level security;

create policy pos_connection_tenant_select on pos_connection
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy pos_connection_owner_insert on pos_connection
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and connected_by = current_membership_id()
    and current_member_role() = 'owner'
  );

create policy pos_connection_owner_update on pos_connection
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
-- on a failed token refresh, FR-008) — a system-triggered write via the same tenant-scoped
-- `authenticated` session as synced_product_signal (see that migration's header), which never
-- carries a member_role claim. `current_member_role() is null` is what distinguishes that worker
-- session from a real member's own session here.
create policy pos_connection_worker_update on pos_connection
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  );

-- Column-level split (see file header): `authenticated` never gets access_token/refresh_token in
-- SELECT or UPDATE — only INSERT, for the one-time write at connect time. A refreshed token is
-- instead written through a literal service_role connection (sync_service.py's own
-- _service_role_db helper, matching 014-accounting-integration's own precedent) — the one write
-- this feature makes that genuinely needs to bypass RLS, because no authenticated session
-- (member or worker) is ever allowed to see or set a token.
grant select (
  id, tenant_id, provider, external_account_id, external_account_name, status, connected_by,
  connected_at, last_synced_at, disconnected_at, created_at, updated_at
) on pos_connection to authenticated;

grant insert (
  id, tenant_id, provider, external_account_id, external_account_name, access_token,
  refresh_token, status, connected_by, connected_at
) on pos_connection to authenticated;

grant update (
  status, disconnected_at, updated_at, last_synced_at
) on pos_connection to authenticated;

grant select, insert, update on pos_connection to service_role;
