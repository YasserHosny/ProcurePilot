-- 20260911000001_current_tenant_id_empty_claims.sql
--
-- current_tenant_id() failed when request.jwt.claims was unset (e.g., anon requests routed
-- through Supabase's transaction pooler). The previous implementation cast the empty string
-- directly to jsonb, producing "invalid input syntax for type json" and surfacing as a 503
-- on sign-up.

create or replace function current_tenant_id()
returns uuid
language sql
stable
as $$
  select nullif(
    nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'tenant_id',
    ''
  )::uuid;
$$;

comment on function current_tenant_id() is
  'The tenant_id claim from the verified JWT, or NULL. Treats a missing or empty jwt-claims setting as NULL so RLS denies cleanly instead of erroring.';
