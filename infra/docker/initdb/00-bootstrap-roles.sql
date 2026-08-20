-- Bootstrap the Supabase roles and the auth schema shell.
--
-- Runs once, from /docker-entrypoint-initdb.d, before any service connects.
--
-- WHY THIS FILE EXISTS
-- GoTrue and Storage assume these objects already exist and crash-loop without them:
--   GoTrue:  'running db migrations: ... ERROR: schema "auth" does not exist'
--   Storage: 'Migration failed ... Reason: role "anon" does not exist'
-- The application migrations (0001-0009) assume them too — every RLS policy grants to
-- `authenticated`, and `membership.user_id` references `auth.users`.
--
-- Nothing in the project created them. The test harness worked only because each test database
-- was hand-seeded with these roles, which quietly masked the gap until the stack was run for real.
--
-- The `auth` SCHEMA is created here, but its TABLES are not: GoTrue owns those and creates them
-- in its own migrations. This file only guarantees the schema exists for GoTrue to write into.

-- Roles. NOLOGIN: these are assumed via `set role` from a verified JWT, never connected to
-- directly. Granting login rights would turn a leaked anon key into a database session.
do $$ begin create role anon nologin noinherit;                     exception when duplicate_object then null; end $$;
do $$ begin create role authenticated nologin noinherit;            exception when duplicate_object then null; end $$;
do $$ begin create role service_role nologin noinherit bypassrls;   exception when duplicate_object then null; end $$;

-- Service owners. GoTrue and Storage connect as these and manage their own schemas.
do $$ begin create role supabase_auth_admin    noinherit login password 'postgres'; exception when duplicate_object then null; end $$;
do $$ begin create role supabase_storage_admin noinherit login password 'postgres'; exception when duplicate_object then null; end $$;

-- postgres must be able to assume the application roles, so migrations can set up grants.
grant anon, authenticated, service_role to postgres;

create schema if not exists auth  authorization supabase_auth_admin;
create schema if not exists storage authorization supabase_storage_admin;

grant usage on schema public to anon, authenticated, service_role;
grant usage on schema auth   to anon, authenticated, service_role;

alter role supabase_auth_admin    set search_path = auth;
alter role supabase_storage_admin set search_path = storage;

-- pgcrypto is needed by gen_random_uuid() in the application schema.
create extension if not exists pgcrypto;
