-- 20260917000003_tenant_email_config.sql — task T003, chunk R3.0 (013-automated-ingestion)
--
-- tenant_email_config — per-tenant email ingestion configuration and rate limit counters.
-- Stores the dedicated forwarding address, enablement state, optional domain allowlist,
-- daily quota limit, and daily counter reset by date.
--
-- Non-negotiable 1: ENABLE + FORCE RLS with USING and WITH CHECK using current_tenant_id().
-- Non-negotiable 2: Tenancy resolved from current_tenant_id(), write restricted to owners.

create table if not exists tenant_email_config (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenant(id) on delete cascade,

  forwarding_address  text not null,
  enabled             boolean not null default true,
  domain_allowlist    text[],
  daily_limit         integer not null default 100 check (daily_limit between 1 and 10000),
  daily_count         integer not null default 0 check (daily_count >= 0),
  daily_count_date    date not null default current_date,
  spf_dkim_required   boolean not null default false,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  created_by          uuid not null references membership(id),

  constraint tenant_email_config_tenant_id_key unique (tenant_id),
  constraint tenant_email_config_address_key unique (forwarding_address),
  constraint tenant_email_config_address_format check (forwarding_address ~ '^[a-z0-9-]+@ingest\.procurepilot\.com$')
);

create index if not exists tenant_email_config_address_lookup_idx
  on tenant_email_config (lower(forwarding_address));

comment on table tenant_email_config is
  'Per-tenant email ingestion settings, forwarding address, domain allowlist, and daily rate limit
   counters (R3.0). See specs/013-automated-ingestion/data-model.md.';

alter table tenant_email_config enable row level security;
alter table tenant_email_config force  row level security;

-- All members can read the configuration (e.g. to copy the forwarding address)
create policy tenant_email_config_tenant_select on tenant_email_config
  for select to authenticated
  using (tenant_id = current_tenant_id());

-- Only tenant owners can configure/edit email ingestion settings
create policy tenant_email_config_owner_insert on tenant_email_config
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  );

create policy tenant_email_config_owner_update on tenant_email_config
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() = 'owner'
  );

grant select, insert, update, delete on tenant_email_config to authenticated;
grant select, insert, update, delete on tenant_email_config to service_role;
