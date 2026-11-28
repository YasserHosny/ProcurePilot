# CI pipeline notes

Last updated: 2026-10-31. Source of truth is `.github/workflows/ci.yml`; this page records *why* it is shaped the way it is.

## Docs-only pull requests skip the heavy jobs

A `changes` job (`dorny/paths-filter`, `predicate-quantifier: every`) decides whether a PR touches anything
outside `docs/`, `specs/`, `.specify/` and `*.md`. If not, every job except the secret scan is skipped.

- It is an `if:` on each job, **not** a workflow-level `on.paths` filter. A workflow that never triggers leaves
  required checks pending forever; a job skipped by `if:` counts as passing.
- If the `changes` job itself fails (say a `paths-filter` API error), every job gated on it is skipped, and a
  skipped job counts as passing. The `End-to-end` gate therefore fails whenever `changes` did not succeed, and it
  accepts a skipped shard matrix only when `changes` reported no code change, so a broken filter cannot let a PR
  through untested. «Regenerate and diff» (below) applies the same rule.
- Pushes to `main` always run everything.
- Editing `ci.yml` itself counts as a code change.
- The job also exposes a `web` output from a second `paths-filter` step (`apps/web/**`, `packages/**`,
  `.github/workflows/**`, `supabase/config.toml`). The second step exists because the first sets
  `predicate-quantifier: every` action-wide, under which a path must match **all** patterns at once and no single
  path is under both `apps/web/**` and `packages/**`, so a positive-only `web` filter would match nothing; the
  second step uses the default `any` quantifier.

## End-to-end is sharded six ways

Playwright runs with `workers: 1`, so the suite is serial inside a shard. The `e2e-shard` matrix splits the spec
*files* across six runners with the duration-balanced planner `scripts/ci/e2e_shard.py` (each shard runs explicit
file lists, not Playwright's `--shard`), each with its own isolated Supabase, Redis, API, extraction worker and web
app. The aggregate job `e2e`, named exactly `End-to-end`, passes when the matrix succeeded, or was skipped because
`changes` found no code change, so the check name other tooling may rely on is unchanged.

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
  touching `apps/web/**`, `packages/**`, `.github/workflows/**`, `supabase/config.toml`, or the shard planner
  `scripts/ci/e2e_shard.py` and its manifest, since those decide which a11y specs share a stack) and always on
  pushes to `main`; the functional step runs either way.
- **Duration-balanced shards.** `scripts/ci/e2e_shard.py plan` does a deterministic longest-processing-time split
  over `scripts/ci/e2e-durations.json`: a11y and functional files are balanced together, so a shard's two steps sum
  to a balanced total. Specs missing from the manifest get the median of the measured weights (1 s if none are
  measured) and are never dropped. The matrix size and the planner's `--total 6` must change together (the matrix,
  both Playwright steps and the `lint` job's `check`). The `lint` job runs the planner's unit tests plus `check`, so
  a new spec cannot be silently left out; `check` also prints a WARNING when more than 10% of spec files have no
  measured duration, so manifest drift shows in the lint log before it shows as a slow shard.
- **Weekly manifest refresh.** `.github/workflows/e2e-durations-refresh.yml` runs on Sundays (and on demand from
  the Actions tab). It downloads the E2E shard logs of the last 5 green push-to-main `CI` runs (the latest successful
  attempt of each shard, so a re-run lint job does not hide them; at least 3 runs must contribute), refits the
  manifest with `e2e_shard.py from-logs --carry` (median per file; a live spec the sample did not measure keeps its
  committed timing, so a partial sample cannot fake a gain), and scores it with `e2e_shard.py gain`: both the current and the
  refitted plan are scored on the refitted durations, and a PR (`ci/e2e-durations-refresh`) is opened or updated
  only when the refit takes at least 5 s off the slowest shard. Smaller weekly changes accumulate against the
  committed manifest until they cross that bar. It reads the shard count from `ci.yml`, so it needs no edit when
  the count changes. It replaces the PR branch only when every commit on it is its own (with a lease on the tip it
  checked); a maintainer's commit there makes it skip the update with a warning. Re-partitioning changes which specs
  share a stack: merge its PR only on a green run.
- **The refresh token.** The PR is pushed and opened with the `E2E_MANIFEST_TOKEN` secret, a fine-grained personal
  access token scoped to this repository with Contents and Pull requests read/write. A PR opened with the default
  `GITHUB_TOKEN` triggers no `pull_request` workflows, so the required checks would never run on it. Without the
  secret the workflow fails on its first step. The token expires; renew it before then.
- To refit by hand: download the shard job logs (`gh api repos/<owner>/<repo>/actions/jobs/<id>/logs`), then
  `python3 scripts/ci/e2e_shard.py from-logs <logs...> > scripts/ci/e2e-durations.json`. The parser strips the ANSI
  codes and timestamps itself. The two screenshot specs report no `✓` lines and keep the median weight.

## Docs screenshots drift always reports

`docs-screenshots.yml` triggers on every PR, and its own `changes` job (`Docs screenshot paths`) decides whether
the capture job («Capture and compare screenshots») runs: the web app source, the docs capture spec,
`apps/web/tests/e2e/support/**`, the Playwright configs and global setup, `packages/i18n/**`,
`docs/user/screenshots/**` and the workflow file itself. On any other PR the capture ends `skipped`. The old
workflow-level `on.paths` filter never started, so its check could not be made required (PPS-135). The weekly
schedule and manual runs always capture.

- **«Regenerate and diff» is a gate job**, and it is the one required on main since 2026-10-31 (the capture job
  is not). It passes when the capture passed, or was skipped because nothing relevant changed, and fails if the
  path filter itself failed: a job skipped because its `needs` failed also counts as passing, so requiring the
  capture job directly would let a broken filter through.

- The `screens` filter is the list to extend when a new file starts to affect the captures.
- The «Start Supabase» and «Start the extraction worker» steps did not fail in any of the 100 runs before
  2026-10-30 (the five non-successes were cancelled runs); the `supabase start failed after 5 attempts` text in
  every log is GitHub echoing the step's script, not an error.

## Sparse checkout (2026-10-31)

`docs/gtm/video/` holds ~825 MB of demo-video cuts (the whole HEAD tree is ~0.91 GB), and no CI or deploy job
reads it. By the week of 2026-10-31 a plain `actions/checkout` took 50–75 s in every job, up from ~3 s. Every
checkout except the secret scan now uses a non-cone sparse checkout (`/*`, `!/docs/gtm/video/`). `actions/checkout`
pairs that with a `blob:none` partial clone, so the video blobs are never downloaded: a local simulation of the
same fetch leaves an 85 MB working copy. The secret scan keeps its full-history checkout, since gitleaks scans the
commits a PR adds. If a job ever needs a video, drop the two sparse inputs from that job's checkout.

Measured (one run each, ±30% runner noise):

| Run | Checkout per job | Slowest E2E shard | Backend tests | Whole run |
|---|---|---|---|---|
| Five green runs before (`41145708177`…`41147908855`) | 49–75 s | 423–443 s | 293–324 s | 442–557 s |
| PR #376 (`41149690966`) | 2–6 s (secret scan, full history: 14 s) | 358 s | 246 s | 377 s |

## Docker layer cache (deploy workflows)

The `deploy-*.yml` workflows cache BuildKit layers in the Actions cache, each under its own `scope` (`api`,
`email-ingestion-worker`, `extraction-worker`, `feedback-worker` (added 2026-11-18), `optimiser`, `web`). Before 2026-10-24 they all used the default scope
with `mode=max`: each image's build overwrote the shared cache index, so builds rarely reused each other's blobs,
and the orphaned blobs filled 10.4 GB of the repository's 10 GB Actions cache. That evicted the pnpm and uv caches CI
relies on. The single-stage images now use `mode=min`, which stores the same layers for a single-stage build;
`web.Dockerfile` is two-stage, so it keeps `mode=max` to cache its build stage.

## Frontend deployment and CDN purge

The frontend image embeds its commit SHA in `/version.txt`, served by nginx with `no-store`.
After updating the Magic Containers image, `deploy-frontend.yml` polls that endpoint with a
cache-busting query every 15 seconds for approximately 10 minutes. Only once the deployed SHA
matches does it synchronously purge the site's wildcard URL from bunny CDN, then print the
landing image's `cdn-cache` header for information. A timeout fails the job and skips the purge.
This prevents old containers from refilling the cache during rollout: unhashed public assets
such as landing images were cached for 30 days and otherwise survived new deployments.

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
run (six shards plus about eight other jobs) stays under.

**2026-10-24: three shards → five.** With three shards the slowest shard ran 7–8.5 min, of which ~5.3 min was specs
and ~2 min fixed stack start-up. The planner predicts ~330 s of specs per shard at `--total 3` and ~199 s at
`--total 5` (imbalance 1.019, all 63 spec files assigned once), so the E2E critical path should drop by about two minutes. Measured
(a single run each, so indicative only given ±30% runner noise):

| Run | Shards | Slowest shard | Whole run |
|---|---|---|---|
| Last green 3-shard run before the change (`40103000301`, `3bb0ebb`) | 419–511 s | 511 s | 8.7 min |
| PR #248 (`40107239093`, head `085ee78`) | 264–340 s | 340 s | 5.9 min |
| `main` after merge (`40108797199`, `54de45f`; a11y always runs on `main`) | 267–342 s | 342 s | 7.0 min |

Shards run about 2.4 min over the planner's ~199 s prediction: the fixed ~2 min stack start-up is not in the
manifest, so per-shard predictions understate wall time by that much.

After the cache fix the Actions cache went from 10.78 GB (955 shared-scope BuildKit entries) to 1.54 GB once
each deploy had rebuilt its own scope, so the pnpm and uv caches are no longer evicted.

**2026-11-23: manifest refit, five shards → six (PPS-229).** Push-to-main runs crept back above 7 minutes. The
manifest had been written once, on 2026-10-18 (60 entries), and never refreshed. By 2026-11-22 the suite had 75
spec files and ~1,085 s of measured test time (was 950 s). The 15 newer specs were scheduled at the median guess
of 13.2 s, but `rfq-a11y` takes 47 s and `feedback-a11y` 33 s, and `requests-a11y` grew from 29 s to 75 s (8 → 20
tests; each still ~4 s). Supabase start (~75 s) and other setup (~60 s) stayed flat: all the growth was test time
and imbalance.

| Period | Shards | Slowest shard | Spread | a11y step | Functional step |
|---|---|---|---|---|---|
| 2026-10-24, just after #248 | 5 | 348–354 s | 57–74 s | 69–81 s | 91–101 s |
| 2026-11-13 to 11-22 | 5 | 413–466 s | 82–152 s | 99–127 s | 103–130 s |

Refitted on the shard logs of the last five green push-to-main runs (25 logs) and scored on those durations, the
old manifest's 5-shard plan has a slowest shard of 277 s of tests; the refit alone brings that to 223 s, and six
shards to 187 s (imbalance 1.015). An out-of-sample check (refit on three November runs, scored on a held-out
run) gave slowest shards of 294 s → 249 s (refit, five shards) → 206 s (six shards). With the ~2.4 min fixed
start-up, the slowest six-shard job should land at about 340–380 s, under the 420 s (7 min) bar. The manifest
now refreshes weekly (above).

## Verified after merge

- The main-run queueing fix is confirmed: two `main` runs started within 3 s of creation ran in parallel.
- The a11y gating is **not** yet confirmed on a backend-only PR: the PR that introduced it touched the workflows,
  which counts as a web change, so the gate has only ever seen `web=true`.

## Not done / ideas

- Refitting `e2e-durations.json` was first evaluated and deliberately not done (2026-10): it would have moved 37
  of 61 files for a gain smaller than runner noise. Shard times then drifted (2026-11), so it was refitted and is
  now refreshed weekly, gated on a 5 s gain so the plan does not reshuffle for noise.
- Impact-based E2E spec selection is the biggest remaining lever and the riskiest; keep the full suite on `main`.
- Serve a prebuilt web app instead of `ng serve` (still `ng serve` in ci.yml).
- Use `pytest-xdist` for backend tests (Backend tests are ~150–210 s, the next floor once E2E shrinks).
- Two Playwright workers for the a11y step only (needs a shared-owner-state audit first).
