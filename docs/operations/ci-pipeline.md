# CI pipeline notes

Last updated: 2026-10-18. Source of truth is `.github/workflows/ci.yml`; this page records *why* it is shaped the way it is.

## Docs-only pull requests skip the heavy jobs

A `changes` job (`dorny/paths-filter`, `predicate-quantifier: every`) decides whether a PR touches anything
outside `docs/`, `specs/`, `.specify/` and `*.md`. If not, every job except the secret scan is skipped.

- It is an `if:` on each job, **not** a workflow-level `on.paths` filter. A workflow that never triggers leaves
  required checks pending forever; a job skipped by `if:` counts as passing.
- Pushes to `main` always run everything.
- Editing `ci.yml` itself counts as a code change.
- The job also exposes a `web` output from a second `paths-filter` step (`apps/web/**`, `packages/**`,
  `.github/workflows/**`, `supabase/config.toml`). The second step exists because the first sets
  `predicate-quantifier: every` action-wide, under which a path must match **all** patterns at once and no single
  path is under both `apps/web/**` and `packages/**`, so a positive-only `web` filter would match nothing; the
  second step uses the default `any` quantifier.

## End-to-end is sharded five ways

Playwright runs with `workers: 1`, so the suite is serial inside a shard. The `e2e-shard` matrix splits the spec
*files* across five runners with the duration-balanced planner `scripts/ci/e2e_shard.py` (each shard runs explicit
file lists, not Playwright's `--shard`), each with its own isolated Supabase, Redis, API, extraction worker and web
app. The aggregate job `e2e`, named exactly `End-to-end`, passes when the matrix succeeded or was skipped, so the
check name other tooling may rely on is unchanged.

- The accessibility step runs the `*a11y*` specs; the following step runs the complement (files whose name lacks
  `a11y`). They used to overlap, which ran ~117 tests twice.
- Supabase CLI is pinned to `2.121.0` so CI does not hit the rate-limited GitHub API while resolving `latest`; bump
  it deliberately. `supabase start -x studio,vector,logflare,edge-runtime,postgres-meta,mailpit,realtime` skips the
  seven unused services, reducing image pulls from 12 to five (`postgres`, `gotrue`, `postgrest`, `kong`, and
  `storage-api`). Startup is retried up to five times with a 30-second-per-attempt backoff. The old 25-second
  per-shard start-up stagger is gone: with duration-balanced shards the delay landed on the critical path.
  `docs-screenshots.yml` uses the same CLI pin, exclusions and retry. To bring a service back, remove it from the
  `-x` list in **both** workflows.
- **Web build overlap.** `ng serve` is started in the background *before* the Supabase pull/start, so the web app
  compiles while the ~100 s Supabase pull/start runs; the dev server only needs the API at request time. The "Wait for
  the web app" step verifies readiness right before the first test (measured 0–1 s).
- **a11y step gating.** The accessibility step runs only when the `changes` job's `web` output is true (a PR
  touching `apps/web/**`, `packages/**`, `.github/workflows/**` or `supabase/config.toml`) and always on pushes to
  `main`; the functional step runs either way.
- **Duration-balanced shards.** `scripts/ci/e2e_shard.py plan` does a deterministic longest-processing-time split
  over `scripts/ci/e2e-durations.json`: a11y and functional files are balanced together, so a shard's two steps sum
  to a balanced total. Specs missing from the manifest get the median of the measured weights (1 s if none are
  measured) and are never dropped. The matrix size and the planner's `--total 5` must change together. The `lint`
  job runs the planner's unit tests plus `check`, so a new spec cannot be silently left out. Regenerate the manifest
  from downloaded CI list-reporter logs with `e2e_shard.py from-logs`.

## Docker layer cache (deploy workflows)

The five `deploy-*.yml` workflows cache BuildKit layers in the Actions cache, each under its own `scope` (`api`,
`email-ingestion-worker`, `extraction-worker`, `optimiser`, `web`). Before 2026-10-24 they all used the default scope
with `mode=max`: each image's build overwrote the shared cache index, so builds rarely reused each other's blobs,
and the orphaned blobs filled 10.4 GB of the repository's 10 GB Actions cache. That evicted the pnpm and uv caches CI
relies on. The four single-stage images now use `mode=min`, which stores the same layers for a single-stage build;
`web.Dockerfile` is two-stage, so it keeps `mode=max` to cache its build stage.

## Concurrency

Pushes to `main` get a per-commit concurrency group (`ci-<sha>`), so several merges landing close together validate
in parallel instead of queueing behind each other, and none is ever cancelled. PR runs keep the per-ref group
(`ci-<ref>`) with `cancel-in-progress`, so superseded PR runs are cancelled.

## Measured effect (2026-10-18)

| Change | Measurement |
|---|---|
| End-to-end wall time (sharding) | 22–26 min → ~9–10 min |
| Docs-only PR | ~26 min → seconds (secret scan only) |
| Slowest shard per run, old count-based sharding vs duration-balanced | mean 579 s over 6 runs → ~520 s over 3 trial runs of the final config, about −10% |
| Same-window A/B on `main` | commit `8e3bde6` (old E2E): slowest shard 605 s, run 620 s; commit `228188a` (new): 544 s / 558 s |

Runner speed varies about ±30% run to run, so single runs are indicative only.

Sharding costs roughly five times the ~150 s stack start-up in runner minutes, in exchange for a shorter wait. Runner
minutes are free on this public repository; the limit that matters is the Free plan's ~20 concurrent jobs, which one
run (five shards plus about eight other jobs) stays under.

**2026-10-24: three shards → five.** With three shards the slowest shard ran 6–8 min, of which ~5.3 min was specs
and ~2 min fixed stack start-up. The planner predicts ~330 s of specs per shard at `--total 3` and ~199 s at
`--total 5` (imbalance 1.019, all 63 spec files assigned once), so the E2E critical path should drop by about two minutes. Not yet measured.

## Verified after merge

- The main-run queueing fix is confirmed: two `main` runs started within 3 s of creation ran in parallel.
- The a11y gating is **not** yet confirmed on a backend-only PR: the PR that introduced it touched the workflows,
  which counts as a web change, so the gate has only ever seen `web=true`.

## Not done / ideas

- Refitting `e2e-durations.json` was evaluated and deliberately not done: it would move 37 of 61 files to a
  different shard, re-opening state-sharing risk between specs, for a balance gain smaller than runner noise.
  Revisit if shard times drift.
- Impact-based E2E spec selection is the biggest remaining lever and the riskiest; keep the full suite on `main`.
- Serve a prebuilt web app instead of `ng serve` (still `ng serve` in ci.yml).
- Use `pytest-xdist` for backend tests (Backend tests are ~150–210 s, the next floor once E2E shrinks).
- Two Playwright workers for the a11y step only (needs a shared-owner-state audit first).
