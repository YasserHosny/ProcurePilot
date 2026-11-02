# Positioning framework

How positioning is developed for a product (or for Iron Systems itself). Output goes into
`<Product>/knowledge/product-positioning.md`. Upstream skill: `product-marketing` (positioning and context);
supporting skills: `customer-research`, `competitor-profiling`, `marketing-psychology`.

## Inputs (must exist first)

- Product profile with verified capabilities (`product-profile.md`)
- Audience hypotheses or evidence (`target-audience.md`)
- Competitive alternatives with sources (`research/competitor-analysis/<id>/`)

## Steps

1. **Competitive alternatives.** What would the buyer do if this product did not exist? Include "spreadsheets and email" and "do nothing".
2. **Unique capabilities.** What the product can do that the alternatives can't, from the verified feature list only.
3. **Value.** What each unique capability lets the buyer achieve. Tie each value to a proof point or mark it a hypothesis.
4. **Best-fit customers.** Who cares most about that value. Name the disqualifiers.
5. **Market category.** The frame that makes the value obvious. Prefer a category buyers already search for; record search evidence if available.
6. **Relevant trends** (optional). Only with a cited source.
7. **Statement and pillars.** Write the positioning statement, then three message pillars, each with proof ids.
8. **Stress test.** Run `campaign-review` on the draft: unsupported claims, vague words, does it fit the brand voice?
9. **Approval.** Present as a draft with hypotheses marked. Record the decision in the file's approval table. Only `approved` positioning feeds campaigns.

## Company vs product positioning

| Level | Today | Where |
|---|---|---|
| Iron Systems | Engineering-first software house; AI solutions, custom software, automation, integration. Website and LinkedIn copy approved for their channels | `knowledge/company/company-profile.md` |
| Product | Defined per product after discovery | `<Product>/knowledge/product-positioning.md` |

Product positioning may borrow company credibility ("built by Iron Systems, an engineering-first software house")
but must not borrow claims the product can't support.
