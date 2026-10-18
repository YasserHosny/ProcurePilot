# Integration suite against hosted Supabase: latency assessment

Date: 2026-10-18 · Scope: `apps/api/tests/integration` (136 files, ~1,190 DB-backed tests) run with
`TEST_DATABASE_URL`/`DATABASE_URL` pointing at the hosted pooler in session mode
(`aws-1-eu-west-1.pooler.supabase.com:5432`) versus a throwaway local
`public.ecr.aws/supabase/postgres:17.6.1.166` container.

## Summary

The hosted run is slow because the suite makes about **89,000 sequential statements and 2,800
connections**, and every one of them waits for one network round trip to eu-west-1. A round trip
costs **67.5 ms** and a connection costs **429 ms**. Postgres does almost no work: the same subset
takes 39.5 s locally and 1,333 s on hosted (34× slower), and the whole integration suite runs locally
in about 5.5 minutes. A cost model of `connects × 0.429 s + statements × 0.0675 s`, built from counted
statements, predicted the hosted subset within 5% (1,265 s predicted, 1,333 s measured). For the full
integration suite it predicts **about 121 minutes of pure network wait**. That matches what was seen:
34 files did not finish in 590 s, and the run was only about 43% done after 20 minutes.

There is no slow query, no sleep or poll loop, and no Supabase HTTP call to hosted. The cost is
round trips. Two small helper changes (psycopg pipeline mode, proof of concept below) remove most
of the two biggest sources:

| Change (PoC, branch `claude/epic-chebyshev-ab8fc5`) | Hosted, measured |
|---|---|
| Teardown: `delete_tenant_scoped_rows`, 88 DELETEs | 6,425 ms → **283 ms** per tenant |
| `test_tenant_isolation.py` `workspaces` fixture, 122 INSERTs | 8,971 ms → **302 ms** per test |
| Subset (4 files, 132 tests), end to end | 1,333 s → **272 s** (4.9×), 132 passed |

## 1. Network: round trip and connection cost

Script: `lat.py` (scratch, below). Run from this workstation, with the DSN taken from the main
checkout's `.env` and `:6543` swapped for `:5432`.

```text
== hosted session :5432
connect: median 429 ms  min 405  max 436  (n=5)
select 1 RTT: median 67.5 ms  p90 68.0  (n=50)
tenant_id base tables: 88
information_schema lookup: 79 ms
```

A connection costs about 6 round trips (TCP, TLS, startup and SCRAM auth through Supavisor). ICMP
to the pooler is blocked, so `select 1` is the only RTT measurement. The direct host
`db.<ref>.supabase.co` resolves only to IPv6, and this host has no IPv6 route
(`connect: Network is unreachable`), so the pooler is the only way in from here.

## 2. What a test does: connections and statements

A pytest plugin (`dbcount.py`, scratch) wrapped `psycopg.connect` and `psycopg.Cursor.execute`.
That covers both test helpers and app code, because `procurepilot_api.db.connect` delegates to
`psycopg.connect`. It counted per test phase across the whole integration suite on the local
throwaway DB:

```text
tests=1189 connects=2844 statements=89208 deletes=34364 infoschema_lookups=380
setup    {'connect': 511,  'stmt': 21413, 'delete': 32}
call     {'connect': 2221, 'stmt': 57779, 'infoschema': 276, 'delete': 24940}
teardown {'connect': 112,  'stmt': 10016, 'delete': 9392, 'infoschema': 104}
predicted hosted network time: connects 1220s + statements 6022s = 120.7 min
  of which teardown DELETEs: 2320s (32%), connects 17%
```

Statements by kind (second full run, 88,648 statements):

| Kind | Count | Share | Hosted cost at 67.5 ms |
|---|---:|---:|---:|
| `DELETE` (teardown, nearly all from `delete_tenant_scoped_rows`) | 34,364 | 39% | ~2,320 s |
| `INSERT` (fixture builders) | 33,632 | 38% | ~2,270 s |
| `set local role` / `reset role` / `set_config('request.jwt.claims')` / `session_replication_role` | 13,371 | 15% | ~900 s |
| `SELECT` | 5,019 | 6% | ~340 s |
| `UPDATE` + other | 2,262 | 2% | ~150 s |
| Connections (2,844 × 429 ms) | | | ~1,220 s |

How each helper contributes:

- **`catalogue_helpers.delete_tenant_scoped_rows`** sends one `information_schema` lookup and then
  one `DELETE` for **each of the 88** `tenant_id` tables, each in its own round trip. That is about
  6.4 s per tenant on hosted. It is called about 380 times (the number of `information_schema`
  lookups), which accounts for essentially all 34k DELETEs. `smart_compare_helpers.cleanup_workspace`
  calls it, plus three more statements.
- **`committed_smart_context` / `cleanup_workspace`** each open their own connection (429 ms each),
  and the cleanup runs inside the test body's `with` block. As a result `--durations` reports
  teardown cost as **call** time, and the teardown column looks nearly empty (8 s of 1,333 s)
  although DELETEs are the largest cost.
- **`test_tenant_isolation.py`'s `workspaces` fixture** builds two rich workspaces of about 61
  inserts each: **122 statements per test** across 117 tests, all rolled back. That is 14% of the
  whole suite's hosted time in a single file (~1,043 s).
- **App code**: each `_authenticated_db` / service call opens a fresh `db.connect()`. That is the
  production design (one connection per request), but it is why the call phase opens 2,221
  connections (`test_order_tracking.py`: 7 per test).
- **`act_as`** costs 2 round trips (`set local role` plus `set_config`), and helpers such as
  `make_canonical_product` add a `select current_role` and a role restore around every insert.

Top files by predicted hosted time (local counts × hosted cost):

```text
  test_tenant_isolation.py                      n=117 con=  117 stmt= 14714 del=   13 ~  1043s cum   14%
  test_reporting_isolation.py                   n= 28 con=  167 stmt= 13495 del= 9630 ~   983s cum   28%
  test_forecasting_pagination.py                n=  1 con=    1 stmt=  4143 del=   87 ~   280s cum   32%
  test_create_idempotency_replays.py            n= 17 con=   71 stmt=  2476 del= 1530 ~   198s cum   35%
  test_pos_connection.py                        n= 15 con=   89 stmt=  2245 del= 1440 ~   190s cum   37%
  test_order_tracking.py                        n= 11 con=   77 stmt=  1880 del= 1085 ~   160s cum   39%
  test_rfq_isolation.py                         n= 41 con=   43 stmt=  2020 del=   26 ~   155s cum   42%
  ...
```

## 3. Durations: subset on hosted versus local

Subset: `test_saving_evidence.py test_saving_verification.py test_order_tracking.py
test_tenant_isolation.py` (132 tests).

```text
# local throwaway (:54397)
132 passed, 1 warning in 39.55s
setup         21.2s   60.0%   call   14.1s   39.9%   teardown   0.0s    0.1%

# hosted session pooler (:5432), same code
132 passed, 1 warning in 1332.83s (0:22:12)
setup       1044.8s   78.6%   call  276.1s   20.8%   teardown   8.1s    0.6%
files: test_tenant_isolation.py 1084.2s, test_order_tracking.py 186.6s,
       test_saving_evidence.py 30.4s, test_saving_verification.py 27.9s
slowest: 24.68s call test_order_tracking.py::test_cross_tenant_and_role_rejections (1.94s local)
```

On hosted, setup is 78.6% of the time, and nearly all of it is the 117 tenant-isolation `workspaces`
fixtures at about 8.9 s each.

## 4. Things that are not the cause

- **Supabase/PostgREST HTTP to hosted**: none. `tests/conftest.py` pins `SUPABASE_URL` to
  `http://localhost:54321` with an autouse fixture, and storage/import tests replace `create_client`
  with fakes. The audit writer's bearer-token path (`shared/audit.py`, `rpc(...)`) does make real
  HTTP calls, but to the *local* Supabase CLI stack, never to hosted. That is a separate
  correctness gap: those tests fail with `PGRST301 Expected 3 parts in JWT` or
  `503 dependency: audit_event` unless a local stack accepts the fake key. This is pre-existing and
  is not a latency issue.
- **Sleeps, polls or retries**: `grep -rn "time.sleep\|asyncio.sleep" apps/api/tests/integration`
  finds nothing. No single test stands out; the slowest hosted test is slow only because it makes
  about 300 round trips.
- **Server-side query cost**: the local container runs the same statements in 39.5 s, and the full
  integration suite in 264–334 s.

## 5. Solutions, ranked by measured or estimated gain

Estimates are against the ~121 min predicted network time for the full hosted integration run.

### A. Pipeline mode in teardown: ~−35 min, low risk (PoC done)

Wrap the delete loop in `delete_tenant_scoped_rows` in `with cur.connection.pipeline():`. All 88
DELETEs then go out in one batch and their results come back together, under the same transaction
and the same `session_replication_role = replica`. Measured with `bench.py` (rolled back, random
tenant id):

```text
== hosted session :5432
teardown: 88 DELETEs, one round trip each (today)       median    6425 ms
teardown: same DELETEs in psycopg pipeline mode         median     283 ms
teardown: set local + one DO block, single round trip   median     162 ms
== local throwaway :54397
teardown: 88 DELETEs, one round trip each (today)       median     138 ms
teardown: same DELETEs in psycopg pipeline mode         median      87 ms
teardown: set local + one DO block, single round trip   median      81 ms
```

About 380 calls × ~6.1 s saved ≈ **2,300 s**. A **DO block** is about 120 ms faster per tenant, but it
has a catch: Supabase's `postgres` role may run `SET session_replication_role` as a top-level
statement but not through `set_config()` inside PL/pgSQL (`permission denied to set parameter
"session_replication_role"`). The SET has to be sent as a separate statement in the same simple-query
string, so the DO-block variant depends on that. Pipeline mode keeps the existing Python shape and
error behaviour: a failed DELETE still raises, just at the end of the pipeline block. Caching the
table list per session saves a further 380 × 79 ms ≈ 30 s.

`ON DELETE CASCADE` is not an alternative: replica mode disables FK enforcement, cascades
included, and that is exactly why the helper deletes table by table.

### B. Pipeline mode in fixture builders that read nothing back: ~−16 min for one file, more if extended

`test_tenant_isolation.py`'s `make_workspace` makes 61 inserts and fetches nothing, so wrapping the
`workspaces` fixture in `conn.pipeline()` is transparent (measured 8,971 ms → 302 ms per test,
≈ **−960 s**). Inserts are 38% of all statements, so the same treatment for other builders
(`make_workspace`, `make_supplier`, `make_workspace_product`, the reporting-isolation fixtures, the
4,143-statement `test_forecasting_pagination.py` seed, which should be a single `insert … select
generate_series`) is the next largest win. The limit is that a builder which reads `RETURNING` or
`fetchone()` in the middle forces a sync. Each one needs a look; this is not a blanket change.

### C. Fewer role-switch round trips: ~−8 min, low risk

`act_as` makes two calls. A single
`select set_config('role','authenticated',true), set_config('request.jwt.claims',%s,true)` is
equivalent to `set local role` plus `set_config` and halves the 13.4k role/claims statements
(≈ −450 s). The bracketing in `make_canonical_product` (`select current_role` → `reset role` →
insert → restore) could be pipelined as well.

### D. Connection reuse in tests: ~−15 min, medium risk

2,844 connections × 429 ms ≈ 1,220 s, and 78% of them are app-side `db.connect()` calls in the call
phase. A test-only pool (monkeypatch `procurepilot_api.db.connect` to hand out pooled connections
with a `RESET ALL; RESET ROLE` reset) would cut most of that. Trade-off: it changes what the tests
exercise. Production opens a fresh connection per request, and the transaction-pooler role-leak
bug class (`make_workspace`'s `reset role` comment) only appears with fresh or leaked sessions. A
pool can also hide missing `set local` scoping. `psycopg_pool` is not installed. Do this last, and
only on top of A–C.

### E. Session- or module-scoped reference data: small

`make_workspace` re-inserts `supported_region`/`currency`/`tax_model` with `on conflict do nothing`
on every call: 4 round trips, ≈ 270 ms per workspace on hosted. A session-scoped fixture would save
about 1–2 minutes in total. Converting the `workspaces` fixture itself to module scope with a
SAVEPOINT per test would save a little more than B, but B already reduces it to about 0.3 s, so the
isolation risk of a shared fixture is not worth it.

### F. pytest-xdist against hosted: up to ~4× wall time, blocked today

The run is latency-bound, not throughput-bound, so N workers scale almost linearly until pooler
limits. However, `pytest-xdist` is not installed, **35 integration files use fixed
`…@example.test` emails** (`users_email_key` collisions, the leak noted in
`test_rfq_service_e2e.py` / `test_analyst_service_e2e.py`), and the owner-guard teardown pattern
must hold under concurrency. Each worker also holds session-mode pooler connections; the Supabase
plan's pooler client limit caps N. Making emails unique per run is a prerequisite.

### G. Run hosted tests from a runner in eu-west-1: removes the problem, costs infrastructure

The cost scales with RTT, so a runner in the same AWS region (about 1 ms RTT) would run the hosted
suite at close to local speed with no code change. GitHub-hosted runners (mostly US) would *not*
help: their RTT to eu-west-1 is similar or worse. CI does not touch hosted today in any case: the
`Backend tests` job uses an ephemeral `postgres` service (`ci.yml:202`, `TEST_DATABASE_URL:
postgresql://postgres:postgres@localhost:5432/postgres`). The only option would be a self-hosted
runner or a bunny.net/AWS container in eu-west-1 for a scheduled hosted job.

### H. Default local verification to a throwaway DB: recommended policy

The full suite takes 264–401 s on a throwaway container, against roughly 2 h on hosted. Hosted adds
value only for environment-specific facts: migrations are actually applied, default privileges
differ per environment (the reason `test_tenant_isolation`'s privilege tests passed only in CI,
#145), and pooler behaviour. Recommendation:

1. Agent briefs and local checks use a throwaway container (recipe in memory
   `throwaway-db-for-unmerged-migrations`). This changes the current default.
2. A hosted **smoke subset**: `pnpm db:check-privileges` plus `test_tenant_isolation.py`
   (~2 min with B, ~18 min without) plus one committed-workspace flow such as `test_order_tracking.py`.
   Run it after a migration lands on hosted, not on every change.
3. Apply A–C regardless, because they also make local and CI runs faster (teardown 138 → 87 ms
   locally).

**Expected combined effect on a full hosted run:** A + B (isolation only) + C ≈ 121 → ~60 min;
adding B across builders and D ≈ ~25–30 min; xdist on top could bring it under 10 min. Policy H
removes the need for most of that.

## 6. Proof of concept

Branch `claude/epic-chebyshev-ab8fc5` (separate draft PR): two test-infrastructure files only. It
changes shared test helpers, so it waits for an explicit go-ahead before merge:

- `apps/api/tests/integration/catalogue_helpers.py`: `delete_tenant_scoped_rows` deletes inside
  `cur.connection.pipeline()`.
- `apps/api/tests/integration/test_tenant_isolation.py`: the `workspaces` fixture builds both
  workspaces inside `conn.pipeline()`.

Verification:

```text
# local, subset, patched
132 passed, 1 warning in 42.09s

# local, deterministic teardown check (committed_smart_context → cleanup_workspace)
tenant-scoped rows inside context: 5
tenant-scoped rows after cleanup_workspace: 0

# hosted, subset, patched
132 passed, 1 warning in 272.14s (0:04:32)
setup     84.3s   call  176.3s   teardown   8.1s
files: test_tenant_isolation.py 1084.2s → 123.2s, test_order_tracking.py 186.6s → 111.8s,
       test_saving_evidence.py 30.4s → 17.3s, test_saving_verification.py 27.9s → 16.3s
```

## 7. Commands

```bash
# throwaway DB (port 54397), storage-schema workaround, all migrations
docker run -d --name pp-perf-db -e POSTGRES_PASSWORD=postgres -p 54397:5432 public.ecr.aws/supabase/postgres:17.6.1.166
supabase migration up --db-url "postgresql://postgres:postgres@localhost:54397/postgres?sslmode=disable"

# durations (from apps/api, main venv, PYTHONPATH=$PWD/src:$PWD/tests)
python -m pytest tests/integration/test_saving_evidence.py tests/integration/test_saving_verification.py \
  tests/integration/test_order_tracking.py tests/integration/test_tenant_isolation.py \
  -q -p no:cacheprovider --durations=0

# statement/connection counting across the suite (local)
DBCOUNT_OUT=count.json python -m pytest -p dbcount tests/integration -q -p no:cacheprovider
```

The hosted runs used a detached `setsid nohup bash run_hosted.sh &`, because the host watchdog kills
long background shells. The scratch scripts (`lat.py`, `bench.py`, `dbcount.py`) are not committed;
`bench.py` runs every measurement in a transaction that is rolled back, against a random tenant id.

Caveats: the full-suite local counts come from runs with 35 (first run) and 59 (second run,
overlapping with other work on the same DB) environmental failures (PostgREST JWT, fixed-email
leaks). Failed tests stop early, so the statement totals are slight undercounts. The hosted numbers
reflect one workstation's network path; another location changes the RTT and every estimate scales
with it.
