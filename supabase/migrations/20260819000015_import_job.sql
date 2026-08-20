-- 20260819000015_import_job.sql — task T005
--
-- One upload: its file, its verdict, and the rows it refused.
--
-- Retained after the fact so an import can be explained. Principle I applied to bulk data — a
-- catalogue that changed for reasons nobody can reconstruct is not trustworthy, and "I imported a
-- spreadsheet last month" is not an explanation.

do $$ begin
  create type import_kind as enum ('products', 'suppliers');
exception when duplicate_object then null; end $$;

do $$ begin
  create type import_status as enum ('validating', 'previewed', 'committed', 'refused');
exception when duplicate_object then null; end $$;

create table if not exists import_job (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null references tenant(id) on delete cascade,
  kind       import_kind not null,
  filename   text not null,
  status     import_status not null default 'validating',
  row_count  integer not null default 0 check (row_count >= 0),

  -- [{line, column, reason}] — line numbers as they appear in the UPLOADED FILE, not as row
  -- indices after parsing. The user has to find the row in their spreadsheet; an internal index
  -- would be accurate and useless.
  error_report jsonb not null default '[]'::jsonb,

  created_by uuid references membership(id) on delete set null,
  created_at timestamptz not null default now(),
  committed_at timestamptz,

  constraint import_job_committed_at_consistent
    check ((status = 'committed') = (committed_at is not null))
);

create index if not exists import_job_tenant_idx on import_job (tenant_id, created_at desc);
