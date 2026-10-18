-- 20261018000010_membership_write_policies.sql — membership writes match the API's rules.
--
-- membership had a single FOR ALL policy (tenant_id = current_tenant_id()) and `authenticated` held
-- table-level INSERT, UPDATE and DELETE, so the database accepted any same-workspace write to any
-- membership row. The API only ever writes membership in these ways:
--
--   * a member changes their own preferred_locale            (MembersService.update_me)
--   * an owner changes a member's role                       (update_member_role, owner-only route)
--   * an owner removes a member: status + is_active_workspace (remove_member, owner-only route)
--   * joining and switching workspaces                       (accept_member_invitation and
--                                                             set_active_workspace, SECURITY DEFINER)
--   * creating a workspace                                   (TenantService, server-side connection)
--
-- This migration holds the database to exactly that:
--   * SELECT stays workspace-wide;
--   * UPDATE is allowed on the caller's own row or, for an owner, on any row in the workspace,
--     and only on role, status, is_active_workspace and preferred_locale (column grants);
--   * role, status and is_active_workspace may change only when the caller is an owner, checked
--     against the caller's live membership row (current_membership_role, 20260927000000);
--   * no INSERT or DELETE for `authenticated` (definer functions and server-side code are
--     unaffected).
-- The existing owner guard (assert_tenant_retains_owner) still runs on every update and delete.

drop policy membership_isolation on membership;

create policy membership_select on membership
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy membership_update on membership
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and (user_id = current_user_id() or current_membership_role() = 'owner')
  )
  with check (tenant_id = current_tenant_id());

revoke insert, update, delete on membership from authenticated;
grant update (role, status, is_active_workspace, preferred_locale) on membership to authenticated;

create or replace function membership_owner_only_changes()
returns trigger
language plpgsql
as $$
begin
  -- Only requests made as the `authenticated` role are checked; definer functions run as their
  -- owner and server-side code connects as a privileged role.
  if current_user <> 'authenticated' then
    return new;
  end if;
  if (new.role is distinct from old.role
      or new.status is distinct from old.status
      or new.is_active_workspace is distinct from old.is_active_workspace)
     and coalesce(current_membership_role(), '') <> 'owner' then
    raise exception 'only a workspace owner can change a member''s role or status'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

comment on function membership_owner_only_changes() is
  'Rejects a change to membership.role, status or is_active_workspace made as `authenticated`
   unless the caller is an owner of the workspace (live membership lookup). 20261018000010.';

create trigger membership_owner_only_changes
  before update on membership
  for each row execute function membership_owner_only_changes();
