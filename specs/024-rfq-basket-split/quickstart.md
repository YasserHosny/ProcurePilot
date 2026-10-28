# Quickstart: verifying 024

## 1. Migration (throwaway DB `pp-x-db` on :54399 until merged)

- Insert a group for another tenant's RFQ with a member JWT: refused (RLS WITH CHECK).
- Insert a second group for the same RFQ: unique violation.
- `update` or `delete` on `purchase_request_group` as `authenticated`: permission denied.
- Run `pnpm test:isolation`.

## 2. Optimiser filter

`services/optimiser` test: two quotations from the same supplier for the same product, one an RFQ
reply and one older and cheaper. A job with `price_quotation_ids = [rfq reply]` prices from the
reply, and a job without it keeps today's latest-price behaviour.

## 3. Round-1 split (integration)

Build an RFQ for rice, flour, oil and sugar with the round-1 quantities and two replies at the round-1
prices. Then:

1. `POST /rfq/{id}/split`, run the solver, and expect a total of SAR 4,063, best single SAR 4,137
   and a saving of SAR 74.
2. `POST /baskets/{id}/prepare-requests` creates 2 drafts:
   - الذهبي: rice and flour, SAR 2,773;
   - الوفرة: oil and sugar, SAR 1,290.

   Every unit price equals what `estimate_from_source_response` gives for that reply. The RFQ is
   `converted`, with both ids.
3. Replay with the same Idempotency-Key: same ids, no new rows.
4. Make the second request insert fail, by forcing a constraint error in a test hook: no group, no
   requests, and the RFQ stays `responded`.
5. Race single `prepare-request` against `prepare-requests` on two threads: exactly one wins, and the
   other gets `rfq_already_converted`.
6. Correct a match or re-review a reply after the split: `split_stale`.

## 4. Group approval

- Set branch thresholds: up to SAR 2,000 goes to approver A, above that to approver B. Submit the
  group, and both steps are assigned to B (`group_threshold_match`).
- Try `POST /requests/{one request}/approve`: 409 `part_of_split`.
- Approve the group as B: both requests are approved with the same `decided_at`, and each can become
  a PO.
- On a second split, reject it with a reason: both are rejected with that reason.

## 5. Web and mobile

- Karma suites for compare, basket-split, approval-queue and request-detail.
- `flutter test` for the approval queue grouping.
- Playwright (`--list` locally; full run in CI): RFQ Responses → Split → Prepare 2 requests → submit
  → group approve.

## 6. Live (after merge, `pnpm db:migrate`, deploy)

On «مطاعم رواق», run a fresh round:

- RFQ to the الذهبي and الوفرة aliases, Gmail replies;
- split (SAR 4,063) → 2 requests → approve as one → 2 POs, each naming its supplier.

Screenshots go in the round-1 flow doc.
