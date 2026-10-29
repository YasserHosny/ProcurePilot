# Flow review — round-1 steps on «مطاعم رواق» (2026-10-28)

The round-1 flow ([`../../../demo-tenant/round-1/README.md`](../../../demo-tenant/round-1/README.md)) run again
from the start on the hosted Saudi workspace, as `pp-sa-owner`, through Claude in Chrome. English UI. Findings
are recorded here to be handled later; nothing found during this run has been fixed in it.

**Status (2026-10-30):** fixed in [#314](https://github.com/YasserHosny/ProcurePilot/pull/314) and [#315](https://github.com/YasserHosny/ProcurePilot/pull/315) (PPS-88), except R6 and the parts of O3 and O6 marked
open below. The fixes were checked live on 2026-10-28, with screenshots, in [`fixes-pps-88/`](fixes-pps-88/README.md).

## Steps

### 1. Send the RFQ (2026-10-28)

RFQ `d8f7fb0c` for 4 dry-goods lines, in packs: basmati rice 10 kg ×20, sunflower oil 18 L tin ×10, white sugar
10 kg ×10, flour 45 kg ×15. Sent to الذهبي للتموين (`+pp-sa-dhahabi`) and الوفرة للمواد الغذائية (`+pp-sa-wafra`),
needed by 4 Nov 2026, terms «الأسعار شاملة التوصيل إلى الفرع، والعرض سارٍ 14 يومًا.» Save Draft, then Send RFQ:
"RFQ sent. Suppliers emailed: 2".

![RFQ History: the new RFQ is Sent, 2 recipients, 0 responses](01-rfq-sent.jpg)

### 2. Supplier replies (2026-10-28, 11:35–11:36)

Quotes from [`../../setup/quotes/gen_quotes_review.py`](../../setup/quotes/gen_quotes_review.py) (SAR, 15% VAT
included, free delivery): الذهبي `DH-26-1241` **4,830.00** (rice 86, oil 150, sugar 38, flour 82 per pack);
الوفرة `WF/2026/0765` **4,855.00** (rice 88, oil 146, sugar 36, flour 85). الوفرة is cheaper on oil and sugar, so
a basket split should come to 4,770 (60 below all-الذهبي). Each was sent from Gmail as a reply to its own RFQ
message, from the supplier's send-as alias to `mtaam-rwaq@mail.procurepilot.iron-sys.com`, body «مرفق عرض السعر
المطلوب.», PDF attached. (Arabic typed into the Gmail body this time.)

Within about a minute both replies were ingested, matched to the RFQ (RFQ History: «Responded», 1 response at
first) and extracted. The Quotation Inbox lists both with the right supplier and stated total, reason «Low
Confidence Extraction»: الوفرة `70ad704c` SAR 4,855, الذهبي `2e7861de` SAR 4,830.

![Quotation Inbox: both quotes, right suppliers and totals, open for review](02-quotes-ingested.jpg)

## Findings

Checked against the code by a side review on 2026-10-28 (file references are as of `ae2e8e67`).

| # | Where | Finding | Impact / fix | Status |
|---|---|---|---|---|
| R1 | Create RFQ | After picking a product, the first click on that line's Quantity field does nothing; a second click works. The app code does nothing odd here (plain `mat-select` + `matInput`, `create.component.html:40,50`); most likely Material's closing overlay backdrop takes the click, which fast automated clicks hit more often | confirm by hand; if real, focus the line's Quantity on `selectionChange` | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)): reproduced by hand with fast clicks; the product field is now a search box with no backdrop, and a pick moves focus to Quantity |
| R2 | RFQ save (API) | Saved RFQ lines come back in an undefined order: entered rice, oil, sugar, flour; the draft and the RFQ email show flour, oil, sugar, rice. Cause is the backend, not the form: every line of one save gets the same `created_at` (`now()` = transaction start, migration `20260924203650_rfq_sourcing.sql:25`), reads `order by created_at` (`modules/rfq/service.py:83,195`), update deletes and re-inserts all lines (`:229–250`), and the send query has no ORDER BY (`:297`) | the buyer's order is lost on screen and in the supplier email; fix with a `position` column written on save and used in every read and the send | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)): `rfq_line.position` written on save, used by every read and the email; RFQs saved earlier keep their stored order |
| R3 | Create RFQ | The Terms and Conditions textarea has no `dir="auto"` (`create.component.html:87`), so Arabic terms sit left-aligned in the English UI | Arabic terms read awkwardly | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)) |
| R4 | Suppliers, RFQ supplier picker | Neither the supplier list (`supplier-list.component.ts:69`, name cell `.html:85–92`) nor the RFQ supplier picker (`create.component.html:68`) shows the supplier's email, so the buyer cannot check where an RFQ will go | wrong-address sends go unnoticed | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314), [#315](https://github.com/YasserHosny/ProcurePilot/pull/315)) |
| R5 | Create RFQ | The product picker has no search: it is a plain `mat-select` (`create.component.html:40–46`) whose typeahead only jumps to the first option starting with the typed text, and never filters. With a large catalogue the buyer scrolls | slow product pick; needs `mat-autocomplete` or an in-panel search field | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)): search filters as you type, Arabic-aware, over every product page |
| R6 | RFQ email | The RFQ email went out in **English** although the workspace default is AR. Intended since #166 (2026-10-18): the email locale is `coalesce(sender's preferred_locale, tenant default_locale)` (`modules/rfq/service.py:300–306`). Since #310 (PPS-86, 2026-10-27) the language picked before sign-in is saved on sign-in, so the owner's English sign-in set `preferred_locale = en`. In the same Gmail inbox, today's 08:07 RFQ email (needed by 30 Oct) was Arabic and the 10:25 and 11:09 ones are English | not a regression; product decision: should supplier emails follow the buyer's UI language, the workspace default, or a per-supplier language? | **Open**: owner decision |

## Owner-requested changes — RFQ History and RFQ page (2026-10-28)

From the owner's annotated screens (numbers on the images match O1–O6). Web paths are under `apps/web/src/app/`,
API paths under `apps/api/src/procurepilot_api/modules/rfq/`.

![Owner annotations on RFQ History: sent date with time, Needed By, recipients popover, responses link, actions menu](owner-annotated-rfq-history.jpg)

![Owner annotations on the RFQ page: breadcrumbs, RFQ Details with Details / Items / Recipients / Responses tabs](owner-annotated-rfq-detail.jpg)

| # | Change | Where | Data available today | Status |
|---|---|---|---|---|
| O1 | RFQ History "Sent Date" shows date **and time** ("Oct 28, 2026 · 2:14 PM") | `rfq/history/history.component.html:57` (time style on `formatDate`) | yes, `sent_at` is a timestamp (`service.py:963`); web only | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)) |
| O2 | "Needed By" values look wrong | not a code bug: the column shows `needed_by_date` correctly (d8f7fb0c, entered 04/11, shows Nov 4). The Oct 25 rounds were recorded with hard-coded dates (`docs/gtm/video/source/record-v24/s1-rfq.cjs:6` → 28/10, `rfq-one.cjs:6` → 30/10), hence needed-by 1–3 days after the send. Fix the recording scripts (date from the send day). Separate latent bug: `core/format/format.service.ts:247` parses date-only strings as UTC midnight, so viewers west of UTC see the day before | — | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)): scripts default to the send day + 7; date-only strings format as local dates |
| O3 | Recipients count clickable/hover: suppliers it went to, with delivery status | `history.component.html:65–69` | partly: `GET /rfq/{id}` has recipients with `draft/sent/failed` and `sent_at`, but only `supplier_id` (no name). **No Delivered/Opened tracking exists**: needs mail-provider webhooks, new columns and statuses | **Partly fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314), [#315](https://github.com/YasserHosny/ProcurePilot/pull/315)): popover with sent / failed / not sent and the time. Delivered / Opened tracking is **open** |
| O4 | Breadcrumbs on the RFQ page: "RFQ History › RFQ · Sent <date time>" | `rfq/compare/compare.component.html:4` (or the new detail page); pattern in `quotations/quotation-review/quotation-review.component.html:10–13`; new i18n keys | yes | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)) |
| O5 | A row opens the RFQ itself ("RFQ Details": status, sent date/time, needed-by, items, recipients) with tabs Details / Items / Recipients (n) / Responses (n), not "RFQ Responses" | rows route to `/rfq/compare/:id` (`history.component.ts:97–106`); add `rfq/:id` in `app.routes.ts:313` and a tabbed detail component reusing compare as the Responses tab | yes: `GET /rfq/{id}` (`RfqDetail`) and `GET /rfq/{id}/responses`; product and supplier names need resolving (lines carry only ids) | **Fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)) |
| O6 | Responses count links to the Responses tab (plain "0" when none); Actions chevron → "•••" menu: View details, Compare responses, Resend, Duplicate, Cancel RFQ | `history.component.html:73–77`, `:80–110` (`mat-menu`) | count yes (`service.py:966–971`); View/Compare web only. **No Cancel, Resend or Duplicate API**: no `cancelled` status (migration), send only emails draft recipients, duplicate could pre-fill create from `getRfq` | **Partly fixed** ([#314](https://github.com/YasserHosny/ProcurePilot/pull/314)): responses link; menu with View details, Compare responses, Duplicate. Resend and Cancel are **open** |
