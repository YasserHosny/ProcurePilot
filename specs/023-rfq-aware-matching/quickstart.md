# Quickstart: verifying 023

## 1. Migration (throwaway DB only, until merged)

Start `pp-x-db` (pgvector/pgvector:pg17 on :54399), apply CI stand-ins, every migration and the seed,
as for PPS-99. Then:

- Insert a decision and try a second root decision for the same line: expect a unique violation.
- Insert a correction pointing at the head: accepted. `current_match_decision` returns only the
  correction.
- Insert a correction pointing at a non-head, or at another line's decision: expect the trigger
  error.
- Use the member's JWT to `select` from `current_match_decision` for another tenant: no rows
  (`pnpm test:isolation` covers this).

## 2. RFQ fit (unit)

```bash
cd apps/api && pytest tests/unit/test_rfq_fit.py -q
```

Cases:

- round-1 lines (8/8 fit);
- «زيت» against two oils (no fit, both offered);
- a 5 kg bag against 10 kg (pack conflict);
- a product not in the RFQ;
- a line with no pack (doubled margin).

## 3. Round-1 replay (integration)

The test creates the RFQ for the 4 round-1 products and records two replies with the round-1 line
texts and packs. It authorizes both and asserts:

- 8 automatic decisions with `reasons.rfq`;
- 0 open match tasks;
- the guardrail evaluation is enqueued;
- RFQ Responses lists the lines in RFQ order.

## 4. Correction

- Correct one RFQ-matched line to another product: the old decision is kept, the view shows the
  new one, and the line's landed cost and the RFQ comparison follow it.
- Prepare a request from that response, then try to correct again: 409 `line_on_purchase_request`.

## 5. Alias sweep

Two quotes each have an open «دقيق» line. Resolve one with learn_alias, and the other leaves the
queue with `learned_from_decision_id` set.

## 6. Extraction pack

Run the extractor fixture test on the regenerated `DH-26-1252` / `WF/2026/0781` PDFs. Every line has
pack fields, for example «كيس 10 كجم» → 1 × 10 kg.

## 7. Live (after merge, `pnpm db:migrate`, deploy)

Run a new RFQ round on «مطاعم رواق» with two Gmail replies. Matching needs no manual step, and the
Match Resolution queue for those quotes is empty. Screenshots go in the round-1 flow doc.
