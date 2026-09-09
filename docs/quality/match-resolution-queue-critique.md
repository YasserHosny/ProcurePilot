# Match Resolution Queue - UI and Functional Critique

Status: Recommendations implemented and verified locally
Feature anchor: `specs/004-matching-normalisation/`
Evaluation date: 2026-09-08

Review basis: independent inspection of the supplied desktop screenshot, the Angular queue component,
its tests and translations, and the matching-task API contract. Findings distinguish a presentation
problem from a confirmed data-integrity defect.

## Executive Summary

The Match Resolution Queue is the human-in-the-loop surface for product matching decisions after
quotation review. The backend distinction is valid: a quotation can be reviewed while its line-level
matching tasks remain open. The current page does not make that distinction clear enough, so users
can reasonably read the screen as contradicting the completed quotation review.

The largest issues are workflow language, financial context, evidence visibility, duplicate row
scannability, and resolution throughput. The queue currently asks reviewers to validate every table
cell without showing enough provenance, calculation context, or candidate detail on the list page.

No evidence reviewed for this critique proves that the queue is loading the wrong quotation-line
records. The apparent contradiction is primarily caused by the UI presenting a line-level matching
status as generic `Open` after the parent quotation has been reviewed. That ambiguity is serious
because it makes correct backend state look untrustworthy.

## What Works Well

- The queue supports search, status, priority, routing-reason, date, and server-side sort controls.
- Buyer and owner actions are separated from read-only access, and resolved tasks switch from
  `Resolve Match` to `View Details`.
- Loading, error, filtered-empty, and unfiltered-empty states are implemented.
- Monetary values use the shared currency-aware formatter rather than displaying a bare numeric
  amount.
- The component guards against stale responses when filters change or pagination overlaps a reload.
- Full quotation IDs and exact queue timestamps are available through tooltips, while the detail page
  contains richer candidate scoring evidence.

## Page Purpose and Current Workflow

The page lists line-level `match_task` records that require a buyer or owner to decide whether a
quotation line maps to an existing catalogue product or requires a catalogue addition. A typical
handoff is:

1. A quotation is uploaded and extracted.
2. The buyer verifies supplier, arithmetic, and extracted quotation fields.
3. The quotation is confirmed as reviewed.
4. Product matching creates open tasks for lines whose match confidence is below the auto-accept
   threshold or where no candidate is found.
5. The Match Resolution Queue shows those open line-level tasks.

The mental model breaks because the queue uses generic labels such as `Status: Open` and `Reason:
Low Confidence` without explaining that these refer to matching tasks, not the reviewed quotation
itself.

## Findings

| Severity | Area | Finding | Evidence | Recommendation |
| --- | --- | --- | --- | --- |
| High | Workflow status | `Status: Open` is ambiguous and appears to contradict the reviewed quotation state. | The screenshot shows quotation `6d37376d` as reviewed in the quotation flow but open in the matching queue. | Rename the column to `Matching Status` and use action-oriented labels such as `Awaiting Match Decision`. Show the upstream quotation state separately. |
| Critical | Financial context | The queue shows unit price without quantity, pack, VAT, discount, delivery fee, or line total. | Line #1 shows `£3.25` in the queue, while the review page shows quantity `500`, VAT `20%`, and total `1950.00 GBP`. | Replace the bare unit price with a commercial terms cell showing quantity, pack, unit price tax basis, VAT, and total line exposure. |
| High | Evidence | The `Candidates` column displays only a count. | Line #1 shows `1`, but the reviewer cannot see the candidate product or score without opening the detail page. | Show a top-candidate preview with product name and score. For zero candidates, show `No candidate found` plus a direct create-product path. |
| High | Evidence | `Low Confidence` lacks the score and failure drivers. | The actual task for line #1 had a candidate but a low score because alias, supplier-code, brand, and variant signals were missing. | Add a tooltip or popover with score, threshold, and signal breakdown. Use wording such as `Low match score` if the value is not calibrated probability. |
| High | Scannability | The flat table repeats quotation IDs and supplier names for each line. | The screenshot shows many adjacent rows for `Alfaisal trade` across quotation IDs `ff963ab2` and `6d37376d`. | Default to grouping by quotation with expandable line rows, quotation reference, issue date, and progress summary. |
| Medium | Workflow throughput | Resolving each line requires navigating to a separate detail page. | The queue action is `Resolve Match` per row, with no visible batch or next-line path. | Add `Confirm and next` on the detail page and consider quick-confirm for single strong candidates. |
| Medium | Time columns | `Queued At` and `Age` duplicate time information and consume horizontal width. | The table uses separate columns for absolute date and relative age. | Merge into one `Queued` column with relative age as primary text and exact timestamp in tooltip. |
| Medium | Provenance | The quotation cell uses a truncated UUID rather than a business reference. | `6d37376d` is useful for debugging but not enough for a buyer validating source documents. | Display supplier quotation reference, source document link, reviewer, and reviewed-at metadata where available. |
| Medium | Accessibility | A clickable row with nested action controls can create confusing keyboard and screen-reader behavior. | The page visually supports both row navigation and a row action button. | Make one clear primary link per row and keep secondary actions as distinct controls with accessible labels. |
| Low | Terminology | The page uses wording that can mix extraction confidence, match score, and workflow status. | `Low Confidence` may be read as low OCR confidence, even when it is product-match confidence. | Rename to `Low match score` or add visible helper context in the reason cell. |
| High | Responsive usability | The 11-column table has no compact or priority-based mobile presentation. | The implementation handles narrow screens with horizontal overflow, leaving the decision action and key evidence potentially off-screen. | Define a compact breakpoint view that keeps line identity, routing reason, top candidate, exposure, age, and action visible; move secondary metadata into an expandable detail region. |
| High | Risk triage | The queue cannot be sorted by financial exposure or confidence score. | Available sorts are limited to queue time, priority, and status; the screenshot shows every task as `Normal`, so priority provides little discrimination. | Add materiality and match-score sorting, and derive or explain priority using exposure, confidence, age, and routing risk. |
| Medium | Information hierarchy | Default-open rows repeat `Open` and `Normal`, spending width on low-information values while critical evidence is hidden. | Every visible row in the supplied state has the same status and priority. | Collapse invariant state into the queue heading or filters and allocate table width to candidate evidence and commercial context. |
| Medium | Source verification | Truncated supplier wording has no visible affordance for the full text or source location. | The original text is clamped to two lines, while only the quotation UUID and timestamp have tooltips. | Add full-text access and a source-document/page reference so reviewers can verify the extracted line without guessing. |
| Medium | Workload visibility | The page provides rows but no queue summary or quotation-level completion progress. | Users cannot see how many quotations, lines, overdue tasks, or high-exposure tasks remain. | Add compact operational counts and per-quotation progress, such as `5 of 6 lines unresolved`, without turning the page into a dashboard. |

## Detailed Recommendations

### Clarify Workflow State

Show both lifecycle layers explicitly:

| Layer | Example Label | Meaning |
| --- | --- | --- |
| Quotation state | `Quotation reviewed` | Supplier, arithmetic, and extracted fields have been approved. |
| Matching state | `Awaiting match decision` | This line still needs catalogue/product resolution. |

This prevents the user from interpreting an open match task as a reopened quotation review.

### Improve Financial Display

The queue should not rely on a bare unit price. A reviewer needs commercial context to decide which
rows are important and whether pack/unit normalization looks plausible.

Recommended display:

| Field | Example |
| --- | --- |
| Quantity and pack | `500 each`, `Pack: 5 x 80 each` |
| Unit price | `3.2500 GBP ex VAT` |
| VAT | `20%` |
| Line exposure | `1950.00 GBP inc VAT` |

This also aligns the matching queue with the quotation review page, where users already see quantity,
VAT, and line total.

### Expose Candidate Evidence

Replace the numeric candidate badge with evidence:

| Current | Recommended |
| --- | --- |
| `1` | `A4 Copy Paper 80gsm - score 26%` |
| `0` | `No candidate found` |
| `Low Confidence` | `Low match score: 26% below 92% threshold` |

When available, show why the score failed: alias hit, supplier-code match, lexical similarity,
semantic similarity, brand match, variant match, pack-unit match, and pack-size plausibility.

### Group by Quotation

A grouped view would match how users think about uploaded documents:

```text
Alfaisal trade - Quote 6d37376d - 6 open matching tasks
  #1 A4 Copy Paper 80gsm - low match score - 1 candidate - Resolve
  #2 Ballpoint Pen Blue - no candidate - Create product
  #3 Manila Folder A4 - no candidate - Create product
```

This reduces repeated cells and lets the user understand progress at document level.

### Streamline Resolution

For a multi-line quotation, the queue should support continuous work:

1. `Resolve and next` on the match detail page.
2. `Back to this quotation group` instead of a generic queue return.
3. Inline quick-confirm only for high-scoring single candidates, with undo.
4. Batch create-product support for repeated no-candidate rows from one quotation.

### Strengthen Auditability

Each row should answer "why am I seeing this?" without forcing a detail-page jump:

| Question | Queue Evidence |
| --- | --- |
| Was the quotation reviewed? | Reviewer and reviewed timestamp. |
| Why is this line routed? | Reason plus score/threshold or no-candidate explanation. |
| What source value is being matched? | Original wording, normalized quantity/pack/unit, and source document link. |
| What happens when I resolve it? | Candidate/product target and resulting match decision state. |

## Suggested Acceptance Criteria

1. Given a reviewed quotation with unresolved match tasks, when the line appears in the queue, then
   the status column clearly reads as matching-task status and does not imply the quotation is
   unreviewed.
2. Given a quotation line with quantity, unit price, VAT, and pack data, when it appears in the queue,
   then the queue displays enough commercial terms to reconcile it against the quotation review page.
3. Given a line with one candidate, when it appears in the queue, then the candidate cell shows the
   candidate product name and match score rather than only a count.
4. Given a line with no candidates, when it appears in the queue, then the action path makes catalogue
   creation explicit.
5. Given multiple open tasks from one quotation, when the page loads, then users can view them grouped
   by quotation with document-level progress.
6. Given a low-confidence match task, when the user hovers or opens details, then the UI shows score,
   threshold, and major failure signals.
7. Given a resolved match task, when it appears under a resolved/all filter, then the row shows what
   product it resolved to, who resolved it, and when.
8. Given keyboard-only navigation, when the user tabs through the table, then row navigation and action
   buttons have distinct, predictable focus targets.
9. Given a narrow viewport, when the queue loads, then the primary decision context and action remain
   visible without requiring horizontal discovery.
10. Given tasks with different financial exposure or match scores, when the reviewer sorts the queue,
    then the highest-risk work can be brought to the top deterministically.
11. Given truncated supplier wording, when the reviewer requests more context, then the complete source
    text and document location are available without losing queue position.

## Open Questions

1. Should matching be presented as a separate queue only, or also as step 2 immediately after quotation
   review confirmation?
2. Should the UI call the metric `confidence`, `match score`, or `similarity score` while the scoring
   model is heuristic and not calibrated probability?
3. What score threshold should permit quick-confirm from the queue?
4. Should no-candidate rows open a matching detail page, a catalogue product creation flow, or a
   combined resolution flow?
5. How should the queue sort by financial materiality when quotations use different currencies?

## Conclusion

The Match Resolution Queue is not showing a proven data contradiction; it is showing two legitimate
workflow layers without naming them clearly. A reviewed quotation can correctly contain open product
matching tasks, but the generic `Status`, `Open`, and `Low Confidence` labels make that state look like
an extraction or quotation-review failure. This is a trust defect in a human-authorisation workflow,
even when the underlying records are correct.

The page is a workable task index, but it is not yet a sufficient validation surface. It identifies
which line needs attention, then withholds the evidence needed to judge urgency and correctness:
commercial exposure, full source context, candidate identity and score, threshold rationale, and the
parent quotation state. The 11-column flat layout also degrades as quotation volume grows and pushes
essential actions out of view on narrow screens.

Release priority should be:

1. Clarify the two lifecycle states and rename confidence terminology.
2. Expose top-candidate evidence, source provenance, and commercial context.
3. Group work by quotation and support risk-based ordering plus `Resolve and next`.
4. Correct the responsive and keyboard interaction model, then validate it in English, Arabic, LTR,
   RTL, desktop, and mobile layouts.

Until priorities 1 and 2 are complete, the page should not be treated as evidence that a reviewer can
reliably validate every line. It can route work, but it does not yet explain that work well enough to
support a confident, auditable human decision.

### Implementation Outcome (2026-09-09)

The release-blocking trust issues identified above are now addressed. The queue groups tasks by
quotation and shows the source filename, quotation reviewer identity, review timestamp, issue date,
authoritative open/total progress, quoted line exposure, routing reason, top candidate, match score,
age, and one explicit action per line. `Low Confidence` is presented as `Below Match Threshold` to
distinguish product-match scoring from extraction confidence. The layout becomes compact line details
on narrow screens and no longer relies on a horizontally scrolling 11-column table or clickable rows
with nested controls.

The workflow is also explicit end to end. Quotation authorization now shows matching setup as loading,
ready, or retryable failure, and success exposes a quotation-scoped `Continue to Product Matching`
action. Match detail uses a direct tenant-scoped line-task endpoint instead of scanning the first page
of the global queue, and `Resolve and Next` remains within the same quotation.

Audit coverage now appends `matching.task_routed`, `matching.auto_accepted`, and `matching.resolved`
events with actor, quotation, line, decision/task, product/candidate, and scoring evidence as applicable.
These actions have explicit labels in the quotation audit trail. Focused backend tests, real hosted-
database integration tests for event persistence and tenant isolation, the full Angular suite, and
Angular lint validate the implemented behavior.

Deferred recommendations are exposure/score server-side sorting, quick-confirm, batch product creation,
and richer source page/region linking. Audit writes remain separate from the matching database mutation;
transaction-level atomicity requires a future database RPC or outbox design. These residual items do not
reintroduce the original status/data contradiction, but should remain tracked before higher-volume use.

The live upload-to-matching Playwright workflow remains pending because the configured Bedrock SSO
session is expired and the Azure fallback credentials are absent. The workflow selectors and assertions
have been updated for the grouped queue, but a credentialed extraction provider is required to execute
that final environment-dependent gate.
