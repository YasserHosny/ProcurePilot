# Quickstart: Accounting Integration & Reconciliation Foundation

## Running it locally

No real QuickBooks account is required for development or the automated test suite —
`ACCOUNTING_PROVIDER_MODE` defaults to `stub` (research.md R5), matching
`EXTRACTION_PROVIDER_MODE`/`INGESTION_EMAIL_PROVIDER`'s existing convention. The stub connector
returns fixture bill/vendor data so the sync → match → discrepancy pipeline is fully exercisable
without external credentials.

```bash
docker compose up --build        # api + web + local Supabase, as usual
pnpm db:migrate                  # applies this feature's new migrations
pnpm db:seed                     # unchanged — no accounting-specific seed data required
```

To manually verify against a real QuickBooks sandbox before shipping:

1. Create a free Intuit Developer account and a sandbox company (research.md R5 — this is a
   one-time human setup step, not something to script or fake).
2. Register an app in the Intuit Developer dashboard, get a client id/secret, and set:
   ```bash
   ACCOUNTING_PROVIDER_MODE=quickbooks
   QUICKBOOKS_CLIENT_ID=...
   QUICKBOOKS_CLIENT_SECRET=...
   QUICKBOOKS_REDIRECT_URI=http://localhost:8000/api/v1/accounting/connect/callback
   QUICKBOOKS_ENVIRONMENT=sandbox
   ```
3. Sign in as an owner, go to the new accounting connection settings screen, and connect the
   sandbox company.

## Testing

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_quickbooks_client.py \
  apps/api/tests/unit/test_matching_service.py \
  apps/api/tests/integration/test_accounting_connection.py \
  apps/api/tests/integration/test_accounting_sync.py \
  apps/api/tests/integration/test_accounting_matching.py \
  apps/api/tests/integration/test_reconciliation_discrepancies.py \
  apps/api/tests/integration/test_accounting_sync_worker.py -v
```

Tenant isolation for the five new tables is proven inside the existing canonical
`apps/api/tests/integration/test_tenant_isolation.py`, not a separate file — run it directly to
confirm the new tables are covered by its own
`test_rls_is_enabled_and_forced_on_every_tenant_scoped_table` meta-test.

## Key files once implemented

- `apps/api/src/procurepilot_api/modules/accounting/` — connection, sync, matching,
  reconciliation services; `router.py` for the 8 contract endpoints.
- `apps/api/src/procurepilot_api/workers/accounting_sync_worker.py` — the daily
  `FOR UPDATE SKIP LOCKED` sync claim loop, same shape as `email_ingestion_worker.py`.
- `apps/web/src/app/features/accounting/` — connection settings, bills list, discrepancy list.
- `specs/014-accounting-integration/contracts/accounting-integration.openapi.yaml` — the API
  contract; reconcile against the real implementation before close-out, the same way
  013-automated-ingestion's own contract needed reconciliation after implementation diverged from
  the pre-written design (see that feature's T041 for the precedent and why this step matters).
