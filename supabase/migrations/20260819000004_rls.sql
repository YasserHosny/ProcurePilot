-- 0004_rls.sql — tasks T014, T015
--
-- Constitution Principle V: tenant isolation is enforced by the DATABASE, not by application
-- diligence. A forgotten `where tenant_id = ...` in application code must not be able to leak
-- another business's commercial data.
--
-- Three details carry the guarantee, and all three are load-bearing:
--
--   1. ENABLE row level security   — turns policies on for ordinary roles.
--   2. FORCE  row level security   — applies them to the TABLE OWNER too. Without FORCE, the
--                                    owning role (which migrations run as) bypasses every policy
--                                    silently, and a test run as the owner would "pass" while
--                                    proving nothing.
--   3. USING *and* WITH CHECK      — USING governs what rows are visible (reads, and which rows
--                                    an update/delete can see). WITH CHECK governs what rows may
--                                    be WRITTEN. A USING-only policy lets a member insert a row
--                                    carrying another workspace's tenant_id, which they then
--                                    cannot see — silent cross-tenant corruption.
--
-- The claim comes from the verified JWT (research R1), injected by the auth hook in 0006.
-- Never from a header, path, or query: client-supplied tenancy is not a boundary.

-- ---------------------------------------------------------------------------
-- Claim accessor
--
-- Returns null rather than raising when the claim is absent or malformed, so a policy comparison
-- yields NULL -> false (deny) instead of erroring. Fail closed, quietly.
-- ---------------------------------------------------------------------------
create or replace function current_tenant_id()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'tenant_id', '')::uuid;
$$;

comment on function current_tenant_id() is
  'The tenant_id claim from the verified JWT, or NULL. NULL denies every tenant-scoped policy.';

-- ---------------------------------------------------------------------------
-- tenant — this table IS the tenant, so it compares id, not tenant_id
-- ---------------------------------------------------------------------------
alter table tenant enable row level security;
alter table tenant force  row level security;

create policy tenant_isolation on tenant
  for all
  to authenticated
  using      (id = current_tenant_id())
  with check (id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- membership
-- ---------------------------------------------------------------------------
alter table membership enable row level security;
alter table membership force  row level security;

create policy membership_isolation on membership
  for all
  to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- member_invitation
-- ---------------------------------------------------------------------------
alter table member_invitation enable row level security;
alter table member_invitation force  row level security;

create policy member_invitation_isolation on member_invitation
  for all
  to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

-- ---------------------------------------------------------------------------
-- platform_invitation — service role only (research R6)
--
-- RLS is enabled with NO policy for authenticated. In Postgres, RLS with no matching policy
-- denies everything, so this is a deliberate total denial rather than an oversight. The
-- service role bypasses RLS and is the only path that may read or spend an invitation — which
-- is correct, because workspace creation runs before any workspace, and therefore any claim,
-- exists.
-- ---------------------------------------------------------------------------
alter table platform_invitation enable row level security;
alter table platform_invitation force  row level security;

-- ---------------------------------------------------------------------------
-- audit_event — readable within the workspace, insertable, NEVER mutable (T015)
--
-- Append-only is enforced twice over: no UPDATE/DELETE policy exists, and the privileges are
-- revoked outright below. FORCE means even the owner is bound by the policies; the REVOKE
-- closes the remaining path.
-- ---------------------------------------------------------------------------
alter table audit_event enable row level security;
alter table audit_event force  row level security;

create policy audit_event_read on audit_event
  for select
  to authenticated
  using (tenant_id = current_tenant_id());

create policy audit_event_append on audit_event
  for insert
  to authenticated
  with check (tenant_id = current_tenant_id());

-- No policy for UPDATE or DELETE anywhere, for any role. Belt and braces:
revoke update, delete on audit_event from authenticated, anon;
revoke update, delete on audit_event from public;

comment on policy audit_event_append on audit_event is
  'Insert only. audit_event has no UPDATE or DELETE policy by design — the audit trail the
   north-star metric depends on must not be rewritable.';

-- ---------------------------------------------------------------------------
-- Grants
--
-- RLS narrows what a role may touch; it does not grant access. Both are required.
-- ---------------------------------------------------------------------------
grant select, insert, update, delete on tenant            to authenticated;
grant select, insert, update, delete on membership        to authenticated;
grant select, insert, update, delete on member_invitation to authenticated;
grant select, insert                 on audit_event       to authenticated;
grant usage, select                  on sequence audit_event_id_seq to authenticated;

grant select on supported_region    to anon, authenticated;
grant select on supported_currency  to anon, authenticated;
grant select on supported_tax_model to anon, authenticated;
