# General demo workspace — Nuvara Group (2026-11-25/26)

Plan: [`plan.md`](plan.md) (approved by Yasser 2026-11-19). Data: profile `gen` in
[`../../gcc/setup/profiles.cjs`](../../gcc/setup/profiles.cjs); quotes from
[`../../gcc/setup/quotes/gen_quotes_general.py`](../../gcc/setup/quotes/gen_quotes_general.py) (folders
`general-round-D`, `general-round-E`).

## Setup

| Step | Result |
|---|---|
| Platform invitation | one row in `platform_invitation` for `+pp-gen-owner`, inserted in the Supabase SQL editor (hash only; `pnpm db:seed` was not used because it also seeds reporting rows into the newest workspace) |
| Sign-up | Nuvara Group, EG / EGP / Egypt VAT, slug `nuvara-group`, owner signed up by Yasser |
| Seed (in-page, as the owner, idempotency keys from the `gen` profile) | 2 branches, 4 cost centres, 4 monthly budgets from 1 Nov (200k / 250k / 150k / 100k), 5 suppliers, 30 products, no guardrail |
| Inbound email | enabled: `nuvara-group@mail.procurepilot.iron-sys.com` |
| Buyer | invited (`+pp-gen-buyer`, "Mona Saeed"), invitation emailed |
| Owner display name | set to the demo name "Karim Adel" (`PATCH /me`) |
| Gmail send-as aliases | `+pp-gen-{arkan,safwa,bayan,delta,nilebyte}` added by Yasser |

## Round D (dry, off camera)

RFQ-000001 to Bayan only, needed by 30 Nov → Bayan's PDF `BGT-Q-26-0911` (EGP 59,280) arrived threaded from its alias,
attributed to Bayan, extracted with «Arithmetic Verified» → authorised (5 flagged fields confirmed as read) → all 5
lines matched to the RFQ products at 100% → request prepared (Head Office, Administration, 30/11) → submitted →
approved on the web ("Within budget, remaining EGP 200,000") → **PO-000001**, EGP 59,280, submitted.

## Round E (on camera, 2026-11-26)

Driven in the UI of a separate Edge profile over CDP (scratchpad `pp.cjs`), captured at 1920×1080 CSS, DPR 1. The
in-app browser pane shows screenshots but cannot save them, and Yasser's Chrome viewport is 1536×674.

| Step | Result |
|---|---|
| RFQ created in the UI | RFQ-000002: 5 lines, Arkan, Safwa, Bayan, Delta, needed by 3 Dec, Head Office terms → sent, "Suppliers emailed: 4" |
| Quotes regenerated with today's date | `general-round-E/` (Arkan PDF, Bayan PDF, Safwa photo `IMG-20261126-WA0017.jpg`; the old `IMG-20261120-WA0014.jpg` is stale and can go) |
| Replies from Gmail, each from its supplier's alias | Arkan 57,190, Safwa (photo) 57,865, Bayan 56,950; Delta silent. All three extracted «Arithmetic Verified», every line and price right |
| Authorised in the review screen | 5 flagged fields confirmed per quote; all 5 lines matched to the RFQ products on each |
| Compare responses | "Splitting this order between suppliers could save EGP 1,485" |
| Basket split | 55,465: Arkan paper + toner 39,700, Safwa cleaner + towels 10,425, Bayan tape 5,340; saving 1,485; solver confidence High |
| Requests prepared | 3 drafts, Head Office, Administration, required by 3 Dec → "No budget configured" (see G9). Fixed by adding a **December** Administration budget of 200,000 (Yasser chose this over withdraw-and-redo) |
| Submitted as one group, approved | Queue: Safwa remaining 154,960, Bayan 149,875, Arkan 184,235 (G10). Approved at phone size (390×844, web app; the Flutter app is not set up on this machine): "Approve EGP 55,465 for Head Office?" → all 3 approved |
| POs | PO-000002 Arkan 39,700, PO-000003 Safwa 10,425, PO-000004 Bayan 5,340, all submitted |
| Outcomes and savings | 5 outcomes against round D's PO-000001 prices: 1,400 + 900 + 480 + 675 + 360 = **EGP 3,815**, all verified |

Screens for the founder campaign: `marketing/ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts/images/source-general/`
(A-07 split, A-08a RFQ create, A-08b RFQ sent, A-09a compare, A-09b approval queue with remaining budget, plus the
verified ledger and the phone approval dialog).

## Findings

| # | What | Where |
|---|---|---|
| G1 | The English quote review shows a raw i18n key for the pack field: `quotations.review.fieldLabels.pack_text` | quote review, flagged fields |
| G2 | The sign-up "Your name" (Karim Adel) was not used: the owner appeared as "Mohamed Yasser" until renamed with `PATCH /me` | sign-up, requests, approval queue |
| G3 | The public landing page still says "For restaurant groups…" and "Built for restaurant groups", against MD-22 | `procurepilot.iron-sys.com/` |
| G4 | The PO form labels a 1-unit pack line "Quantity" and shows no pack hint, while every other line reads "Quantity (packs)" and "pack of N" | PO from request, toner line |
| G5 | A fresh owner's interface opened in Arabic although the workspace language is English | first sign-in |
| G6 | The avatar shows "YA" (from the email) although the display name is Karim Adel | top bar, every screen |
| G7 | The split and approval screens name the RFQ by a UUID fragment ("From RFQ 7fb83413", "Split from RFQ 7fb83413") instead of RFQ-000002; on the split page the link also overlaps the buttons | basket split, approval queue, approval detail |
| G8 | The "Prepare purchase requests" dialog clips the "Branch" label | basket split → Prepare 3 requests |
| G9 | Budgets don't roll over: a monthly budget from 1 Nov covers November only, so requests needed on 3 Dec show "No budget configured" although the cost centre has a budget. Split requests can't be edited (`part_of_split`), so the date can't be moved either | prepared requests, approval queue |
| G10 | In the approval queue each request of one split shows a different "Remaining" (others subtracted, itself not), although the group is approved as one | approval queue |
| G11 | At phone width the approval queue is a wide table: Approve sits off-screen to the right and the budget column wraps word by word | approval queue, 390 px |
| G12 | The submit button on a split request reads like a tooltip: "Submits all 3 requests of this split" | purchase request (split) |
| G13 | The record-outcome form says "Total paid excl. tax" while the workspace's prices include VAT and the amounts are VAT-inclusive | record outcome from PO |
| G14 | The approval detail shows the requester's email under the name (fine in use, but it has to be masked in screenshots) | approval detail |
