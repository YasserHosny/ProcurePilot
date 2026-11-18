-- 20261118000700_auth_hook_operator_claim.sql — spec 025 (PPS-223), T063. SEPARABLE.
--
-- Stamps a `platform_operator` claim on the access token so the web app can decide whether to
-- show the triage navigation entry. It is a UI HINT ONLY:
--   * a token keeps its claims until it expires, so the claim can be stale after a revoke;
--   * the API never reads it. Authority is the live platform_operator lookup on every request
--     (is_platform_operator() / current_operator), and every operator RLS policy calls that
--     function, not the claim.
-- Dropping this migration changes nothing about who can read or change feedback. The fallback
-- for the web app is GET /platform/feedback/me.
--
-- Everything else in the hook is exactly as in 20260819000006_auth_hook.sql: tenant_id and
-- member_role from the active membership, and the `role` claim never touched.

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
    claims := claims - 'tenant_id' - 'member_role';
  end if;

  -- UI hint only; see the header.
  if exists (
    select 1
    from platform_operator po
    where po.user_id = (event ->> 'user_id')::uuid
      and po.revoked_at is null
  ) then
    claims := jsonb_set(claims, '{platform_operator}', 'true'::jsonb);
  else
    claims := claims - 'platform_operator';
  end if;

  return jsonb_set(event, '{claims}', claims);
end;
$$;

grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

comment on function public.custom_access_token_hook(jsonb) is
  'Injects tenant_id and member_role into the access token from the caller''s active membership,
   and a platform_operator UI-hint claim for active platform operators (never an authority: the
   API and RLS check platform_operator live). Never touches the `role` claim.';
