-- ProcurePilot additions to the supabase/postgres image's own initialisation.
--
-- Mounted as a single FILE into /docker-entrypoint-initdb.d/init-scripts/. Do NOT mount the whole
-- directory: that masks the image's own init scripts, which is what previously left the database
-- with no anon, authenticated, or supabase_auth_admin roles and sent GoTrue and Storage into
-- crash-loops. The image creates those roles and the extensions; this file adds only what it does
-- not, and must stay idempotent and additive.
--
-- Deliberately NOT here: role creation, the auth schema, pgcrypto. All are the image's job, and
-- duplicating them is how the masking bug hid for as long as it did.

-- NOT DONE HERE: dropping the image's pre-baked auth schema so GoTrue can rebuild it. That was
-- tried and did not help — GoTrue recreated all 23 tables itself and still failed on the same
-- migration, so the fault is not the image's copy. Left out rather than kept as a superstition.

-- Application-specific extensions, in case the image's set changes.
create extension if not exists "pg_trgm";   -- fuzzy product matching, chunk 4.4
create extension if not exists "vector";    -- embedding search, chunk 4.4

-- The postgres role must be able to assume the application roles so that migrations can set up
-- grants and so tests can act as `authenticated` to prove RLS.
do $$
begin
  execute 'grant anon, authenticated, service_role to postgres';
exception
  when undefined_object then
    raise notice 'Supabase roles are absent; the image init scripts did not run.';
end $$;
