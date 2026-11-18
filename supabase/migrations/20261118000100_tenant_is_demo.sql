-- 20261118000100_tenant_is_demo.sql — spec 025 (in-app user feedback), task T008.
--
-- Marks hosted demo workspaces so feedback from them can be told apart from real pilot feedback.
-- The flag is copied onto each feedback_submission at submit time, so changing it later does not
-- rewrite history.
--
-- Set by an ops step on the hosted demo tenants, never by a workspace member: `authenticated`
-- holds column-level UPDATE on tenant (20261018000012) for name, default_locale,
-- reporting_timezone and currency only, so this column is deliberately not in that grant.

alter table tenant
  add column is_demo boolean not null default false;

comment on column tenant.is_demo is
  'True for hosted demo workspaces. Set by an ops step, not by members (no client UPDATE grant).
   Copied onto feedback_submission.is_demo at submit time. 20261118000100.';
