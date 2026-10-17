# Round 1 walkthrough — dry goods, «مطاعم سند» (hosted)

The first full purchasing round run through the real product on hosted
(`procurepilot.iron-sys.com`), workspace «مطاعم سند» (EGP, Egypt VAT), as the owner account
`pp-owner`. Dataset and findings: [`../README.md`](../README.md). Video status:
[`../../video/production-tracker.md`](../../video/production-tracker.md).

Screenshots were taken from the live demo tenant on 2026-10-18, after PRs #108–#112 were deployed.
They show the product as it is, including the open label issues listed at the end.

## The round in one line

RFQ to 2 suppliers (Oct 16) → both reply by email with Arabic PDF quotes → extracted and authorized →
10 product matches confirmed → compare responses → prepare a request from النور's quote
(EGP 56,425) → submit → approve → draft purchase order PO-000001.

## Steps

### 1. Send the RFQ (Oct 16)

RFQ for 5 dry-goods lines (lentils, sunflower oil 18 L tin, rice 25 kg sack, sugar 25 kg sack,
pasta 20 kg carton) to النور للمواد الغذائية and الأمانة للتجارة, needed by Oct 20. The email goes out in
Arabic, names the buyer and carries the buyer's terms (#89).

![RFQ History: the round-1 RFQ is Converted, 2 recipients, 2 responses](01-rfq-history.jpg)

### 2. Supplier replies arrive by email

Each supplier replied from Gmail (plus-address aliases, see `../README.md` § Mailboxes) with an
Arabic PDF quote. The email-ingestion worker stores the attachment (Arabic file names, #90), matches
the reply to the RFQ (#84) and queues extraction.

### 3. Extraction, review and authorization

Azure Document Intelligence reads each PDF. Dates in DD/MM/YYYY (#96), right-to-left tables read row by
row (#100). Both quotes needed a human check of a low-confidence supplier name and were then
authorized (#104). Totals reconcile: النور 56,425; الأمانة 56,925 including 250 delivery.

After authorization the quotes no longer appear in the Quotation Inbox (it lists open review tasks
only), so there is no screen listing received quotes — see "Open issues".

### 4. Match products

The 10 quote lines (5 per supplier) were confirmed against the catalogue in Match Resolution.
Exact-name lines can now be confirmed in bulk (#109).

### 5. Compare the responses

`RFQ History → (row) → RFQ Responses` shows each supplier's lines with per-pack prices. النور is
cheaper overall; الأمانة is cheaper on rice, sugar and lentils — the case basket split is for.

![RFQ Responses: النور, total 56,425](02-rfq-compare-al-nour.jpg)

![RFQ Responses: الأمانة](03-rfq-compare-al-amana.jpg)

### 6. Prepare and submit the purchase request

Choose the branch (فرع المعادي), then **Prepare Request** on النور's card. The draft request carries
the quoted lines, priced per pack, estimated total **EGP 56,425** (#110; before the fix it showed
6,135.58). Choose the cost centre (المطبخ — المعادي) and **Submit Request**.

![Prepared request: per-pack prices, EGP 56,425](04-request-prepared.jpg)

### 7. Approve

The request is routed to the owner (no approval rule set, so owner fallback). Approve from the
Approval Queue (web). The phone approval is tested separately.

![Approval Queue: within budget, 5 lines](05-approval-queue.jpg)

![Request approved; Create purchase order available](06-request-approved.jpg)

### 8. Create the purchase order

**Create purchase order** pre-fills the supplier (النور), order number (PO-000001), per-pack
quantities and prices and canonical base units (#110, #112). Set the expected delivery date and
create. The PO is a draft until submitted; ProcurePilot never writes back to suppliers or accounting.

![PO-000001: lines, total EGP 56,425](07-po-lines.jpg)

![PO-000001: evidence actions and timeline](08-po-actions.jpg)

## Not yet run in round 1

- Basket split across النور and الأمانة (optimiser deployed on hosted 2026-10-17, #108).
- Phone approval (mobile build at 390×844).
- Savings ledger entry for this PO.

## Open issues seen on these screens

Being fixed in the "Fix on-camera label gaps from the round-1 PO run" session:

- PO lines show the per-pack price as per base unit ("EGP 940.00 / kilogram" is the price of a
  25 kg sack).
- English "(pack of 25 kilogram)" is appended to Arabic line descriptions.
- Quantities shown as "50.000000" on RFQ Responses.
- The new-request button on Purchase Requests is labelled "Save Draft".
- Basket split with no matching offers shows a raw validation error.
- The cost-centre list is not filtered by branch.

Not yet raised:

- No screen lists received quotations once their review is done.
- The request page still offers "Create purchase order" after PO-000001 exists.
- "Remaining budget" stays at EGP 380,000 after approving and ordering EGP 56,425.
