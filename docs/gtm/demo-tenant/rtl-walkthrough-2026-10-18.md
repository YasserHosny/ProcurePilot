# Arabic RTL walkthrough — «مطاعم سند» (hosted), 2026-10-18

The owner's interface language was switched to Arabic and every page in the navigation was opened,
plus the detail pages used in the demo: RFQ create/edit/compare, quote review, basket-split result,
purchase order detail, edit and create, request detail and create, guardrail settings, record outcome,
product intelligence, email log and settings.

Method: each page was scanned in the browser for visible text with Latin letters (brand, currency codes,
emails, file names and the workspace slug ignored), and the demo pages were checked by screenshot for
layout.

## What works

- Layout mirrors correctly: sidebar on the right, tables, forms, cards and back arrows (exceptions in
  finding 35).
- Page titles, navigation, buttons, table headers, empty states and messages are Arabic, apart from
  the raw keys, English alert titles and untranslated field labels in findings 31 and 36.
- Line amounts and totals on compare, basket split, PO and request pages use Arabic-Indic digits and
  «ج.م»; the exceptions (basket-split saving banner, guardrail card, request totals with "EGP") are in
  finding 34.
- Product and branch names show in Arabic, except the matched-product name on quote review
  (finding 33); supplier names show in Arabic except in the email log (finding 36).

## Findings

Findings 31–36 in [`README.md`](README.md):

| # | Where | What |
|---|---|---|
| 31 | Ingestion dashboard, email log, digest settings | raw i18n keys; English alert titles |
| 32 | Compare, basket split, PO detail, product intelligence | unit names in English |
| 33 | Quote review | matched product shown by its English catalogue name |
| 34 | Date fields, guardrail card, basket-split banner, PO/outcome forms | MM/DD dates; unformatted or Latin-digit money; USD/GBP placeholders, GBP default |
| 35 | Guardrail settings, RFQ draft edit | clipped toggle label; raw 6-decimal quantity clipped |
| 36 | Email log, quote review | supplier ids and extraction internals shown to users |

The guardrail used for the R4.3 auto-prepare test was created on this walkthrough, in Arabic:
max EGP 30,000, at least 1 response, price variance up to 20%, all five suppliers, default branch
فرع المعادي.

## Guardrail auto-prepare (tracker 1.2)

Run in Arabic on 2026-10-18, after creating the guardrail above:

1. RFQ `183b07f9` to الحاج سيد للخضار: tomatoes 120 kg, cucumbers 60 kg, needed by 22 October. The
   email went out in English (finding 37).
2. الحاج سيد replied from Gmail with PDF quote QS-2026-1058 (EGP 2,190). Extracted correctly; one flagged
   field (expiry date) confirmed; authorized.
3. Both lines matched automatically (0.965, learned from round 2's confirmed matches).
4. Six seconds later the guardrail fired: auto-preparation event `6173bb1a`, draft request `9e657ae3`
   for فرع المعادي, EGP 2,190, prices per pack from the quote, required by 22 October. Remaining Maadi
   budget shown: EGP 287,755.

No person clicked Prepare Request; the request stays a draft until someone submits it (no autonomous
purchasing). Finding 38: nothing on the request shows it was prepared by the guardrail, and it has no
cost centre.
