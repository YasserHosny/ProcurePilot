# Matching Functionality - Multi-Model Critique

Status: Read-only critique, recommendations not yet implemented
Evaluation date: 2026-09-10
Scope: `specs/004-matching-normalisation/`, matching API, matching queue, match resolution detail,
audit trail, tenant isolation, scoring, candidate retrieval, alias learning, and tests.

## Review Method

This critique combines three passes:

1. Antigravity (`agy`, Gemini 3.1 Pro high effort), read-only.
2. Codex/GPT (`codex` CLI default model after an initial `gpt-5` label retry failure), read-only.
3. Orchestrator review against repository evidence.

The external agents were instructed not to edit files or commit. Both completed with no new
repository changes. Their touched-file summaries only reflected pre-existing local changes in
`AGENTS.md`, `apps/web/src/styles.scss`, and `docker-compose.web-dev.yml`.

## Executive Assessment

The recent Match Resolution Queue enhancement materially improved the user-visible contradiction
between quotation review and matching. The queue now groups tasks by quotation, shows parent
quotation context, quoted exposure, reviewer metadata, source filename, top candidate information,
and uses `Below Match Threshold` rather than the earlier ambiguous `Low Confidence` label.

The remaining risk is concentrated in the actual decision moment and the durability of the matching
contract. The page can now explain why a line reached the queue, but the detail flow can still make
some decisions too easy to confirm, can lose important exposure context, and still displays some
technical signals in ways that overstate their meaning. On the backend, the largest concerns are
idempotency, transaction boundaries, stale OpenAPI coverage, and dead supplier-code matching in the
live pipeline.

The append-only matching-history finding from the older audit is mostly fixed by
`20260905000004_matching_append_only.sql`; it should remain covered by regression tests so it does
not quietly regress.

## Confirmed Findings

| Severity | Finding | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| High | Resolve Match accepts an `Idempotency-Key` header but does not use it. | `apps/api/src/procurepilot_api/modules/matching/router.py:86` accepts `_idempotency_key`, then calls `service.resolve(...)` without passing it. `apps/api/src/procurepilot_api/modules/matching/resolution_service.py:42` rejects a retry once a decision exists. | A successful decision followed by a network retry can surface as `409 line_already_matched` instead of replaying the successful result. For a human authorization workflow, that looks like a failed save even when data changed. | Persist idempotency keys for match resolutions and replay the first result for duplicate keys. Add API and UI tests for retry-after-success. |
| High | Match resolution is not atomic across product creation, alias learning, decision insert, task update, audit write, and landed-cost computation. | `resolution_service.py:49`, `resolution_service.py:65`, `resolution_service.py:73`, `resolution_service.py:94`, `resolution_service.py:95`, and `resolution_service.py:115` perform separate operations. | A mid-flow failure can leave partial state, such as a created product without a decision, a decision without an audit event, or a resolved task without a landed-cost row. | Move resolution into a transactional database RPC or use an outbox pattern for audit/cost side effects. Decide whether audit failure blocks the user action or is retried asynchronously. |
| High | Close-candidate tasks auto-select rank 1 on the detail page. | `match-resolution.component.ts:222` auto-selects the first candidate whenever any candidates exist. `MatchingService._route_or_accept()` uses `close_candidates` when the top two scores are within the review margin at `service.py:289`. | A row routed specifically because the system should not guess can be confirmed with Enter before the user explicitly chooses between close candidates. | For `task.reason === 'close_candidates'`, leave candidate selection empty and require explicit selection. Add a component test that confirm buttons start disabled for close calls. |
| High | The matching OpenAPI contract is stale after the queue/detail enhancement. | `router.py:31` exposes `GET /quotation-lines/{line_id}/match-task`, but `specs/004-matching-normalisation/contracts/matching.openapi.yaml:22` does not include that path. `router.py:62` supports search/date/sort parameters missing from the contract. `schemas.py:58` and `schemas.py:107` expose quoted exposure and quotation summary fields missing from the contract definitions around `matching.openapi.yaml:217` and `matching.openapi.yaml:279`. | The contract no longer protects the fields that made the queue trustworthy. Client generation, contract tests, and external consumers can drift from runtime behavior. | Update the OpenAPI file and add a contract drift check for matching endpoints and response fields. |
| High | Supplier-code deterministic matching is still dead in the live pipeline. | `deterministic.py` supports supplier-code aliases, but `service.py:193` always passes `supplier_code_aliases=[]`. | Exact supplier SKU matches can route to slower fuzzy review or fail to match, while the spec still implies GTIN, supplier-code, and alias deterministic order. | Wire supplier-code evidence into the pipeline with tenant and supplier scoping, or remove supplier-code claims until the data exists. Add an integration test for the live path, not only the pure helper. |
| Medium-High | The UI still shows semantic similarity even when the active model is the stub hash embedding. | `scoring.py:19` correctly moves semantic weight into lexical for `stub-hash-v1`, and `search.py:78` makes semantic retrieval threshold unreachable. However, `match-resolution.component.html:295` always renders `Semantic Similarity`, and the SQL RPC can still compute/order on semantic similarity for returned rows. | Reviewers may treat a hash-derived value as meaningful semantic evidence. This weakens trust in the reason breakdown even when final scoring has been adjusted. | Hide semantic similarity, or label it unavailable, when `candidate.embedding_model === 'stub-hash-v1'`. Avoid using stub semantic values for tie ordering. |
| Medium | Quoted line total is visible in the queue but not in the open detail view. | Queue renders `quoted_line_total` at `resolution-queue.component.html:145`. Detail line metrics render quantity, pack, unit price, VAT, delivery, and discount at `match-resolution.component.html:67`, but omit `quoted_line_total` and `quoted_line_total_issue`. | The reviewer loses the materiality context at the exact point of authorization. | Add quoted exposure and mixed-currency warning to the detail line card. |
| Medium | New-product creation does not default the quotation supplier. | The product form has `preferred_supplier_id` at `match-resolution.component.ts:106`, but `applyTask()` only patches name and pack fields at `match-resolution.component.ts:231`. `QuotationMatchSummary` exposes supplier name but not supplier id. | A common no-candidate workflow forces the buyer to re-select the supplier that is already known from the reviewed quotation. | Add `supplier_id` to the quotation summary response and pre-select it in the create-product form when available. |
| Medium | Queue search enriches unpaged rows in Python. | With a search query, `list_match_tasks()` executes the unpaged task query, hydrates every task, filters in Python, then slices at `service.py:136`. `_task()` performs multiple row lookups per task at `service.py:455`. | Tenant-local queue search can become slow and expensive as task volume grows. | Move search and projection into SQL/RPC or a read model; page before expensive hydration. |
| Medium | Resolve Match contains accessibility and i18n regressions. | Candidate cards are `div role="button"` with `tabindex="0"` at `match-resolution.component.html:217`, while global keyboard handling at `match-resolution.component.ts:273` uses Enter for full confirmation and does not implement native Space activation for the focused card. Feature labels such as `Brand:`, `Variant:`, `Pack Unit:`, `Pack Size:`, and `Price:` are hardcoded at `match-resolution.component.html:303`. Base unit options render `unit.label_en` at `match-resolution.component.html:438`. | Keyboard and screen-reader behavior does not match expected button semantics, and Arabic users still see English labels. This violates the i18n non-negotiable for user-facing strings. | Use real button/radio controls or implement complete role-button keyboard semantics. Move all labels into `packages/i18n`, and render `label_ar` when the active language is Arabic. |
| Low-Medium | Some UI language still exposes internal implementation terms. | `packages/i18n/en.json:948` renders `Keyboard Controls (FR-012)`. Queue status strings at `en.json:880` still say generic `Open` rather than a matching-specific state. | Users should not see feature-ticket identifiers, and generic state wording can still blur quotation state with matching-task state. | Rename to user-facing language such as `Keyboard controls` and `Awaiting match decision`. |
| Low-Medium | Append-only history is fixed in migrations but needs direct regression coverage. | `supabase/migrations/20260905000004_matching_append_only.sql:24` drops the broad policy for `match_candidate`, `match_decision`, and `landed_cost`, recreates select/insert policies, and revokes update/delete at line 41. | The highest-risk old finding is addressed, but without explicit update/delete tests it can regress unnoticed in later migrations. | Add hosted DB integration tests proving authenticated users cannot update/delete `match_candidate`, `match_decision`, or `landed_cost`. |

## Already Satisfied Recommendations

- The queue groups tasks by quotation instead of repeating a flat table for every line.
- Parent quotation status, source filename, reviewer identity, review timestamp, issue date, open/total
  line counts, and quoted exposure are available in the queue.
- The earlier `Low Confidence` label is now `Below Match Threshold`, which separates matching score
  from extraction confidence.
- The queue previews the top candidate and score instead of showing only candidate count.
- The detail route uses `GET /quotation-lines/{line_id}/match-task` rather than scanning the global
  queue.
- `Resolve and Next` keeps the reviewer inside the same quotation.
- Matching audit actions exist for task routing, automatic acceptance, and human resolution.
- Scoring code no longer gives semantic scoring weight to `stub-hash-v1`.

## Design Recommendations

1. Treat `close_candidates` as a deliberate-friction state. Do not preselect rank 1, show the score gap,
   and require an explicit candidate choice.
2. Carry quoted exposure into the detail page so queue and resolution views reconcile without mental
   arithmetic.
3. Hide or downgrade semantic evidence while the embedding model is the hash stub.
4. Replace internal status labels with business workflow labels: `Awaiting match decision`,
   `Being reviewed`, and `Resolved`.
5. Keep the grouped queue, but add exposure and score sorting before larger-volume use.
6. Make the no-candidate path feel first-class: prefill supplier, keep product creation compact, and
   visually clarify that existing candidates are being bypassed when `no_match_new_product` is chosen.

## Functional Recommendations

1. Implement match-resolution idempotency and transaction boundaries before relying on retries or
   high-volume use.
2. Update `matching.openapi.yaml` to reflect the real endpoints, query parameters, and enriched
   response fields.
3. Wire live supplier-code matching or remove the claim from the matching spec until it exists.
4. Add direct regression tests for matching-history append-only permissions.
5. Move searched queue listing toward a paged SQL/RPC projection to avoid per-task hydration at scale.
6. Build a labelled feedback dataset from human decisions beyond alias reuse: positives, hard
   negatives, close-call selections, and no-match reasons.
7. Keep SC-002/SC-003 marked unproven until a held-out benchmark exists and CI runs it.

## Conclusion

The matching flow is now much more trustworthy at the queue level than it was during the first
contradiction report. Users can see that a reviewed quotation may still have open line-level product
matching work, and the page now gives enough context to understand why a line is queued.

The next quality step is to protect the authorization moment itself. Idempotency, atomicity, explicit
close-candidate selection, and up-to-date contracts matter because this flow converts extracted quote
data into trusted catalogue and landed-cost data. Small UI defaults and stale contracts can turn a
correctly routed human review into a weak audit trail.

Priority order:

1. Idempotent, atomic match resolution.
2. Close-candidate explicit-selection UX.
3. OpenAPI contract refresh and drift tests.
4. Supplier-code live-path implementation.
5. Detail-page exposure, supplier prefill, i18n, and accessibility cleanup.
6. Search scalability and benchmark/feedback dataset work.
