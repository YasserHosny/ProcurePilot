-- 20260822000037_branch.sql — task T002, chunk R2.0
--
-- branch — the first Phase 2 entity. Introduces this codebase's first WITHIN-TENANT visibility
-- axis (branch-scoped RLS) alongside tenant isolation itself: an owner sees every branch in
-- their tenant; a member holding a branch-scoped role (branch_manager, approver) sees only the
-- branch(es) they are assigned to via branch_role_assignment (added in a later migration in this
-- same chunk); a member with no branch assignment at all (an unscoped role, or a branch-scopable
-- role simply not yet assigned) sees every branch, same as owner — see research.md R1 for the
-- full design rationale and alternatives considered.

create table if not exists branch (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenant(id) on delete cascade,
  name        text not null,
  address     text,
  region      text references supported_region(code),
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  -- Enables composite (tenant_id, id) FK references from cost_centre, budget, and
  -- branch_role_assignment (added in later migrations in this chunk) — see the note on
  -- 20260822000036_membership_composite_key.sql for why this matters.
  constraint branch_tenant_id_key unique (tenant_id, id)
);

create index if not exists branch_tenant_idx on branch (tenant_id);

comment on table branch is
  'A physical location or organisational division within a tenant (chunk R2.0). No hard-delete
   path: deactivation (is_active = false) is the only retirement path, permitted even with
   dependents (spec.md User Story 1, Acceptance Scenario 3) — the application layer surfaces an
   explicit confirmation, the database does not block the update.';

-- ---------------------------------------------------------------------------
-- Branch-scoped visibility helpers
--
-- current_membership_id() mirrors the app layer's own live-lookup pattern for role resolution
-- (apps/api/src/procurepilot_api/deps.py's _fetch_one_active_membership) rather than trusting a
-- JWT claim: a branch reassignment therefore takes effect on the member's very next request,
-- with no token refresh required, per spec.md's edge case on role/branch-assignment changes.
--
-- current_member_role() reads the member_role claim already present on every JWT since chunk
-- 4.1's auth hook — no new claim, no auth-hook change, matching current_tenant_id() and
-- current_user_id()'s existing claims-read style exactly.
-- ---------------------------------------------------------------------------

create or replace function current_membership_id()
returns uuid
language sql
stable
as $$
  select id from membership
  where tenant_id = current_tenant_id()
    and user_id = current_user_id()
    and status = 'active'
  limit 1;
$$;

comment on function current_membership_id() is
  'The signed-in member''s own membership.id for the current tenant context, via a live lookup —
   not a JWT claim — so a branch_role_assignment change is reflected immediately. Mirrors
   apps/api''s own _fetch_one_active_membership filter (status = active, not is_active_workspace,
   since the JWT''s tenant_id claim already fixes which workspace context applies).';

create or replace function current_member_role()
returns text
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'member_role', '');
$$;

comment on function current_member_role() is
  'The member_role claim from the verified JWT, or NULL. Used only for the owner-sees-everything
   branch-visibility shortcut (research.md R1) — never as the source of truth for authorization
   decisions, which remains the app layer''s live-lookup-with-consistency-check pattern.';

alter table branch enable row level security;
alter table branch force  row level security;

create policy branch_tenant_isolation on branch
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- The branch-scoped SELECT-narrowing policy (research.md R1) is added in
-- 20260822000038_branch_role_assignment.sql, once that table exists — it cannot be defined here
-- without a forward reference to a table this migration does not yet create.

grant select, insert, update, delete on branch to authenticated;
grant select, insert, update, delete on branch to service_role;
