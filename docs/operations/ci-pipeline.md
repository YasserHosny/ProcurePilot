# CI pipeline notes

Last updated: 2026-10-18. Source of truth is `.github/workflows/ci.yml`; this page records *why* it is shaped the way it is.

## Docs-only pull requests skip the heavy jobs

A `changes` job (`dorny/paths-filter`, `predicate-quantifier: every`) decides whether a PR touches anything
outside `docs/`, `specs/`, `.specify/` and `*.md`. If not, every job except the secret scan is skipped.

- It is an `if:` on each job, **not** a workflow-level `on.paths` filter. A workflow that never triggers leaves
  required checks pending forever; a job skipped by `if:` counts as passing.
- Pushes to `main` always run everything.
- Editing `ci.yml` itself counts as a code change.

## End-to-end is sharded three ways

Playwright runs with `workers: 1`, so the suite is serial inside a shard. The `e2e-shard` matrix splits the spec
*files* across three runners (`--shard=N/3`), each with its own isolated Supabase, Redis, API, extraction worker and
web app. The aggregate job `e2e`, named exactly `End-to-end`, passes when the matrix succeeded or was skipped, so the
check name other tooling may rely on is unchanged.

- The accessibility step runs the `*a11y*` specs; the following step runs the complement (files whose name lacks
  `a11y`). They used to overlap, which ran ~117 tests twice.
- Supabase CLI is pinned to `2.121.0` so CI does not hit the rate-limited GitHub API while resolving `latest`; bump
  it deliberately. `supabase start -x studio,vector,logflare,edge-runtime,postgres-meta,mailpit,realtime` skips the
  seven unused services, reducing image pulls from 12 to five (`postgres`, `gotrue`, `postgrest`, `kong`, and
  `storage-api`). Shards stagger startup by 25 seconds each, then retry up to five times with a 30-second-per-attempt
  backoff. `docs-screenshots.yml` uses the same CLI pin, exclusions and retry, without the shard stagger. To bring a
  service back, remove it from the `-x` list in **both** workflows.

## Pushes to main finish

`cancel-in-progress` is `github.event_name == 'pull_request'`, so superseded PR runs are cancelled while pushes to
`main` complete. A concurrency group keeps only one pending run, though, so several merges landing during one run
still collapse to the last pending run.

## Measured effect (2026-10-18)

| Change | Measurement |
|---|---|
| End-to-end wall time (sharding) | 22–26 min → ~9–10 min |
| Docs-only PR | ~26 min → seconds (secret scan only) |
| Supabase startup hardening | Reliability, not speed: shard times remain ~485–550 s. Registry retry/rate-limit log lines per shard went from 31–48 to 0–13 over three trial runs, with one 30-line outlier in the first run. Recent red CI runs had included whole-run `supabase start` failures and a `setup-cli@latest` rate-limit failure. |

Sharding costs roughly three times the ~170 s stack start-up in runner minutes, in exchange for about half the wait.

## Not done / ideas

- Impact-based E2E spec selection is the biggest remaining lever and the riskiest; keep the full suite on `main`.
- Serve a prebuilt web app instead of using `ng serve`.
- Add a fourth shard.
- Use `pytest-xdist` for backend tests.
