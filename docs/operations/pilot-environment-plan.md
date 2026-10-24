# Pilot environment setup plan (E-1, PPS-29)

Drafted 2026-10-24 for Sprint 1 (26 Oct – 6 Nov). Decision D-1 (2026-10-14): a **separate paid
hosted production**, meaning its own Supabase project and its own bunny.net containers, isolated
from today's staging/demo at `procurepilot.iron-sys.com`.

**Done when** (from PPS-29): the app is reachable over HTTPS; inbound email reaches it; one
backup has been restored and the restore recorded on PPS-29; `pnpm test:isolation` is green
against it; one full live walkthrough has passed on it.

Owners: **User** (accounts, billing, DNS, credentials), **Orch** (configuration, migrations,
checks, docs), **Lane** (workflow code, through a PR).

---

## 0. What exists today

| Piece | Staging/demo today | Production |
|---|---|---|
| Supabase | project `vamrz…` | none |
| bunny.net | app with `procurepilot-backend` + `procurepilot-frontend`; workers app with extraction, email-ingestion, optimiser and `shared-redis` | none |
| Deploys | push to `main` → staging, via repository secrets `BUNNY_*_APP_ID` | no workflow, no GitHub Environment |
| Mail | Mailgun sending `mail.procurepilot.iron-sys.com`; Supabase Auth SMTP via Mailgun (PPS-25) | none |
| Backups | whatever the staging project's plan gives; never restore-tested | — |

Findings from reading the repo for this plan:

- `infra/README.md` §3 describes `staging`/`production` GitHub Environments. No deploy workflow
  uses one: every deploy goes to whatever the repository secrets point at, which is staging.
- The local, gitignored `infra/terraform/production.tfvars` describes staging despite its name.
  Rename it `staging.tfvars` before production gets its own.
- The API reaches the workers app's Redis across apps (runbook §7.2). On production, Redis is
  password-protected (`requirepass`, password in `REDIS_URL`).

## 1. Decisions needed first (User)

| # | Decision | Recommendation / outcome |
|---|---|---|
| E1-a | **Domain.** The web and API hostname customers see. | **Decided 2026-10-24: `pilot.iron-sys.com`**, moving to `app.<company domain>` once G-10 names the company. A later change costs a DNS record plus the Supabase Site URL. |
| E1-b | **Supabase region.** | **Decided 2026-10-24: Frankfurt (`eu-central-1`)**, the nearest supported region to Egypt. Check whether the pilot agreement's PDPL clause (G-6) says anything about where data lives. |
| E1-c | **Supabase plan.** | **Decided 2026-10-24: Pro** (about $25/month plus compute). The Free plan pauses idle projects and offers no backups you can restore from. Skip point-in-time recovery for now; the agreed RPO is 24 h (runbook §5). |
| E1-d | **Extraction provider in production.** | `azure_di`, the same as staging. Never `stub` (runbook §9). The Azure DI keys live only on the bunny.net worker. |
| E1-e | **Embeddings (P-5, PPS-13).** | Follow whatever PPS-13 decides. Use the same mode in staging and production so demo results predict pilot results. |

E1-a to E1-c were answered on 2026-10-24, so Phase A can start (D-1 asked for the plan tier to be
confirmed before anything billable is created).

## 2. Steps

### Phase A — Accounts and data (User creates; Orch configures) · ~1 day

1. **User:** create the Supabase project (E1-b region, E1-c plan). Share the project ref and keep
   the DB password in your password manager. Orch never needs it in chat; `DATABASE_URL` goes
   straight into GitHub/bunny secrets.
2. **Orch:** apply all migrations with `DATABASE_URL=<prod, port 5432> pnpm db:migrate`. That
   ends with `pnpm db:check-privileges`. Check with `supabase migration list` that every file in
   `supabase/migrations/` (165 today) is applied.
3. **Orch:** Auth settings: Site URL = E1-a; redirect allow list = `/auth/update-password`;
   sign-up behaviour the same as staging; custom SMTP through a **separate** Mailgun SMTP
   credential (User creates it, as for PPS-25).
4. **Orch:** confirm the four storage buckets exist (the migrations create them) and are private.
5. **Orch:** seed reference data only (`pnpm db:seed`). No demo tenant and no test data.

**Done when:** migrations and the privilege check pass; the Auth reset email reaches a test inbox.

### Phase B — Containers and deploys (Lane PR + User secrets) · ~1–2 days

1. **User:** create two bunny.net apps mirroring staging: `procurepilot-prod` (backend +
   frontend) and `procurepilot-prod-workers` (extraction, email-ingestion, optimiser, Redis with a
   password). This is a one-time manual step, the same as staging (runbook §7.7).
2. **User:** create a GitHub Environment `production`, with **required reviewer = you** and
   environment-scoped secrets `BUNNY_BACKEND_APP_ID`, `BUNNY_FRONTEND_APP_ID`,
   `BUNNY_WORKERS_APP_ID`.
3. **Lane (PR):** add a production deploy path. Each `deploy-*.yml` gets a `workflow_dispatch`
   input or a release-tag trigger that runs under `environment: production`, so it deploys the
   **image already built and tested for staging** (same SHA), never a fresh build. Push to `main`
   keeps deploying staging only.
4. **User + Orch:** set container env vars from the API settings (`config.py`):
   `API_ENV=production`, `SUPABASE_*`, `DATABASE_URL` (pooler, with `prepare_threshold=None`
   already handled in code), `REDIS_URL` with the password, `API_CORS_ORIGINS` = E1-a,
   `EXTRACTION_PROVIDER_MODE`, Mailgun keys, `INGESTION_EMAIL_DOMAIN`, `SENTRY_DSN`. Use staging's
   list as the checklist; copy no secret values from staging.
5. **User:** DNS for E1-a pointed at the production app. Check HTTPS.

**Done when:** `/api/health` is 200 on the production hostname; the web app loads and signs in;
a production deploy needed your approval in GitHub.

### Phase C — Email in and out (User DNS + Orch config) · ~½ day

1. **User:** add a Mailgun inbound domain for production (e.g. `in.<E1-a domain>`, MX records),
   separate from staging's, so a pilot's forwarded quotes can never land in the demo DB.
2. **Orch:** add a Mailgun route to the production webhook; set the webhook signing key.
3. **Orch:** send a test quote email to a test tenant's ingestion address and confirm it arrives
   and is extracted.

**Done when:** a forwarded PDF quote shows up as an extracted quotation in production.

### Phase D — Backups and the restore test (Orch, User approves) · ~½ day

1. Confirm in the dashboard that daily backups run (Pro plan).
2. Add an independent nightly `pg_dump` (GitHub Actions, scheduled, environment `production`),
   encrypted, kept 14 days outside Supabase. Then losing the Supabase account does not lose the
   data.
3. **Restore test:** restore the latest dump into a throwaway Postgres (memory: the `:54399`
   container recipe) or a scratch Supabase project. Compare row counts on the main tenant tables
   and record the time taken (RTO is 4 h per runbook §5) on PPS-29.

**Done when:** a restore is recorded on PPS-29 with its date, its size and how long it took.

### Phase E — Proof (Orch) · ~½ day

1. `pnpm test:isolation` against production, with a throwaway pair of test tenants deleted
   afterwards (memory: the owner-guard trigger needs `session_replication_role` around teardown).
2. A full live walkthrough on production: RFQ → quotes in → compare → guardrail draft → mobile
   approval (mobile built with `API_BASE_URL` = production) → PO. Screenshots go under
   `docs/gtm/demo-tenant/pilot-env/`.
3. Update `docs/operations/runbook.md` §7 with the production topology, and record the
   environment on PPS-29.

**Done when:** isolation is green, the walkthrough passes, and PPS-29 meets every condition above.

---

## 3. Order and timing

```text
E1-a/b/c (User, day 1)
  └─ A accounts + migrations ─┬─ B containers + deploys ─┬─ C email ─┐
                              └─ D backups + restore ────┴──────────┴─ E proof
```

About 4–5 working days of effort, spread over the sprint because several steps wait on you.
The three decisions are made, so Phase A can begin on 26 Oct.

## 4. Not in this plan

- Background jobs container (P-4, PPS-12: report schedules, offer refresh, exports, digests). It
  is missing on staging too. Production should get it when staging does; it does not block the
  first pilot.
- Self-hosting (D-1 keeps it as a later option, `self-hosted-deployment-plan.md`).
- Monitoring beyond Sentry and bunny.net logs.
