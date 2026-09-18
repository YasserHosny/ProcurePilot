-- 20260917000002_ingestion_jobs.sql — task T002, chunk R3.0 (013-automated-ingestion)
--
-- ingestion_jobs — background queue for asynchronous ingestion tasks (email processing,
-- mobile capture extraction, supplier catalogue imports).
--
-- Uses database-backed worker pattern with FOR UPDATE SKIP LOCKED over (status, created_at)
-- where status = 'pending', identical to report_scheduler, export_worker, and digest_worker.
--
-- Non-negotiable 1: ENABLE + FORCE RLS with USING and WITH CHECK using current_tenant_id().

create type ingestion_job_type as enum (
  'email_ingest', 'capture_ingest', 'catalogue_import'
);

create type ingestion_job_status as enum (
  'pending', 'processing', 'completed', 'failed'
);

create table if not exists ingestion_jobs (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenant(id) on delete cascade,

  job_type       ingestion_job_type not null,
  status         ingestion_job_status not null default 'pending',
  payload        jsonb not null default '{}'::jsonb,

  attempts       integer not null default 0 check (attempts >= 0),
  max_attempts   integer not null default 3 check (max_attempts > 0),
  last_error     text,

  locked_by      text,
  locked_at      timestamptz,

  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  completed_at   timestamptz,

  constraint ingestion_jobs_tenant_id_key unique (tenant_id, id),
  constraint ingestion_jobs_completed_after_created
    check (completed_at is null or completed_at >= created_at)
);

-- Partial index for worker queue polling: claims due pending jobs via FOR UPDATE SKIP LOCKED
create index if not exists ingestion_jobs_pending_worker_idx
  on ingestion_jobs (created_at)
  where status = 'pending';

-- Operational and monitoring queries
create index if not exists ingestion_jobs_tenant_status_idx
  on ingestion_jobs (tenant_id, job_type, status, created_at desc);

comment on table ingestion_jobs is
  'Worker queue for asynchronous ingestion tasks (email, capture, catalogue import). Polled by
   ingestion workers via FOR UPDATE SKIP LOCKED pattern. See specs/013-automated-ingestion/data-model.md.';

alter table ingestion_jobs enable row level security;
alter table ingestion_jobs force  row level security;

create policy ingestion_jobs_tenant_isolation on ingestion_jobs
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

grant select, insert, update, delete on ingestion_jobs to authenticated;
grant select, insert, update, delete on ingestion_jobs to service_role;
