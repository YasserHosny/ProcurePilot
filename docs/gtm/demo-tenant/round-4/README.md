# Round 4 — recorded-round dry run (2026-10-18)

Dry run of the round the demo video records (production tracker items 2.4 and 2.5): Maadi low stock
of oil, rice and onions → RFQ to three suppliers → quotes including a WhatsApp photo → guardrail
drafts the request → phone approval → PO → savings, completed end to end. Run on hosted against «مطاعم سند», in Arabic,
through the real screens (web in Chrome, supplier replies from Gmail).

## What ran

| Step | Result |
|---|---|
| PO-000001 to 000004 marked sent | done, so the savings baseline (last PO price, #173) has paid prices to compare against |
| RFQ `bf71b1df` (Maadi, needed by 22/10/2026): 8 × زيت عباد الشمس (صفيحة 18 لتر), 12 × أرز مصري (شيكارة 25 كجم), 80 كجم بصل أبيض → النور، الأمانة، الحاج سيد | sent from the app; the three emails arrived (finding 39: quantities shown in the base unit, fixed in #180) |
| النور replies with a PDF: rice 12 × 930, oil 8 × 1,665 = 24,480 ج.م | received, attributed to the RFQ, read correctly, total reconciled |
| الأمانة replies with a WhatsApp photo of a printed, stamped quote (`IMG-20261019-WA0007.jpg`): oil 8 × 1,640, rice 12 × 925 = 24,220 ج.م | received and read correctly from the photo, total reconciled; the supplier name on the photo scored 50%, but the RFQ reply attributed it |
| الحاج سيد replies with a PDF: onions 80 kg × 17.50 = 1,400 ج.م | received, read correctly |
| Review and match | quotes authorised; 4 oil/rice lines confirmed by hand (stand-in embedding scores 31–36%, finding 20); onions matched automatically |
| Guardrail (≤ 30,000 EGP, ≥ 1 reply, ≤ 20% variance) | **did not fire**: it drafts only from a reply covering every RFQ line, and no supplier quoted all three (finding 43) |
| الأمانة sends an updated photo quote covering all three (`IMG-20261019-WA0011.jpg`, onions 80 × 17.25, total 25,600 ج.م) | read correctly; its three lines matched automatically from the earlier decisions |
| Guardrail fires | **draft request `7a880ac5`, EGP 25,600, from الأمانة's photo quote**, with the «أعدّته الضوابط تلقائيًا» banner; RFQ → converted; owner email «مسودة طلب جاهزة للمراجعة — الأمانة للتجارة» 2 s later |
| Request submitted for approval | Maadi remaining budget shown as 287,755 |
| Phone approval | approved on the phone web build (Arabic): the approval screen shows the «أعدّته الضوابط تلقائيًا» banner, lines, total and remaining budget; request → ordered |
| PO | **PO-000005** created from the approved request (supplier, lines and prices pre-filled), EGP 25,600, sent |
| Savings | **Record outcome** on PO-000005 pre-filled three lines in base units; saved. Baseline = last PO price: rice 37.60/kg (PO-000001, 940 a sack) → +180; onions 18.50/kg (PO-000002) → +100; oil 93.33/L (PO-000001, 1,680 a tin) → +320. **Total 600 EGP**, pending verification |

Decision (owner, 2026-10-18): in the recorded round, الأمانة's photo quote covers all three items, so
the guardrail drafts the request from the photo in one scene.

## Before recording

- Guardrail default cost centre set to «المطبخ — المعادي» (the dry-run draft had none).
- #180 and #181 merged; check they are deployed before recording.
- Findings 41 (raw JSON stated total on review) and 42 (photo expiry date not read) have fix sessions running.
- On camera: the phone approval list shows the requester's email, not a name; the PO banner shows the request's raw id; Record outcome shows raw quantities and amounts (`300.000000`, `11100.0000`); PO lines show the base unit in English (finding 32).
- The approved 3,450 request from round 2–3 still has no PO; it appears in «من طلب شراء معتمد».
- Record with a fresh RFQ; this one is converted.

## Files

[`quotes/`](quotes/) holds the supplier quote sources: the HTML for each quote, the two WhatsApp
photos, the two PDFs, and `photo.py`, which turns a rendered quote into a phone-style photo
(perspective, desk background, uneven light, blur, sensor noise, JPEG at WhatsApp size).
