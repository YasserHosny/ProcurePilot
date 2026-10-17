# Extraction Worker

Reads supplier quotations (PDF, image, CSV, XLSX) into structured header and line data, with a confidence
per field, and decides whether a quotation needs human review. Spec: `specs/003-quotation-inbox-extraction`
(plus FR-005A, FR-011A) and `specs/022-home-currency-readiness`.

- Package `procurepilot_extraction_worker`; entrypoint `python -m procurepilot_extraction_worker` starts an RQ
  worker on `EXTRACTION_QUEUE_NAME` (default `quotation-extraction`).
- Talks to the API only through Redis jobs and Postgres; it does not import `apps/api`.
- Open database connections with this package's `db.connect` (prepared statements off, needed by Supabase's
  transaction pooler).

## How a quotation is read

| Input | Path |
|---|---|
| CSV / XLSX | `structured_parse.py` reads the cells directly; no AI |
| PDF / image, `EXTRACTION_PROVIDER_MODE=bedrock` (default) | `bedrock.py`; on failure falls back to `azure_di.py` |
| PDF / image, `EXTRACTION_PROVIDER_MODE=azure_di` | `azure_di.py` only |
| `EXTRACTION_PROVIDER_MODE=stub` | Fixed test output; for local runs and CI |

After any provider: dates are parsed in `dates.py` (DD/MM by workspace region, Arabic-Indic digits, Arabic month
names), currencies are detected in `currency.py` (no currency is guessed — the workspace home currency is only
stored as a suggestion), and `worker.py` picks a review reason when one applies (for example
`currency_unresolved`, `date_unparsed`, `merged_line_items`, `line_count_mismatch`, `total_unverified`,
`arithmetic_mismatch`, `low_confidence`). Azure line items come from the document's table, matched by Arabic or
English header meaning, so right-to-left tables are read correctly.

## Configuration

`DATABASE_URL`, `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `EXTRACTION_QUEUE_NAME`,
`EXTRACTION_PROVIDER_MODE`, `EXTRACTION_CONFIDENCE_THRESHOLD` (default `0.85`), `AWS_DEFAULT_REGION`,
`AWS_PROFILE`, `BEDROCK_MODEL_ID`, `AZURE_DI_ENDPOINT`, `AZURE_DI_KEY`, `LOG_LEVEL`. See `settings.py` for defaults.
Azure keys exist only on the hosted worker container, not in any local `.env`.

## Tests

```bash
cd services/extraction-worker
uv run pytest -q
uv run ruff check src tests
```

Azure fixtures under `tests/fixtures/azure_layout/` are hand-built in Azure's response format from real demo
documents (see that folder's README). `scripts/record_azure_fixtures.py` re-records real responses when Azure keys
are available.

## Operations

- Deploy: `.github/workflows/deploy-extraction-worker.yml` builds `infra/docker/extraction-worker.Dockerfile`
  and updates the `procurepilot-extraction-worker` container in the bunny.net workers app.
- Re-run extraction for refused quotations: `procurepilot_api.workers.requeue_extraction` in `apps/api`
  (`docs/operations/runbook.md`).
