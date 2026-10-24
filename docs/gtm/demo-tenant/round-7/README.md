# Round 7 — English-interface recording on the Ledger UI (2026-10-24)

The same flow as [round 6](../round-6/README.md), run right after it with the owner's interface switched to
English (account menu; restored to Arabic afterwards) and the English Flutter web build, for the English cuts of
the v2.4 demo video. Recorded with [`../../video/source/record-v24/`](../../video/source/record-v24/)
(`PP_LANG=en`); raw clips in `~/Videos/pp-recording/v24/en/` (not in git: several show the owner's email).

## What ran

| Step | Result | Clip |
|---|---|---|
| Phone: low-stock report, oil, Maadi, 1 left | «Low stock report submitted. Count remaining: 1 L» | `s0-phone-lowstock` |
| Web: RFQ for oil ×8, rice ×12, onions 80 kg to the same three suppliers, needed by 29/10 | RFQ `d402687a` sent to 3; the supplier email is English (it follows the sender's interface language) | `s1-rfq` |
| Supplier replies from Gmail, from each supplier alias, threaded (owner OK) | الأمانة photo `IMG-20261024-WA0026.jpg` (oil 1,560 · rice 890 · onions 16.00 = 24,440 ج.م) first; النور PDF `NR-26-0459` (23,480); الحاج سيد PDF `QS-2026-1117` (1,320). All attributed correctly, totals reconciled | — |
| Review | الأمانة authorised on camera («Arithmetic Verified», EGP 24,440.00; expiry 03/11 confirmed); the other two off camera | `s2-quote-photo` |
| Guardrail | draft request `1615516c`, EGP 24,440, «Prepared automatically by a guardrail» | — |
| Smart Compare, oil × 8 | الأمانة recommended, EGP 12,480 vs النور 12,680 (1% margin) | `s3c-smart-compare` |
| Draft submitted; approved on the phone | request `1615516c` → ordered | `s3-guardrail-draft`, `s4-phone-approve` |
| PO-000009 from the request, submitted; outcome recorded | oil +120, rice +60, onions +20 = **EGP 200** against round 6's PO prices | `s5-po-savings` |
| Savings verified by the owner (off camera) | ledger **EGP 1,760.00**, 15 verified outcomes | `s6-savings-close` |

Quote documents: [`quotes/`](quotes/) (built by `../round-6/quotes/make_round.py 7`).

## Recording notes

- Restarting the kiosk with `--disable-backgrounding-occluded-windows --disable-renderer-backgrounding
  --disable-background-timer-throttling` lets both the kiosk and Gmail render while one covers the other.
- The phone and web sign-ins survive a kiosk restart (they live in `~/.pp-recorder-profile`).

Same finding as round 6: Smart Compare shows «Price valid from Oct 24, 2026 (no expiry date)» and
"Open-ended" although the quote states an expiry of 03/11/2026.
