# Flow review 2026-10-28 — R10 and R11 fixes checked live (PPS-123, PPS-124)

Checked on 2026-10-31 as `pp-sa-owner` of «مطاعم رواق», on RFQ `d8f7fb0c` (Responses tab), **before merge of [#373](https://github.com/YasserHosny/ProcurePilot/pull/373)**:
- the branch `fix/pps-123-124-rfq-responses` ran locally (API on :8101, web build on :4301);
- both read the hosted Supabase data;
- nothing was prepared or split: the page was only read.

The RFQ is already converted: the guardrail prepared request `34049121` from الذهبي's reply, and that request is now
ordered. Screenshots 01–04 were retaken after the landed-cost change below. 05 comes from the first pass; that screen did
not change. The owner's email is pixelated in 05.

| # | Fix | Seen live | Screenshot |
|---|---|---|---|
| R10 | Cheapest supplier per RFQ line | Each line's lowest landed cost for the RFQ's quantity carries «Lowest landed cost» / «أقل تكلفة واصلة» and the row highlight: flour and rice at الذهبي (1,230, 1,720); oil and sugar at الوفرة (1,460, 360). «Lowest total» stays on الذهبي (4,830) | [01](01-responses-ar.jpg), [03](03-responses-en.jpg), [04](04-wafra-converted-en.jpg) |
| R10 | Split saving | One hint above the replies: «Splitting this order between suppliers could save SAR 60.» / «تقسيم هذا الطلب بين الموردين قد يوفّر ٦٠ ر.س.» (4,830 − 4,770, from landed costs). The RFQ is converted, so the hint has no action. On an open RFQ it sits right above the RFQ's one «Split between suppliers» button (`splitRfq()`), which opens Basket Split pre-filled from the RFQ | [01](01-responses-ar.jpg), [03](03-responses-en.jpg) |
| R11 | Fired guardrail reads as a success and links its draft | «Guardrail fired and prepared a draft request.» in green (`--pp-success`), followed by «Open draft request», which opens `/requests/34049121…` | [03](03-responses-en.jpg), [05](05-draft-link-opens-request-en.jpg) |
| R11 | No duplicate action on a converted RFQ | Neither card offers Prepare Request. Both show «Open request» / «فتح الطلب», which goes to `34049121`. If a split converted the RFQ into several requests, Prepare Request would stay disabled, with «This RFQ is already converted into a request.» | [02](02-wafra-converted-ar.jpg), [04](04-wafra-converted-en.jpg) |
| R11 | «not open» explained | الوفرة: «Not applied: this RFQ was already converted into a request.» / «لم يُطبَّق: تم تحويل طلب عروض الأسعار بالفعل إلى طلب شراء.» (new reason `rfq_converted`). `rfq_not_open` now reads «Not applied: this RFQ is not open for replies (draft or expired).» | [02](02-wafra-converted-ar.jpg), [04](04-wafra-converted-en.jpg) |

## Why landed cost, not the quoted price

Codex's review of #373 found that the first version could promise a saving the split doesn't deliver:
- it compared quoted unit price × the supplier's quoted quantity;
- the split prices each supplier from its landed cost at the RFQ's own quantities, and adds delivery fees and minimum
  orders.

Each reply now carries `rfq_landed_costs`, priced the way the optimiser prices the split, and `supplier_terms_apply`. The
marks and the hint use those figures, and the hint stays hidden when a supplier's delivery or minimum-order terms apply.
On `d8f7fb0c` the landed costs equal the quoted line totals (free delivery, no supplier terms), so the saving is still
SAR 60.

Also checked:

- **The API refuses a second preparation.** Once an RFQ is converted, `POST /rfq/{id}/prepare-request` with a new key
  returns 409 `rfq_already_converted`: it runs under the per-RFQ preparation lock from #330. This is covered by
  `apps/api/tests/integration/test_rfq_service_e2e.py`, re-run on the hosted test DB. If the page is stale and still
  sends one, the page shows «RFQ is already converted» and reloads, so the card turns into «Open request».
- **Tests:**
  - Karma: `compare.component.spec.ts` covers per-line minima, the split hint, and the fired, converted (one and
    several requests) and open states.
  - pytest: `test_rfq_guardrails.py` and `test_rfq_guardrail_explanations.py` cover `purchase_request_id` and
    `rfq_converted`; `test_rfq_responses_landed_cost.py` covers landed cost at the RFQ quantity, delivery in the total,
    expired and unmatched lines, supplier terms and tenant isolation.

Notes:

- After switching the language from Arabic to English, the money amounts in the tables stayed in Arabic digits until
  the page was reloaded (the hint switched at once). This is older than the branch: the money pipe does not re-render
  when the language changes. 03 and 04 were taken after a reload.
- After the English captures the owner's language was set back to Arabic.
