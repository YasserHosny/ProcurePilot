# Migrations moved to `supabase/migrations/`

The SQL migrations that used to live here are now in `supabase/migrations/`, applied with
`supabase db reset` / `supabase migration up`.

## Why

ADR-007 chose "versioned SQL files + Supabase CLI". The CLI reads migrations from
`supabase/migrations/` and nowhere else, so keeping a second copy here meant either duplicating
every file or teaching the CLI a non-standard path. Duplication is how two sources of truth start
drifting; the engineering spec's `apps/api/migrations/` path is the detail that gave way, not the
decision.

Filenames now carry the CLI's timestamp prefix. The ordinal in the suffix (`..._0004_rls.sql`)
still reflects the original sequence.

Nothing else about the migrations changed.
