# PPS-50 — a quote's expiry reaches Smart Compare (hosted check, 2026-10-24)

Rounds 6 and 7 found Smart Compare showing «بدون تاريخ انتهاء» / "Price valid from Oct 24, 2026 (no
expiry date)" for الأمانة's photo quote, although the quote says «صالح حتى: 03/11/2026» and the reviewer
confirmed that field. The cause: the offer (`landed_cost`) never took `valid_to` from the quotation.
[#255](https://github.com/YasserHosny/ProcurePilot/pull/255) fixed that, and this walkthrough checks it on
hosted after the deploy (image `f9961f4`).

**Not run on «مطاعم سند».** It ran in a throwaway workspace, «PPS-50 Verify Co 1792871804», with its
reporting timezone set to Africa/Cairo like the demo tenant. The document is the round-7 photo quote
`IMG-20261024-WA0026.jpg` (oil 8 × 1,560, rice 12 × 890, onions 80 × 16 = 24,440 ج.م, valid until
03/11/2026). The quote was uploaded and extracted through the API. The rest went through the real web
screens, driven by a headless Playwright script, in English with one Arabic view.

## What ran

| Step | Result | Screenshot |
|---|---|---|
| Review | Azure DI read the photo: issue 24/10/2026, expiry 03/11/2026 flagged at 50%, total reconciled | [01](01-review-expiry-flagged.jpg) |
| Confirm as-is | supplier set to الأمانة للتجارة, expiry confirmed as extracted («Valid for 11 days», "Corrected by Human") | [02](02-review-expiry-confirmed-as-is.jpg) |
| Authorise | two-step authorisation; quotation → Reviewed | [03](03-authorise-dialog.jpg), [04](04-quotation-authorised.jpg) |
| Bulk confirm exact matches | the rice line matched the catalogue's «أرز مصري» by exact name: "1 matches confirmed." | [05](05-matching-queue-exact-banner.jpg), [06](06-bulk-confirm-exact-result.jpg) |
| Resolve the oil line | no candidate → new product «زيت عباد الشمس صفيحة 18 لتر» (1 × 18 L) | [07](07-resolve-oil-new-product.jpg), [08](08-oil-match-decision.jpg) |
| Smart Compare, oil × 8 | **"Price valid from Oct 24, 2026 to Nov 3, 2026"**; Valid Until **Nov 3, 2026**; recommended, EGP 12,480 | [09](09-smart-compare-oil-en.jpg) |
| Smart Compare, rice × 12 | same validity, carried through the bulk-confirm path | [10](10-smart-compare-rice-en.jpg) |
| Smart Compare in Arabic | «السعر صالح من 2026/10/24 إلى 2026/11/03»; «صالح حتى 2026/11/03» | [11](11-smart-compare-oil-ar.jpg) |

In the database, both offers have `valid_to` = 2026-11-03 23:59:59 Cairo time, so the quote is good
through the whole expiry day. Before the fix, every offer from a quotation had `valid_to` NULL.

## Findings

1. **A workspace left on UTC shows the expiry one day late in Cairo.** The expiry day ends at midnight in the
   workspace's reporting timezone, but the web formats dates in the browser's timezone. A first run in a
   workspace still on the sign-up default (UTC) showed "Nov 4, 2026" in a Cairo browser
   ([12](12-utc-workspace-reads-nov-4.jpg)). «مطاعم سند» is on Africa/Cairo, so it reads correctly. An
   Egyptian pilot that never changes the timezone in Settings would see the date shifted, and its offer
   would stay valid two hours too long. Options: default the timezone from the region at sign-up, or
   format the expiry as a calendar date in the workspace timezone. Tracked as PPS-55 (P-27).
2. **"1 matches confirmed."** The bulk-confirm result string (`matching.queue.exact.confirmed` in
   `packages/i18n`) has no singular form. Tracked as PPS-56 (P-28).
3. Offers written before the deploy stay open-ended, because `landed_cost` is append-only. The two quotes
   from rounds 6 and 7 still show "no expiry date"; a new quote on «مطاعم سند» will show its expiry.
