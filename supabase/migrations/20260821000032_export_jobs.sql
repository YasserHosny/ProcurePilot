-- 20260821000032_export_jobs.sql
--
-- export_job — the durable, user-visible job resource behind POST /exports and GET /exports/{id}.
-- Same shape as chunk 4.3's extraction_job and chunk 4.5's basket_split_job: Redis/RQ only
-- delivers work to the worker (which, per plan.md's Constitution Check, is apps/api's OWN package
-- run under a different entrypoint — NOT a new services/ directory, since export rendering has no
-- comparable CPU-bound/blocking-risk argument), this row is the source of truth the API polls
-- against.

create table if not exists export_job (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenant(id) on delete cascade,
  requested_by    uuid not null references membership(id),

  kind            text not null default 'savings_ledger',
  format          export_format not null,
  filters         jsonb not null,

  status          export_job_status not null default 'queued',
  storage_bucket  text,
  storage_path    text,
  download_url    text,
  row_count       integer,
  error           jsonb,

  created_at      timestamptz not null default now(),
  started_at      timestamptz,
  completed_at    timestamptz,

  constraint export_job_completed_at_only_terminal
    check ((status in ('completed', 'failed')) = (completed_at is not null)),
  constraint export_job_completed_has_storage
    check (
      status <> 'completed'
      or (storage_bucket is not null and storage_path is not null and row_count is not null)
    ),
  constraint export_job_failed_has_error
    check (status <> 'failed' or error is not null),
  constraint export_job_row_count_not_negative
    check (row_count is null or row_count >= 0)
);

create index if not exists export_job_tenant_requested_idx
  on export_job (tenant_id, requested_by, created_at desc);

comment on table export_job is
  'Async savings-ledger export tracking (FR-007-FR-009). kind is a const-like value
   (''savings_ledger'') for this chunk — a future export type reuses the same table rather than
   inventing a parallel one. See research.md R3.';
