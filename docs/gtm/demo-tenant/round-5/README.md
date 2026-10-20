# Round 5 — English-interface recording (2026-10-20)

A fresh real round on «مطاعم سند», run and recorded with the owner's interface set to English (web: the account menu's language switch, restored to Arabic afterwards; phone: an English Flutter web build), for the English cuts of the demo video. Recorded by tab capture over the Chrome DevTools protocol (`docs/gtm/video/source/opening/assemble.py`), which does not depend on which screen the kiosk window lands on under Wayland.

## What ran

| Step | Result |
|---|---|
| Phone: low-stock report, oil, Maadi, 1 left | submitted; confirmation «Count remaining: 1 L» (the #195 fix) |
| Web: RFQ for 8 tins of oil, 12 sacks of rice, 80 kg of onions to النور, الأمانة, الحاج سيد, needed by 22/10 | sent; the RFQ email is English (tenant default locale) |
| Supplier replies from Gmail (one per supplier alias, each threaded on its own RFQ message) | الأمانة: photo quote covering all three (`IMG-20261020-WA0014.jpg`: oil 1,595 · rice 905 · onions 16.50, total 24,940 ج.م); النور: PDF (oil 1,620 · rice 915, total 23,940); الحاج سيد: PDF (onions 16.90, total 1,352). All three read with the right supplier and totals |
| Review | الأمانة authorised on camera; النور and الحاج سيد off camera |
| Guardrail | fired for الأمانة's reply: request `36722942`, EGP 24,940, «Prepared automatically by a guardrail» — but only after findings 48 and 47 were worked around (see below) |
| Smart Compare, oil × 8 | الأمانة recommended, EGP 12,760 vs النور 12,960 (1% margin) |
| Request submitted; approved on the phone | «Request approved.» |
| PO-000007 created from the request and submitted; outcome recorded | 3 savings records: oil +120, rice +60, onions +20 = **EGP 200** against last PO prices |
| Savings verified by the owner | ledger **EGP 1,260.00**, 9 verified outcomes |

Quote documents and their sources: [`quotes/`](quotes/) (`render.cjs` prints the PDFs and the photo source from the HTML; `photo.py` turns it into the phone photo).
