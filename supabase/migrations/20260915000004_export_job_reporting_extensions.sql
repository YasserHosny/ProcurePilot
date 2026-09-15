-- 20260915000004_export_job_reporting_extensions.sql — task T004, chunk R2.5
-- (012-reporting-hardening)
--
-- export_job remains the single job-and-artifact record for on-demand AND scheduled
-- generation (data-model.md). This migration widens it: schedule linkage, locale, rule
-- version, the immutable schedule snapshot, retention expiry, the new kind set, and the
-- per-period idempotency key.
--
-- ORDER MATTERS: the two ALTER TYPE ... ADD VALUE statements run FIRST and are never
-- referenced again in this file. Postgres forbids using a newly added enum value inside the
-- same transaction that added it, and the migration runner wraps each file in one
-- transaction — so the CHECK that references 'expired'
-- (export_job_completed_at_only_terminal, replaced to treat 'expired' as terminal) lives in
-- the NEXT migration (20260915000005), not here. Same discipline as 20260913000001's enum
-- widening.

alter type export_format    add value if not exists 'csv';
alter type export_job_status add value if not exists 'expired';

alter table export_job
  add column if not exists schedule_id       uuid,
  add column if not exists locale            text not null default 'en',
  add column if not exists rule_version      text not null default '',
  add column if not exists schedule_snapshot jsonb,
  add column if not exists expires_at        timestamptz;

alter table export_job
  add constraint export_job_schedule_fkey
    foreign key (tenant_id, schedule_id) references report_schedule (tenant_id, id);

alter table export_job
  add constraint export_job_locale_check check (locale in ('en', 'ar')),
  add constraint export_job_kind_r25
    check (kind in ('savings_ledger', 'spend_by_supplier', 'alerts_summary'));

-- The per-period idempotency key (research R4): one artifact per schedule per period window,
-- regardless of how many times the scheduler replays the tick. On-demand jobs
-- (schedule_id null) are excluded from uniqueness on purpose — concurrent equivalent
-- on-demand requests are not de-duplicated (the honest POST /exports contract).
create unique index if not exists export_job_schedule_period_uidx
  on export_job (tenant_id, schedule_id, (filters->>'period_start'))
  where schedule_id is not null;

-- Reports center listing (T012): cursor pagination over (tenant_id, created_at desc).
create index if not exists export_job_tenant_created_idx
  on export_job (tenant_id, created_at desc);

comment on column export_job.schedule_id is
  'The schedule this artifact was generated for, when scheduled. On-demand jobs leave it null.';
comment on column export_job.schedule_snapshot is
  'Immutable copy of the schedule definition (kind, format, filters, weekday, locale, rule
   version) taken when the scheduled run was enqueued, so replay survives schedule edits and
   deletion (security critique finding 7, research R13).';
comment on column export_job.expires_at is
  'Set at completion: completion time + retention window (FR-014). The purge pass flips status
   to expired and clears storage after this instant; expired is terminal for downloads.';
