-- 20261118000200_platform_operator.sql — spec 025 (in-app user feedback), task T009.
--
-- A platform operator is an existing workspace member who also has a live row here. The row is
-- granted and revoked by an operator CLI (service role / postgres), never by a client. Operators
-- may read and triage feedback across workspaces (ADR-027; owner exception to constitution
-- Principle V recorded in plan.md). Nothing else in the schema consults this table.
--
-- Clients never touch the table: RLS is enabled and forced with no policy for any client role,
-- and every client grant is revoked. The only client-visible surface is the boolean
-- is_platform_operator(), which RLS policies on feedback tables call.

create table platform_operator (
  user_id             uuid primary key references auth.users (id) on delete cascade,
  email               text not null,
  granted_at          timestamptz not null default now(),
  granted_by          text not null,
  revoked_at          timestamptz null,
  digest_opt_in       boolean not null default false,
  digest_locale       text not null default 'en' check (digest_locale in ('en', 'ar')),
  digest_last_sent_at timestamptz null
);

comment on table platform_operator is
  'Platform operators (spec 025, ADR-027). A row with revoked_at set is inactive. Service role
   and postgres only: no client grants, no client policy. 20261118000200.';
comment on column platform_operator.digest_opt_in is
  'Daily feedback digest, default off (FR-024).';
comment on column platform_operator.digest_last_sent_at is
  'Watermark: a digest includes only submissions newer than this.';

alter table platform_operator enable row level security;
alter table platform_operator force  row level security;

-- Deliberately no policy: with RLS forced and no matching policy every client role is denied.
-- service_role bypasses RLS (BYPASSRLS), so it needs only the table grant.
revoke all on platform_operator from public, anon, authenticated;
grant select, insert, update, delete on platform_operator to service_role;

-- ---------------------------------------------------------------------------
-- is_platform_operator() — is the JWT's subject a live operator?
--
-- SECURITY DEFINER because the table is unreadable to clients; the function returns only a
-- boolean about the caller's own subject, so it leaks nothing about other operators. The search
-- path is fixed (pg_catalog first, then public) so a caller-controlled schema cannot shadow
-- anything it references. A missing or malformed `sub` yields false, never an error.
-- ---------------------------------------------------------------------------
create or replace function is_platform_operator()
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select exists (
    select 1
    from public.platform_operator po
    where po.user_id = nullif(
            nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub', ''
          )::uuid
      and po.revoked_at is null
  );
$$;

comment on function is_platform_operator() is
  'True when the verified JWT subject has a live (not revoked) platform_operator row.
   SECURITY DEFINER with a fixed search_path; returns only a boolean about the caller. 20261118000200.';

revoke execute on function is_platform_operator() from public, anon;
grant  execute on function is_platform_operator() to authenticated, service_role;
