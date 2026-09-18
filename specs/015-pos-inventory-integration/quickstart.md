# Quickstart: POS & Inventory Integration — Usage Signals

## Running it locally

No real Square account is required for development or the automated test suite —
`POS_PROVIDER_MODE` defaults to `stub` (research.md R2), matching
`ACCOUNTING_PROVIDER_MODE`/`EXTRACTION_PROVIDER_MODE`'s existing convention. The stub connector
returns fixture sales-transaction and inventory-level data so the sync → match → signal pipeline
is fully exercisable without external credentials.

```bash
docker compose up --build        # api + web + local Supabase, as usual
pnpm db:migrate                  # applies this feature's new migrations
pnpm db:seed                     # unchanged — no POS-specific seed data required
```

To manually verify against a real Square sandbox before shipping:

1. Create a free Square Developer account and a sandbox seller (one-time human setup step, not
   something to script or fake).
2. Register an application in the Square Developer dashboard, get an application id/secret, and
   set:
   ```bash
   POS_PROVIDER_MODE=square
   SQUARE_APPLICATION_ID=...
   SQUARE_APPLICATION_SECRET=...
   SQUARE_REDIRECT_URI=http://localhost:8000/api/v1/pos/connect/callback
   SQUARE_ENVIRONMENT=sandbox
   POS_TOKEN_ENCRYPTION_KEY=...
   ```
3. Sign in as an owner, go to the new POS connection settings screen, and connect the sandbox
   seller account.

## Testing

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_square_client.py \
  apps/api/tests/unit/test_pos_matching_service.py \
  apps/api/tests/integration/test_pos_connection.py \
  apps/api/tests/integration/test_pos_sync.py \
  apps/api/tests/integration/test_pos_matching.py \
  apps/api/tests/integration/test_pos_sync_worker.py -v
```

Tenant isolation for the three new tables is proven inside the existing canonical
`apps/api/tests/integration/test_tenant_isolation.py`, not a separate file — run it directly to
confirm the new tables are covered by its own
`test_rls_is_enabled_and_forced_on_every_tenant_scoped_table` meta-test.

## Key files once implemented

- `apps/api/src/procurepilot_api/shared/token_crypto.py` — extracted from
  `modules/accounting/token_crypto.py` (research.md R3); both `accounting` and `pos` import from
  here. Verify the accounting module's own imports were updated in the same change, not left
  pointing at a duplicate.
- `apps/api/src/procurepilot_api/modules/pos/` — connection, sync, matching services; `router.py`
  for the 8 contract endpoints.
- `apps/api/src/procurepilot_api/workers/pos_sync_worker.py` — the recurring sync claim loop, same
  shape as `accounting_sync_worker.py`.
- `apps/web/src/app/features/pos/` — connection settings, unmatched-signals review screen.
- Existing screens gain inline context only, no new dashboard route: `offers/compare` (Smart
  Compare) and the catalogue product view show `sales_velocity_per_day` / `stock_on_hand` when a
  matched signal exists, per research.md R7 — verify no change was made to
  `modules/offers/recommendation.py`'s scoring logic itself (FR-003).
- `specs/015-pos-inventory-integration/contracts/pos-integration.openapi.yaml` — the API contract;
  reconcile against the real implementation before close-out, same as every prior feature's own
  contract-vs-implementation reconciliation step.
