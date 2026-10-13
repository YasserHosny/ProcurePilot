# Self-Hosted Deployment Plan — Local Workstation (RTX 3090)

Status: **draft / not started** · Written: 2026-10-10

Goal: run ProcurePilot on a local workstation (RTX 3090, 24 GB VRAM) instead of hosted Supabase +
bunny.net Magic Containers, and optionally use the GPU to replace cloud AI providers
(AWS Bedrock, Azure Document Intelligence).

Most of the stack is already containerised, so Phases 1, 2 and 4 are ops work with no code changes.
Phase 3 (local AI) is the only part that needs new code.

## Current infrastructure (baseline)

| Area | Today |
|---|---|
| Containers | `infra/docker/`: `api`, `web` (Nginx), `extraction-worker`, `email-ingestion-worker`; compose also runs `redis`, `optimiser`, `export-worker`, `webhook-worker`, `offer-refresh-scheduler`, `catalogue-refresh-worker` |
| Data | Hosted Supabase: Postgres 17 (`pgvector`, `pg_trgm`), Auth, Storage · Redis + RQ queues |
| Hosting | bunny.net Magic Containers + bunny DNS, managed by Terraform (`infra/terraform/`, `BunnyWay/bunnynet`) |
| Registry / CI | GHCR · GitHub Actions (`ci`, `deploy-backend`, `deploy-frontend`, `deploy-extraction-worker`, `deploy-email-ingestion-worker`, `docs-screenshots`, `mobile-build-size-check`) |
| External services | AWS Bedrock (Claude), Azure Document Intelligence, Mailgun, QuickBooks, Xero, Square, Sentry, PostHog, FCM/APNs |

## Phase 1 — Run the stack on the box (no code changes)

- [ ] **Supabase**: run the official self-hosted Supabase docker-compose (Postgres 17 + pgvector/pg_trgm,
      GoTrue Auth, Storage, Kong). Do not use `supabase start`; that CLI stack is meant for development.
- [ ] **Migrations**: apply with `pnpm db:migrate` against the new database. Deploys never run
      migrations automatically, so make this an explicit deploy step.
- [ ] **App services**: run the existing `docker-compose.yml` services with `restart: unless-stopped`.
- [ ] **Add `email-ingestion-worker` to the compose file.** Today it only runs on bunny.net.
- [ ] **Reverse proxy**: extend `infra/nginx/nginx.conf` to route `/api` → api and the Supabase
      endpoints → Kong, alongside the web app.
- [ ] **Deploy path**: keep building images in GitHub Actions → GHCR. On the box, either:
  - Watchtower pulls new images automatically, or
  - a GitHub self-hosted runner runs a new `deploy-local.yml` workflow (replaces the bunny.net step).
- [ ] **Env**: generate a production `.env` on the box (new JWT secret, anon/service-role keys,
      encryption keys). Never commit it.

## Phase 2 — Reach the box from the internet

Several things need a public HTTPS address: Mailgun's inbound webhook, the QuickBooks/Xero/Square
OAuth redirects, and the mobile app.

- [ ] **Recommended: Cloudflare Tunnel** (`cloudflared`). No ports are opened on your router, you get
      TLS automatically, and it works without a static IP.
- [ ] Point DNS at the tunnel instead of bunny.net. Drop the bunny parts of Terraform, or replace them
      with the Cloudflare provider.
- [ ] Update the external callback URLs: Mailgun inbound route, `QUICKBOOKS_REDIRECT_URI`,
      `XERO_REDIRECT_URI`, Square, `API_CORS_ORIGINS`, and the mobile app's API base URL.
- Alternative for internal-only use: **Tailscale**. Simpler, but Mailgun and the OAuth callbacks would
  stop working.

## Phase 3 — Use the 3090 for AI (needs new code)

Today the code only supports these providers (`apps/api/src/procurepilot_api/config.py`):

- `extraction_provider_mode`: `stub | bedrock | azure_di`
- `matching_embedding_provider_mode`: `stub | bedrock`
- `analyst_intent_provider_mode`: `stub | bedrock`

Work: add a `local` option to each, calling an OpenAI-compatible endpoint served by **vLLM** or
**Ollama** on the GPU. Files to touch include
`services/extraction-worker/src/procurepilot_extraction_worker/{providers,settings}.py`,
`apps/api/src/procurepilot_api/modules/matching/embeddings.py` and
`apps/api/src/procurepilot_api/modules/analyst/intent.py`.

Models that fit within 24 GB of GPU memory:

| Job | Local model | Replaces |
|---|---|---|
| Quotation extraction (PDFs/images) | Qwen2.5-VL-7B or Qwen3-VL-8B, plus docling/PaddleOCR for layout | Bedrock Claude + Azure Document Intelligence |
| Analyst question understanding | A Qwen3-14B-class model, or a quantised ~32B model | Bedrock Claude |
| Product-matching embeddings | bge-m3 or Qwen3-Embedding (small, can share the GPU) | Bedrock embeddings (off by default) |

Caveats:

- **Running all three at once is tight.** You'll probably need one main model loaded at a time plus
  the small embedding model. Queue extraction jobs so they don't compete with analyst requests.
- **Extraction quality will drop compared to Claude.** There is no extraction eval harness today (only
  `ml/evals/product_matching/`). Build one first, and switch only when the eval passes.
- **Embedding size**: the pgvector column's dimension must match the new model's output. A change
  needs a forward-only migration plus a re-embed.
- Under the delegation rules, implementation goes to Codex/Agy as a normal spec
  (e.g. `specs/022-self-hosted-deployment` or a separate `local-inference` spec).

## Phase 4 — Operations (what the cloud handled for you)

- [ ] **Backups**: nightly `pg_dump` plus the Supabase Storage files, copied off the machine
      (e.g. Backblaze B2 / S3). Test restoring them on a schedule.
- [ ] **Power**: a UPS, and auto-start on boot (Docker restart policies, or a systemd unit for the
      compose stack).
- [ ] **Monitoring**: keep Sentry. Add uptime checks (e.g. Uptime Kuma) and alerts for GPU
      temperature/VRAM, disk space and container health.
- [ ] **Security**: secrets only in `.env`. Expose the Postgres port and Supabase Studio only over
      Tailscale, never publicly. Turn on OS auto-updates and a firewall (deny inbound; the tunnel
      only makes outbound connections).
- [ ] **Data migration**: dump the hosted Supabase (`public` + `auth` schemas) and copy the Storage
      objects. It's only test/staging data, so starting fresh with `pnpm db:seed` is also fine.
- [ ] **Verification**: run `pnpm test:isolation` and a full live UI walkthrough against the
      self-hosted stack before switching DNS.

## What stays external regardless

- **Mailgun**: sending email from a home IP gets it marked as spam.
- **FCM / APNs**: mobile push.
- **QuickBooks, Xero, Square**: these are the integrations themselves.
- **Sentry, PostHog**: they could be self-hosted too, but the effort isn't worth it.

## Suggested order

1. Phases 1 + 2 + 4 first, still calling Bedrock/Azure over the internet. This gives you a working
   self-hosted app quickly with nothing new to build.
2. Phase 3 later, as its own feature with an eval gate, so local models only take over once they're
   shown to be good enough.
