-- FR-029 completion: the rendering locale is recorded on every report schedule, not only
-- on the generated artifacts. Migration 20260915000002 created report_schedule without the
-- column (locale rode export_job/schedule_snapshot only), which left an explicitly requested
-- create-time locale with nowhere to persist — the Wave 17 scheduler reads it from the row.
-- Added forward-only here rather than editing 02 post-authoring; the disposable verification
-- databases already have 01-05 applied.

alter table report_schedule
  add column if not exists locale text not null default 'en';

do $$
begin
  alter table report_schedule
    add constraint report_schedule_locale_check check (locale in ('en', 'ar'));
exception
  when duplicate_object then null;
end $$;
