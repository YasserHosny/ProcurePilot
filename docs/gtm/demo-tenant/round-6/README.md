# Round 6 — Arabic-interface recording on the Ledger UI (2026-10-24)

A fresh real round on «مطاعم سند» for the v2.4 demo video ([`../../video/script-v2.4.md`](../../video/script-v2.4.md)),
run and recorded in the Arabic interface after the Ledger design system shipped to the web app (#235)
and the Flutter app (#245). Recorded by tab capture over the Chrome DevTools protocol with
[`../../video/source/record-v24/`](../../video/source/record-v24/) (`PP_LANG=ar`); raw clips are in
`~/Videos/pp-recording/v24/ar/` on the recording machine (not in git: several show the owner's email).

## What ran

| Step | Result | Clip |
|---|---|---|
| Phone: low-stock report, oil, Maadi, 1 left | report `9c9cf2a7`; confirmation «تم إرسال بلاغ انخفاض المخزون. الكمية المتبقية: ١ لتر» | `s0-phone-lowstock` (22 s) |
| Web: RFQ for oil ×8, rice ×12, onions 80 kg to النور, الأمانة, الحاج سيد, needed by 28/10 | RFQ `e7dfc3fa` sent to 3 | `s1-rfq` |
| Supplier replies from Gmail, each from its supplier alias, threaded on its own RFQ message (owner OK) | الأمانة photo `IMG-20261024-WA0021.jpg` (oil 1,575 · rice 895 · onions 16.25 = 24,640 ج.م) sent first; النور PDF `NR-26-0447` (23,720); الحاج سيد PDF `QS-2026-1104` (1,340). All three attributed to the right supplier, totals reconciled | — |
| Review | الأمانة's photo quote authorised on camera (one flagged field, the expiry date 03/11, confirmed as read); النور and الحاج سيد authorised off camera | `s2-quote-photo` |
| Guardrail | fired once the exact-name matches were accepted: draft request `509ccac0`, EGP 24,640, «أعدّته الضوابط تلقائيًا» from الأمانة's quote, cost centre «المطبخ — المعادي» | — |
| Smart Compare, oil × 8 | الأمانة recommended, EGP 12,600 vs النور 12,800 (1% margin) | `s3c-smart-compare` |
| Draft submitted | request `509ccac0` submitted | `s3-guardrail-draft` |
| Phone approval | approved; the request moves straight to *ordered* (by design, `requests/service.py`) | `s4-phone-approve` |
| PO-000008 from the request, submitted; outcome recorded from the PO | 3 savings records: oil +160, rice +120, onions +20 = **EGP 300** against the last PO prices (round 5) | `s5-po-savings` |
| Savings verified by the owner (off camera) | ledger **EGP 1,560.00**, 12 verified outcomes | `s6-savings-close` |

Quote documents and their sources: [`quotes/`](quotes/) (`make_round.py` builds the HTML from the round-5
templates, `render_round.cjs` prints the PDFs and the photo source, `../../round-5/quotes/photo.py` makes the
phone photo).

## Recording notes

- The phone build must be made from a `main` that includes #245, with
  `API_BASE_URL=http://localhost:4310/api/v1` (the `/api/v1` path is part of the base). A build without it
  loads, shows "0 pending" and silently finds no products.
- A hash-only `goto` in the phone tab keeps the old app instance; `phone.cjs` reloads after every `goto`.
- The kiosk Chrome must be started detached (`setsid`), or it closes with the shell that started it.
- Gmail on the web stops rendering when the full-screen kiosk window covers it; move it to the other screen.

## Findings to raise

| # | What | Where |
|---|---|---|
| a | Smart Compare shows the offer as «بدون تاريخ انتهاء» (no expiry) although the quote states «صالح حتى 03/11/2026» and the review confirmed it | `/offers/compare`, الأمانة's offer |

Owner email on camera (to be masked at source before any clip is committed or cut): quote review
«رُفع بواسطة», phone approvals list and detail «مقدم الطلب».
