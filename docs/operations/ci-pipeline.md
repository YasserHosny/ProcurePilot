# CI pipeline notes

Last updated: 2026-10-16. Source of truth is `.github/workflows/ci.yml`; this page records *why* it is shaped the way it is.

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
- `supabase start` is retried up to three times: parallel shards pull images at the same moment and the registry
  occasionally answers `toomanyrequests`. If a run ever fails on an image pull despite the retry, cache or mirror the
  images rather than raising the retry count.

## Measured effect (2026-10-16)

| | Before | After |
|---|---|---|
| End-to-end wall time | 22–26 min | ~10 min |
| Docs-only PR | ~26 min | seconds (secret scan only) |

Sharding costs roughly three times the ~170 s stack start-up in runner minutes, in exchange for about half the wait.
