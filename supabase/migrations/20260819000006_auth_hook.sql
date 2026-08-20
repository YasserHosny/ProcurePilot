-- 0006_auth_hook.sql — task T017
--
-- research R1: the acceptance criterion is that the issued JWT CARRIES tenant_id. RLS policies
-- read the claim from the token (see current_tenant_id() in 0004) — a policy cannot call back
-- into application code, so the value must be inside the token at issuance.
--
-- A Supabase custom access token hook runs at token issuance and can inject claims. Because it
-- runs on every issuance and refresh, a membership or role change takes effect on the next
-- refresh rather than being frozen at sign-up — which is why app_metadata written once at
-- sign-up was rejected: a stale role claim is a privilege bug.
--
-- ⚠️  VERIFY THE HOOK CONTRACT against the Supabase version pinned in docker-compose.yml before
--     relying on this. research.md flags it as the highest-risk external dependency in the chunk;
--     the hook's expected argument and return shape has changed between versions.
--
-- ⚠️  DO NOT write the member's role into the `role` claim. Supabase and PostgREST use `role` as
--     the POSTGRES role to switch to for the request (`authenticated`, `anon`, `service_role`).
--     Setting it to 'owner' or 'buyer' makes PostgREST issue `set role owner`, which fails with
--     'role "owner" does not exist' and breaks every request. The member's role therefore travels
--     as a separate `member_role` claim, and `role` is left exactly as Supabase set it.

create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  claims        jsonb;
  active        record;
begin
  claims := coalesce(event -> 'claims', '{}'::jsonb);

  select m.tenant_id, m.role
    into active
  from membership m
  where m.user_id = (event ->> 'user_id')::uuid
    and m.is_active_workspace
    and m.status = 'active'
  limit 1;

  if found then
    claims := jsonb_set(claims, '{tenant_id}',   to_jsonb(active.tenant_id::text));
    claims := jsonb_set(claims, '{member_role}', to_jsonb(active.role::text));
  else
    -- No active membership: issue a token with NO tenant claim. current_tenant_id() then returns
    -- NULL and every tenant-scoped policy denies. A user between workspaces sees nothing rather
    -- than something arbitrary.
    claims := claims - 'tenant_id' - 'member_role';
  end if;

  return jsonb_set(event, '{claims}', claims);
end;
$$;

grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

comment on function public.custom_access_token_hook(jsonb) is
  'Injects tenant_id and member_role into the access token from the caller''s active membership.
   Never touches the `role` claim, which Postgres/PostgREST reserve for the database role.
   Register as the custom access token hook in Supabase Auth configuration.';
