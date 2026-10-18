-- 20261018000012_tenant_write_policies.sql — tenant writes match the API's rules.
--
-- tenant had a single FOR ALL policy (id = current_tenant_id()) and `authenticated` held table-level
-- INSERT, UPDATE and DELETE, so the database accepted any member's write to their own workspace
-- row. The API only ever writes tenant in these ways:
--
--   * an owner changes name, default_locale, reporting_timezone   (PATCH /tenant, owner-only route)
--   * an owner changes currency                                    (set_tenant_currency, invoker)
--   * creating a workspace                                         (TenantService, server-side
--                                                                   connection)
--
-- This migration holds the database to exactly that:
--   * SELECT stays as it was (the caller's own workspace);
--   * UPDATE only by an owner, checked against the caller's live membership row
--     (current_membership_role, 20260927000000), and only on name, default_locale,
--     reporting_timezone and currency (column grants);
--   * no INSERT or DELETE for `authenticated` (definer functions and server-side code are
--     unaffected).

drop policy tenant_isolation on tenant;

create policy tenant_select on tenant
  for select to authenticated
  using (id = current_tenant_id());

create policy tenant_update on tenant
  for update to authenticated
  using (id = current_tenant_id() and current_membership_role() = 'owner')
  with check (id = current_tenant_id() and current_membership_role() = 'owner');

revoke insert, update, delete, truncate on tenant from authenticated;
grant update (name, default_locale, reporting_timezone, currency) on tenant to authenticated;
