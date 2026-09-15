-- 20260915000001_tenant_reporting_timezone.sql — task T001, chunk R2.5 (012-reporting-hardening)
--
-- tenant.reporting_timezone — the timezone every scheduled-report window, digest window, and
-- next-run computation for this workspace is derived in (spec FR-021, research R3). Stored on the
-- tenant because a workspace reports in ONE timezone: a schedule's "week" is the tenant's week.
--
-- The value is validated as an IANA timezone name by the API layer (T018's owner-only
-- PATCH /api/v1/tenant check); the database stores the text. This matches the established
-- division of labour for reference-shaped values (supported_currency/supported_region style):
-- the database constrains shape only where it can do so honestly, the API constrains meaning.

alter table tenant
  add column if not exists reporting_timezone text not null default 'UTC';

comment on column tenant.reporting_timezone is
  'IANA timezone name (e.g. Africa/Cairo, UTC) used to derive all reporting windows and
   next-run instants for this workspace. Validated by the API on write (owner-only,
   PATCH /api/v1/tenant); defaults to UTC so existing workspaces keep their current
   semantics until an owner changes it. See specs/012-reporting-hardening/data-model.md.';
