# Matching & Normalisation — Implementation Audit vs Spec and Roadmap

> Read-only audit of chunk 4.4 (`specs/004-matching-normalisation/`) against its own spec,
> `docs/roadmap/procurepilot_roadmap.md` §13.2/§13.4, and the constitution. Two independent passes:
> (1) a fact-finding read of the actual implementation mapped against every FR/SC in the spec, and
> (2) an adversarial read-only critique from Codex, asked to defend or concede each contested
> finding rather than simply agree. Nothing in this document has been fixed yet — this is the
> findings pass, not the resolution pass. Run 2026-09-05.
>
> **Status update, 2026-09-10:** follow-up migrations and tests now enforce append-only
> permissions for `match_candidate`, `match_decision`, and `landed_cost`; the live pipeline now
> wires supplier-code aliases from line-level extracted fields; and human match resolution now
> persists retry mappings for `Idempotency-Key`. Historical findings below are kept for traceability
> and should be read together with this status note.

---

## 1. Headline result

Most of the spec is genuinely implemented, not stubbed: 14 of 20 functional requirements and 3 of
7 success criteria are solid, with real logic and file:line evidence, not comments describing
intent. The deterministic-key path, the keyboard-only resolution queue, tenant isolation, and RBAC
are all correctly built. The team has also already caught and fixed one instance of this exact
failure mode before (an earlier lexical-matching implementation that silently used Python
`difflib` instead of `pg_trgm`/`pgvector` — replaced).

But three things need attention before this chunk can be trusted at face value:

1. **`FR-017` (append-only match/cost history) is missing at the database level** — confirmed by
   both passes, rated high severity by both. The correct pattern already exists verbatim elsewhere
   in this codebase and was not applied here.
2. **The "calibrated confidence" score is not calibrated** — confirmed by both passes. Severity is
   *lower than it first appears*, because the scoring weights make fuzzy (non-deterministic)
   auto-accept mathematically unreachable at the current threshold (see §3.2) — but the label is
   still false, and deterministic matches are not infallible either.
3. **A semantically-meaningless stub embedding is live in production** with real scoring weight —
   confirmed by both passes, same threshold-math caveat on severity, but it still pollutes
   candidate generation and reviewer-facing "reason" text with a fake signal.

Separately: `specs/004-matching-normalisation/tasks.md` marks at least 8 test files "done" that do
not exist anywhere in the repo. Treat this task list as unverified until re-checked against the
filesystem — this is a process finding as much as a coverage gap.

---

## 2. FR / SC compliance table

Status legend: ✅ Implemented · 🟡 Partial (real but gapped) · 🔴 Missing · ⚪ Unverifiable (spec
itself says so)

| ID | Status | Evidence | Gap |
|---|---|---|---|
| FR-001 (only reviewed quotations) | ✅ | `service.py:74-75` raises `ConflictError` unless `quote["status"]=="reviewed"` | — |
| FR-002 (GTIN → supplier code → alias order) | 🟡 | `deterministic.py:25-40` checks in the correct order | Supplier-code branch is dead code: `service.py:141` always calls `find_deterministic_candidate(..., supplier_code_aliases=[])` — hardcoded empty list, no caller ever populates it. A unit test exercises the pure function directly and passes, creating false confidence this path is live. |
| FR-003 (similarity fallback) | ✅ | `service.py:158-163` | — |
| FR-004 (single calibrated confidence) | 🟡 | `scoring.py:33-44` weighted sum, matches the design doc's stated weights | `score_candidate` is `_clamp(raw)` — an identity mapping. No Platt scaling, isotonic regression, or any fit against labelled outcomes exists anywhere in the repo. See §3.2. |
| FR-005 (confidence + reason) | ✅ | `scoring.py:47-67` always includes a component breakdown | — |
| FR-006 (auto-accept) | ✅ | `service.py:228-233` | — |
| FR-007 (route on no-candidate/close-call) | ✅ | `service.py:219-239` | — |
| FR-008 (5 outcome types) | ✅ | `resolution_service.py`, `schemas.py` | — |
| FR-009 (create product from no-match) | ✅ | `resolution_service.py:44-49` reuses `CatalogueService.create_product` | — |
| FR-010 (alias learning) | ✅ | `alias_service.py:13-48`, `deterministic.py:38-40` | — |
| FR-011 (standalone queue) | ✅ | `service.py:82-119` | — |
| FR-012 (keyboard-only resolution) | ✅ | `match-resolution.component.ts:294-334` — real `@HostListener('window:keydown')`, digit-select/arrow-nav/confirm | — |
| FR-013 (landed cost formula) | ✅ | `landed_cost/rules.py:61-71`, `Decimal` throughout | — |
| FR-014 (store raw inputs + rule version) | ✅ | `rules.py:72-82`, `service.py:133-134` | — |
| FR-015 (reproducible replay) | 🟡 | `rules.py:98-110` pure-function replay proven in isolation (`test_landed_cost_replay.py`) | Never proven against a *stored* row through an actual rule-version change — see FR-016. |
| FR-016 (bitemporal valid-time + record-time) | 🟡 | Schema has both `valid_from`/`valid_to` and `recorded_at` | `valid_to` is written by zero code paths — permanently `NULL` on every row. The valid-time half is schema-present but functionally inert. |
| FR-017 (append-only, no destructive overwrite) | 🔴 | `supabase/migrations/20260819000027_matching_rls.sql` grants `select, insert, update, delete` on `match_candidate`, `match_task`, `match_decision`, **and `landed_cost`** to `authenticated`, with a broad `for all` policy. Compare `audit_event`'s pattern (`20260819000004_rls.sql:109-110,124`): explicit `revoke update, delete`, insert-only policy. | See §3.1 — highest-severity finding in this audit. |
| FR-018 (unit/pack normalisation) | ✅ | `service.py:80-85` | — |
| FR-019 (RBAC: owner/buyer mutate, others read) | ✅ | `test_matching_rbac.py` — a real parametrized guard×role matrix | — |
| FR-020 (cross-tenant not-found-not-forbidden) | ✅ | Standard tenant-isolation RLS pattern; API consistently raises `NotFoundError`, never `ForbiddenError` | — |
| SC-001 (zero manual effort, high-confidence lines) | ✅ | Follows from FR-001/006 | — |
| SC-002 (92% auto-accept precision) | ⚪ | `ml/evals/product_matching/run_eval.py` returns `gate_status: "not_validated_no_held_out_benchmark"` — honestly labelled, not silently claimed | No benchmark exists (`ml/benchmarks/product_matching/` has only a README). Spec itself pre-authorizes this gap. |
| SC-003 (≤8% review band) | ⚪ | Same harness | Same as SC-002 |
| SC-004 (few-keystroke resolution) | ✅ | Same evidence as FR-012 | — |
| SC-005 (wording never reviewed twice) | 🟡 | Alias-hit deterministic path implements the mechanism (`deterministic.py:38-40`) | The exact regression test this guarantee needs (`test_match_alias_learning.py`, tasks.md T029) does not exist. Plausible from reading the code, but unproven end-to-end. |
| SC-006 (landed cost explainable + replayable) | 🟡 | Pure-function replay proven | No test proves it against a real stored row after an actual rule-version change (see FR-016/017, §3.4). |
| SC-007 (true landed cost visible) | ✅ | `service.py:312-316`, `GET /quotation-lines/{id}/landed-cost` | — |

### Roadmap §13.2 pipeline stages

| Stage | Status | Evidence | Gap |
|---|---|---|---|
| 1. Deterministic keys | 🟡 | See FR-002 | Supplier-code key is dead code |
| 2. Lexical `pg_trgm` | ✅ | Real SQL function, `similarity()`, GIN trigram indexes | Own code comment documents a prior near-miss: an earlier implementation bypassed `pg_trgm`/`pgvector` entirely with Python `difflib` — caught and replaced |
| 3. Semantic `pgvector` | 🟡 | Mechanism (indexes, RPC, blend) is real and correctly wired | The embedding itself is `StubEmbeddingProvider` — a SHA-256 hash of the text, chunked into 256 floats. See §3.3. |
| 4. Feature scoring | ✅ | `scoring.py`, `search.py:53-61` | Price/pack plausibility default to neutral 0.5 (no historical price aggregation yet) — an acknowledged simplification, not a hidden gap |
| 5. Calibrated confidence | 🟡 | See FR-004, §3.2 | — |
| Feedback loop (alias write on decision) | ✅ | `resolution_service.py:63-70` | — |

---

## 3. Debated findings

Each finding below carries the original framing, Codex's independent verdict (it was asked to
verify the code itself, not take the framing on faith), and a combined assessment.

### 3.1 FR-017 — append-only history missing at the DB level

**Verdict: Agree, high severity — confirmed independently.**

`match_decision` and `landed_cost` (plus `match_candidate`, `match_task`) grant `update, delete` to
`authenticated` with a broad tenant `for all` policy. The identical guarantee is correctly enforced
elsewhere in this same repo for `audit_event` (explicit revoke + insert-only policy) — the pattern
existed and simply wasn't applied here. Constitution non-negotiable #7 states this exact
requirement, though written specifically about `audit_event`; FR-017 makes the identical demand of
match and cost history.

Mitigating factor found on verification: no FastAPI route exposes update/delete on `match_decision`
or `landed_cost` today, so there's no accidental product-surface risk right now. That does **not**
satisfy FR-017 — the guarantee is supposed to live in the database, not in "nobody built that
endpoint yet." Any future code that uses the `authenticated` role directly (a script, a different
service, a Supabase client call) can mutate or delete history with nothing to stop it.

**New finding surfaced by the debate**: both tables also cascade-delete from their parent quotation
line (`on delete cascade`). If a quotation line is ever hard-deleted after matching, its match and
cost history vanishes with it — plausibly fine for tenant teardown, not fine for ordinary business
retention.

**Recommendation**: revoke `update, delete` on `match_candidate`, `match_task`, `match_decision`,
and `landed_cost` from `authenticated`, matching the `audit_event` migration pattern exactly.
Separately confirm whether the `on delete cascade` from quotation lines is intended for these two
tables or should be `on delete restrict`/soft-delete instead.

### 3.2 "Calibrated confidence" is an uncalibrated heuristic

**Verdict: Partially agree, medium-high — real problem, narrower blast radius than first framed.**

Confirmed: `scoring.py` is a weighted sum with an identity clamp, no Platt scaling, isotonic
regression, or fit against labelled outcomes anywhere in the repo. FR-004 requires "a single
calibrated confidence score," and the roadmap names expected calibration error as a required
metric — neither is met by any measurable definition.

**Important nuance from the debate**: the deterministic-match signal contributes a fixed 0.30 of
the weighted sum. At the default `MATCHING_AUTO_ACCEPT_THRESHOLD = 0.92`, a purely fuzzy candidate
(no deterministic hit) caps out at a theoretical maximum of 0.70 — below the auto-accept
threshold. In practice, **auto-accept today is almost entirely deterministic-key acceptance**
(alias, GTIN, and supplier-code), not uncalibrated fuzzy-score acceptance. This
meaningfully narrows the immediate risk from "any wrong-but-confident-looking fuzzy match can
silently auto-accept" to "deterministic-key acceptance is the load-bearing gate, and deterministic
keys are not infallible either" (stale aliases, bad GTINs, duplicate catalogue products, ambiguous
supplier codes can still auto-accept and silently corrupt downstream landed cost).

**Recommendation**: label the number as a heuristic match score in UI/API until real calibration
exists (don't call it "confidence" or imply a probability). Consider making auto-accept
explicitly reason-gated (deterministic reasons only) rather than purely score-gated, so the
threshold isn't doing work it was never validated to do.

### 3.3 Stub embedding live in production with real scoring weight

**Verdict: Agree, medium-high — confirmed independently, with an added detail that matters.**

Confirmed: `StubEmbeddingProvider` hashes the lowercased text with SHA-256 into 256 floats,
L2-normalized — no semantic content. Two paraphrases of the same product hash to unrelated
vectors; cosine similarity between different strings is indistinguishable from noise.

**New detail surfaced by the debate**: the stub is used in **candidate generation**
(`match_candidate_search`), not only in final scoring. That means random vector alignment can
surface candidates that lexical search alone would never have proposed — polluting the reviewer's
candidate list, not just a score, even though (per §3.2) it's unlikely to independently push a
fuzzy candidate over the auto-accept line today.

A reviewer reading "semantic similarity" as a stated reason is being shown a fabricated signal.
There's no defensible case for a hash embedding as a "weak proxy" — exact/near-exact wording is
already better covered by alias hits and `pg_trgm`.

**Recommendation**: pick one — force the semantic component to neutral (0.5) while `stub-hash-v1`
is active, zero its scoring weight until a real model is wired in, or exclude the stub from
candidate generation entirely (keep it only as deterministic test fixture data).

### 3.4 Bitemporal schema and rule-version replay: future-proofing or premature abstraction?

**Verdict: Partially agree, medium — the schema is defensible, the claimed behavior is not real yet.**

Storing `raw_inputs`, `rule_version`, `valid_from`, `recorded_at`, and immutable computed amounts
is reasonable minimal future-proofing — retrofitting these columns after cost rows are already
referenced by savings/offers/requests would be materially more painful. Not gold-plating on the
schema side.

But `LandedCostService.active_rule_version` is hardcoded to `RULE_VERSION_V1` and
`compute_landed_cost()` rejects any other version — there is no registry, config, or migration
path for it to ever actually change, and no test exercises a version change. User Story 4's "change
the active rule version, reopen an old line, confirm it's unchanged" scenario is not an exercisable
behavior in this codebase today; the task list claims a test for exactly this and the named file
doesn't exist. Separately, `valid_from` is set to "now" at computation time (record-time-adjacent),
not necessarily when the supplier's price actually applies — and `valid_to` is written nowhere,
despite being queried by downstream offer/recommendation code per the debate.

**Recommendation**: either build a minimal rule-version registry (even a single config value with
a migration path) so US4 becomes real, or explicitly document that v1-only replay is the entire
scope of this chunk and US4 is deferred — don't leave it in an ambiguous "looks implemented, isn't
exercisable" state.

### 3.5 No benchmark dataset — Phase 1 matching engineering proceeded without it anyway

**Verdict: Agree, high — still a useful finding despite the gate having been knowingly overridden.**

The roadmap's Phase 0 gate explicitly required a 500+-pair labelled benchmark before beginning
Phase 1 matching engineering, calling the alternative "the most expensive mistake available." That
benchmark does not exist. This repo has a documented pattern of the project owner knowingly
overriding phase gates (per `CLAUDE.md`, the Phase 1→2 gate was also explicitly overridden) — so
this is not a surprise finding, but the debate confirmed it's not merely re-describing an accepted
business risk either.

The distinction that survived scrutiny: "we haven't hit the customer/revenue numbers for a Phase 2
gate" is a business-timing risk. "We have no labelled data to know whether the auto-accept
threshold, review margin, or embedding choice are anywhere near correct" is a **product data
integrity risk** — it can silently degrade landed cost, offer comparison, and savings evidence with
nothing to catch it, and (per §3.2's mitigating math) that risk currently concentrates on
deterministic-match correctness and review-queue quality rather than runaway fuzzy auto-accept.

**Recommendation**: this doesn't block current work, but it should stay a visibly tracked
prerequisite before raising the auto-accept threshold, expanding automatic acceptance beyond
deterministic evidence, or claiming that SC-002/SC-003 are met.

### 3.6 Eval harness exists but isn't wired into CI

**Verdict: Agree, medium.**

`ml/evals/product_matching/run_eval.py` exists and is honest about the missing benchmark, but
nothing in `.github/workflows/` runs it. The roadmap requires any model/prompt/threshold change to
run the eval suite with a precision regression blocking merge — currently nothing enforces that.

**Recommendation**: add a CI step now that runs the harness and accepts the current
`not_validated_no_held_out_benchmark` status as passing. The moment a real benchmark lands, the
same job flips to enforcing precision/review-band/ECE thresholds — avoids the harness staying
ornamental because "wire it into CI" became a second thing to remember later.

---

## 4. Architectural critique (independent, not tied to a single FR)

From the adversarial pass, and confirmed as directionally sound in the debate:

- **The layered pipeline itself (deterministic → lexical → semantic → feature scoring → threshold
  routing → alias feedback) is the right family of architecture** for procurement matching. This
  is not a pure embedding-similarity problem — pack size, unit, brand, supplier wording, aliases,
  and price plausibility all carry real signal that a single embedding model wouldn't capture on
  its own. Keeping permanent human review (not a temporary crutch) is also correct per the
  constitution.
- **Candidate generation and decision scoring are not separated sharply enough.** The stub
  embedding pollutes retrieval (which candidates even get shown), not just final scoring. A
  cleaner separation: broad recall-oriented retrieval (deterministic + trigram + *real* embeddings
  once available) feeding a distinct, calibrated scoring/decision layer — so a bad or fake retrieval
  signal can't silently reshape what reviewers even see.
- **The auto-accept boundary should be reason-aware, not purely score-aware.** Deterministic
  matches (alias/GTIN/code) could reasonably have their own acceptance policy distinct from fuzzy
  candidates, which should require actual benchmark-proven calibration before any unsupervised
  acceptance — right now one threshold does both jobs, and only survives scrutiny today because of
  the incidental 0.30-weight ceiling described in §3.2, not because it was designed that way.
- **The biggest missing strategic piece is treating labelled feedback as a first-class dataset**,
  not just `ProductAlias`. Alias learning improves repeat-exact-wording cases but doesn't produce
  hard negatives, near-miss examples, supplier-specific ambiguity cases, or calibration data — the
  exact inputs the eval harness and any future calibration work will need. Nothing today
  deliberately collects that broader signal from every human resolution decision, only the
  narrow alias-reuse case.

---

## 5. Process finding: `tasks.md` overstates test coverage

At least 8 test files are marked `[x]` complete in `specs/004-matching-normalisation/tasks.md`
that do not exist anywhere in the repository:

- `test_matching_pipeline.py` (T016)
- `test_matching_routing.py` (T017) — this is the missing test for the single highest-stakes
  decision in the whole feature: the auto-accept/review-routing boundary itself has no integration
  test at all.
- `test_matching_isolation.py` (T018) — partially subsumed by `test_tenant_isolation.py`'s later
  extension, so less severe than the others.
- `test_match_task_queue.py` (T028)
- `test_match_alias_learning.py` (T029) — this is SC-005's "never reviewed twice" guarantee;
  currently unproven end-to-end.
- `test_match_alias_conflicts.py` (T030)
- `test_landed_cost_workflow.py` (T043)
- `test_landed_cost_audit.py` (T049/T050) — all of User Story 4.

This means the tasks document cannot be trusted as evidence of verification for this chunk without
independently checking the filesystem, which is exactly what produced this audit. One item in the
opposite direction: `test_matching_candidate_search.py` is a real, useful test covering the
`pg_trgm`/`pgvector` RPC directly, but isn't tracked in `tasks.md` at all — untracked coverage
rather than untracked debt, a minor process gap either way.

**Recommendation**: re-audit `tasks.md` against the filesystem for every chunk, not just this one,
before treating any task checklist as proof of completion going forward.

---

## 6. Priority order for follow-up work

1. **FR-017** — resolved for `match_candidate`, `match_decision`, and `landed_cost` by
   `20260905000004_matching_append_only.sql`, with authenticated update/delete regression coverage
   added on 2026-09-10. `match_task` remains mutable by design because queue status transitions from
   open/in-progress to resolved.
2. **Stub embedding** — zero its scoring weight and/or exclude it from candidate generation until a
   real embedding model is wired in. Second-highest severity, also a small fix.
3. **Label confidence honestly** in UI/API as a heuristic match score, not "calibrated confidence,"
   until real calibration exists.
4. **Re-verify `tasks.md`** against the filesystem for this chunk; write the missing
   `test_matching_routing.py` (auto-accept/review-routing boundary) and
   `test_match_alias_learning.py` (SC-005) first — these guard the two guarantees the product most
   depends on.
5. **Wire the eval harness into CI** as a smoke gate now (asserting the honest
   `not_validated_no_held_out_benchmark` status), so it's load-bearing the moment a benchmark
   exists.
6. **FR-002 supplier-code matching** — resolved on 2026-09-10 for the live API path: matching now
   reads line-level extracted supplier product codes and uses tenant/supplier-scoped aliases before
   falling back to similarity.
7. **Decide User Story 4's scope**: build a minimal rule-version registry, or explicitly narrow
   this chunk's claim to "v1-only replay," and stop presenting bitemporal `valid_to` as populated
   when it never is.
8. **Track the missing benchmark dataset** as a live prerequisite, not a closed decision — it
   currently blocks validating SC-002/SC-003 and the auto-accept threshold itself.
