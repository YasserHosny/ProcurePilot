# Competitor landscape — summary

**Generated**: 2026-10-28 · **Depth**: quick scan · **Scope**: multi-branch F&B purchasing, Egypt first, then the GCC

Profiles: [Supy](supy.md) · [Foodics](foodics.md) · [Suplyd](suplyd.md) · [MarketMan](marketman.md) · [Apicbase](apicbase.md).
Choco (choco.com) was scraped and then dropped. Its 2026 site sells only to food *distributors* (order capture, e-commerce, CRM), and its markets are DE/ES/FR/US/UK. Raw data is in `raw/choco/`.

SEO and traffic metrics are **not included**: no SEO-data connector was attached. Review-site ratings were not pulled either.

## Overview

The pages checked show no competitor selling what ProcurePilot sells: collecting competing quotes from a buyer's own suppliers, in whatever format they arrive, and turning them into a comparable decision with proven savings. The field splits three ways:
1. **Back-of-house suites** (Supy, MarketMan, Apicbase): inventory, recipes and COGS, with POs and invoice AI. Prices come from a maintained price list or from invoices *after* purchase.
2. **POS ecosystems** (Foodics): purchasing is a bundled feature, and sourcing is partnered out (Suplyd in Egypt).
3. **Marketplaces** (Suplyd): the platform *is* the supplier. Convenient, but the buyer compares within one catalogue.

## Comparison

| | Supy | Foodics | Suplyd | MarketMan | Apicbase |
|---|---|---|---|---|---|
| Category | BoH suite | POS + ecosystem | Marketplace | BoH suite | Enterprise BoH |
| MENA presence | Strong (GCC customers, AR site) | Strong (KSA HQ, EG since 2020) | Egypt only | Not observed | Not observed |
| Arabic site | Yes | Yes | Not observed | No | No |
| Public price | from $250/mo | 228–765/mo (KSA, SAR assumed) | n/a (marketplace) | $249–449+/mo | Sales-led, min. 5 outlets |
| RFQ / quote comparison | Not observed | Not observed | n/a | Not observed | Not observed |
| Invoice AI | Yes | Not observed | n/a | Yes | Invoice matching |
| Scale claim | 3,000–3,500 restaurants | 40,000+ restaurants | 5,000+ restaurants (EG) | 15,000+ | 4,000+ sites |

## Positioning map

```
                 Buyer-side decision (which supplier, what price)
                                  ▲
                                  │      ● ProcurePilot (target position)
                                  │
   Local / Arabic ◀───────────────┼───────────────▶ Global / English
          ● Suplyd (seller-side)  │
          ● Foodics               │
          ● Supy                  │  ● MarketMan   ● Apicbase
                                  ▼
                 Operations record (stock, recipes, POs, POS)
```

## Key takeaways

1. **The quote-to-decision step is open.** None of the five shows RFQs or quote comparison on the pages checked. Confirm in a Supy demo before using it publicly.
2. **Supy is the reference competitor in the GCC.** It already has approvals, permissions, Arabic and WhatsApp PO delivery, so it's one module away from overlapping with us. Position as complementary ("Supy runs your stock; ProcurePilot picks your supplier") until proven otherwise.
3. **Suplyd is the Egypt objection.** Answer: it's one supplier among the ones you compare. Our ICP (multi-branch groups with their own negotiated suppliers) is not its long tail.
4. **Foodics is a channel, not an enemy.** Its POS sits in most target accounts. A Foodics integration or App Marketplace listing addresses the "non-Square POS" fit gap and puts ProcurePilot where buyers already are.
5. **Price anchor:** back-of-house SaaS lists at about $250 a month per operator (Supy, MarketMan). A ProcurePilot price around that level is easy to justify if one sourcing round saves more than it costs.

## Gaps and opportunities

- **Messaging**: everyone talks about *food-cost %* and *variance*. Nobody claims "savings per purchasing decision, with the receipt". Own that phrase.
- **Format**: Egyptian quotes arrive as WhatsApp photos, PDFs and Arabic text. Nobody shows extraction of *quotes* (invoice AI only). Lead demos with an Arabic photo quote.
- **Trend**: Apicbase markets MCP / "chat with your data". Keep it as a later differentiator for the savings ledger, not a pilot priority.

## Next steps

- `sales-enablement`: battlecards for Supy, Suplyd and Foodics from these profiles
- Verify the "not observed" gaps in a live Supy demo before any public comparison claim
- Optional deep pass: G2 and Capterra reviews for Supy and MarketMan, once an SEO or scrape connector is available
