# General demo workspace — dataset plan (draft for approval, 2026-11-19)

Why: ProcurePilot is now shown as a purchasing assistant for any business (MD-22), and new posts are English
only (MD-23). Posts A-07, A-08 and A-09 (25 Nov, 30 Nov, 4 Dec) need real English screens with no restaurant
data. This workspace is also meant for the next general demo video. All names and numbers are fictional
demo data.

Built the same way as «مطاعم سند» and «Rawaq Restaurant Group» ([`../README.md`](../README.md),
[`../../gcc/setup/`](../../gcc/setup/)): Yasser signs up and signs in, then the setup script adds the data through
the API as the signed-in owner. Nothing touches the existing workspaces.

## 1. Workspace

| Item | Value |
|---|---|
| Company | **Nuvara Group**: a fictional Egyptian company with a head office and a warehouse. It could be any business. The name is to be checked against real Egyptian companies before the first post |
| Language | English (workspace and owner interface) |
| Currency and tax | **EGP**, Egypt VAT 14%. Quotes state prices **including** VAT, as in the Sanad rounds |
| Inbound email | enabled before the first RFQ (`/tenants/email-config/enable`), or replies are never matched |

## 2. Branches, cost centres and monthly budgets (from 1 Nov 2026)

| Branch | Cost centre (code) | Monthly budget (EGP) |
|---|---|---|
| Head Office, New Cairo | Administration (ADM-HO) | 200,000 |
| Head Office, New Cairo | IT (IT-HO) | 250,000 |
| Head Office, New Cairo | Maintenance (MNT-HO) | 150,000 |
| Warehouse, 6th of October City | Warehouse Operations (WH-OCT) | 100,000 |

## 3. Products (30, in packs; approximate EGP prices incl. VAT, estimates)

| # | Product | Base unit × pack | ~EGP / pack |
|---|---|---|---|
| | **Office supplies** | | |
| 1 | A4 Copy Paper 80 gsm (box of 5 reams) | each × 5 | 1,300 |
| 2 | Ballpoint Pens, Blue (box of 50) | each × 50 | 250 |
| 3 | Laser Toner Cartridge, Black (3,000 pages) | each × 1 | 2,400 |
| 4 | Lever Arch Files (box of 10) | each × 10 | 650 |
| 5 | Sticky Notes 76 × 76 mm (pack of 12) | each × 12 | 220 |
| 6 | Whiteboard Markers (box of 12) | each × 12 | 300 |
| | **Cleaning** | | |
| 7 | Floor Cleaner (4 L) | litre × 4 | 160 |
| 8 | Liquid Hand Soap (5 L) | litre × 5 | 220 |
| 9 | Bleach (20 L) | litre × 20 | 300 |
| 10 | Paper Towel Rolls (carton of 12) | each × 12 | 480 |
| 11 | Toilet Tissue (carton of 48 rolls) | each × 48 | 900 |
| 12 | Garbage Bags 120 L (carton of 100) | each × 100 | 550 |
| 13 | Microfibre Cloths (pack of 10) | each × 10 | 200 |
| | **Maintenance spares** | | |
| 14 | LED Tube 18 W, 120 cm (box of 25) | each × 25 | 2,250 |
| 15 | Circuit Breaker 32 A | each × 1 | 350 |
| 16 | PVC Drain Pipe 4 in, 6 m | each × 1 | 450 |
| 17 | Interior Wall Paint, White (18 L) | litre × 18 | 2,800 |
| 18 | Silicone Sealant (box of 24 tubes) | each × 24 | 1,450 |
| 19 | Air-Conditioner Filters (pack of 4) | each × 4 | 600 |
| | **IT equipment** | | |
| 20 | USB Keyboard and Mouse Set | each × 1 | 750 |
| 21 | 24-inch Monitor | each × 1 | 7,500 |
| 22 | Cat6 Network Cable (305 m box) | each × 1 | 4,200 |
| 23 | Wireless Router | each × 1 | 2,900 |
| 24 | 1 TB External SSD | each × 1 | 4,800 |
| 25 | UPS 1,500 VA | each × 1 | 6,500 |
| | **Warehouse** | | |
| 26 | Stretch Film 50 cm (box of 6 rolls) | each × 6 | 1,100 |
| 27 | Packing Tape 48 mm (carton of 36) | each × 36 | 900 |
| 28 | Double-Wall Cartons 60 × 40 × 40 cm (bundle of 25) | each × 25 | 1,250 |
| 29 | Wooden Pallet 120 × 100 cm | each × 1 | 650 |
| 30 | Work Gloves (pack of 12 pairs) | each × 12 | 420 |

No brand names on products, so no real brand appears in the posts.

## 4. Suppliers (fictional, each address is our own Gmail plus-alias `+pp-gen-<key>`)

| Supplier | Sells | Terms | Lead time |
|---|---|---|---|
| Arkan Office Supplies | office supplies, IT accessories | Net 30 days | 2 days |
| Safwa Hygiene Supplies | cleaning | Net 30 days | 1 day |
| Bayan General Trading | office, cleaning, warehouse | Net 30 days | 3 days |
| Delta Technical Spares | maintenance spares | Net 15 days | 2 days |
| NileByte Distribution | IT equipment | Net 30 days | 3 days |

Each alias is set up as a Gmail "Send mail as" address, as for the earlier suppliers, so replies come from the
right supplier. No mail goes to anyone outside our own mailbox.

## 5. People

| Role | Account | Notes |
|---|---|---|
| Owner and approver | `+pp-gen-owner` | Yasser signs up the workspace with it and approves on the phone |
| Buyer | `+pp-gen-buyer` | invited by the owner; Yasser accepts the invite and sets the password |

Claude does not create accounts or type passwords. The owner's email shows on some screens (for example
"Uploaded by" and the approvals list), so it is masked in every published image.

## 6. Rounds

**Round D (dry, off camera)** sets the "last PO price" that savings are measured against. A new workspace has no
price history, so without it every saving would read 0. RFQ for the 5 lines below to Bayan only → one PDF quote
→ request → approval → PO at: paper 1,350 · toner 2,500 · floor cleaner 170 · paper towels 500 · tape 950
(EGP 59,280, Administration).

**Round E (the one in the screenshots).** One RFQ from the buyer for the Administration cost centre, needed by
27 Nov, to **4 suppliers** (Arkan, Safwa, Bayan, Delta). Delta does not reply.

| Line | Qty (packs) | Arkan (PDF) | Safwa (WhatsApp photo) | Bayan (PDF) |
|---|---|---|---|---|
| A4 Copy Paper (box of 5 reams) | 20 | **1,280** | 1,340 | 1,310 |
| Laser Toner Cartridge | 6 | **2,350** | 2,480 | 2,420 |
| Floor Cleaner (4 L) | 24 | 175 | **150** | 160 |
| Paper Towel Rolls (carton of 12) | 15 | 510 | **455** | 470 |
| Packing Tape (carton of 36) | 6 | 940 | 960 | **890** |
| **Total (EGP, incl. VAT)** | | 57,190 | 57,865 | **56,950** |

- Review and authorise the three quotes. Smart Compare shows the cheapest supplier per line.
- **Basket split:** Arkan paper and toner 39,700 · Safwa cleaner and towels 10,425 · Bayan tape 5,340 =
  **EGP 55,465**, which saves **EGP 1,485** against the best single supplier (Bayan, 56,950).
- Prepare the 3 requests from the split. The approver sees them as one split with the Administration budget:
  200,000 − 59,280 (round D) = 140,720 remaining before this split, 85,255 after it.
- Approve on the phone → 3 POs → record the outcomes → the owner verifies the savings. Against round D's PO
  prices, round E saves paper 1,400 + toner 900 + cleaner 480 + towels 675 + tape 360 = **EGP 3,815**.
- The guardrail stays **off** for this workspace: while a guardrail is on, the split cannot be reached
  (finding W2, PPS-148).

## 7. Screenshots (1920 × 1080, English UI, demo data, owner email masked)

| Post | Screens |
|---|---|
| A-07 | basket split result: 3 suppliers, EGP 55,465, saves EGP 1,485 |
| A-08 | RFQ create with 4 suppliers chosen · "RFQ sent. Suppliers emailed: 4" |
| A-09 | the split reaching the approver with the remaining Administration budget · Smart Compare |

Saved to `marketing/ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts/images/source-general/`.

## What Yasser does

1. Approve or change this plan (name, prices, suppliers).
2. Add the 7 Gmail send-as aliases (5 suppliers, owner, buyer).
3. Mint a platform invitation (`pnpm db:seed` with the hosted `DATABASE_URL`), then sign up "Nuvara Group" on
   procurepilot.iron-sys.com/signup with `+pp-gen-owner` (Egypt, EGP, Egypt VAT), in Claude's browser pane.
4. Accept the buyer invite. Approve each supplier reply email before it is sent (same as the earlier rounds).
