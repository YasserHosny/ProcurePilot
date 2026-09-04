# ProcurePilot — Release Plan: Web App to bunny.net & Supabase

> Authoritative release plan for the ProcurePilot web application (Angular SPA + FastAPI
> backend) on bunny.net Magic Containers backed by hosted Supabase.

Last updated: 2026-09-02

This document consolidates the previous deployment and release plans. Where older guidance
conflicted with the current infrastructure reference, the newer seven-phase release flow and
`infra/README.md` are authoritative. Use `infra/README.md` for infrastructure internals,
GitHub Secrets Reference details, and staging/production separation; this plan focuses on the
release sequence and operational checks.

---

## Environments

| Environment | Purpose | Trigger |
|---|---|---|
| Local | Developer feedback | Local container command for builds and integration testing; Supabase services via CLI |
| CI | Tests and image builds | PR / push to `main` |
| Staging | Design-partner validation | Successful CI on `main` |
| Production | Live customers | Manual promotion from staging |

Local Supabase database, auth, and storage services are managed by the Supabase CLI; `docker-compose.yml` remains available for container builds and integration testing, as described in `infra/README.md` §6.

---

## Prerequisites

Before starting, confirm you have:

- [ ] A bunny.net account with API access (Magic Containers enabled)
- [ ] A hosted Supabase project (Postgres 17, pgvector + pg_trgm extensions available)
- [ ] A GitHub repository with GHCR (GitHub Container Registry) enabled
- [ ] Terraform >= 1.5.0 installed locally
- [ ] Supabase command-line tool installed (`npm i -g supabase` or standalone binary)
- [ ] Docker & Docker Buildx installed locally
- [ ] Domain name (`procurepilot.com`) DNS managed by bunny.net or ready to delegate
- [ ] `infra/README.md` reviewed, especially §2 GitHub Secrets Reference and §3 Staging and Production Separation

Operational invariants for this release:

- No secret values are committed. Use `<placeholder>` syntax in committed docs and examples.
- Migrations are forward-only and are never edited after merge.
- Tenant isolation is enforced through database RLS and verified JWT claims.
- The `custom_access_token_hook` from migration `20260819000006` is critical; without it, RLS policies return zero rows.
- No autonomous purchasing is introduced in this release.

---

## Phase 1: Supabase Project Setup

### 1.1 Create the Hosted Supabase Project

1. Go to [app.supabase.com](https://app.supabase.com) and create a new project.
2. Select **Postgres 17** as the database version.
3. Choose a region close to your primary users (EU recommended, `eu-central-1` aligns with the Bunny `DE` region).
4. Note the following from the project dashboard (Settings -> API):
   - `SUPABASE_URL` — Project URL (e.g. `https://vamrzajpuldklanvhvip.supabase.co`)
   - `SUPABASE_ANON_KEY` — `anon` public key
   - `SUPABASE_SERVICE_ROLE_KEY` — `service_role` key (keep secret)
   - `SUPABASE_JWT_SECRET` — JWT secret (Settings -> API -> JWT Settings)

Staging and production use separate Supabase projects, auth user stores, storage buckets,
JWT secrets, anon keys, and service-role keys. Do not share data or credentials between
environments. See `infra/README.md` §3 for the full environment separation model.

### 1.2 Enable Required Extensions

Connect to the Supabase SQL Editor and run:

```sql
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

These are enabled by migration `20260819000001_extensions.sql`, but pre-enabling avoids
permission issues.

### 1.3 Apply Migrations

Link the local project to the hosted Supabase instance and push migrations:

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

This applies all 46 migrations in `supabase/migrations/` in order. Migrations are
forward-only; never edit or delete a merged migration file.

**Verify:** Run a spot check in the Supabase SQL Editor:

```sql
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
```

Confirm core tables exist: `tenant`, `member`, `workspace_product`, `supplier`, `quotation`,
`document`, `purchase_request`, `approval_step`, `branch`, `cost_centre`, `budget`, etc.

### 1.4 Configure the Custom Access Token Hook

The `custom_access_token_hook` function (migration `20260819000006`) injects `tenant_id` and
`member_role` into the JWT. Without it, every RLS policy returns zero rows.

On hosted Supabase, enable this hook via the dashboard:

1. Go to **Authentication -> Hooks** in the Supabase dashboard.
2. Enable the **Custom Access Token** hook.
3. Set the hook URI to: `pg-functions://postgres/public/custom_access_token_hook`

**Verify:** Sign in as a test user and decode the JWT at [jwt.io](https://jwt.io). The payload
should include `tenant_id` and `member_role` claims.

### 1.5 Configure Storage Buckets

Create the required storage buckets via the dashboard or SQL:

```sql
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES
  ('quotation-documents', 'quotation-documents', false, 52428800),
  ('exports', 'exports', false, 52428800)
ON CONFLICT (id) DO NOTHING;
```

### 1.6 Seed Reference Data

Run the seed script against the hosted Supabase instance:

```bash
export SUPABASE_URL=https://<your-ref>.supabase.co
export SUPABASE_ANON_KEY=<anon-key>
export SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
export DATABASE_URL=postgresql://postgres:<db-password>@db.<your-ref>.supabase.co:5432/postgres

cd apps/api
uv run python scripts/seed.py
```

This creates the platform invitation token and reference data (units of measure, currencies,
etc.).

## Phase 2: Container Images

GitHub Container Registry (`ghcr.io`) is the image registry. Docker Buildx builds Linux
AMD64 images and tags each image with both `latest` and the commit SHA. GitHub Actions should
use the GitHub Actions cache for repeat builds.

### 2.1 Build and Push the Backend Image

```bash
# Log in to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u <github-username> --password-stdin

# Build and push
docker buildx build \
  --platform linux/amd64 \
  -f infra/docker/api.Dockerfile \
  -t ghcr.io/<org>/procurepilot-api:latest \
  -t ghcr.io/<org>/procurepilot-api:$(git rev-parse --short HEAD) \
  --push .
```

The backend deployment workflow should run unit and integration tests before updating the
runtime image. Tenant-isolation tests remain mandatory for any tenancy-related change.

### 2.2 Build and Push the Frontend Image

```bash
docker buildx build \
  --platform linux/amd64 \
  -f infra/docker/web.Dockerfile \
  -t ghcr.io/<org>/procurepilot-web:latest \
  -t ghcr.io/<org>/procurepilot-web:$(git rev-parse --short HEAD) \
  --push .
```

The frontend image serves the Angular production bundle through nginx. Nginx injects runtime
proxy configuration at container startup.

### 2.3 Verify Images

```bash
docker pull ghcr.io/<org>/procurepilot-api:latest
docker pull ghcr.io/<org>/procurepilot-web:latest
```

### 2.4 Local Development Runtime

```bash
docker compose up --build
# Frontend: http://localhost
# API proxied through Nginx: http://localhost/api/
```

| Setting | Bunny Magic Containers | Docker Compose |
|---|---|---|
| `BACKEND_HOST` | `localhost`, because frontend and backend containers share a Bunny network namespace | `backend`, because nginx reaches the API by Compose service name |

### 2.5 Build and Push the Extraction Worker Image

```bash
docker buildx build \
  --platform linux/amd64 \
  -f infra/docker/extraction-worker.Dockerfile \
  -t ghcr.io/<org>/procurepilot-extraction-worker:latest \
  -t ghcr.io/<org>/procurepilot-extraction-worker:$(git rev-parse --short HEAD) \
  --push .
```

The worker image is a separate container from the backend API. It runs `rq` workers that
consume extraction jobs from Redis. Its CI workflow is
`.github/workflows/deploy-extraction-worker.yml`, which deploys to the **workers** Bunny app
(`BUNNY_WORKERS_APP_ID`), not the production app.

### 2.6 Mobile Build Workflow Placeholder

`build-mobile.yml` is a Phase 2 placeholder for `apps/mobile/**`. When Phase 2 opens, the
workflow should build Flutter iOS and Android bundles, upload artifacts, and tag releases for
store submission. Do not implement mobile release automation before the Phase 2 gate.

---

## Phase 3: bunny.net Infrastructure (Terraform)

Terraform is the source for bunny.net Magic Containers, custom hostnames, DNS routing, and the
GHCR registry connection. The Supabase project is created and configured in Phase 1; do not
treat Terraform as the source for Supabase project provisioning unless a later ADR changes
that.

Use `infra/README.md` §4 for the Terraform directory layout and validation command. Store
Terraform state remotely before the first durable production deployment; the backend bucket
choice remains an operational decision.

### 3.1 Create a Terraform Variables File

Create `infra/terraform/production.tfvars` (do NOT commit, add to `.gitignore` if needed):

```hcl
bunny_api_key         = "<bunny-account-api-key>"
environment           = "production"
project_name          = "procurepilot"
domain_name           = "procurepilot.com"
github_username       = "<github-username>"
github_token          = "<github-pat-read-packages>"
image_namespace       = "<github-org-lowercase>"
supabase_url          = "https://<ref>.supabase.co"
supabase_anon_key     = "<anon-key>"
supabase_service_role_key = "<service-role-key>"
supabase_jwt_secret   = "<jwt-secret>"
```

### 3.2 Initialize and Apply Terraform

```bash
cd infra/terraform
terraform init
terraform plan -var-file=production.tfvars
terraform apply -var-file=production.tfvars
```

This creates:

- A **GHCR image registry** connection on bunny.net
- A **Magic Containers application** with two containers (`procurepilot-backend` on port 8000, `procurepilot-frontend` on port 80)
- A **DNS zone** for `procurepilot.com`
- **CNAME records**: `procurepilot-api.procurepilot.com` -> backend, `procurepilot.com` -> frontend

### 3.3 Note the Terraform Outputs

```bash
terraform output
```

Record:

- `app_id` — needed as `BUNNY_BACKEND_APP_ID` / `BUNNY_FRONTEND_APP_ID` in GitHub secrets
- `dns_zone_id` — for reference
- `backend_hostname` — `procurepilot-api.procurepilot.com`
- `frontend_hostname` — `procurepilot.com`

### 3.4 Configure Container Environment Variables

In the bunny.net dashboard (Magic Containers -> your app -> container settings), set
environment variables for the **backend container** (`procurepilot-backend`):

| Variable | Value |
|---|---|
| `API_HOST` | `0.0.0.0` |
| `API_PORT` | `8000` |
| `API_ENV` | `production` |
| `API_LOG_LEVEL` | `warning` |
| `API_CORS_ORIGINS` | `https://procurepilot.com` |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | `<anon-key>` |
| `SUPABASE_SERVICE_ROLE_KEY` | `<service-role-key>` |
| `SUPABASE_JWT_SECRET` | `<jwt-secret>` |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` |
| `SUPABASE_JWT_ISSUER` | `https://<ref>.supabase.co/auth/v1` |
| `DATABASE_URL` | `postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres` |
| `REDIS_URL` | `redis://<redis-host>:6379/0` (or omit if workers run separately) |
| `PLATFORM_INVITATION_TTL_DAYS` | `7` |
| `MEMBER_INVITATION_TTL_DAYS` | `7` |
| `RATE_LIMIT_AUTH` | `10/minute` |
| `EXTRACTION_PROVIDER_MODE` | `stub` (switch to `azure_di` or `bedrock` when ready) |
| `EXTRACTION_CONFIDENCE_THRESHOLD` | `0.85` |

The **frontend container** (`procurepilot-frontend`) needs no application environment
variables. It serves static files via nginx, and the SPA uses relative `/api/v1` paths
proxied by nginx to the backend container on `localhost:8000` in the shared Bunny network
namespace.

### 3.5 Configure the Workers App

The extraction worker and Redis run in a **separate** bunny.net Magic Containers app
(`procurepilot-workers`), not in the production app. This provides independent scaling and
resource isolation.

Create the workers app in bunny.net and add two containers:

| Container | Image | Port | Purpose |
|---|---|---|---|
| `procurepilot-extraction-worker` | `ghcr.io/<org>/procurepilot-extraction-worker:latest` | — | RQ worker consuming extraction jobs |
| `shared-redis` | `redis:7.4-alpine` | 6379 | Job queue for RQ |

Because these two containers are in the same app, the worker reaches Redis at
`redis://localhost:6379/0`.

The **backend API** (in the production app) connects to this Redis via the workers app's
**Anycast IP**. Find the Anycast IP in the bunny.net dashboard under the workers app's
endpoint configuration (e.g. `109.224.230.150`). Set `REDIS_URL=redis://<anycast-ip>:6379/0`
on the backend container.

Configure the extraction worker's environment variables per the runbook §7.3.

### 3.6 Configure Domain & SSL

Backend `.env` files are never committed. They contain Supabase credentials, AI-provider
keys, and CORS origins. CI and Bunny secrets are configured outside the repository; see
`infra/README.md` §2 for the exact GitHub secret names and where they are configured.

### 3.7 Configure Domain & SSL

1. **Delegate DNS**: Point your domain registrar's nameservers to bunny.net's nameservers
   (shown in the bunny.net DNS zone dashboard), or use a CNAME to the Bunny endpoint if using
   a subdomain (e.g. `procurepilot.iron-sys.com`).
2. **SSL**: bunny.net Magic Containers automatically provision and renew TLS certificates via
   Let's Encrypt once DNS resolves. Verify HTTPS works after DNS propagation (5-60 minutes).

## Phase 4: GitHub Secrets & CI/CD

GitHub Actions is the CI/CD platform. Workflows are path-filtered, build with Docker Buildx,
push to GHCR, and deploy by calling `BunnyWay/actions/container-update-image`.

### 4.1 Set GitHub Repository Secrets

Configure the Bunny deployment secrets in GitHub Repository or Environment Secrets. The
canonical secret list and scope guidance live in `infra/README.md` §2. `GITHUB_TOKEN` is
provided automatically by GitHub Actions and is used for GHCR pushes.

### 4.2 Verify CI Pipeline

Push to `main` (or run `workflow_dispatch`) and confirm:

1. **`ci.yml`** — all jobs pass: secret scan, lint, backend tests, tenant isolation, web unit tests, e2e
2. **`deploy-backend.yml`** — builds, pushes to GHCR, updates the Bunny backend container
3. **`deploy-frontend.yml`** — builds, pushes to GHCR, updates the Bunny frontend container
4. **`deploy-extraction-worker.yml`** — builds, pushes to GHCR, updates the worker container on the workers Bunny app

### 4.3 Deployment Workflow Expectations

`deploy-backend.yml` triggers on changes to `apps/api/**` or
`.github/workflows/deploy-backend.yml` and should:

1. Check out the repository.
2. Log in to GHCR with `GITHUB_TOKEN`.
3. Build and push the backend image with `latest` and commit-SHA tags.
4. Run unit and integration tests in the container.
5. Update Bunny Magic Container `<project>-backend` with the selected image tag.

`deploy-frontend.yml` triggers on changes to `apps/web/**` or
`.github/workflows/deploy-frontend.yml` and should:

1. Check out the repository.
2. Build the Angular production bundle.
3. Build and push the nginx image with `latest` and commit-SHA tags.
4. Update Bunny Magic Container `<project>-frontend` with the selected image tag.

### 4.4 Production Promotion Flow

The intended flow is defined in `infra/README.md` §3.3:

1. Merge to `main` triggers automatic build + deploy to **staging**.
2. Validate in staging.
3. Promote to **production** via manual GitHub Actions environment approval or a release tag.

For the initial release, deploying directly from `main` to production is acceptable. Add the
staging gate once the first production deployment is stable.

### 4.5 Feature Flags

- Use PostHog or Supabase config for feature gates.
- Phase 2 features remain gated until G1 is passed.
- Basket optimiser and integrations remain behind gates in Phase 3.
- Any feature gate that exposes tenant-scoped data must preserve RLS enforcement and JWT-claim tenancy.
- Any automation gate must preserve the rule that humans authorise purchasing decisions.

### 4.6 CI/CD Validation Checklist

- [ ] GitHub repository or environment secrets configured per `infra/README.md` §2
- [ ] `ci.yml` green on the release commit
- [ ] `deploy-backend.yml` green
- [ ] `deploy-frontend.yml` green
- [ ] `deploy-extraction-worker.yml` green
- [ ] Image tags include both `latest` and commit SHA
- [ ] GHCR package visibility allows bunny.net to pull images
- [ ] Staging deployment completed or initial direct-production exception recorded
- [ ] Manual production approval or release tag used when staging gate is active

---

## Phase 5: Nginx Production Hardening

The current `infra/nginx/nginx.conf` has `connect-src` allowing `http://localhost:*`, which is
fine for development but should be tightened for production.

Update the CSP `connect-src` directive for the production image:

```
connect-src 'self' https://procurepilot-api.procurepilot.com https://<ref>.supabase.co wss://<ref>.supabase.co;
```

If the frontend and backend share a Bunny network namespace in the same app, `connect-src 'self'`
is sufficient since the SPA uses relative `/api/v1` paths.

Nginx injects the upstream host at startup through `envsubst`, so verify the production image
resolves the backend through the expected Bunny runtime topology and the local image resolves
through the Compose service name.

### 5.1 Security Header Checklist

- [ ] HTTPS enforced (HTTP redirects to HTTPS)
- [ ] HSTS header present (`Strict-Transport-Security`)
- [ ] X-Content-Type-Options: nosniff
- [ ] X-Frame-Options: DENY
- [ ] CSP header present and restrictive
- [ ] No secrets in browser network responses

---

## Phase 6: Smoke Test & Validation

### 6.1 Health Checks

```bash
# Backend
curl -sf https://procurepilot-api.procurepilot.com/api/v1/health

# Frontend
curl -sf https://procurepilot.com/ | head -5
```

Monitoring should use `/api/v1/health` for the backend and `/index.html` or `/` for the
frontend, depending on the monitor configuration.

### 6.2 Functional Smoke Test

1. Open the production URL in a browser.
2. Sign up a new user using the platform invitation token.
3. Create a workspace (tenant).
4. Navigate through the main flows:
   - Catalogue -> add a product
   - Suppliers -> add a supplier
   - Quotations -> upload a document
   - Review queue -> review a quotation (verify extraction provenance shows a real AI
     provider, not `stub-provider-v1`)
   - Requests -> create a purchase request (Phase 2 R2.1)
5. Verify i18n: switch locale to Arabic, confirm RTL layout.
6. Verify responsive layout: resize the browser to mobile widths (< 600px) and tablet widths
   (600-959px); confirm layouts adapt correctly with no horizontal overflow.
7. Verify tenant isolation: sign up a second user, confirm they see no data from the first tenant.

### 6.3 Release Validation Checklist

- [ ] Backend health check passing
- [ ] Frontend health check passing
- [ ] Sign-up flow works with platform invitation token
- [ ] Workspace creation works
- [ ] Catalogue flow works
- [ ] Supplier flow works
- [ ] Quotation upload works in `stub` extraction mode
- [ ] Review queue flow works
- [ ] RTL Arabic layout verified
- [ ] JWT tokens carry `tenant_id` claim
- [ ] Cross-tenant requests return 404 (not 403)
- [ ] No user-facing hardcoded copy introduced outside `packages/i18n`
- [ ] Monetary values include explicit currency

---

## Phase 7: Post-Release

### 7.1 Monitoring Setup

- [ ] Set up Sentry project and add `SENTRY_DSN` to backend env vars and web `environment.prod.ts`
- [ ] Set up PostHog project and add `POSTHOG_API_KEY`
- [ ] Configure bunny.net uptime monitoring for `https://procurepilot.com` and the API health endpoint
- [ ] Set up alerting for container restarts and health check failures
- [ ] Configure Sentry alerts for backend, web, and future mobile clients
- [ ] Configure PostHog funnels for release-critical product flows and retained gates
- [ ] Monitor availability through bunny.net dashboard checks and Sentry alerts
- [ ] SLA target: 99.5% Phase 1, 99.9% Phase 3

### 7.2 Backup Verification

- [ ] Confirm Supabase daily backups are enabled (Pro plan or higher)
- [ ] Test a point-in-time recovery in a throwaway project
- [ ] Document the database recovery procedure for migrations

### 7.3 Extraction Worker Deployment (Implemented)

The extraction worker (`services/extraction-worker`) is deployed as a **separate bunny.net
Magic Containers app** (`procurepilot-workers`), alongside a `shared-redis` container. This
was chosen over adding workers to the production app because:

- Independent scaling — extraction load does not affect API/frontend resources.
- Independent redeployment — worker code changes do not restart the API.
- Resource isolation — long-running AI inference calls do not contend with HTTP requests.

The production app's backend connects to Redis in the workers app via **Anycast IP** (not
`localhost`), since they are in separate Bunny apps. See Phase 3.5 and the runbook §7.2 for
the cross-app networking details.

**CI/CD:** `.github/workflows/deploy-extraction-worker.yml` deploys the worker image to
GHCR and updates the container on the workers app using `BUNNY_WORKERS_APP_ID`.

Each worker needs: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `REDIS_URL`,
`EXTRACTION_PROVIDER_MODE`, and AI-provider credentials (AWS for Bedrock, Azure for DI).
See the runbook §7.3 for the full variable list.

### 7.4 Staging Environment

Once production is stable, replicate the setup for staging:

```bash
cd infra/terraform
terraform workspace new staging
terraform apply -var-file=staging.tfvars
```

Staging uses:

- Separate Supabase project (independent data)
- `staging.procurepilot.com` hostname
- `staging-api.procurepilot.com` API hostname
- Separate GitHub Actions environment with auto-deploy on `main` merge

Use `infra/README.md` §3 as the full reference for independent configuration, data, routing,
and production promotion controls.

### 7.5 AI and Model-Change Release Gate

AI model and prompt changes must pass the evaluation harness before merge. A regression
blocks release until the measured accuracy, confidence, and review-band thresholds return to
the documented targets.

---

## Quick Reference: Architecture Diagram

```
  ┌──────────────────────────────────────────────────┐
  │  bunny.net — Production App                      │
  │  (shared network namespace)                      │
  │                                                  │
  │  ┌─────────────┐    ┌─────────────────┐          │
  │  │  Nginx :80   │───►│  FastAPI :8000   │         │
  │  │  (frontend)  │    │  (backend)       │──┐      │
  │  └─────────────┘    └─────────────────┘  │      │
  └──────────────────────────────────────────┼──────┘
       ▲                                     │
       │ HTTPS                               │ Anycast IP
  ┌────┴────┐                                │ (cross-app)
  │ Browser │                                │
  │ (SPA)   │                                ▼
  └─────────┘    ┌──────────────────────────────────┐
                 │  bunny.net — Workers App          │
                 │  (shared network namespace)       │
                 │                                   │
                 │  ┌──────────────┐  ┌───────────┐  │
                 │  │  Extraction   │  │  Redis    │  │
                 │  │  Worker       │──│  :6379    │  │
                 │  └──────────────┘  └───────────┘  │
                 └──────────┬────────────────────────┘
                            │
                   ┌────────▼─────────┐
                   │  Supabase Cloud   │
                   │  ┌─────────────┐  │
                   │  │ Postgres 17  │  │
                   │  │ (pgvector)   │  │
                   │  ├─────────────┤  │
                   │  │ GoTrue Auth  │  │
                   │  ├─────────────┤  │
                   │  │ Storage      │  │
                   │  └─────────────┘  │
                   └──────────────────┘
```

---

## Rollback Procedures

### Container Recovery

Every image is tagged with the commit SHA. To restore a previous backend image:

```bash
# Via bunny.net API
curl -X PATCH "https://api.bunny.net/compute/container-app/<app-id>/container/procurepilot-backend" \
  -H "AccessKey: <BUNNY_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"ImageTag": "<previous-commit-sha>"}'
```

Or use the bunny.net dashboard -> Magic Containers -> select container -> change image tag.

### Database Recovery

Migrations are forward-only. If a migration must be reverted:

1. Write a new migration that undoes the changes.
2. Apply it via `supabase db push`.
3. Never edit or delete a merged migration file.

For catastrophic failures, use Supabase's point-in-time recovery (PITR) from the dashboard.

---

## Checklist Summary

| Step | Status |
|---|---|
| Supabase project created | ☐ |
| Extensions enabled | ☐ |
| Migrations applied | ☐ |
| Access token hook configured | ☐ |
| Storage buckets created | ☐ |
| Reference data seeded | ☐ |
| Backend image built and pushed | ☐ |
| Frontend image built and pushed | ☐ |
| Terraform applied | ☐ |
| Container env vars configured (production app) | ☐ |
| Container env vars configured (workers app) | ☐ |
| Cross-app Redis reachable via Anycast IP | ☐ |
| Extraction provider mode set (not `stub`) | ☐ |
| Domain DNS delegated | ☐ |
| SSL verified | ☐ |
| GitHub secrets set | ☐ |
| CI pipeline green | ☐ |
| Health checks passing | ☐ |
| Functional smoke test passed | ☐ |
| Security headers verified | ☐ |
| Monitoring configured | ☐ |
