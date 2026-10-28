# Flow review 2026-10-28 — fixes checked live (PPS-88)

The R1–R5 and O1–O6 fixes from #314 were driven on hosted «مطاعم رواق» as `pp-sa-owner` on 2026-10-28, after the
deploy and the `rfq_line.position` migration. A new draft RFQ `be24857e` was saved and **not sent**, so no
supplier email went out. Email order is covered by `apps/api/tests/integration/test_rfq_line_order.py`. Supplier
email addresses are pixelated in these screenshots.

| # | Fix | Seen live | Screenshot |
|---|---|---|---|
| O1 | Sent Date shows date and time | "Oct 28, 2026 · 11:09 AM"; Arabic «٢٨‏/١٠‏/٢٠٢٦ · ١١:٠٩ ص» | [01](01-history-en.jpg), [15](15-history-ar.jpg) |
| O3 | Recipients count opens who it went to | sent RFQ: both suppliers "Sent 11:09 AM"; draft: "2 suppliers, not sent yet" | [02](02-history-draft-recipients-popover-en.jpg) |
| O6 | Responses link; "•••" menu | View details · Compare responses (disabled at 0 responses) · Duplicate | [11](11-history-actions-menu-en.jpg) |
| O4, O5 | RFQ Details, breadcrumbs, tabs | row → `/rfq/d8f7fb0c…`; "RFQ History › RFQ · Sent Oct 28, 2026 · 11:09 AM"; Details / Items / Recipients (2) / Responses (2); `?tab=` deep links | [03](03-details-en.jpg), [05](05-details-recipients-en.jpg), [06](06-details-responses-en.jpg), [16](16-details-recipients-ar.jpg) |
| R5 | Product search | «ارز» (no hamza) finds «أرز بسمتي (كيس 10 كجم)» | [07](07-create-product-search-ar-name.jpg) |
| R1 | Focus moves to Quantity after a pick | after each pick, focus was already in that line's Quantity; "20" typed straight in. Before the fix, fast clicks landed on the select's closing backdrop | — |
| R4 | Supplier email visible | under each name in the RFQ picker; Contact email column in Suppliers | [08](08-create-supplier-picker-emails.jpg), [13](13-suppliers-contact-email-en.jpg), [14](14-suppliers-contact-email-ar.jpg) |
| R3 | Arabic terms align themselves | the Arabic terms sit at the right in the English UI | [09](09-create-filled-terms-rtl.jpg) |
| R2 | Lines keep the buyer's order | entered rice, oil, sugar, flour; a fresh read of `be24857e` returns the same order (English and Arabic) | [10](10-new-draft-items-in-entry-order.jpg), [17](17-new-draft-items-ar.jpg) |
| Duplicate | Pre-fills a new draft | `/rfq/create?from=d8f7fb0c…`: lines, suppliers and terms filled, Needed By empty, notice shown; not saved | [12](12-duplicate-prefill-en.jpg) |

Notes:

- RFQs saved before the fix keep the order they were stored in (`d8f7fb0c` still reads flour, oil, sugar, rice;
  [04](04-details-items-old-rfq-en.jpg)). The backfill numbers existing lines by `created_at, id`, and the order
  entered was never stored.
- Found in this run and fixed in the follow-up PR:
  - the recipients popover was narrower than its content (Material's 280px menu cap), so it scrolled sideways and clipped "Not sent";
  - contact emails wrapped at the hyphen in the supplier list.
- Not changed: in the Arabic UI the Recipients and Responses counts stay in Latin digits, as before.
- The language was switched to Arabic for the RTL screenshots and back to English afterwards.
