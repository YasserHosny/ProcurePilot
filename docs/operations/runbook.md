# ProcurePilot — Operations Runbook

> Step-by-step procedures for running ProcurePilot in production.

---

## 1. On-Call Basics

- Primary dashboards: Bunny Magic Containers, Supabase Dashboard, Sentry, PostHog.
- Severity levels:
  - **SEV-1** — platform down or data incorrect affecting payments/audit; page founder.
  - **SEV-2** — degraded experience; investigate within 1 hour.
  - **SEV-3** — non-urgent issue; ticket for next business day.

## 2. Health Checks

```bash
# Backend
curl https://<project>-api.<domain>/api/health

# Frontend
curl -I https://<project>.<domain>/index.html
```

## 3. Common Failures

### 3.1 Backend container unhealthy
1. Check Bunny container logs for crash or OOM.
2. If image issue, roll back to previous `ghcr` tag in Bunny dashboard.
3. Verify `BACKEND_HOST` is not set incorrectly on frontend.
4. If DB connection fails, check Supabase connection pooler / PgBouncer.

### 3.2 Extraction latency spikes
1. Check Bedrock/Azure status pages.
2. Review Sentry/PostHog for queue depth.
3. Scale extraction-worker container if queue > threshold.
4. Confirm document hash cache hit rate.

### 3.3 Matching precision drops
1. Run AI eval harness on latest benchmark.
2. Check for new supplier description patterns not in training data.
3. Lower auto-accept threshold temporarily if human review capacity exists. This only affects exact-key matches unless `MATCHING_FUZZY_AUTO_ACCEPT_ENABLED=true`; do not enable that until the match score is calibrated.
4. Add new aliases from recent corrections.

### 3.4 Review queue backlog
1. Dashboard: review-band size and items per 100 lines.
2. Prioritise by financial impact.
3. If persistent, widen candidate generation or improve alias learning.

### 3.5 Mobile push failures
1. Check Expo push service status.
2. Verify push tokens are current in tenant profile.
3. Test deep link routing.

### 3.6 Failed inbound email ingestion

1. Find terminal failed email-ingest jobs:

   ```sql
   select id, tenant_id, last_error
   from ingestion_jobs
   where job_type='email_ingest' and status='failed';
   ```

2. Check the job error and worker logs, then fix the underlying cause before retrying. The
   requeue command requires a failed `email_ingest` job with a stored `raw_email_path`.
3. Run the command from an environment with the worker's `DATABASE_URL` and API settings, such
   as the API or worker container. Preview the selected job first, then requeue it:

   ```bash
   python -m procurepilot_api.workers.requeue_email_ingest --job-id <id> --dry-run
   python -m procurepilot_api.workers.requeue_email_ingest --job-id <id>
   ```

   For all eligible failed email-ingest jobs for one tenant, use
   `--all-failed --tenant-id <id>` (and include `--dry-run` to preview). The command resets
   selected jobs to `pending` with zero attempts and records an `email_ingest_requeued` audit
   event. It exits non-zero if any explicitly requested job ID was skipped.
4. Confirm the worker completes the job and the corresponding `ingestion_email_log` row is
   `completed`. A post-parse processing failure is recorded as a failed log row with a short
   error. A failure before the raw email is fetched or parsed creates no log row.

**Known limit:** a worker hard-killed during its final attempt can leave no email-log row. The
failed job can still be recovered with this command when its stored raw email path is available.

### 3.7 Refused quotations after an extraction failure

A quotation is `refused` only when the document is unreadable or the extraction process itself
failed. An unreadable date no longer refuses a quotation; it goes to the review queue as
`date_unparsed` instead.

Line-structure problems also go to review rather than refusal: `merged_line_items` (one
extracted line holds several items), `line_count_mismatch` (the quote's table has more item rows
than lines produced), and `total_unverified` (a PDF/image quote with no stated total or no
computable line totals; CSV/XLSX uploads are exempt). A reviewer's save clears all three.

> **Deploy ordering:** these three values are added to the `review_task_reason` enum by
> `supabase/migrations/20261017000001_review_reason_line_structure.sql`. Apply that migration to
> the hosted database **before** deploying the extraction worker. Deploys do not run migrations,
> and a worker that writes an unknown enum value fails the job and refuses the quotation.

1. Fix the underlying cause (provider outage, worker bug, configuration) before retrying.
2. From an environment with the API's `DATABASE_URL` and `REDIS_URL`, such as the API or worker
   container, preview and then requeue:

   ```bash
   python -m procurepilot_api.workers.requeue_extraction --quotation-id <uuid> --dry-run
   python -m procurepilot_api.workers.requeue_extraction --quotation-id <uuid>
   ```

   `--quotation-id` can be repeated. For every eligible refused quotation in one tenant, use
   `--all-refused --tenant-id <uuid>` (with `--dry-run` to preview). A quotation is eligible only
   when it is `refused`, has a source document, and its latest extraction job is `failed` with
   error code `extraction_failed`; anything else is skipped. Each requeued quotation moves to
   `extracting` with a new queued extraction job and records a `quotation_extraction_requeued`
   audit event. If the Redis enqueue fails, the new job is marked failed
   (`redis_enqueue_failed`) and the quotation returns to `refused`. The command exits non-zero if
   any quotation was skipped.
3. Confirm the quotation reaches the review queue.

## 4. Scaling Actions

- **Database CPU > 70% sustained:** enable Supabase read replicas or review query plans.
- **Storage > 80%:** configure lifecycle rules for old source documents.
- **Backend CPU > 80%:** increase Bunny container CPU/ram or add second container.
- **Extraction queue > 1000 documents:** scale extraction-worker horizontally.

## 5. Backup & Restore

- Supabase provides daily automated backups.
- Test restore monthly in a separate project.
- Document RPO: 24 hours; RTO: 4 hours.

## 6. Security Incidents

1. Revoke affected user sessions via Supabase Auth.
2. Audit `AuditEvent` for suspicious actions.
3. Rotate leaked secrets.
4. Notify affected tenants per DPA.
5. Post-incident review within 5 business days.

## 7. Production Topology

### 7.1 bunny.net App Layout

Production uses **two separate bunny.net Magic Container apps**, not one:

| App | Containers | Purpose |
|---|---|---|
| `procurepilot-production` | `procurepilot-backend` (port 8000), `procurepilot-frontend` (port 80) | API + SPA; shared network namespace |
| `procurepilot-workers` | `procurepilot-extraction-worker`, `procurepilot-email-ingestion-worker`, `procurepilot-optimiser-worker`, `shared-redis` (port 6379) | Background extraction, inbound-email ingestion and basket-split jobs |

Containers within the same app share a network namespace (communicate via `localhost`).
Containers in **different** apps do not share a namespace — the backend API connects to the
workers app's Redis via **bunny.net Anycast IP** (e.g. `109.224.230.150:6379`), not `localhost`.

### 7.2 Cross-App Redis Networking

The backend API enqueues extraction jobs to Redis. Redis lives in the workers app. The
`REDIS_URL` on the backend container must point to the workers app's Anycast IP, not
`localhost` or a DNS hostname:

```
REDIS_URL=redis://109.224.230.150:6379/0
```

If Redis is unreachable from the backend:
1. Confirm the workers app is running and the `shared-redis` container is healthy.
2. Verify the Anycast IP hasn't changed (check the workers app's endpoint in the bunny.net
   dashboard).
3. Check that the Redis container's port (6379) is configured as a public endpoint on the
   workers app.

### 7.3 Extraction Worker Environment Variables

The extraction worker has its **own** set of env vars, separate from the backend API. These
must be configured on the `procurepilot-extraction-worker` container in the workers app:

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key for storage and DB writes |
| `DATABASE_URL` | Direct Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` (same app as Redis) |
| `EXTRACTION_PROVIDER_MODE` | `stub`, `bedrock`, or `azure_di` |
| `EXTRACTION_CONFIDENCE_THRESHOLD` | Default `0.85` |
| `AWS_ACCESS_KEY_ID` | For Bedrock provider |
| `AWS_SECRET_ACCESS_KEY` | For Bedrock provider |
| `AWS_DEFAULT_REGION` | e.g. `us-east-1` |
| `AZURE_DI_ENDPOINT` | For Azure Document Intelligence |
| `AZURE_DI_KEY` | For Azure Document Intelligence |
| `LOG_LEVEL` | `debug`, `info` (default), `warning`, `error`, `critical` |

The worker's `REDIS_URL` is `localhost` because Redis is in the same workers app. The
backend's `REDIS_URL` is the Anycast IP because Redis is in a different app.

### 7.4 Extraction Provider Mode Switching

To switch the extraction provider (e.g. from `stub` to `bedrock`):

1. Go to bunny.net dashboard → `procurepilot-workers` app → Container settings.
2. Edit `procurepilot-extraction-worker` → Environment variables tab.
3. Change `EXTRACTION_PROVIDER_MODE` to the desired value.
4. Click **Update Container**, then **Save Changes** (this triggers a redeployment).
5. Verify by uploading a test document and checking extraction provenance in the review page.

**Gotcha — stub provider provenance:** The `FakeExtractionProvider` (stub) misleadingly
reports `method: "bedrock"` and `model_version: "stub-provider-v1"` in provenance. Always
check the `model_version` field — a real Bedrock extraction shows the actual model ARN, not
`stub-provider-v1`.

### 7.5 Extraction Fallback Chain

When `EXTRACTION_PROVIDER_MODE=bedrock`, the worker uses this fallback chain:

1. Try Bedrock (Claude 3 Haiku via `boto3`).
2. If Bedrock throws any exception, silently fall back to Azure Document Intelligence.
3. The provenance will show `method: azure_di` even though `bedrock` was configured.

Common reasons Bedrock fails silently:
- AWS IAM credentials lack `bedrock:InvokeModel` permission.
- The model ARN is unreachable from the container's region.
- AWS credential environment variables not set on the worker container.

To diagnose: check the worker container logs in the bunny.net dashboard for the Bedrock
exception. Azure DI fallback often produces excellent results (95%+ confidence) so the
failure may go unnoticed in production.

### 7.6 Container Env Var Changes Require Redeployment

bunny.net does **not** hot-reload environment variables. After changing any env var on any
container:

1. Click **Update Container** in the container settings.
2. Click **Save Changes** at the app level — this triggers a full redeployment.
3. Wait for the container status to return to "Running" before testing.

### 7.7 Optimiser (Basket Split) Worker

The Two-Supplier Basket Split and advanced basket optimisation run in `services/optimiser`, an
RQ consumer on the `basket-split` queue. If it is not running, `basket_split_job` rows stay
`queued` and nothing computes them. Image: `ghcr.io/<owner>/procurepilot-optimiser-worker`
(built from `infra/docker/optimiser.Dockerfile`, rolled by
`.github/workflows/deploy-optimiser-worker.yml`, which only **updates** an existing container).

**One-time owner step:** in the `procurepilot-workers` app, create a container named exactly
`procurepilot-optimiser-worker` from that image (no public port, no endpoint needed) with:

| Variable | Required | Value |
|---|---|---|
| `DATABASE_URL` | yes | Supabase pooler connection string (the worker disables prepared statements itself) |
| `REDIS_URL` | yes | `redis://localhost:6379/0` (same workers app as `shared-redis`); must be the **same** Redis the backend's `REDIS_URL` points at |
| `BASKET_SPLIT_QUEUE_NAME` | yes | `basket-split` (must equal the backend's value) |

No other variables are read (`services/optimiser/.../settings.py`). Then **Save Changes** at the
app level (see 7.6). On start the log shows
`optimiser worker starting: queue=basket-split redis=<host>:<port>`; it exits immediately if
Redis is unreachable.

**Backend settings (optional):** `BASKET_SPLIT_STALL_SECONDS` (default 60) fails a queued job
when no worker is registered on the queue for that long; `BASKET_SPLIT_EXPIRY_SECONDS`
(default 900) fails any job still queued, or running, that long. The UI then shows
"the optimisation service is not responding" with a retry button (error codes
`optimiser_unavailable` / `optimiser_timeout`) instead of polling forever.

**Diagnose a stuck basket split:** is a `procurepilot-optimiser-worker` container Running? Do
its logs show the startup line? Does `rq info` against the shared Redis list a worker on
`basket-split`?

### 7.8 Email-Ingestion Worker

Inbound supplier emails (Mailgun → `POST /api/v1/webhooks/inbound-email`) are stored and queued as
`ingestion_job` rows with `job_type='email_ingest'`. The email-ingestion worker claims them from
the **database** every 15 s (no Redis queue for this step), stores the attachments, matches the
reply to its RFQ and supplier, and then enqueues extraction on Redis. If it is not running, inbound
quotes pile up as queued jobs and never reach the Quotation Inbox. Image:
`ghcr.io/<owner>/procurepilot-email-ingestion-worker`, built from
`infra/docker/email-ingestion-worker.Dockerfile` and rolled by
`.github/workflows/deploy-email-ingestion-worker.yml`, which only **updates** an existing container.

**One-time owner step:** in the `procurepilot-workers` app, create a container named exactly
`procurepilot-email-ingestion-worker` from that image (no public port, no endpoint). It runs the
API package and loads the API's full `Settings`, so it exits at start-up unless every required
API setting is present. Copy them from the backend container:

| Variable | Required | Value |
|---|---|---|
| `DATABASE_URL` | yes | Supabase pooler connection string (same as the backend) |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | yes | Used to read the raw email and write attachments to Storage |
| `SUPABASE_ANON_KEY`, `SUPABASE_JWT_AUDIENCE`, `SUPABASE_JWT_ISSUER` | yes | Not used by the worker, but required by `Settings` |
| `API_HOST`, `API_PORT`, `API_ENV`, `API_LOG_LEVEL`, `API_CORS_ORIGINS` | yes | Same values as the backend; required by `Settings` |
| `WEB_API_BASE_URL`, `WEB_DEFAULT_LOCALE` | yes | Same as the backend |
| `PLATFORM_INVITATION_TTL_DAYS`, `MEMBER_INVITATION_TTL_DAYS`, `RATE_LIMIT_AUTH` | yes | Same as the backend; required by `Settings` |
| `REDIS_URL` | yes in practice | `redis://localhost:6379/0` (same workers app as `shared-redis`). Defaults to that value; extraction is enqueued here, so it must be the Redis the extraction worker consumes |
| `EXTRACTION_QUEUE_NAME` | if changed | Must equal the extraction worker's queue name |
| `INGESTION_RAW_BUCKET` | if changed | Storage bucket for raw emails (default in `config.py`) |

The authoritative list of required settings is the set of `Settings` fields in
`apps/api/src/procurepilot_api/config.py` with no default. Then **Save Changes** at the app level
(see 7.6).

**Diagnose lost inbound quotes:** is the container Running? Do its logs show jobs being claimed?
Are there `ingestion_job` rows with `job_type='email_ingest'` stuck in `queued`? The operator CLI
`python -m procurepilot_api.workers.requeue_email_ingest` re-queues jobs by `--job-id` or `--all-failed` (try `--dry-run` first).

## 8. Logging & Diagnostics

### 8.1 Accessing Container Logs

bunny.net exposes container stdout/stderr in the dashboard:

1. Go to bunny.net → select the app (`procurepilot-production` or `procurepilot-workers`).
2. Select the container → **Logs** tab.
3. API logs are structured JSON; search for `"trace_id":"<value>"` to follow a single request.

### 8.2 Trace ID Correlation

Every API response includes an `X-Trace-Id` header. To trace a user-reported error:

1. Get the trace ID from the error response or browser dev tools (`X-Trace-Id` header).
2. Search the backend container logs for that trace ID.
3. All log lines for that request share the same `trace_id` field.

### 8.3 Changing the Log Level

The API log level is controlled by `API_LOG_LEVEL` (default: `info`). To increase verbosity:

1. Set `API_LOG_LEVEL=debug` on the backend container.
2. Click **Update Container** → **Save Changes** (triggers redeployment per §7.6).
3. Reproduce the issue; `debug`-level logs include detailed request processing.
4. Revert to `info` after diagnosis to reduce log volume.

### 8.4 Worker Logging

The extraction worker uses the same structured JSON logging as the API (shared
`procurepilot-logging` package). Key events to look for:

- `"bedrock failed, falling back to azure_di"` (warning) — Bedrock is misconfigured or
  unavailable; the fallback is no longer silent.
- `"extraction job failed"` (error) — full traceback of the failure.
- `"using stub provider"` (info) — extraction is running in stub mode; check
  `EXTRACTION_PROVIDER_MODE` if this appears in production.

Log level is controlled by the `LOG_LEVEL` env var on the worker container (default `info`).

## 9. Deployment Day Checklist

- [ ] Backend `.env` has all required credentials.
- [ ] `/api/health` responds.
- [ ] Frontend builds with `ng build --configuration=production`.
- [ ] `docker compose up --build` succeeds locally.
- [ ] GHCR images pushed with `latest` tag.
- [ ] Bunny production app containers updated and healthy.
- [ ] Bunny workers app containers updated and healthy.
- [ ] Redis reachable from backend via Anycast IP.
- [ ] Extraction worker `EXTRACTION_PROVIDER_MODE` set correctly (not `stub` in production).
- [ ] RLS enabled on all tables.
- [ ] Smoke test: onboard → upload → extract → compare → record saving.
- [ ] Verify extraction provenance shows the expected AI provider (not `stub-provider-v1`).

## 10. GHCR Package Visibility

GHCR packages default to private. bunny.net pulls images from GHCR using a configured Image
Registry with a GitHub PAT (scope: `read:packages`). If a new image fails to pull:

1. Go to GitHub → Packages → select the package.
2. Ensure visibility allows the PAT to read it, or that the repo's package settings are
   correctly linked.
3. Verify the Image Registry credentials in the bunny.net dashboard are still valid.

## 11. Contact Escalation

- Engineering lead — technical issues.
- Founder / Product Lead — commercial, prioritisation, customer comms.
- AI lead — model/prompt regressions.
