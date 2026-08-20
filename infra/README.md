# ProcurePilot Infrastructure & Deployment

This directory contains infrastructure definitions, Docker configurations, Nginx proxy templates,
and helper scripts for ProcurePilot deployments.

---

## 1. Architecture Overview

- **Hosting & Compute:** [bunny.net](https://bunny.net/) Magic Containers (serverless container runtime at the edge).
- **Container Registry:** GitHub Container Registry (`ghcr.io`).
- **Database & Auth:** Hosted Supabase (PostgreSQL 17 with `pgvector` & `pg_trgm`, GoTrue Auth, Storage).
- **DNS & CDN:** bunny.net DNS and Edge CDN routing.
- **CI/CD:** GitHub Actions with path-filtered deployment workflows.

---

## 2. GitHub Secrets Reference (T079)

All deployments authenticate against GHCR using GitHub Actions' built-in `GITHUB_TOKEN` and deploy
to bunny.net Magic Containers using the following secrets.

> **CRITICAL:** Never commit secret values to the repository. Secrets are scanned by `gitleaks` on
> every pull request.

| Secret Name | Purpose | Where It Is Configured |
|---|---|---|
| `BUNNY_API_KEY` | Account-level API key for bunny.net; grants authorization to update container images via `BunnyWay/actions/container-update-image`. | GitHub Repository Secrets (or GitHub Organization Secrets). |
| `BUNNY_BACKEND_APP_ID` | The Magic Containers Application ID corresponding to the backend API (`procurepilot-backend`). | GitHub Environment / Repository Secrets. |
| `BUNNY_FRONTEND_APP_ID` | The Magic Containers Application ID corresponding to the frontend SPA (`procurepilot-frontend`). | GitHub Environment / Repository Secrets. |
| `GITHUB_TOKEN` *(built-in)* | Automatically supplied by GitHub Actions runtime. Used to authenticate to `ghcr.io` for pushing Docker images (`packages: write`). | Handled automatically by GitHub Actions. |

---

## 3. Staging and Production Separation (T080)

Staging and production environments are strictly isolated across configuration, data, infrastructure,
and promotion workflows.

### 3.1 Independent Configuration
- **GitHub Environments:** GitHub Actions workflows use dedicated GitHub Environments (`staging` and `production`) with environment-scoped secrets and protection rules.
- **Terraform Workspaces:** Infrastructure variables are parameterized per environment via variable definitions (e.g., `staging.tfvars` vs `production.tfvars`).
- **Hostnames and Routing:**
  - **Production:** Web on `procurepilot.com` (or `@`), API on `procurepilot-api.procurepilot.com`.
  - **Staging:** Web on `staging.procurepilot.com`, API on `staging-api.procurepilot.com`.

### 3.2 Independent Data
- **Supabase Projects:** Staging and Production run on completely separate hosted Supabase projects with independent database instances, GoTrue auth user stores, and storage buckets.
- **Encryption & Tokens:** Distinct `SUPABASE_JWT_SECRET`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` are used in each environment. A token issued for staging is invalid in production.
- **Zero Cross-Contamination:** Production databases are never accessed by staging builds or vice versa.

### 3.3 Promotion Pipeline
1. Pushes merged into `main` trigger automated builds and deployment to the **Staging** environment.
2. Changes undergo integration testing and design-partner validation in Staging.
3. Promotion to **Production** is gated behind manual authorization or release tags in GitHub Actions environments, preventing untested code from reaching live users.

---

## 4. Terraform Skeleton (T078)

The `infra/terraform/` directory contains declarative configurations for managing bunny.net
Magic Container applications, image registries, and DNS routing.

### Directory Layout
- `versions.tf` — Terraform version constraints and `BunnyWay/bunnynet` provider declarations.
- `variables.tf` — Variable declarations with type definitions and sensitivity flags.
- `main.tf` — Resources for container image registry integration (`GHCR`), compute container application, and DNS records.
- `outputs.tf` — Output declarations for application IDs and public endpoints.

### Validation
To initialize and validate the Terraform configuration:

```bash
cd infra/terraform
terraform init -backend=false
terraform validate
```

---

## 5. Deployment Workflows

- `.github/workflows/deploy-backend.yml` — Builds `infra/docker/api.Dockerfile`, tags with `latest` and `${{ github.sha }}`, pushes to GHCR, and updates the backend container on bunny.net.
- `.github/workflows/deploy-frontend.yml` — Builds the Angular SPA and Nginx image from `infra/docker/web.Dockerfile`, tags with `latest` and `${{ github.sha }}`, pushes to GHCR, and updates the frontend container on bunny.net.

---

## 6. Discrepancy Note: Local Development Stack

Older documentation (`docs/operations/deployment-plan.md` §1, §5) describes the local Supabase stack
as running entirely via `docker-compose.yml`. In accordance with ADR-005 and chunk research R5, local
Supabase database, auth, and storage services are managed using the **Supabase CLI** (`supabase start`).
The `docker-compose.yml` file remains available for container builds and integration testing, while
active local development connects to the CLI-managed stack.
