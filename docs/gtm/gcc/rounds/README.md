# Saudi demo rounds — «مطاعم رواق» (2026-10-24/25, PPS-39)

Three real rounds on the hosted Saudi workspace, run as in the Egypt rounds
([`../../demo-tenant/round-6/README.md`](../../demo-tenant/round-6/README.md)): a dry round to set the last PO
prices, then one recorded round in each interface language. Workspace and data:
[`../setup/setup_workspace.cjs`](../setup/setup_workspace.cjs); quotes: [`../setup/quotes/`](../setup/quotes/)
(rounds D, A and E). Recorded by tab capture with
[`../../video/source/record-v24/`](../../video/source/record-v24/) (`PP_TENANT=sa`); raw clips are in
`~/Videos/pp-recording/sa/{ar,en}/` on the recording machine (not in git: several show the owner's email).

Every round: oil ×10, basmati ×30, tomatoes ×20 to الذهبي للتموين, الوفرة للمواد الغذائية and خضار القصيم
الطازجة; الذهبي sends a WhatsApp photo, the other two send PDFs; all prices include 15% VAT, stated in the
quote's total row. Supplier replies went from the owner's Gmail send-as aliases, each threaded on its own RFQ
message (owner OK per batch).

## Rounds

| Round | RFQ | Quotes (ر.س) | Request | PO | Saving recorded |
|---|---|---|---|---|---|
| D — dry, off camera | `c16a1c49` | الذهبي `DH-26-1184` 5,100 · الوفرة 4,440 · القصيم 780 | `ece82ef9` | PO-000001, SAR 5,100 | baseline "last quoted price": 0 on every line |
| A — Arabic UI | `a200c7ac` | الذهبي `DH-26-1203` 4,910 · الوفرة 4,290 · القصيم 740 | `ca54ffb9` (guardrail draft) | PO-000002, SAR 4,910 | oil 60 · rice 90 · tomatoes 40 = **SAR 190** |
| E — English UI | `7f3917e9` | الذهبي `DH-26-1219` 4,790 · الوفرة `WF/2026/0748` 4,190 · القصيم `QS-5557` 720 | `36ea1bad` (guardrail draft) | PO-000003, SAR 4,790 | oil 40 · rice 60 · tomatoes 20 = **SAR 120** |

The ledger after round E: **SAR 310.00** verified, 9 verified outcomes. RFQ `2718df03` is an earlier send
from before inbound email was enabled for the workspace (no Reply-To); it was superseded by `c16a1c49` and has no
replies.

## Clips (both languages)

| Clip | Shows |
|---|---|
| `s0-phone-lowstock` | Olaya branch reports oil low from the phone |
| `s1-rfq` | one RFQ to the three suppliers, quantities in packs |
| `s2-quote-photo` | الذهبي's WhatsApp photo read: lines, SAR, VAT-inclusive total reconciled, then Authorise |
| `s2r-authorised` | result insert: «Reviewed & Authorized» |
| `s3c-smart-compare` | oil ×10: الذهبي recommended, landed cost per pack (EN round: SAR 1,480 vs 1,520) |
| `s3-guardrail-draft` | the guardrail's draft from الذهبي's quote, within the SAR 10,000 limit, submitted |
| `s4-phone-approve` | manager approves on the phone, «Request approved.» |
| `s4r-approved` | result insert: request approved and ordered |
| `s5-po-savings` | PO from the approved request, submitted, outcome recorded against the last PO price |
| `s6-savings-close` | the verified ledger |

## Screens

Full-size frames from the masked recordings of rounds A (Arabic UI) and E (English UI), one per step (`screens/{ar,en}/`). The owner's email is masked; the frames are the same footage the video uses.

| # | Step | Arabic UI | English UI |
|---|---|---|---|
| 01 | Phone home (owner) | [AR](screens/ar/01-phone-home.jpg) | [EN](screens/en/01-phone-home.jpg) |
| 02 | Low-stock report: oil, Olaya branch, 1 left | [AR](screens/ar/02-phone-lowstock-filled.jpg) | [EN](screens/en/02-phone-lowstock-filled.jpg) |
| 03 | Report sent | [AR](screens/ar/03-phone-lowstock-sent.jpg) | [EN](screens/en/03-phone-lowstock-sent.jpg) |
| 04 | RFQ: three lines in packs | [AR](screens/ar/04-rfq-lines.jpg) | [EN](screens/en/04-rfq-lines.jpg) |
| 05 | RFQ: three suppliers and needed-by date | [AR](screens/ar/05-rfq-suppliers.jpg) | [EN](screens/en/05-rfq-suppliers.jpg) |
| 06 | RFQ sent to 3 suppliers | [AR](screens/ar/06-rfq-sent.jpg) | [EN](screens/en/06-rfq-sent.jpg) |
| 07 | Quotation inbox: two PDFs and a WhatsApp photo | [AR](screens/ar/07-quote-inbox.jpg) | [EN](screens/en/07-quote-inbox.jpg) |
| 08 | الذهبي photo quote read: SAR, VAT-inclusive total reconciled, flagged fields | [AR](screens/ar/08-quote-review.jpg) | [EN](screens/en/08-quote-review.jpg) |
| 09 | Extracted lines beside the photo | [AR](screens/ar/09-quote-lines-photo.jpg) | [EN](screens/en/09-quote-lines-photo.jpg) |
| 10 | Quote reviewed and authorised | [AR](screens/ar/10-quote-authorised.jpg) | [EN](screens/en/10-quote-authorised.jpg) |
| 11 | Smart Compare, oil ×10: الذهبي recommended | [AR](screens/ar/11-smart-compare.jpg) | [EN](screens/en/11-smart-compare.jpg) |
| 12 | Guardrail draft request from الذهبي quote, within the SAR limit | [AR](screens/ar/12-guardrail-draft.jpg) | [EN](screens/en/12-guardrail-draft.jpg) |
| 13 | Phone: approval detail | [AR](screens/ar/13-phone-approval-detail.jpg) | [EN](screens/en/13-phone-approval-detail.jpg) |
| 14 | Phone: «Request approved» | [AR](screens/ar/14-phone-approved.jpg) | [EN](screens/en/14-phone-approved.jpg) |
| 15 | Request approved and ordered (web) | [AR](screens/ar/15-request-approved.jpg) | [EN](screens/en/15-request-approved.jpg) |
| 16 | PO prefilled from the approved request | [AR](screens/ar/16-po-from-request.jpg) | [EN](screens/en/16-po-from-request.jpg) |
| 17 | PO submitted | [AR](screens/ar/17-po-submitted.jpg) | [EN](screens/en/17-po-submitted.jpg) |
| 18 | Record outcome from the PO | [AR](screens/ar/18-outcome-form.jpg) | [EN](screens/en/18-outcome-form.jpg) |
| 19 | Ledger: this order's savings, pending verification | [AR](screens/ar/19-ledger-after-outcome.jpg) | [EN](screens/en/19-ledger-after-outcome.jpg) |
| 20 | Ledger after verification | [AR](screens/ar/20-ledger-verified.jpg) | [EN](screens/en/20-ledger-verified.jpg) |

## Notes

- A new workspace has no price history, so the guardrail stays silent (`no_price_history_baseline`) until a
  round has been ordered; that is why the dry round comes first.
- Inbound email must be enabled for the workspace (`/tenants/email-config/enable`) before the first RFQ, or the
  RFQ goes out without a Reply-To and replies are never attributed.
- The VAT-inclusive total row («الإجمالي شامل ضريبة القيمة المضافة 15%») used to be read as a total of 15 and a
  fake line; fixed in #277 before round A.

## Findings to raise

| # | What | Where |
|---|---|---|
| a | A zero saving shows as a red «-SAR 0.00» (negative zero) on one dry-round line | `/savings`, tomatoes, round D |

Owner email on camera (to be masked at source before any clip is committed or cut): quote review «رُفع بواسطة» /
"Uploaded by" and "Reviewed by", request approval "Assigned to", phone approvals list and detail.

# All-English rounds — Rawaq Restaurant Group (PPS-64) and Liffey Kitchen Group (PPS-65), 2026-10-25

Two more hosted workspaces, with English names, products, suppliers, quotes and UI: Rawaq Restaurant Group (Saudi
Arabia, SAR, `PP_PROFILE=sa-en`) and Liffey Kitchen Group (Dublin and Cork, EUR, `PP_PROFILE=ie`). Each had a dry
round and one recorded round, run the same way as the Saudi rounds above. The workspace and data come from
[`../setup/profiles.cjs`](../setup/profiles.cjs) and the quotes from
[`../setup/quotes/gen_quotes_en.py`](../setup/quotes/gen_quotes_en.py) (folders `sa-en-round-{D,E}` and
`ie-round-{D,E}`). The recorder ran with `PP_TENANT=sa-en` / `ie`, and the phone used the English web build. Raw
clips are in `~/Videos/pp-recording/{sa-en,ie}/en/` on the recording machine.

Every round has the same three lines (oil ×10, basmati ×30, tomatoes ×20). The first supplier is the cheapest and
sends a WhatsApp photo; the other two send PDFs. Saudi prices include 15% VAT. Irish prices exclude VAT, with a
zero-rated VAT line and a Subtotal row; #286 stopped that row being counted as an item.

| Workspace | Round | Quotes | PO | Saving recorded |
|---|---|---|---|---|
| Rawaq | D, dry | Golden Crescent `GC-26-0412` SAR 5,100 · Red Sea `RS-2026-0318` 4,440 · Qassim `QF-7731` 780 | PO-000001, SAR 5,100 | baseline only |
| Rawaq | E, recorded | Golden Crescent `GC-26-0437` SAR 4,790 · Red Sea `RS-2026-0342` 4,190 · Qassim `QF-7756` 720 | PO-000002, SAR 4,790 | **SAR 310**; ledger SAR 310.00 |
| Liffey | D, dry | Brennan & Walsh `BW-26-1184` €1,343 · Atlantic `AFF-2026-0712` €1,111 · Kerrigan `KFP-5521` €272 | PO-000001, €1,343 | ledger €40.00 before round E |
| Liffey | E, recorded | Brennan & Walsh `BW-26-1219` €1,289.50 · Atlantic `AFF-2026-0748` €1,070 · Kerrigan `KFP-5557` €259 | PO-000002, €1,289.50 | **€53.50**; ledger €93.50 |

Cuts: `docs/gtm/video/cuts/gcc-sa-en-v1/` and `docs/gtm/video/cuts/eu-en-v1/`, built by
[`../../video/source/edit-sa-en/`](../../video/source/edit-sa-en/) and
[`../../video/source/edit-ie/`](../../video/source/edit-ie/). Both are forks of `edit-sa` with English only and
spans retimed to these recordings.

## Screens (English rounds)

These are the same 20 steps as the table above, taken from the masked recordings:
[`screens/sa-en/`](screens/sa-en/) (Rawaq) and [`screens/ie/`](screens/ie/) (Liffey). The file names match the
step numbers above.

## Findings (English rounds)

| # | What | Where |
|---|---|---|
| b | After an RFQ is sent, the RFQ list can still say "Loading RFQs…" more than a second later (Liffey). So the cut holds on the "RFQ sent. Suppliers emailed: 3" toast. | `/rfq`, Liffey round E |
| c | Euro amounts drop a trailing zero ("EUR 1,289.5"), and a zero saving shows as red "-SAR 0.00" (PPS-66). | purchase request, `/savings` |
