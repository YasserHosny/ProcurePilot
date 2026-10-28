# Research: Replies to an RFQ Match Against the RFQ's Own Lines (023)

Date: 2026-10-28. Every finding below was read from `main` at `3d3038d8`. File:line references are
to that commit.

## R1. Where RFQ matching plugs in

- **Decision.** Add an RFQ stage at the head of `MatchingService`'s per-line loop
  (`modules/matching/service.py` ~500–557, the loop that tries `find_deterministic_candidate`, then
  `build_similarity_candidates`). For each line that has no decision and no candidates yet:
  `rfq_fit = fit_against_rfq(line, rfq_lines)` → exactly one fit → persist that single candidate
  and create the automatic decision (same path as the deterministic branch). Several fits or a
  pack conflict → persist the fitting RFQ lines as the top candidates (reason flags below), then
  let the existing similarity candidates follow, and route to a task.
- **Rationale.** The deterministic branch already shows the pattern: persist one candidate with
  reasons, then call `_create_automatic_decision`. That path already enqueues the ADR-019
  guardrail evaluation, writes the `matching.auto_accepted` audit event and computes landed cost
  (service.py ~650–700). Reusing it keeps every side effect identical.
- **Alternatives.**
  - A post-pass after normal matching that "upgrades" tasks. Rejected: it creates and then closes
    tasks, so queues and metrics flicker.
  - A separate worker. Rejected: matching is synchronous inside the API today, and an RFQ is ≤ 50
    lines.

## R2. How a quotation knows its RFQ

- **Decision.** Use `rfq_response.quotation_id` → `rfq_recipient.rfq_id` → `rfq_line` (product, quantity,
  position, since 20261028000000), plus `pack_definition` for each product's purchasing pack. One
  query per quotation, not per line.
- **Rationale.** The link already exists (`20260924203650_rfq_sourcing.sql:56`). All of these tables
  are tenant-scoped with RLS, and the matching service reads through the member's client, so no new
  tenancy surface is added.

## R3. The fit rule (FR-002, FR-006, FR-007)

- **Decision.** The rule is deterministic and replayable, and it is versioned as
  `rfq-fit-v1` in the candidate's `scoring_version` and reasons.
  1. **Wording score** per RFQ line = the best of:
     - trigram similarity (`pg_trgm.similarity`, the function `search.py` already uses) between the
       normalised quoted text and the product's tenant name;
     - the same similarity against each alias of that product;
     - token containment: every token of the product's head noun appears in the quoted text after
       normalisation (NFKC, Arabic letter folding as in `azure_di._normalise_header`, digits
       folded).
  2. **Pack check**:
     - When the quoted line has a pack, its base quantity per pack (`pack_count × unit_size` in
       `pack_unit`, converted to the product's base unit) must equal the RFQ product's
       `pack_definition.base_quantity` (in the product's base unit) within 0.5 %. Otherwise it is a *pack conflict*
       (FR-007).
     - When the quoted line has no pack, the pack check is "unknown".
  3. **Fit.**
     - A line fits RFQ line *k* when its wording score with *k* ≥ `RFQ_FIT_FLOOR` and the pack
       check is not a conflict.
     - It is matched when exactly one RFQ line fits **and** that line's score beats the next RFQ
       line by ≥ `RFQ_FIT_MARGIN`. When the pack is unknown, the margin doubles (FR-006).
  4. **Position.** Equal quoted and RFQ position adds +0.05 to the wording score, as a tie-breaker
     only. It can never turn a non-fit into a fit, because the floor is checked before the bonus.
- **Calibration.**
  - Starting values: `RFQ_FIT_FLOOR = 0.30` (equal to `matching_trigram_threshold`) and
    `RFQ_FIT_MARGIN = 0.15`. Both become settings (`MATCHING_RFQ_FIT_FLOOR`,
    `MATCHING_RFQ_FIT_MARGIN`).
  - Task T002 measures the wording scores of the 8 round-1 lines against their RFQ's 4 products
    (read-only on hosted «مطاعم رواق», RFQ `1b7cd76b`) and records them in this file before the
    values are committed. SC-001 needs all 8 above the floor with margin. SC-003 needs the
    ambiguous-oil and pack-conflict fixtures to stay below it.
- **Rationale.**
  - Restricting the search to the RFQ's 4 products turns a 1-in-N catalogue problem into a
    1-in-4 problem. The round-1 failures (28 % and 34 %) were catalogue-wide composite scores,
    whose features were mostly the 0.5 placeholders.
  - Calibration on a labelled benchmark is still not feasible (CLAUDE.md, spec 004 R5/R10), so a
    transparent rule with recorded inputs is the honest form.
- **Alternatives.**
  - Reuse `score_candidate` with an "rfq" weight. Rejected: it inherits the placeholder features
    and is not explainable.
  - Embeddings. Rejected: the hosted embedding mode is a stub (`STUB_EMBEDDING_MODEL`).

## R4. Explaining a candidate without placeholders (FR-009, FR-010)

- **Decision.**
  - `reason_payload` gains a `measured` map listing only signals actually computed, and the web
    renders only those.
  - The legacy `feature_score` 0.5 values stay in stored JSON, because `match_candidate` rows are
    immutable, but the web no longer shows a feature whose input was `None`.
  - Rows written before this change (no `measured` key) treat `lexical_similarity` as measured,
    `semantic_similarity` as measured only when the embedding model is not the stub, and every
    `feature_score` entry as unmeasured.
  - RFQ candidates carry `rfq: {rfq_id, rfq_line_id, position, pack_check, wording_score}`. The
    web leads the explanation with "Your RFQ line N · product · pack × quantity" and uses neutral
    colouring, not the low-confidence red (FR-010).
- **Rationale.** Stored candidates are evidence (Constitution I) and must not be rewritten. The fix
  is in presentation, plus a richer payload going forward.

## R5. Correcting a match without breaking append-only (FR-005)

- **Finding.**
  - `match_decision` is append-only by design: the file header of
    `20260819000024_match_decisions.sql` says "correcting a previously confirmed match … needs its
    own supersession model later".
  - It enforces one row per line (`match_decision_one_per_line`).
  - Readers: about 19 modules, including the optimiser worker, landed cost, savings, offers,
    supplier IQ, alerts, analyst, request valuation, RFQ responses and the guardrail evaluation.
- **Decision: an insert-only supersession chain.**
  - New column `match_decision.supersedes_decision_id uuid null`, a composite FK to
    `(tenant_id, id)` of the same table.
  - Replace `match_decision_one_per_line` with:
    - `unique nulls not distinct (tenant_id, quotation_line_id, supersedes_decision_id)`, so each
      line has exactly one root;
    - `unique (supersedes_decision_id)`, so each decision is superseded at most once.

    Together these make each line's decisions a single chain with one head. No row is ever
    updated.
  - A trigger checks that the superseded decision belongs to the same tenant and line.
  - New view `current_match_decision` (`security_invoker = true`) lists the heads, i.e. decisions
    with no successor.
  - Every reader that means "the line's match" moves to the view. Readers that mean history
    (audit, savings evidence of a past purchase) keep the table.
  - A correction inserts a new human decision with `supersedes_decision_id` set, then:
    1. computes landed cost for it (the old `landed_cost` rows stay as history; readers follow the
       current decision);
    2. enqueues guardrail evaluation (ADR-019);
    3. writes `matching.decision_corrected` audit with both ids.
- **Lock.** A correction is refused (409 `line_on_purchase_request`) when a non-withdrawn,
  non-rejected purchase request line prices from a `landed_cost` of the current decision
  (`purchase_request_line.estimated_unit_price_source_landed_cost_id`).
- **Rationale.** This keeps Constitution II (no destructive update to outcome records) and lets the
  database guarantee one current decision per line.
- **Alternatives.**
  - `superseded_at` on the old row. Rejected: it is an update to an outcome record.
  - Delete-and-reinsert into a history table. Rejected: it destroys history and breaks the
    `landed_cost` cascade.
  - A separate supersession table. Rejected: the database cannot enforce "one current per line"
    across two tables without triggers on both.
- **Risk.** The reader migration is the largest part of 023. Task T010 greps every
  `match_decision` reference and classifies it (current or history) in this file before code
  changes. The isolation suite (`pnpm test:isolation`) covers the new view.

## R6. A learned wording clears open lines (FR-011, FR-012)

- **Finding.**
  - Aliases are tenant-wide and matched on exact case-folded text (`_aliases_for_line`, `limit 2`).
  - New lines with a known alias are auto-accepted deterministically.
  - Lines already queued are never re-evaluated: `_ensure_pipeline` skips a line that already has
    candidates (service.py ~503–510). That is why round 1's second «دقيق» stayed open.
- **Decision.**
  - After `AliasService.learn_or_reuse_alias` succeeds in a human resolution, run
    `sweep_open_lines_for_alias(alias)`. It selects open `match_task` lines in the tenant whose
    normalised `original_text` equals the alias text (the `exact.normalise_name` rule) and that
    have no decision.
  - For each, it inserts an automatic decision with reason `alias_hit` and
    `learned_from_decision_id`, then resolves the task.
  - The sweep is bounded (200 lines per call, like `EXACT_SCAN_LIMIT`) and runs in the same
    request after the decision commits. A failure is logged and retried by the next resolution,
    never blocking the one in hand.
  - Corrections (FR-012) list lines whose decision has `learned_from_decision_id` = the corrected
    decision.
- **RFQ matches never teach (FR-004).** RFQ automatic decisions create no alias, and the sweep
  ignores them.

## R7. The pack column (FR-013, R1-M9)

- **Finding.**
  - `azure_di._header_role` (azure_di.py:452) maps columns to roles: unit_price, line_total,
    description, quantity, unit. There is no `pack` role, so the round-1 «العبوة» column ("كيس 10
    كجم", "تنكة 18 لتر") is dropped.
  - The worker already persists `pack_count`/`unit_size`/`pack_unit` when present (worker.py:169).
  - The Bedrock and structured parsers already ask for them.
- **Decision.**
  - Add a `pack` role: «العبوة», «التعبئة», «الحجم», "pack", "packing", "pack size", "packaging".
  - Add a `parse_pack_text()` that turns "كيس 10 كجم" into (1, 10, kg), "كرتون 12 × 1 لتر" into
    (12, 1, L), and "Carton 24x500g" into (24, 0.5, kg), with Arabic-Indic digits.
  - When parsing fails, the raw text is kept as a `field_extraction` row `pack_text` (surfaced through `extracted_fields`, as
  `_with_line_extracted_fields` assembles them), and the pack fields get
    confidence 0.4, so Quotation Review flags them (FR-013 "flag, not empty").
- **Fixtures.** The round-1 PDFs `DH-26-1252` and `WF/2026/0781`, regenerated with
  `docs/gtm/gcc/setup/quotes/gen_quotes.py`, become extraction fixtures.

## R8. Lines with no decision after re-authorize

Re-authorizing re-runs `_ensure_pipeline`, which already skips decided lines. RFQ matching inherits
that behaviour, and confirmed decisions are never touched (spec edge case).
