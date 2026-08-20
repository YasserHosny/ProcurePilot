# Quickstart: Platform Foundation

**Feature**: 001-platform-foundation | **Date**: 2026-08-20

Target: a developer with no prior exposure to this project reaches a running local system in
under 30 minutes (SC-007). If this document takes you longer, that is a defect in the document.

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker + Compose v2 | 24+ | Runs the whole stack |
| Node.js + pnpm | 20 LTS / 9+ | Angular build, monorepo tooling |
| Python + uv | 3.12 / latest | Backend dependencies |
| Supabase CLI | 2.x | Runs the whole Supabase stack and applies migrations (ADR-007) |
| Google Chrome | any recent | End-to-end tests use the system browser, not a bundled one |
| Git | any recent | — |

---

## 1. Clone and configure

```bash
git clone https://github.com/YasserHosny/ProcurePilot.git
cd ProcurePilot
```

## 2. Start Supabase

```bash
supabase start
```

This starts Postgres, Auth, PostgREST, Storage, Kong and Studio, applies everything in
`supabase/migrations/`, and honours `supabase/config.toml` — which enables the custom access token
hook. That hook is not optional: it puts `tenant_id` into the JWT, and row-level security reads the
claim from there. Without it every tenant-scoped query returns zero rows and the app looks *empty*
rather than broken, which is a confusing hour to lose.

**Not `docker compose`.** A hand-assembled compose stack was tried first and abandoned: three
GoTrue versions could not complete their own migrations against it, including the pairing Supabase
themselves publish. `research.md` R5 records the whole episode. `docker-compose.yml` remains for
building the api and web images; it no longer starts Supabase.

| Service | URL |
|---|---|
| Supabase API | http://localhost:54321 |
| Postgres | postgresql://postgres:postgres@localhost:54322/postgres |
| Supabase Studio | http://localhost:54323 |
| Inbucket (captured email) | http://localhost:54324 |

## 3. Write your local environment

```bash
supabase status -o env        # shows ANON_KEY, SERVICE_ROLE_KEY, JWT_SECRET, DB_URL
cp .env.example .env          # then paste those four values in
```

`.env.example` is committed and holds **no real values**. The anon and service_role keys are not
arbitrary secrets — they are JWTs signed with the project's JWT secret — so they cannot be written
into a template; take them from `supabase status`. `.env` is git-ignored and a gitleaks scan blocks
any PR carrying a secret (FR-027, SC-009).

## 4. Seed reference data

```bash
pnpm db:seed
```

Enabled regions, currencies and tax models, plus one **platform invitation token**, printed once.
You need it to sign up: the pilot is invitation-gated (FR-033), including locally.

## 5. Run the API and the web app

```bash
# terminal 1
set -a && . ./.env && set +a
uv run --project apps/api uvicorn procurepilot_api.main:app \
  --host 127.0.0.1 --port 8000 --app-dir apps/api/src

# terminal 2
cd apps/web && pnpm install && pnpm exec ng serve
```

| Service | URL |
|---|---|
| Web app | http://localhost:4200 |
| API | http://localhost:8000/api/v1 |
| API docs | http://localhost:8000/docs |

## 6. Verify it works

```bash
curl -s http://localhost:8000/api/v1/health
# {"status":"ok"}
```

A `503` here means the API started but the database did not. That is the health check doing its
job (FR-024) — check the compose logs for the `db` service rather than retrying.

Then in the browser:

1. Open http://localhost:4200 → you are redirected to sign-in.
2. Follow the sign-up link, paste the seeded invitation token.
3. Enter a business name, and pick a region, currency, and tax model — there is no default, by
   design (FR-031).
4. You land in the shell as the workspace **owner**.
5. Switch the language to Arabic. The layout mirrors to RTL and every string changes. If you see
   a raw key, that is a missing catalogue entry — a bug, not a placeholder (SC-005).

## 7. Prove the isolation guarantee

The single most important thing this chunk delivers:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres pnpm test:isolation
```

The environment variable is required, not optional: without it these tests **skip** rather than
fail, which looks identical to passing in a summary line.

This creates two workspaces, gives each a marker record, and asserts that neither can read,
list, or detect the other's — through the API *and* directly against the database with a
member's credentials. It runs on every PR and blocks the merge on failure (FR-030).

If you change anything touching tenancy, run this before anything else.

---

## Running the test suites

```bash
pnpm test              # everything
pnpm test:api          # pytest — unit, integration, contract
pnpm test:web          # Karma + Jasmine
pnpm test:e2e          # Playwright against the running stack (needs steps 2-5 up)
pnpm test:a11y         # axe-core, zero violations required (FR-022)
pnpm lint              # ruff + Angular CLI lint
```

---

## Common problems

**`docker compose up` fails on a port already in use.** Supabase's local stack claims several
ports (54321–54324). Stop any other Supabase project first: `supabase stop --all`.

**Sign-up returns 403 with `invitation_invalid`.** The seeded token is single-use. Re-run
`pnpm db:seed` for a fresh one, or mint one in Studio against `platform_invitation`.

**The JWT has no `tenant_id` claim.** The custom access token auth hook did not run — the most
likely cause is a Supabase version mismatch in `docker-compose.yml` (research R1 flags this as
the chunk's highest-risk external dependency). Confirm the hook is registered in the local
Supabase config before debugging application code.

**RLS blocks a query you expected to work.** Check which role the connection is using. The
service role bypasses RLS and is restricted to migrations and the platform-invitation flow; if
application code reaches for it, that is the bug (research R4).

**Arabic renders left-to-right.** The `dir` attribute is set on the document root from the active
language. A component overriding it, or using `margin-left` instead of `margin-inline-start`, is
the usual cause.

---

## What is deliberately absent

Do not go looking for these — they belong to later chunks:

- Products, suppliers, catalogue (chunk 4.2)
- Document upload, extraction, review queue (chunk 4.3)
- Matching, landed cost (chunk 4.4)
- Comparison, recommendations (chunk 4.5)
- Savings ledger, exports, billing (chunk 4.6)
- Redis — deferred until the first background job (research R7)
- The mobile app — placeholder directory only (Phase 2)
