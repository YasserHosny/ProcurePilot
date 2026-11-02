# Flow review 2026-10-28 — R6 fix checked live (PPS-134)

R6: RFQ emails went out in the sender's interface language. After the fix in
[#372](https://github.com/YasserHosny/ProcurePilot/pull/372), each supplier's email uses
`coalesce(supplier.preferred_locale, tenant.default_locale)` and the sender's language is not read.

Checked on hosted on 2026-10-31 at 02:21 (Cairo), after the deploy of ba4d984d, on «مطاعم رواق» (workspace
default Arabic) as `pp-sa-owner`, through Claude in Chrome. The owner's UI was switched to **English** from the
account menu, which stores `membership.preferred_locale = en`. That is the setup that made every supplier email
English on 2026-10-28. الوفرة was set to English on the new «Email Language» field; الذهبي was left unset. One RFQ
(`ed988c06`: basmati rice 10 kg × 10 packs, needed by 6 Nov 2026) was sent to both. The owner's email is
pixelated in 01–03, 06 and 07, and the `+pp-sa-…` alias stays readable.

| # | What | Seen live | Screenshot |
|---|---|---|---|
| 1 | «Email Language» on Edit Supplier: «Workspace default (Arabic)», «Arabic», «English» | الوفرة, UI in English | [01](01-email-language-options-en.jpg) |
| 2 | الوفرة saved as English, kept after a reload | `supplier.preferred_locale = en` | [02](02-wafra-english.jpg) |
| 3 | الذهبي left on the workspace default | shows «Workspace default (Arabic)»; `preferred_locale` null | [03](03-dhahabi-workspace-default.jpg) |
| 4 | Send RFQ to both, UI in English | «Send this RFQ to الوفرة للمواد الغذائية, الذهبي للتموين for 1 item, needed by Nov 6, 2026?» | [04](04-send-rfq-confirm-en.jpg) |
| 5 | Sent | «RFQ sent. Suppliers emailed: 2»; both recipients `sent` at 00:21:25 UTC | [05](05-rfq-sent-two-suppliers.jpg) |
| 6 | **الذهبي (unset) gets Arabic** although the sender's UI is English | subject «طلب عرض سعر — مطاعم رواق — مطلوب قبل ٦ نوفمبر ٢٠٢٦», `dir="rtl"`, «١٠ عبوة (١٠ كجم للعبوة) — ١٠٠ كجم» | [06](06-gmail-dhahabi-arabic.jpg) |
| 7 | **الوفرة (English) gets English** | subject «Request for quotation — مطاعم رواق — needed by 6 November 2026», «10 packs (10 kg each) — 100 kg» | [07](07-gmail-wafra-english.jpg) |

Notes:

- Found during this check and filed as PPS-141 (P-110): on Edit Supplier, the half-width «Email Language» field
  wraps its hint onto two lines, and «language.» runs into the «Payment Terms» label (visible in 02 and 03).
  The full-width field on Create Supplier is fine.
- Afterwards the owner's UI was set back to Arabic (`preferred_locale = ar`). الوفرة stays set to English in this
  workspace, so its later RFQ emails are in English.
- The RFQ `ed988c06` is left open with no replies.
