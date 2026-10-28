# Implementation Plan: Replies to an RFQ Match Against the RFQ's Own Lines

**Branch**: `023-rfq-aware-matching` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)
**Tracking**: Jira PPS-95 (P-65) · `docs/gtm/gtm-execution-plan.md`

## Summary

Matching gets an RFQ stage ahead of the catalogue search. When a quotation answers an RFQ, each
quoted line is compared with that RFQ's 1–50 lines using a transparent rule, `rfq-fit-v1`:
wording, pack, and position as a tie-break only (research R3). Exactly one fit is accepted
automatically through the same path deterministic hits already use (owner decision Q1). Anything
else goes to a human, with the fitting RFQ lines offered first.

Because automatic RFQ acceptance can now be wrong in ways a human must undo, match decisions
become **correctable**. This is done with an insert-only supersession chain and a
`current_match_decision` view (R5), so the append-only rule (Constitution II) holds.

Three smaller parts ride along:

- A learned wording sweeps open lines with the same text (R6).
- Match explanations show only measured signals (R4).
- The Azure extractor learns the pack column (R7).

## Technical Context

**Language/Version**: Python 3.12 (`apps/api`, `services/extraction-worker`, `services/optimiser`), TypeScript 6 / Angular 22 (`apps/web`)
**Primary Dependencies**: existing only (FastAPI, psycopg, supabase-py, `pg_trgm`); no new packages
**Storage**: Supabase Postgres 17. Changes:
- one migration: `match_decision.supersedes_decision_id`, `match_decision.learned_from_decision_id`, the chain constraints, the trigger and the `current_match_decision` view;
- settings `MATCHING_RFQ_FIT_FLOOR` and `MATCHING_RFQ_FIT_MARGIN`.

**Testing**:
- pytest: unit tests for the fit rule and pack parser, integration tests on a throwaway DB for the migration, the chain constraints and RLS on the view;
- Karma for the explanation and correction UI;
- Playwright for the RFQ round end to end (2 quotes, 0 manual matches);
- `ml/evals/product_matching` before and after (SC-006);
- `pnpm test:isolation`.

**Target Platform**: hosted web + API + extraction worker (bunny Magic Containers)
**Project Type**: web service + SPA + worker
**Performance Goals**: the RFQ stage adds one query per quotation and ≤ 50 × lines in-memory comparisons. Matching a 50-line reply stays within today's time ±10 %.
**Constraints**:
- deterministic and replayable (rule version in reasons);
- no `UPDATE`/`DELETE` on `match_decision`;
- every money and quantity value is in the purchasing pack (ADR-020).

**Scale/Scope**:
- 1 migration;
- about 19 `match_decision` readers to classify (current or history), in roughly 12 modules;
- 2 web screens (Match Resolution detail, quotation matches list);
- 1 extractor function.

## Constitution Check

- **I Evidence over assertion**: PASS. Each RFQ decision stores its inputs: RFQ line, wording score,
  pack check and rule version. Unmeasured signals are no longer shown as numbers (FR-009).
- **II Deterministic, replayable**: PASS, by design. Fit is a pure function of stored inputs and a
  versioned rule. Corrections are insert-only (R5). Landed cost for the new decision is computed by
  the existing versioned function, and old rows are kept.
- **III Human authority**: PASS with the owner decision recorded. Q1 (2026-10-28) accepts an
  unambiguous RFQ fit automatically. This is a *matching* decision, not a purchase: a human still
  reviews the extraction before matching runs, and authorises every request and order. "Sub-threshold
  confidence MUST force review" is honoured: ambiguous, pack-conflict and low-wording lines go to a
  human (FR-002, FR-007).
- **V Tenant isolation**: PASS, but this is in-house work. The new view is `security_invoker`, and the
  new FKs are composite `(tenant_id, id)`. Per project memory, the tenancy parts (the view, the trigger
  and the RLS checks) are not delegated. Run `pnpm test:isolation`.
- **VI Modular monolith**: PASS. The RFQ read goes through a small `rfq` read interface
  (`rfq_lines_for_quotation`) rather than matching querying RFQ tables ad hoc.
- **VII Money/language**: PASS. Pack comparison happens in base units with numeric arithmetic, and new
  copy is in en + ar.
- **Gate result**: no unjustified violation. The one notable design item is under Complexity
  Tracking.

## Project Structure

```text
specs/023-rfq-aware-matching/{spec.md, plan.md, research.md, data-model.md, quickstart.md,
                              contracts/matching-rfq.openapi.yaml, checklists/}

supabase/migrations/2026110xxxxxxx_match_decision_supersession.sql   # R5 chain + view + learned_from

apps/api/src/procurepilot_api/
  modules/rfq/read_api.py              # rfq_lines_for_quotation(quotation_id) — the module interface
  modules/matching/rfq_fit.py          # pure fit rule (R3) + reason payload
  modules/matching/service.py          # RFQ stage in the per-line loop; sweep after alias learning
  modules/matching/resolution_service.py   # correction endpoint logic; alias sweep call (R6)
  modules/matching/scoring.py          # `measured` map in reason_payload (R4)
  modules/matching/router.py           # POST /quotation-lines/{id}/match/corrections
  modules/{landed_cost,offers,savings,requests,rfq,alerts,analyst}/…   # reader moves to current_match_decision
  config.py                            # MATCHING_RFQ_FIT_FLOOR / MATCHING_RFQ_FIT_MARGIN
services/optimiser/src/procurepilot_optimiser_worker/repository.py   # join current_match_decision
services/extraction-worker/src/procurepilot_extraction_worker/azure_di.py   # pack role + parse_pack_text
apps/web/src/app/features/matching/
  resolution-detail/…                  # RFQ-led explanation, measured signals only, Correct match
  quotation-matches/…                  # automatic matches list shows "From your RFQ line N" + Correct
packages/i18n/{en,ar}.json
```

**Structure decision**: existing modular monolith. No new deployable.

## Phasing (for /speckit.tasks)

1. **Foundations.** Migration R5 on a throwaway DB, then reader classification T010 and the move to
   the view (in-house, test:isolation). Settings.
2. **US1** RFQ stage. Calibration T002 (read-only hosted) → `rfq_fit.py` → service integration →
   the round-1 replay test.
3. **US1 correction**: endpoint, lock, landed cost and guardrail re-enqueue, then the web Correct
   action.
4. **US2** explanation (`measured` map plus web).
5. **US3** alias sweep.
6. **US4** extractor pack column plus the round-1 fixtures.
7. Live round-1 re-walk on hosted after deploy and `pnpm db:migrate` (memory: drive the real UI).

Delegation: the web and extractor pieces go to lanes (Agy for web). The migration, the view and
the reader moves stay in-house (tenancy).

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| Supersession chain + `current_match_decision` view, about 19 reader moves | Q1 makes automatic RFQ matches possible, and a wrong one must be undoable without an `UPDATE` (Constitution II) | `superseded_at` on the old row is a destructive update. Leaving correction out leaves no recovery from a bad automatic match. |
