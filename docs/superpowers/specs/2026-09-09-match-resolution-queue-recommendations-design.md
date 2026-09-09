# Match Resolution Queue Recommendations Design

**Date:** 2026-09-09
**Status:** Approved for implementation
**Source critique:** `docs/quality/match-resolution-queue-critique.md`
**Feature boundary:** `specs/004-matching-normalisation/`

## Goal

Make the Match Resolution Queue a trustworthy, auditable human-decision surface by clarifying the
relationship between quotation review and line matching, grouping work by quotation, exposing the
evidence needed to resolve each line, and streamlining sequential resolution.

## Scope Decisions

Quotation authorization and product matching remain separate lifecycle stages. After authorization,
the review page presents an explicit `Continue to Product Matching` action instead of redirecting.

The queue is grouped by quotation. The existing Match Resolution detail page remains the place where
a reviewer examines all scoring evidence and submits a decision.

Deferred items are batch confirmation, inline quick-confirm, a duplicate master-detail matching
workspace, cross-currency exposure ranking, and correction of an append-only saved match decision.

## Lifecycle Model

The UI shows both layers explicitly:

| Layer | UI label | Meaning |
| --- | --- | --- |
| Quotation | `Quotation reviewed` | Supplier, arithmetic, and extracted fields were authorized. |
| Match task | `Awaiting match decision` | This line still needs catalogue resolution. |

Generic queue labels change from `Status` to `Matching Status`, and `Low Confidence` changes to
`Low Match Score`. The latter is a heuristic ranking score, not a calibrated probability.

## Queue Layout

Angular groups the flat `MatchTaskList` response by quotation ID. A group header contains supplier
name, source filename/reference plus shortened internal ID, quotation status and reviewed timestamp,
issue date, authoritative total-line and unresolved-task counts, a source/review link, and an
accessible expand control.

Each expanded line row contains:

- displayed line number and full supplier wording access;
- quantity, pack, unit price, VAT, delivery, and discount context;
- server-computed `Quoted Exposure` with explicit currency;
- matching status and routing reason;
- top candidate product, match score, configured threshold, and major failed signals;
- queue age with exact timestamp access;
- one primary `Resolve Match`, `Create Product`, or `View Decision` link.

The row itself is not interactive. Links and buttons are distinct keyboard targets. On narrow screens,
each line becomes a compact unframed detail row that keeps identity, routing reason, candidate evidence,
exposure, age, and action visible without horizontal discovery.

## API Contract

The existing cursor-paginated `GET /api/v1/match-tasks` endpoint remains the queue resource. It already
accepts `quotation_id`; the web page adds URL query-parameter support for that filter.

`MatchTask` gains a compact quotation summary containing `id`, `status`, `reviewed_at`, `issue_date`,
source document ID and filename/reference, total line count, open match-task count, and supplier name.
The API supplies counts because cursor pages can split one quotation; the UI never infers total progress
from only loaded rows.

`QuotationLineSummary` gains `quoted_line_total: Money | null` and
`quoted_line_total_issue: "currency_mismatch" | null`, calculated with decimal arithmetic:

```text
subtotal = quantity * unit_price
line_net = subtotal + delivery_fee - discount
quoted_line_total = line_net * (1 + vat_rate)
```

Missing VAT, delivery, and discount are zero. Missing quantity or unit price produces `null`. All
present money inputs must use one currency. A mismatch returns a null total and the explicit issue
code instead of failing the whole queue or fabricating a total. This is quoted exposure, not
normalized landed cost.

The existing candidate structure supplies product identity, score, scoring version, and signal
breakdown. The queue previews rank 1 and leaves complete evidence on the detail page. Resolved tasks use
the existing decision object and add reviewer display identity only when it can be resolved within the
authenticated tenant boundary; otherwise the membership identifier remains visible.

## Navigation and Failures

After authorization, matching initialization has a visible loading state. Success exposes `Continue to
Product Matching`; failure exposes `Matching setup needs retry` and a retry action. The quotation remains
reviewed when initialization fails, and the error is not swallowed.

Continuation opens `/matching?quotation_id=<id>`. The queue reads and preserves the filter. Resolution
links carry quotation context. `Resolve and Next` loads the next unresolved task for the same quotation;
after the final task, it returns to the expanded completed quotation group.

The detail page must not locate a line by scanning only the first page of all workspace tasks. Add
`GET /api/v1/quotation-lines/{line_id}/match-task`, returning the latest task and decision for that
line. It preserves cross-tenant not-found behavior. Existing line-ID routes use this endpoint.

Groups are keyed by quotation ID and recomputed after each cursor page append. API counts remain
authoritative. A concurrently resolved next task triggers a quotation-scoped refresh.

## Auditability

Append-only audit events cover:

| Action | Actor | Target | Required metadata |
| --- | --- | --- | --- |
| `matching.task_routed` | initiating member/system context | quotation | line ID, task ID, reason, score, threshold, scoring version |
| `matching.auto_accepted` | initiating member/system context | quotation | line ID, decision ID, candidate ID, product ID, score, scoring version |
| `matching.resolved` | human member | quotation | line ID, task ID, decision ID, outcome, candidate ID, product ID, score, scoring version |

Events use the authenticated audit writer so tenancy comes from the verified JWT. The quotation ID is
the target and matching identifiers are metadata, allowing events to appear in quotation audit history.
Match decisions remain the append-only authoritative outcome.

Business records and audit events currently use separate requests. This design does not claim
cross-request database atomicity. Audit-write failures are surfaced and tested; transaction-level
atomicity requires a separately approved database RPC or outbox design.

## Internationalization and Accessibility

All new strings live in English and Arabic catalogues. CSS uses logical properties and supports LTR and
RTL. Full source wording is available without hover-only interaction. Tooltips supplement rather than
replace visible evidence. Expand controls, links, and decision actions have distinct accessible names,
stable dimensions, and predictable focus order. Color is never the sole state indicator.

## Verification Strategy

Implementation follows test-driven slices:

1. API contract and calculation tests for quotation summary, counts, quoted exposure, currency mismatch,
   candidate preview data, and resolved reviewer evidence.
2. Integration tests for tenant isolation and matching audit events, including actor, quotation, line,
   score/version, outcome, candidate, and product metadata.
3. Angular tests for URL filtering, grouping across appended pages, terminology, commercial context,
   top-candidate evidence, responsive priority fields, and resolved decision evidence.
4. Detail-page tests for direct/scoped lookup, resolve-and-next, final-task return, concurrent refresh,
   and visible initialization retry errors.
5. English/Arabic catalogue validation, web and API lint, unit suites, isolation tests, axe checks, and
   desktop/mobile LTR/RTL screenshots.

The critical end-to-end path is:

```text
authorize -> initialize matching -> continue to filtered grouped queue -> inspect evidence
-> resolve -> resolve next -> completed group -> matching events visible in quotation audit history
```

## Delegation Record

The grouped layout was selected through the browser visual companion. A read-only Antigravity design
review was dispatched with a 15-minute watchdog. It stalled during its own browser/runtime setup,
returned no usable final report, and was not accepted as evidence. It made no accepted code changes.
