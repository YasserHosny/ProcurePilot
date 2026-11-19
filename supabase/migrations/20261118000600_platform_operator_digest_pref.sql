-- 20261118000600_platform_operator_digest_pref.sql — spec 025 (PPS-223), T065.
--
-- platform_operator has no client grants (20261118000200), so an operator cannot read or write
-- their own digest preference directly. These SECURITY DEFINER functions are the only door, and
-- each one touches exactly one row: the caller's own, found from the verified `sub` claim, and
-- only while the operator is active (revoked_at is null). A revoked operator reads and changes
-- nothing: both functions return zero rows.
--
-- operator_tenant_names() is the one other thing a triage view needs and an operator cannot read:
-- the display name of the workspace a submission came from. It returns names only (no other
-- tenant column), only for operators, only for the ids asked about. Tenant rows stay otherwise
-- unreadable to operators, so the operator exception remains confined to the feedback tables
-- plus this name lookup (to be recorded in ADR-027).

create or replace function operator_digest_preference()
returns table (digest_opt_in boolean, digest_locale text)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select po.digest_opt_in, po.digest_locale
  from platform_operator po
  where po.user_id = (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid
    and po.revoked_at is null;
$$;

create or replace function set_operator_digest_preference(
  p_enabled boolean,
  p_locale  text default null
)
returns table (digest_opt_in boolean, digest_locale text)
language plpgsql
volatile
security definer
set search_path = pg_catalog, public
as $$
#variable_conflict use_column
declare
  v_user uuid := (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid;
begin
  if p_enabled is null then
    raise exception 'p_enabled is required' using errcode = '22023';
  end if;
  if p_locale is not null and p_locale not in ('en', 'ar') then
    raise exception 'unsupported digest locale' using errcode = '22023';
  end if;

  -- Turning the digest on starts the watermark at now(), so feedback that arrived while it was
  -- off is not sent as a backlog the first morning.
  return query
  update platform_operator po
     set digest_opt_in = p_enabled,
         digest_locale = coalesce(p_locale, po.digest_locale),
         digest_last_sent_at = case
           when p_enabled and not po.digest_opt_in then now()
           else po.digest_last_sent_at
         end
   where po.user_id = v_user
     and po.revoked_at is null
  returning po.digest_opt_in, po.digest_locale;
end;
$$;

create or replace function operator_tenant_names(p_tenant_ids uuid[])
returns table (tenant_id uuid, tenant_name text)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select t.id, t.name
  from tenant t
  where is_platform_operator()
    and t.id = any(p_tenant_ids);
$$;

revoke execute on function operator_digest_preference() from public, anon;
revoke execute on function set_operator_digest_preference(boolean, text) from public, anon;
revoke execute on function operator_tenant_names(uuid[]) from public, anon;
grant execute on function operator_digest_preference() to authenticated;
grant execute on function set_operator_digest_preference(boolean, text) to authenticated;
grant execute on function operator_tenant_names(uuid[]) to authenticated;

comment on function operator_digest_preference() is
  'The calling active platform operator''s own digest preference; zero rows for anyone else.';
comment on function set_operator_digest_preference(boolean, text) is
  'Sets the calling active platform operator''s own digest preference; zero rows for anyone else.';
comment on function operator_tenant_names(uuid[]) is
  'Workspace display names for platform operators only; no other tenant column is exposed.';
