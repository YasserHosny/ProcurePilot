# Tasks: Replies to an RFQ Match Against the RFQ's Own Lines (023)

**Input**: `specs/023-rfq-aware-matching/` — spec.md, plan.md, research.md (R1–R8), data-model.md,
contracts/matching-rfq.openapi.yaml, quickstart.md
**Tracking**: Jira PPS-95 (P-65)
**Tests**: included. The owner's working default is TDD: each test task goes red before its
implementation task.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md
- Paths are repo-relative. API is `apps/api/src/procurepilot_api/`; API tests are `apps/api/tests/`.

**Who does what** (plan.md and project memory):

- **In-house (orchestrator)**: the migration, the view, RLS and isolation checks, and the reader
  moves (T004–T010).
- **Lanes**: the web work (Agy) and the extraction-worker work.
- **Testing unmerged migrations**: only on the throwaway DB `pp-x-db` (:54399), never on hosted or a
  shared local DB.

---

## Phase 1: Setup

- [x] T001 Add settings `matching_rfq_fit_floor` (default 0.30, env `MATCHING_RFQ_FIT_FLOOR`) and `matching_rfq_fit_margin` (default 0.15, env `MATCHING_RFQ_FIT_MARGIN`), both `ge=0, le=1`, next to `matching_trigram_threshold` in `apps/api/src/procurepilot_api/config.py`. Document both in the root `.env.example`, next to `MATCHING_TRIGRAM_THRESHOLD`.
- [x] T002 Calibrate the fit rule read-only on hosted «مطاعم رواق» (never «مطاعم سند»).
  - For RFQ `1b7cd76b` and its two replies (quotes `DH-26-1252`, `WF/2026/0781`), compute `pg_trgm.similarity(normalised original_text, product tenant_name)` for each of the 8 quoted lines against each of the 4 RFQ products.
  - Record the 8×4 matrix and the chosen floor and margin under research.md §R3 "Calibration" in `specs/023-rfq-aware-matching/research.md`.
  - If any right pair is below 0.30, or beats the runner-up by less than 0.15, adjust the defaults in T001 and record why.

---

## Phase 2: Foundational (blocks every story)

**Purpose**: correctable, append-only match decisions (research R5) and the RFQ read interface. US1
needs both: automatic RFQ matches must be correctable.

- [x] T003 Write a failing migration test in `apps/api/tests/integration/test_match_decision_supersession.py` (throwaway DB) covering:
  1. a second root decision for a line raises a unique violation;
  2. a correction pointing at the head is accepted, and `current_match_decision` returns only it;
  3. a correction pointing at a non-head, or at another line's or tenant's decision, raises `23514` from the trigger;
  4. `UPDATE`/`DELETE` on `match_decision` as `authenticated` is denied;
  5. a member JWT sees no other tenant's rows in `current_match_decision`.
- [x] T004 Create `supabase/migrations/20261029000000_match_decision_supersession.sql`:
  - **Columns**: add `supersedes_decision_id` and `learned_from_decision_id`, each with a composite FK `(tenant_id, …) → match_decision (tenant_id, id)`.
  - **Constraints**: drop `match_decision_one_per_line`. Add `match_decision_one_root_per_line unique nulls not distinct (tenant_id, quotation_line_id, supersedes_decision_id)` and `match_decision_superseded_once unique (supersedes_decision_id)`.
  - **Trigger**: `match_decision_supersession_same_line` (before insert): same tenant, same line, and the target is the current head.
  - **View**: `current_match_decision` with `security_invoker = true`, granted the same `select` as `match_decision`.
  - **Data**: no backfill is needed (all existing rows are roots).
  - **Done when**: T003 is green on `pp-x-db`.
- [x] T005 Add `current_match_decision` coverage to `apps/api/tests/integration/test_tenant_isolation.py` (cross-tenant read returns nothing), then run `pnpm test:isolation` against the throwaway DB.
- [x] T006 Classify every `match_decision` reference as **current** (means "the line's match") or **history** (audit, a past purchase's evidence). Run `grep -rn "match_decision" apps/api/src services/*/src` and record the table under research.md §R5 "Reader classification" in `specs/023-rfq-aware-matching/research.md`. Expected current: landed_cost, offers (service, supplier_iq, supplier_iq_repository), requests/valuation, rfq/service, rfq/guardrail_evaluation, alerts/conditions, analyst/service, workers/offer_refresh_scheduler, matching/service, and the optimiser repository. Expected history: savings evidence and baseline.
- [x] T007 Move the **current** readers from T006 in the API modules to `current_match_decision`, in SQL strings and PostgREST `.table(...)` calls. The files are those listed in T006 under `apps/api/src/procurepilot_api/modules/`. Keep `match_decision` for inserts and history reads. Then run the existing integration suites for offers, rfq, requests, savings, alerts and analyst on the throwaway DB, and check they stay green.
- [x] T008 [P] Move `read_current_offers` and the advanced offer query to `current_match_decision` in `services/optimiser/src/procurepilot_optimiser_worker/repository.py`. Update the fixtures in `services/optimiser/tests/test_repository.py`, and add a case where a superseded decision's landed cost is ignored.
- [x] T009 [P] Add `rfq_lines_for_quotation(conn, tenant_id, quotation_id) -> RfqContext | None` in a new `apps/api/src/procurepilot_api/modules/rfq/read_api.py`.
  - It reads `rfq_id` and `(rfq_line_id, workspace_product_id, quantity, position, product tenant_name, aliases, pack base_quantity, base_unit)`.
  - It uses one query through `rfq_response → rfq_recipient → rfq_line`, joining `workspace_product`, `pack_definition` and `product_alias`.
  - It returns `None` for a quotation that answers no RFQ.
  - Unit test: `apps/api/tests/integration/test_rfq_read_api.py`.
- [x] T010 Add `supersedes_decision_id: UUID | None` and `learned_from_decision_id: UUID | None` to `MatchDecision` in `apps/api/src/procurepilot_api/modules/matching/schemas.py`, and set them in `_decision()` in `apps/api/src/procurepilot_api/modules/matching/service.py`.

**Checkpoint**: the schema is merged-ready, every reader follows the current decision, and the
existing suites are green.

---

## Phase 3: User Story 1 — Lines of an RFQ reply arrive matched to the RFQ's products (P1) 🎯 MVP

**Goal**: an unambiguous RFQ fit is accepted automatically. Everything else goes to a human with the
RFQ lines offered first, and a buyer can correct any match until it is on a request.

**Independent test**: quickstart §3, the round-1 replay. 8/8 lines are matched automatically, and 0
tasks are left open.

### Tests (red first)

- [x] T011 [P] [US1] Write unit tests for the fit rule in `apps/api/tests/unit/test_rfq_fit.py`:
  - round-1 texts against the 4 products: each fits exactly its own;
  - «زيت» against two oil products: no fit, both returned as fitting;
  - a 5 kg bag against 10 kg: `pack_check="conflict"`, no fit;
  - a product not in the RFQ: no fit;
  - no pack on the quoted line: fit only with the doubled margin;
  - a position bonus cannot lift a below-floor line;
  - the output reasons carry `rule_version="rfq-fit-v1"`.
- [x] T012 [P] [US1] Write a round-1 replay integration test in `apps/api/tests/integration/test_rfq_aware_matching.py` (throwaway DB). It builds an RFQ with 4 products and 2 replies using the round-1 texts and packs, authorizes both, and asserts:
  - 8 automatic decisions with `reasons.rfq`;
  - 0 open `match_task`;
  - one guardrail evaluation enqueued per quotation;
  - `GET /rfq/{id}/responses` lists the lines in RFQ order;
  - a quotation with no RFQ matches exactly as before.
- [x] T013 [P] [US1] Write correction integration tests in `apps/api/tests/integration/test_match_correction.py`:
  - correcting the head creates a human decision with `supersedes_decision_id`, the view returns it, and a landed cost exists for it;
  - a stale `expected_current_decision_id` gives 409 `decision_changed`;
  - a line priced by a submitted request gives 409 `line_on_purchase_request` with `purchase_request_id`;
  - after the request is withdrawn, correction is allowed;
  - the audit event `matching.decision_corrected` is written;
  - the same Idempotency-Key replays the same result.

### Implementation

- [x] T014 [P] [US1] Implement the pure fit rule in a new `apps/api/src/procurepilot_api/modules/matching/rfq_fit.py`, per research R3.
  - Normalisation: NFKC, Arabic letter folding and digit folding, reusing the folding table from `services/extraction-worker/.../azure_di._normalise_header`, copied rather than imported across services.
  - Wording score: the max of trigram similarity against the product name and its aliases, and token containment.
  - Pack check: compare in base units within 0.5 %.
  - Floor and margin: from settings.
  - It returns `RfqFit(matched_rfq_line | None, fitting_lines, reasons)`.
  - T011 green.
- [x] T015 [US1] Integrate the RFQ stage into the per-line loop of `MatchingService` in `apps/api/src/procurepilot_api/modules/matching/service.py` (~500–557), before `find_deterministic_candidate`.
  - Load `rfq_lines_for_quotation` once per quotation.
  - On a single fit: persist one candidate (`scoring_version="rfq-fit-v1"`) and call `_create_automatic_decision`, with audit target `reason="rfq_fit"`, `rfq_id`, `rfq_line_id` and `rule_version`.
  - On fitting lines without a single fit: persist them as the top-ranked candidates, then the similarity candidates, and route to a task.
  - T012 green.
- [x] T016 [US1] Make sure automatic RFQ decisions never learn an alias (FR-004). Assert this in `apps/api/tests/integration/test_rfq_aware_matching.py`, and guard any alias write on `reasons.rfq` in `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`.
- [x] T017 [US1] Implement correction in `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`: — The lines_matched_through_old_wording list fills once US3 (T025) writes learned_from_decision_id.
  - add `MatchResolutionService.correct(line_id, payload, idempotency_key)`;
  - lock the line, compare `expected_current_decision_id` with the head, and check the purchase-request lock through `purchase_request_line.estimated_unit_price_source_landed_cost_id` (statuses not in withdrawn or rejected);
  - insert the superseding human decision, compute landed cost, enqueue the guardrail evaluation, write the audit, and optionally learn the alias;
  - return the lines with `learned_from_decision_id` = the superseded decision (FR-012).
- [x] T018 [US1] Add the route `POST /quotation-lines/{line_id}/match/corrections` with owner/buyer role, a required Idempotency-Key, and the request/response models from `contracts/matching-rfq.openapi.yaml`. Changes go in `apps/api/src/procurepilot_api/modules/matching/router.py` and `schemas.py`. T013 green.
- [x] T019 [P] [US1] Web, delegated to Agy: in `apps/web/src/app/features/matching/match-resolution/match-resolution.component.{ts,html,scss,spec.ts}` and `matching-api.ts`, add:
  - "From your RFQ line N" on automatic matches;
  - "Not in your RFQ" and "Pack differs from your RFQ (X asked, Y quoted)" labels;
  - a "Correct match" action that calls the corrections endpoint, maps the 409 reasons to copy ("On request PR-…: withdraw it first"), and lists the lines matched through the old wording.

  Add i18n keys in `packages/i18n/{en,ar}.json`. Karma red → green.
- [x] T020 [P] [US1] Web, delegated to Agy: in `apps/web/src/app/features/matching/resolution-queue/resolution-queue.component.{ts,html,spec.ts}`, the auto-accepted filter shows the RFQ label and a Correct link per row.

**Checkpoint**: US1 works end to end on the throwaway DB, and the round-1 replay passes.

---

## Phase 4: User Story 2 — The match explanation shows what was measured (P2)

**Independent test**: an RFQ-proposed candidate and a similarity-only candidate. Neither shows a 50 %
placeholder, and the RFQ one leads with the RFQ line.

- [x] T021 [P] [US2] Write unit tests in `apps/api/tests/unit/test_matching_scoring.py`: `reason_payload` includes a `measured` map with only non-None inputs, and the deterministic and similarity builders pass through the inputs they actually measured.
- [x] T022 [US2] Add `measured` to `reason_payload` in `apps/api/src/procurepilot_api/modules/matching/scoring.py`, and pass the measured inputs from `apps/api/src/procurepilot_api/modules/matching/search.py` and `deterministic.py`. Leave stored rows untouched. T021 green.
- [x] T023 [P] [US2] Web, delegated to Agy: `apps/web/src/app/features/matching/match-resolution/match-resolution-candidates.component.{ts,html,scss}` and its spec:
  - render only the `measured` signals; legacy rows without `measured` follow the rule in research R4;
  - "Semantic: Not available" and 50 % feature bars are gone;
  - RFQ candidates lead with "Your RFQ line N · product · pack × quantity" and are not styled red.

  Karma red → green, with en and ar copy.

---

## Phase 5: User Story 3 — One confirmation of a wording clears every open line that uses it (P2)

**Independent test**: quickstart §5.

- [x] T024 [P] [US3] Write integration tests in `apps/api/tests/integration/test_alias_sweep.py`:
  - two quotes with an open «دقيق» line: resolving one with learn_alias decides the other automatically, with `learned_from_decision_id`, and the task is resolved;
  - «دقيق فاخر» stays open;
  - lines from another tenant are untouched;
  - the sweep caps at 200 lines;
  - an RFQ automatic decision triggers no sweep.
- [x] T025 [US3] Implement `sweep_open_lines_for_alias(client, member, alias_row, learned_from_decision_id)` in `apps/api/src/procurepilot_api/modules/matching/service.py`. Use the normalisation in `exact.normalise_name` and write the audit `matching.alias_sweep_matched`. Call it after a successful alias learn in `resolution_service._complete_resolution_side_effects` and in the correction path (T017). A sweep failure is logged and does not fail the resolution. T024 green.
- [x] T026 [P] [US3] Web, delegated to Agy: after a resolution or correction that swept lines, the snackbar says "Also matched N more lines with the same wording". This goes in `apps/web/src/app/features/matching/match-resolution/match-resolution.component.ts`, with i18n en and ar.

---

## Phase 6: User Story 4 — The pack the supplier printed is kept (P3)

**Independent test**: quickstart §6.

- [ ] T027 [P] [US4] Generate the round-1 quote PDFs `DH-26-1252` and `WF/2026/0781` with `docs/gtm/gcc/setup/quotes/gen_quotes.py`, and add them plus their Azure DI JSON responses as fixtures under `services/extraction-worker/tests/fixtures/round1/` — Open: the round-1 fixtures in tests/fixtures/azure_layout/ are hand-built from the template (no Azure DI keys locally); the recorded Azure responses are still owed.
- [x] T028 [P] [US4] Write failing tests in `services/extraction-worker/tests/test_pack_column.py`:
  - `parse_pack_text` gives «كيس 10 كجم» → (1, 10, kg), «تنكة 18 لتر» → (1, 18, L), «كرتون 12 × 1 لتر» → (12, 1, L), "Carton 24x500g" → (24, 0.5, kg), and handles Arabic-Indic digits;
  - unparseable text yields a `pack_text` field with confidence 0.4;
  - the round-1 fixtures give pack fields on all 4 lines of each quote.
- [x] T029 [US4] In `services/extraction-worker/src/procurepilot_extraction_worker/azure_di.py`:
  - add a `pack` role to `_header_role`: «العبوة», «التعبئة», «الحجم», "pack", "packing", "pack size", "packaging";
  - add `parse_pack_text()`;
  - emit `pack_count`/`unit_size`/`pack_unit` fields, or a low-confidence `pack_text` field.

  T028 green. Run the whole worker suite (`services/extraction-worker/tests/`).
- [ ] T030 [US4] Check that Quotation Review shows the pack and flags a low-confidence pack. This is in `apps/web/src/app/features/quotations/quotation-review/` and is delegated to Agy only if a gap is found, with a Karma spec.

---

## Phase 7: Polish & cross-cutting

- [x] T031 [P] Run `ml/evals/product_matching` on `main` and on the branch, and record both in `specs/023-rfq-aware-matching/research.md`. Precision and recall must be unchanged for quotes that answer no RFQ (SC-006).
- [x] T032 [P] Write an e2e test in `apps/web/tests/e2e/rfq-aware-matching.spec.ts`: an RFQ with 2 replies, authorize both, and the Match Resolution queue for those quotes is empty; correct one match. Prove it compiles with `npx playwright test --list`; the full run is in CI.
- [ ] T033 Before the PR, run `debate-review --local` and fix the real findings. Write the PR body with `mattpocock-skills:pr`.
- [ ] T034 After merge, run `pnpm db:migrate` on hosted (it ends with `pnpm db:check-privileges`) and confirm with `supabase migration list`. Deploy the API, optimiser and extraction worker. Prove the worker image is new with a retry-extraction (memory: extraction deploy can stay stale).
- [x] T035 Re-walk round 1 live on «مطاعم رواق»: a new RFQ, two Gmail replies, authorize, and no manual matching. Save screenshots to the round-1 flow doc under `docs/gtm/demo-tenant/`, with the owner email redacted. Update Jira PPS-95 to Done with a Progress comment. — Done 2026-10-31: RFQ `9de0a3ce`, 8/8 lines matched automatically from their RFQ lines, packs filled; [`docs/gtm/demo-tenant/round-1-rewalk-2026-10-30/`](../../docs/gtm/demo-tenant/round-1-rewalk-2026-10-30/README.md).

---

## Dependencies

```text
T001,T002 ─▶ T014
T003 ─▶ T004 ─▶ T005, T006 ─▶ T007, T008 ;  T009, T010 (after T004)
Phase 2 ─▶ US1 (T011–T020) ─▶ US2, US3 (independent of each other) ;  US4 independent of all but T027→T028→T029
T017 ─▶ T025 (sweep also runs after a correction)
all ─▶ T031–T035
```

- **US1 is the MVP**: Phase 2 plus T011–T018 deliver the automatic RFQ matches and correction on the
  API. T019/T020 add the web.
- **US4 (extractor)** can start immediately and in parallel. It touches only the worker.

## Parallel examples

- After T004: T006 (classification) ‖ T009 (rfq read api) ‖ T010 (schema).
- US1 tests: T011 ‖ T012 ‖ T013. Web: T019 ‖ T020, once T018's contract is fixed.
- US4 (T027–T029) runs alongside all of Phases 2–5.

## Implementation strategy

1. Phase 2 in-house on `pp-x-db`, until the existing suites are green with the view.
2. US1 API (T011–T018), demonstrable through the API and the replay test.
3. US1 web (Agy), then US2 and US3, then US4 (worker lane) in parallel.
4. One PR per phase boundary is acceptable (the migration with the reader move; then US1; then
   US2–US4). Each PR is `debate-review --local`'d and merged when green.
