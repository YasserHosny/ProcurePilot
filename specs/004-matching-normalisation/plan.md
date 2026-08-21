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
