# Flow review 2026-10-28 — R7 and R8 fixes checked live (PPS-120, PPS-121)

The fixes from [#360](https://github.com/YasserHosny/ProcurePilot/pull/360) were driven on «مطاعم رواق» as
`pp-sa-owner` on 2026-10-30, after the deploy (7de8ffa3), through Claude in Chrome. The web build on
`localhost:4310` is #360's head (fb69b2ac) with `/api` proxied to the hosted API, so it runs the same code against
the hosted data. Three test copies of the round's quote PDFs were uploaded («Upload Anyway» on the duplicate
warning), authorized, and archived afterwards: d2c29e47 (الوفرة, English UI), 94241f1e (الذهبي, Arabic UI) and
4562d72a (الذهبي, English UI). A fourth copy, 8abc780d, was used on 2026-10-30 before the fix to measure the
problem, and archived too. The owner's email is pixelated in 04, 05 and 06.

The page was sampled every 100–150 ms from the click on «Confirm & Authorize» in the dialog.

| # | Fix | Seen live | Screenshot |
|---|---|---|---|
| R7 | «Authorizing…» on the status pill | d2c29e47 at 75 ms, 4562d72a at 79 ms: spinner + «Authorizing…», `role=status`. Arabic, 94241f1e at 113 ms: «جارٍ الاعتماد…» | [06](06-authorizing-status-pill-en.jpg), [04](04-authorizing-pill-ar.jpg) |
| R7 | Nothing else can be clicked while authorizing | Retry Extraction, Create Re-Quote, Archive, Add Line Item, Refuse, Save and Confirm all disabled; the data panel is `aria-busy` | [06](06-authorizing-status-pill-en.jpg), [02](02-authorizing-footer-en.jpg) |
| R7 | No blank page after the answer | straight from «Authorizing…» to «Reviewed & Authorized» with «Preparing product matching…» (4562d72a at 10.3 s, d2c29e47 at 11.4 s, 94241f1e at 9.96 s); the loading state never appeared | [05](05-authorized-ar.jpg) |
| R8 | Editable Unit Price without trailing zeros | `88` (الوفرة rice) and `86` (الذهبي rice), not «88.0000»; tabbing out of the unedited price staged nothing (Save stayed disabled) | [01](01-line-prices-en.jpg), [03](03-line-prices-ar.jpg) |
| R8 | Line Total reads like money | `1,760` in English; `١٬٧٢٠` in Arabic | [01](01-line-prices-en.jpg), [03](03-line-prices-ar.jpg) |

Timings (network, from the click): PATCH (supplier) 2.2–2.5 s, then `POST /confirm` 7.7–8.7 s. The confirm is
slower than the 6.0 s measured before the fix on 8abc780d; the busy state covers the whole wait. Returning from
confirm before preparing matching is PPS-130 (P-99); `GET /matches` speed is a separate task.

Notes:

- Not changed, seen in the Arabic UI: Pack Details still reads «1 × 10.0 kilogram» (English unit), and right after
  switching language the line header total shows «SAR 1,720» in Latin digits while the Line Total field shows
  «١٬٧٢٠».
- The language was switched to Arabic for 03–05 and back to English afterwards (it is saved per user on the server).
