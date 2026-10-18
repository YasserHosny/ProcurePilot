# Local Development Runbook

ProcurePilot local development uses the hosted Supabase project as the database and auth/storage
backend. Do not run a local Postgres or local Supabase stack for normal app development.

## Prerequisites

- Docker and `docker-compose` are installed.
- Node and `pnpm` are installed.
- Python tooling is available through `uv`.
- `.env` exists and contains hosted Supabase values:
  - `SUPABASE_URL=https://<project-ref>.supabase.co`
  - `SUPABASE_ANON_KEY=<hosted anon key>`
  - `SUPABASE_SERVICE_ROLE_KEY=<hosted service role key>`
  - `SUPABASE_JWT_SECRET=<hosted JWT secret>`
  - `SUPABASE_JWT_ISSUER=https://<project-ref>.supabase.co/auth/v1`
  - `DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres`

`REDIS_URL` may stay as `redis://localhost:6379/0` for host tools. Docker Compose overrides it to
`redis://redis:6379/0` inside containers.

## Start

```bash
docker-compose up -d redis api extraction-worker
pnpm --dir apps/web ng serve --host 127.0.0.1 --port 4200
```

Open the app at:

```text
http://127.0.0.1:4200/
```

The Angular dev server proxies `/api` to the local FastAPI container at `http://127.0.0.1:8000`.

## Verify

```bash
curl -sS http://127.0.0.1:8000/api/v1/health
docker-compose ps
```

Expected API health response:

```json
{"status":"ok"}
```

## Migrations And Seed

Run migrations against the hosted database only:

```bash
pnpm db:migrate
```

`db:migrate` then runs `pnpm db:check-privileges`, a read-only check that every migration file is
recorded as applied and that `anon`/`authenticated` hold no table rights the migrations do not
grant (no TRUNCATE/REFERENCES/TRIGGER/MAINTAIN, no integration-token columns, no default grants
on new tables, forced RLS on every table a client role can reach). It exits non-zero on any
problem. A warning about `supabase_admin`'s default privileges is expected on hosted: the
migrating role cannot change them, so a table created in the dashboard or SQL editor needs an
explicit `REVOKE`. Run the check on its own at any time with `pnpm db:check-privileges`.

Seed hosted reference data and a platform invitation:

```bash
pnpm db:seed
```

Invite someone into an existing workspace on behalf of one of its owners (the CLI equivalent of
Team -> Invite; prints a one-time acceptance link to send by hand — the app does not email it):

```bash
pnpm db:invite-member --owner-email owner@example.com --email new.person@example.com --role buyer
```

Add `--tenant-id` if the owner owns several workspaces, and `--replace` to revoke and re-issue a
still-pending invitation. Set `WEB_ORIGIN` to the hosted web app so the link points there.

All three commands require `DATABASE_URL` from `.env` to point at the hosted Supabase Postgres database.

## Stop

```bash
docker-compose stop api extraction-worker redis
```

If the Angular dev server is running in a terminal, stop it with `Ctrl+C`.

## What Not To Run

Do not start local `db`, `auth`, `rest`, `storage`, `kong`, or `studio` services. They are not part
of local development anymore. The backend reads hosted Supabase and Postgres settings from `.env`.
