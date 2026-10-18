# Arabic RTL walkthrough — «مطاعم سند» (hosted), 2026-10-18

The owner's interface language was switched to Arabic and every page in the navigation was opened,
plus the detail pages used in the demo: RFQ create/edit/compare, quote review, basket-split result,
purchase order detail, edit and create, request detail and create, guardrail settings, record outcome,
product intelligence, email log and settings.

Method: each page was scanned in the browser for visible text with Latin letters (brand, currency codes,
emails, file names and the workspace slug ignored), and the demo pages were checked by screenshot for
layout.

## What works

- Layout mirrors correctly: sidebar on the right, tables, forms, cards and back arrows.
- All page titles, navigation, buttons, table headers, empty states and messages are Arabic.
- Amounts on compare, basket split, PO and request pages use Arabic-Indic digits and «ج.م».
- Product, supplier and branch names show in Arabic everywhere except the case in finding 33.

## Findings

Findings 31–36 in [`README.md`](README.md):

| # | Where | What |
|---|---|---|
| 31 | Ingestion dashboard, email log, digest settings, RFQ email | raw i18n keys; English alert titles and email subject |
| 32 | Compare, basket split, PO detail, product intelligence | unit names in English |
| 33 | Quote review | matched product shown by its English catalogue name |
| 34 | Date fields, guardrail card, basket-split banner, PO/outcome forms | MM/DD dates; unformatted or Latin-digit money; USD/GBP placeholders, GBP default |
| 35 | Guardrail settings, RFQ draft edit | clipped toggle label; raw 6-decimal quantity clipped |
| 36 | Email log, quote review | supplier ids and extraction internals shown to users |

The guardrail used for the R4.3 auto-prepare test was created on this walkthrough, in Arabic:
max EGP 30,000, at least 1 response, price variance up to 20%, all five suppliers, default branch
فرع المعادي.
