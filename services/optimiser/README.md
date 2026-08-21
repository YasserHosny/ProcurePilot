# Optimiser Worker

`services/optimiser` is the isolated worker for chunk 4.5 basket-split jobs.

It mirrors `services/extraction-worker`:

- Package: `procurepilot_optimiser_worker`
- Entrypoint: `python -m procurepilot_optimiser_worker`
- Queue: `BASKET_SPLIT_QUEUE_NAME`, default `basket-split`
- Runtime communication: Redis/RQ payload `{job_id, tenant_id}` plus direct Postgres reads/writes
- Boundary: no imports from `apps/api`; duplicate small helpers locally when needed

Run tests from an isolated venv rooted in this directory, with only this package installed:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```
