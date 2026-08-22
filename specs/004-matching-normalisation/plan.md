# Implementation Plan: Matching and Normalisation

**Branch**: `004-matching-normalisation` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-matching-normalisation/spec.md`

## Summary

Once a quotation reaches its reviewed, trusted state (chunk 4.3), each of its line items is matched
to a catalogue product: deterministic keys first (GTIN, supplier code, a previously confirmed
alias), then lexical (`pg_trgm`) and semantic (`pgvector`) similarity, then feature scoring, landing
on a calibrated confidence that auto-accepts, auto-rejects, or routes to a human match-resolution
queue. A human decision — confirm, different pack/variant, compatible alternative, or no
match/create new product — writes or reuses a `ProductAlias` so the same wording is never reviewed
twice. Every matched line gets a landed cost: a pure, versioned, replayable function over its
price, tax, delivery fee and discount, stored bitemporally and append-only. This is the first real
exercise of Constitution Principle II.

## Technical Context

**Language/Version**: unchanged — Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged from chunks 4.1–4.3 for `apps/api`. **No new external
dependency and no new deployable** — see the Constitution Check discrepancy below; matching is
in-database computation (`pg_trgm`, `pgvector`, both already enabled since chunk 4.1) plus scoring
logic inside `apps/api`'s existing modular monolith. No new frontend dependency.

**Storage**: Supabase Postgres 17 (unchanged) for `match_candidate`, `match_decision`,
`landed_cost`. `pg_trgm` and `pgvector` extensions, enabled in chunk 4.1's foundation migration
specifically for this chunk, are queried for the first time. Reuses chunk 4.2's `product_alias`,
`workspace_product`, `pack_definition` and chunk 4.3's `quotation_line`, `field_extraction` without
redefining them.

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core (unchanged). New for
this chunk: matching precision/recall evaluation under `ml/evals/` against a held-out labelled
benchmark under `ml/benchmarks/` (per constitution Quality Gates: ≥92% precision at auto-accept,
≤8% review band) — same honest-gap treatment as chunk 4.3's extraction accuracy, since no real
labelled benchmark exists yet.

**Target Platform**: unchanged — Linux containers, evergreen browsers. No new container.

**Project Type**: Angular SPA + FastAPI modular monolith — **no new service this chunk**, correcting
a discrepancy between `engineering-spec.md` (which names a `services/matching-worker`) and the
constitution (which pre-authorises only the extraction worker and the optimiser). See Constitution
Check.

**Performance Goals**: matching precision at auto-accept ≥92%, review band ≤8% (both unvalidated
until a real benchmark exists — see spec.md Assumptions); landed-cost computation must be
bit-identical on replay at a pinned rule version (constitution Quality Gates).

**Constraints**: matching only ever consumes `quotation.status = 'reviewed'` rows (FR-001); every
match candidate carries a reason, not just a score (FR-005); a human decision always creates or
reuses a `product_alias`, never bypassing chunk 4.2's existing table (FR-010); landed cost is an
amount+currency pair, bitemporal, append-only (FR-013, FR-016, FR-017); match-resolution work is
keyboard-first (FR-012), same discipline as chunk 4.3's review screen.

**Scale/Scope**: pilot-sized — the same reviewed-quotation volume chunk 4.3 already handles; most
lines expected to resolve automatically once aliases accumulate. Two new `apps/api` modules
(`matching`, `landed_cost`, both already anticipated in `engineering-spec.md` §2.1's module table),
one new screen (match-resolution queue and its per-line detail), no new external service.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | **Yes** | Every `match_candidate` carries a confidence score and a reason (alias hit, code match, wording similarity, price plausibility) — never a bare number. A `match_decision` records whether it was automatic or human, and by whom if human. | ⏳ Design must keep candidate reasons as structured, queryable data, not a free-text blob |
| **II. Deterministic, Replayable Normalisation** | **Yes — the first real test of this principle** | Landed cost MUST be a pure function of stored raw inputs plus a rule-version identifier, recomputable to a bit-identical result, with price/cost data bitemporal (valid-time and record-time, both required) and outcome history append-only. | ⏳ Design must produce a real rule-version mechanism, not a comment promising one |
| **III. Human Authority Over Automation** | **Yes** | A match below the auto-accept threshold, or with closely competing candidates, MUST route to a human queue rather than guess. The queue is a first-class resource (like chunk 4.3's `review_task`), not a filtered view. | ⏳ Design must model match-resolution work as its own queue resource |
| **IV. Every Insight Ends in an Action** | Partially | The match-resolution queue is the action surface — every routed line leads to a decision, never a passive report. No dashboard ships in this chunk. | ✅ PASS |
| **V. Tenant Isolation by Construction** | **Yes** | `match_candidate`, `match_decision`, and `landed_cost` are all tenant-scoped and need `tenant_id` + RLS `ENABLED`/`FORCED`, following the uniform pattern from chunks 4.1–4.3. | ⏳ Standard pattern, no new isolation surface (no Storage-style second boundary this chunk) |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes — a real discrepancy, resolved here** | `engineering-spec.md` §2.3 names `services/matching-worker` as its own deployable. The constitution's exact text: "Only the extraction worker and the optimiser are pre-authorised for extraction when load justifies it." Matching is **not** named, and unlike extraction (slow, third-party API calls with their own uptime/latency profile), matching is in-database computation (`pg_trgm`/`pgvector` queries plus scoring) with no external network call and no equivalent isolation argument. Per the constitution's Governance section ("this constitution supersedes other development practices... where a document... conflicts with it, this document wins"), this plan does **not** introduce `services/matching-worker`. Matching and landed-cost logic live inside `apps/api` as the `matching` and `landed_cost` modules, both already anticipated in `engineering-spec.md` §2.1's own module table — the service-listing in §2.3 is treated as stale/aspirational, not binding. | ⏳ Must be stated explicitly, not silently followed or silently ignored |
| **VII. Money, Tax, Language from the Schema Up** | Yes | Landed cost is an amount+currency pair, matching chunks 4.2–4.3's `Money` convention exactly — no new money shape, no currency conversion. All match-resolution screen strings come from `packages/i18n`, both languages, RTL-tested. | ✅ PASS |

**Workflow gates**: specification precedes code ✅ (spec approved, all checklist items pass, zero
clarification markers); stage gates ✅ (this is Phase 1 chunk 4.4, G1 is the gate ahead); delegated
work reviewed ✅ (planned — every delegated diff reviewed against this plan and the constitution
before it lands, same discipline as chunks 4.2 and 4.3).

## Project Structure

### Documentation (this feature)

```text
specs/004-matching-normalisation/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── matching.openapi.yaml
├── checklists/
│   └── requirements.md  # passing
└── tasks.md              # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
apps/api/
├── src/procurepilot_api/modules/
│   ├── matching/           # candidate generation, scoring, resolution endpoints
│   └── landed_cost/         # rule-versioned cost computation, replay
├── migrations/ → supabase/migrations/  (versioned SQL, this chunk's tables + RLS)
└── tests/{unit,integration,contract}/

apps/web/
└── src/app/features/matching/
    ├── resolution-queue/   # cross-quotation match-resolution queue, filterable
    └── match-resolution/   # per-line candidate comparison, keyboard-first, reason display

packages/
└── i18n/                   # matching.* namespace, en + ar, kept at parity
```

**Structure Decision**: Same modular monolith, no new service — see Constitution Check above.
`matching` and `landed_cost` land inside `apps/api` per `engineering-spec.md` §2.1's own module
table; the `services/matching-worker` line in that document's §2.3 is not followed. `pg_trgm` and
`pgvector` queries run directly against Postgres from within the `matching` module, no separate
process.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Unlike chunk 4.3, this chunk introduces neither a new deployable nor a new
infrastructure dependency — the one architectural question it raised (a possible `matching-worker`
service, per `engineering-spec.md`) was resolved by *not* introducing it, per the Constitution Check
above, rather than by justifying it.

## Constitution Check — re-run against delivered code (T058)

Run at the close of chunk 4.4, against what was built, verified directly against a real local
Supabase Postgres (all migrations through `20260821000001` applied) — not accepted from either
delegate's self-report.

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Evidence Over Assertion** | ✅ PASS | Every `match_candidate` row carries a decimal-string `confidence` and a structured `reasons` jsonb — alias hit, GTIN match, supplier code match, lexical similarity, semantic similarity, and per-feature scores — never a bare number. Confirmed live against a real database: a candidate produced by the new `match_candidate_search` SQL function carries real `lexical_similarity`/`semantic_similarity` values, not placeholders. |
| **II. Deterministic, Replayable Normalisation** | ✅ PASS | `landed_cost` is computed by a pinned `rule_version` (`landed-cost-v1`) from stored `raw_inputs`; `vat_amount = unit_price_amount * quantity * vat_rate`, `total_amount` sums unit price, VAT, and delivery fee, less discount, plus zero `other_charges`. Bitemporal (`valid_from`/`valid_to`/`recorded_at`) and append-only — a recomputation under a future rule version inserts a new row rather than mutating history, confirmed by `test_landed_cost_replay.py`. |
| **III. Human Authority Over Automation** | ✅ PASS | `_route_or_accept` in `matching/service.py` only creates an automatic `match_decision` when confidence clears `MATCHING_AUTO_ACCEPT_THRESHOLD` (0.92) **and** the top two candidates aren't within `MATCHING_REVIEW_MARGIN` (0.05) of each other; anything else — including zero candidates — creates a `match_task` instead. All five human outcomes (`same_product`, `different_pack`, `different_variant`, `compatible_alternative`, `no_match_new_product`) are selectable from the match-resolution screen, keyboard-first per FR-012, with every selection (candidate, outcome, inline product-creation fields) verified — by direct code review, not the delegate's own claim — to be included in the resolution payload every time, the same bug class chunk 4.3 found and this chunk did not repeat. |
| **IV. Every Insight Ends in an Action** | ✅ PASS | The resolution queue (`/matching`) is the only surface for outstanding match work; every task links to its per-line resolution screen, which is the only place a decision is recorded. No passive dashboard. |
| **V. Tenant Isolation by Construction** | ✅ PASS | `match_candidate`, `match_task`, `match_decision`, and `landed_cost` all show RLS `ENABLED`/`FORCED` with `tenant_isolation` `USING`/`WITH CHECK` policies, queried directly. `test_tenant_isolation.py` exercises real cross-workspace reads and a real cross-workspace write denial on all four tables, plus the two-embedding split (`canonical_product.canonical_embedding` correctly readable as the shared-spine exception; `workspace_product.tenant_name_embedding` correctly invisible cross-tenant). 36/36 isolation tests pass against a real database. |
| **VI. Modular Monolith Until Scale Demands Otherwise** | ✅ PASS | No new deployable was introduced — `matching` and `landed_cost` are `apps/api` modules only, confirmed by diff (no `services/` additions, no `docker-compose.yml` changes). |
| **VII. Money, Tax, Language from the Schema Up** | ✅ PASS | Every `landed_cost` monetary field is an explicit amount+currency pair; a database CHECK constraint requires every currency column to equal `total_currency` (no silent conversion). `matching.*` and landed-cost display strings are in `packages/i18n` at exact parity — 733/733 keys in both `en.json` and `ar.json`, confirmed by an independent key-diff, not the delegate's claim. |

**Workflow gates**: delegated work reviewed ✅ — backend (Codex), frontend (Antigravity), and docs
(Codex) lanes were dispatched, and every diff was re-verified against a live local Postgres and the
real frontend toolchain (Karma, `ng lint`) rather than accepted from self-reports. This chunk's
delegation runs were also interrupted mid-flight by external process kills on all three lanes at
once (see the Operational note below) — real, load-bearing gaps surfaced by re-verification, not
by either delegate's own sandbox:

- **The centerpiece gap**: the backend lane's first pass scored "lexical" and "semantic" similarity
  entirely in Python — `difflib.SequenceMatcher` and a hand-rolled cosine calculation recomputed
  from scratch on every call — and never read or wrote `canonical_product.canonical_embedding` or
  `workspace_product.tenant_name_embedding`, the two columns migration `20260819000026` built
  specifically for this chunk. It also loaded the entire `workspace_product` table into application
  memory per match attempt. This is exactly what research.md R3/R4 said not to do, and the delegate
  itself flagged the gap honestly in its own report rather than claiming a false pass. Fixed with a
  new orchestrator-authored migration (`20260821000001_matching_candidate_search.sql`) defining a
  `security invoker` SQL function doing real `pg_trgm` `similarity()` and real `pgvector` `<=>`
  cosine-distance queries against the persisted embedding columns, callable via
  `client.rpc("match_candidate_search", …)` so RLS still applies with no new policy needed; a
  scoped delta had the backend lane wire it in and add embedding write-back to the catalogue
  service. Verified with three new tests I wrote directly against the real database, proving a
  supplier-wording typo is caught by trigram similarity, unrelated text is excluded, and a missing
  embedding scores the neutral 0.5 (not 0, not a false match) per research.md R5.
- **A false "clean lint" claim**: the frontend lane's self-report claimed `ng lint` was clean; a
  real run found two real errors (`JsonPipe` and `RoleDirective` imported but never used in
  `match-resolution.component.ts`). Fixed directly — both were genuinely dead imports, the
  read-only/role gating that screen needs is enforced in component logic (`isWriter()`), not the
  template directive.
- **Operational note, not a code defect**: all three delegate dispatches (backend, frontend, docs)
  were killed by an external `SIGTERM` mid-run at least once; the frontend lane specifically failed
  twice with "timeout waiting for response" before the actual cause was found — `apps/web/.angular`
  had grown to 794MB, the same class of workspace-scan timeout chunk 4.2 already hit once. Clearing
  the gitignored cache before the third dispatch resolved it. Recorded to memory so a future session
  checks cache size before assuming the delegation tool itself is broken.

### Quality gates

| Gate | Threshold | Status |
|---|---|---|
| Cross-tenant isolation | Proven on every change | ✅ 36/36 against a real database, including the two-embedding shared/tenant-scoped split |
| Candidate evidence (Principle I) | Confidence + structured reasons, not a bare score | ✅ Verified live: `match_candidate_search` returns real `lexical_similarity`/`semantic_similarity`, combined with deterministic and feature scores per R5's exact weights |
| Human routing (Principle III) | Low-confidence or close calls never auto-decided | ✅ `_route_or_accept` threshold + close-call margin logic verified by direct code review and `test_matching_rbac.py`/unit tests |
| Landed-cost replay (Principle II) | Bit-identical recomputation at a pinned rule version | ✅ `test_landed_cost_replay.py` passes against a real database; a new rule version inserts rather than mutates |
| Backend test suite | All passing | ✅ 320 passed, 1 skipped (unrelated, pre-existing), ruff clean, against a real local Postgres |
| Frontend test suite | All passing | ✅ 72 passed, `ng lint` clean (after the fix above), i18n 733/733 exact parity — all confirmed by an independent re-run, not the delegate's report |
| Keyboard-only resolution (FR-012) | Candidate select + confirm without a mouse | ✅ Verified by direct code review of the keyboard handler (digits 1–9 select by rank, arrows navigate, `O` cycles outcome, `Enter`/`Ctrl+Enter` confirms) and the dedicated Playwright spec; **not** re-driven through a live browser this session (see honest gaps) |

### The honest gaps

- **No live browser walkthrough this chunk.** Every prior chunk's live walkthrough caught a real bug
  static review and automated tests missed (chunk 4.2's `[object Object]` rendering, chunk 4.3's
  dropped-supplier-selection bug). This chunk relied instead on real-database-backed automated tests
  (backend) and a real, unmocked Karma/`ng lint` run (frontend) plus direct reading of the exact
  payload-construction and keyboard-handling code, under this session's explicit instruction to
  economise on Claude usage. This is a real, disclosed gap, not a silent skip — a future session
  should drive the actual `/matching` and `/matching/:id` screens against a live stack before fully
  trusting the UI layer.
- **`ml/evals/product_matching/run_eval.py` cannot honestly report the ≥92% precision / ≤8% review
  band gates**, for the same reason chunk 4.3's extraction accuracy couldn't: no real held-out
  labelled benchmark with hard negatives exists yet. The harness itself runs and is labelled
  accordingly — mechanical correctness, not a real accuracy claim.
- **The DB-side search is an exact scan, not ANN-indexed** — per research.md R4, acceptable at pilot
  catalogue size; an HNSW index is additive future work once volume demands it, not a correctness
  gap today.
