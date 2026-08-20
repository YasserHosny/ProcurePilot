-- 0008_workspace_switching.sql — closes a gap found reviewing the User Story 1 endpoints.
--
-- THE PROBLEM
-- `membership` is protected by `tenant_id = current_tenant_id()`, which is correct for every
-- in-workspace query and makes one operation structurally impossible: listing the workspaces a
-- person belongs to. By construction they can only ever see their membership in the workspace
-- the token already names, so "which workspaces am I in?" returns exactly one — the one you
-- already knew about. Switching workspace has the same problem in reverse: the target membership
-- is invisible from inside the current workspace, so it cannot be selected.
--
-- THE REJECTED FIX
-- The first implementation reached past RLS entirely, opening a direct connection as the database
-- owner and filtering with `where user_id = ...` in application code. It is not exploitable as
-- written, because user_id comes from the verified token — but it is precisely the arrangement
-- Constitution Principle V exists to forbid: isolation resting on a WHERE clause being correct,
-- in the request path, as a precedent for every later chunk to copy.
--
-- THE FIX
-- Two SECURITY DEFINER functions, following the same pattern as record_audit_event. Both derive
-- the caller from the JWT's `sub` claim and NEVER from a parameter — a user id argument would let
-- any member enumerate anyone else's workspaces.

create or replace function current_user_id()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'sub', '')::uuid;
$$;

comment on function current_user_id() is
  'The authenticated user id from the verified JWT, or NULL. Never taken from a parameter.';

-- ---------------------------------------------------------------------------
-- list_my_workspaces — every workspace the CALLER belongs to, across tenancy
-- ---------------------------------------------------------------------------
create or replace function list_my_workspaces()
returns table (
  tenant_id uuid,
  name      text,
  role      member_role,
  is_active boolean
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  caller uuid := current_user_id();
begin
  if caller is null then
    return;  -- no claim, no rows. Never "all rows".
  end if;

  return query
    select m.tenant_id, t.name, m.role, m.is_active_workspace
      from membership m
      join tenant t on t.id = m.tenant_id
     where m.user_id = caller
       and m.status = 'active'
     order by t.name, m.tenant_id;
end;
$$;

-- ---------------------------------------------------------------------------
-- set_active_workspace — move the caller's active flag, if they belong there
-- ---------------------------------------------------------------------------
create or replace function set_active_workspace(p_tenant_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  caller uuid := current_user_id();
  target uuid;
begin
  if caller is null then
    raise exception 'not authenticated' using errcode = 'insufficient_privilege';
  end if;

  select m.id into target
    from membership m
   where m.user_id = caller
     and m.tenant_id = p_tenant_id
     and m.status = 'active';

  -- Not a member: report it as absent, never as forbidden (FR-005). Whether a workspace exists
  -- is itself information.
  if target is null then
    return false;
  end if;

  update membership set is_active_workspace = false
   where user_id = caller and is_active_workspace;

  update membership set is_active_workspace = true
   where id = target;

  return true;
end;
$$;

grant execute on function current_user_id()                to authenticated;
grant execute on function list_my_workspaces()             to authenticated;
grant execute on function set_active_workspace(uuid)       to authenticated;
revoke execute on function list_my_workspaces()            from anon, public;
revoke execute on function set_active_workspace(uuid)      from anon, public;

comment on function list_my_workspaces() is
  'Workspaces the caller belongs to. SECURITY DEFINER because membership RLS is scoped to the
   active workspace, which makes cross-workspace listing impossible by construction. The caller
   comes from the JWT, so it cannot be pointed at another user.';
