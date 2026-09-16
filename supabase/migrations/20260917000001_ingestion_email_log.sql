-- 20260917000001_ingestion_email_log.sql — task T001, chunk R3.0 (013-automated-ingestion)
--
-- ingestion_email_log — stores metadata for inbound emails received by the ingestion pipeline.
-- Provides RFC 5322 message_id deduplication per tenant, supplier matching provenance,
-- attachment tracking, and replay audit.
--
-- Non-negotiable 1: ENABLE + FORCE RLS with USING and WITH CHECK using current_tenant_id().

create type ingestion_email_status as enum (
  'received', 'processing', 'completed', 'failed', 'duplicate', 'rejected'
);

create table if not exists ingestion_email_log (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenant(id) on delete cascade,

  message_id          text not null,
  from_address        text not null,
  from_domain         text not null,
  subject             text,
  in_reply_to         text,
  references_list     text[] not null default '{}',

  received_at         timestamptz not null default now(),
  processed_at        timestamptz,
  status              ingestion_email_status not null default 'received',
  error_message       text,
  attachment_count    integer not null default 0 check (attachment_count >= 0),
  raw_email_ref       text,

  quotation_id        uuid references quotation(id) on delete set null,
  supplier_id         uuid references supplier(id) on delete set null,
  match_method        text check (match_method is null or match_method in ('address', 'domain', 'thread', 'manual')),

  created_at          timestamptz not null default now(),

  -- Composite key pattern: tenant-scoped children or FKs
  constraint ingestion_email_log_tenant_id_key unique (tenant_id, id),

  -- Deduplication: one message_id per tenant (RFC 5322 uniqueness)
  constraint ingestion_email_log_tenant_message_id_key unique (tenant_id, message_id)
);

create index if not exists ingestion_email_log_tenant_domain_idx
  on ingestion_email_log (tenant_id, from_domain);

create index if not exists ingestion_email_log_tenant_status_idx
  on ingestion_email_log (tenant_id, status);

create index if not exists ingestion_email_log_tenant_received_idx
  on ingestion_email_log (tenant_id, received_at desc);

create index if not exists ingestion_email_log_tenant_quotation_idx
  on ingestion_email_log (tenant_id, quotation_id)
  where quotation_id is not null;

comment on table ingestion_email_log is
  'Metadata and audit record for every inbound email processed for a workspace (R3.0). Enforces
   per-tenant Message-ID deduplication and records supplier identification provenance.';

alter table ingestion_email_log enable row level security;
alter table ingestion_email_log force  row level security;

create policy ingestion_email_log_tenant_isolation on ingestion_email_log
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

grant select, insert, update, delete on ingestion_email_log to authenticated;
grant select, insert, update, delete on ingestion_email_log to service_role;
