# ProcurePilot — Deployment / CI-CD / Infrastructure Plan

> How ProcurePilot builds, deploys, and rolls back across environments.

---

## 1. Environments

| Environment | Purpose | Trigger |
|---|---|---|
| Local | Developer feedback | `docker compose up --build` |
| CI | Tests and image builds | PR / push to `main` |
| Staging | Design-partner validation | Successful CI on `main` |
| Production | Live customers | Manual promotion from staging |

## 2. CI/CD Platform

- **GitHub Actions** with path-filtered workflows.
- **Container registry:** GitHub Container Registry (`ghcr.io`).
- **Build:** Docker Buildx with GHA cache.
- **Deploy:** `BunnyWay/actions/container-update-image` to bunny.net Magic Containers.

## 3. Workflows

### `deploy-backend.yml`

Triggers on changes to `apps/api/**` or `.github/workflows/deploy-backend.yml`.

1. Checkout.
2. Log in to GHCR with `GITHUB_TOKEN`.
3. Build and push backend image with tags `latest` and commit SHA.
4. Run unit and integration tests in container.
5. Update Bunny Magic Container `<project>-backend` with `latest`.

### `deploy-frontend.yml`

Triggers on changes to `apps/web/**` or `.github/workflows/deploy-frontend.yml`.

1. Checkout.
2. Build Angular production bundle.
3. Build and push Nginx image with tags `latest` and commit SHA.
4. Update Bunny Magic Container `<project>-frontend` with `latest`.

### `build-mobile.yml`

Triggers on changes to `apps/mobile/**`.

1. Checkout.
2. Build Flutter iOS and Android bundles.
3. Upload artifacts; tag release for store submission.

## 4. Bunny Magic Containers

- Single Bunny app contains two runtime containers:
  - `<project>-backend` — port 8000, hostname `<project>-api.<domain>`.
  - `<project>-frontend` — port 80, hostname `<project>.<domain>`.
- Containers share a network namespace; frontend uses `BACKEND_HOST=localhost`.
- Required GitHub secrets:
  - `BUNNY_API_KEY`
  - `BUNNY_BACKEND_APP_ID`
  - `BUNNY_FRONTEND_APP_ID`

## 5. Local Development

```bash
docker compose up --build
# Frontend: http://localhost
# API proxied through Nginx: http://localhost/api/
```

- `BACKEND_HOST=backend` in Docker Compose (service name).
- `BACKEND_HOST=localhost` in Bunny production.

## 6. Feature Flags

- Use PostHog or Supabase config for feature flags.
- Phase 2 features gated until G1 is passed.
- Basket optimiser and integrations behind flags in Phase 3.

## 7. Rollback

- Bunny containers can be rolled back to the previous GHCR image tag.
- Database rollbacks require forward-compatible migrations + a revert script for the last migration.
- AI model/prompt changes are gated by eval harness; a regression blocks merge.

## 8. Secrets & Configuration

- Backend `.env` (never committed): Supabase credentials, AWS/Azure AI keys, CORS origins.
- CI secrets: Bunny API key, GHCR token.
- Nginx injects `BACKEND_HOST` at container startup via envsubst.

## 9. Infrastructure as Code

- Terraform manages Bunny Magic Containers, custom hostnames, and Supabase project provisioning.
- Terraform state stored remotely (bucket/backend to be chosen before first deploy).

## 10. Monitoring & Alerting

- **Health checks:** `/api/health` backend; `/index.html` frontend.
- **Error tracking:** Sentry across web, mobile, backend.
- **Product analytics:** PostHog funnels and feature flags.
- **Uptime:** Bunny dashboard + Sentry alerts.
- **SLA target:** 99.5% Phase 1, 99.9% Phase 3.
