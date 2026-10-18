# Demo finding 27: bulk confirmation latency

Scope: preserve spec 004 matching resolution and the frozen-plan bulk confirmation contract.
The approved finding requests a backend performance repair; no schema change is required.

Plan and checks:

- [x] Measure one resolution and an eleven-line bulk request through hosted PostgREST.
- [x] Retain the resolution pipeline and bound concurrent work; use authenticated clients.
- [x] Serialize equal alias text within a batch to preserve alias reuse and conflict order.
- [x] Defer guardrail jobs until workers complete and enqueue once per distinct quotation.
- [x] Batch and reuse input reads; leave decisions, aliases and idempotency records live.
- [x] Verify aliases, human decisions, closed tasks, audit, landed cost, replay and conflicts.
- [x] Run the final matching regression suite, lint, repeat benchmark and sabotage check.

Constitution: provenance and human decisions remain unchanged. All application reads/writes
continue through caller-authenticated clients and existing RLS. Audit remains append-only.
No tenancy, JWT, or migration changes. Tests operate only on newly created test workspaces.

Complexity tradeoff: bounded threads overlap hosted network latency while retaining one shared
resolution implementation. Equal aliases run sequentially in plan order because alias learning
is a read followed by an insert. Context propagation preserves request trace IDs. Guardrails run
after all workers, including after a partial failure, so they see completed decisions.

Bulk selection retains its already-read line and product inputs, then batch-loads their canonical
products and quotations. A small worker-local read adapter reuses these rows across the existing
resolution and landed-cost helpers. Explicit projections exclude embeddings. The adapter only
caches unique-ID reads of these four input tables; decisions, aliases, tasks, landed costs and
idempotency records always remain live. Cache lifetime is one bulk call, with one authenticated
client per group. No data or HTTP/auth state is shared across requests or tenants.

Measured on hosted Supabase with real test-user access tokens, all resolution side effects
active, and guardrail enqueue mocked. Fixture setup/teardown are outside the timers.

| Operation | Before | Final implementation | REST round trips before / after |
| --- | ---: | ---: | ---: |
| One resolution | 3.050 s | 3.134 s | 24 / 24 |
| Eleven-line bulk | 34.580 s | 3.322 s | 270 / 162 |

The bulk fixture spans two quotations: enqueue calls decrease from eleven to two. The initial
concurrency-only implementation measured 4.125 s but had a 25.336 s repeat; another diagnostic
run measured 4.831 s. That variability motivated reducing database work as well as overlapping
RTT. The final implementation reduces round trips by 40%, with the first final hosted run
passing both the real REST benchmark and the alias/trace test (2 passed in 37.01 s). The single
endpoint retains its original pipeline and round-trip count.

Twelve workers permit eleven distinct aliases in one wave; six workers would require two
~3 s waves before the read optimization. Equal alias text deliberately remains sequential.
The existing 100-line cap bounds pending work. Single-line latency varies with hosted RTT;
the test also bounds bulk request count so a fast network cannot hide a query regression.

No DDL or migrations were executed or added. No RLS, tenant resolution, or JWT code was changed.

Final filename-selected matching/resolution/bulk suite: 174 passed, 1 skipped (the opt-in
REST benchmark), 1 warning in 350.72 s. This includes the new cache-scope/live-read unit test.
The REST benchmark is executed separately with hosted credentials. Ruff check and format check
pass on all four changed Python files.

Sabotage: restored `confirm_exact_matches` from main in an isolated Python test process,
retaining the test SQL adapter. The new equal-alias/one-quotation regression failed:
`Expected 'mock' to be called once. Called 3 times.` Final sabotage result: 1 failed in 8.87 s. The working
source was never reverted. This proves the regression detects the old bulk enqueue behavior.

Repeat hosted verification: single resolution 3.134 s / 24 REST round trips; eleven-line bulk
3.322 s / 162 REST round trips, two guardrail enqueues for two quotations. All HTTP requests
were under 0.305 s in that run. The benchmark checks derived uuid5 keys, ordinary human
provenance, aliases, closed tasks, audit events, landed costs, same-key replay, a request-count
ceiling and the five-second latency ceiling. Together with the equal-alias/trace test:
2 passed, 1 warning in 37.37 s. Final normal bulk runs were 3.293 s and 3.322 s (~10.4x faster).

Local commit is blocked by the workspace filesystem: `git add` cannot create `.git/index.lock`
(`Read-only file system`). The branch is `fix/bulk-confirm-speed`, originally clean at main.
No push or PR was attempted. Changes remain in the working tree; the new cache unit-test file
is untracked because staging is blocked. A complete patch is saved at
`/tmp/f27-bulk-confirm-speed.patch`, including that untracked file.
