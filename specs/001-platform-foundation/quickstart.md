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
| Supabase CLI | latest | Migrations (ADR-007) |
| Git | any recent | — |

---

## 1. Clone and configure

```bash
git clone https://github.com/YasserHosny/ProcurePilot.git
cd ProcurePilot
cp .env.example .env
```

`.env.example` is committed and contains **no real values** — only keys with safe local
defaults. `.env` is git-ignored, and a gitleaks scan blocks any PR that carries a secret
(FR-027, SC-009). Nothing in step 1 requires a cloud account: the local stack is self-contained.

## 2. Start everything

```bash
docker compose up --build
```

This brings up the API, the web app behind Nginx, and the local Supabase stack — one command,
per the acceptance criterion (research R5).

| Service | URL |
|---|---|
| Web app | http://localhost:4200 |
| API | http://localhost:8000/api/v1 |
| API docs | http://localhost:8000/docs |
| Supabase Studio | http://localhost:54323 |

## 3. Apply migrations and seed reference data

```bash
pnpm db:migrate     # versioned SQL via Supabase CLI
pnpm db:seed        # enabled regions, currencies, tax models + one platform invitation
```

The seed prints a **platform invitation token**. You need it for the next step — sign-up is
invitation-gated during the pilot (FR-033), including locally.

## 4. Verify it works

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

## 5. Prove the isolation guarantee

The single most important thing this chunk delivers:

```bash
pnpm test:isolation
```

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
pnpm test:e2e          # Playwright against the compose stack
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
