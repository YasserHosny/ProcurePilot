-- 0001_extensions.sql — task T011
--
-- Enabled here, in the foundation, though nothing queries them until chunks 4.3/4.4.
-- Extension enablement is a privileged, environment-level operation; concentrating it in the
-- foundation migration means later chunks ship plain table migrations and staging cannot drift
-- from production on a privilege the app cannot grant itself.
-- Justified in specs/001-platform-foundation/plan.md, Complexity Tracking.

create extension if not exists "pgcrypto";      -- gen_random_uuid()
create extension if not exists "pg_trgm";       -- fuzzy matching, chunk 4.4
create extension if not exists "vector";        -- pgvector, embedding search, chunk 4.4
