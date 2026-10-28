---
product_id: procurepilot
last_reviewed: 2026-10-27
---

# ProcurePilot: target audience

Company-wide personas are in `knowledge/audience/buyer-personas.md`. This file narrows them to this product.
Label every row **V / I / H / ?** (see `product-profile.md`). Personas built without customer evidence are **H**.

**State of evidence (2026-10-27):** no customer interviews, pilot feedback or buyer quotes exist in any source
inspected. "V" below means *the product team has chosen this target* (documented), not that buyers confirmed it.

## Ideal customer profile

| Attribute | Value | Label | Evidence |
|---|---|---|---|
| Industry / segment | Multi-location F&B: restaurant groups first; the plan also names retail and hospitality chains, pharmacy chains and distributors | V (team's chosen wedge); fit with buyers H | SRC-012 ("Starting wedge"), SRC-017 landing eyebrow |
| Company size | 2+ branches (or 1 branch with a central kitchen/warehouse); 5+ suppliers; at least weekly orders | V (pilot qualification criteria) | SRC-012 |
| Region and language | Egypt first (landing, first-customer plan). Saudi Arabia chosen as the first GCC market (demo workspace and video ready). An Ireland/eurozone English demo also exists | V (documented choices); priority between them ? | SRC-012, SRC-014, SRC-015 |
| Trigger events (why now) | Opening more branches; supplier price swings; owner losing visibility of what branches pay | H | None |
| Systems they already run | WhatsApp, phone, Excel for purchasing; Odoo, local software or Excel for accounting (Egypt) | I (team's market read) | SRC-012 fit-gap table |
| Disqualifiers | Single branch without central purchasing; fewer than 5 suppliers; no named decision maker; needs WhatsApp API, POS other than Square or ERP integration on day one; KWD/BHD/OMR currencies; real customer data before the production environment exists | V (from documented gaps and qualification) | SRC-012, SRC-018 |

## Buying group

| Role | Persona id | Cares about | Main worry | What we promise them | Label |
|---|---|---|---|---|---|
| User | PP-buyer (buyer / operations officer) | Less copying quotes by hand; fair comparison | Learning a new tool; supplier reaction | Quotes read for you, compared pack for pack, every price traced to its quote | H |
| Champion | PP-ops (operations or purchasing manager) | Control across branches | Being blamed if the tool gets a number wrong | A person reviews and approves every step; low-confidence lines go to review | H |
| Decision maker | PP-owner (owner / GM) | Verified savings, spend control | Paying for savings that aren't real | Savings count only once verified against evidence | H (PRD names this persona) |
| Financial buyer | PP-owner or finance | Budget per branch and cost centre | Overspend | Approvals checked against remaining budget | H |
| Technical influencer | Rare in this ICP (no in-house IT assumed) | Data safety | Supplier prices leaking | Data isolation per workspace; data export and deletion on exit | H |
| Branch manager (user, mobile) | PP-branch | Ordering without paperwork | Delays in approval | Requests and approvals on the phone | H |

## Jobs to be done and switching forces

| Force | Notes | Label |
|---|---|---|
| Push (frustration with today) | Quotes scattered across WhatsApp, phone and Excel; copying errors; can't compare pack sizes; no record of what was saved | H (team's framing; demo opening dramatises it) |
| Pull (what attracts them) | One place for quotes; landed-cost comparison; phone approvals; verified savings; Arabic-first UI | H |
| Habit (what keeps them stuck) | Suppliers and staff already use WhatsApp; personal supplier relationships; "it works well enough" | H |
| Anxiety (what worries them about switching) | Supplier prices visible to an outside company; extraction mistakes; staff time to set up; a new tool from a new vendor with no customers yet | H |

## Customer language (verbatim only, with source)

| Quote | Speaker role | Source and date | Consent to use publicly? |
|---|---|---|---|
| *None collected yet.* The product's Arabic word for saving was changed to «توفير» after the owner noted Egyptian buyers say «توفير» / «توفيرات», not «وفر» (2026-10-25) | Owner (not a customer) | SRC-013 P-29 | n/a. Owner's language note, not a customer quote |

## Where they spend attention (organic channels)

| Channel | Evidence that this audience is there | Label |
|---|---|---|
| WhatsApp (1:1, groups, status) | GTM plan's primary channel; pilot-invite cards made for WhatsApp | I (team's plan). WhatsApp outreach is outside this Marketing OS's channel list |
| Facebook groups (F&B owners, SME founders in Egypt) | Named in the GTM plan | H |
| LinkedIn (owners, operations managers of chains) | Named in the GTM plan (manual DMs, no ads) | H |
| Instagram / Reels, YouTube | 9:16 and 16:9 demo cuts exist for these | H |
| In person (trade associations, supplier expos) | Named in the GTM plan | H (offline; outside the Marketing OS channel list) |
