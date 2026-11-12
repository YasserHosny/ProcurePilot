# ProcurePilot Function Business Value

> Business impact, user journey impact, and value proof for each major ProcurePilot function.
> Last updated: 7 Sep 2026.

---

## Value Chain Summary

ProcurePilot's business value is not one isolated screen. It is the compounding value chain:

`fragmented supplier data -> trusted extracted data -> matched products -> normalised landed costs -> better decisions -> captured outcomes -> verified savings`

Each function either improves trust in the data, improves the purchasing decision, reduces operational work, controls spend before it happens, or proves the financial outcome after the fact.

For most ProcurePilot functions, the revenue effect is indirect but material: lower input costs protect gross margin, faster decisions reduce stock-out risk, better supplier leverage improves cash flow, and verified savings free money that can be reinvested into growth. The product should describe this honestly as margin and revenue protection, not as automatic revenue creation.

| Function | User value | Business and revenue value | Proof signal |
|---|---|---|---|
| Catalogue and suppliers | Clean buying vocabulary | Comparable spend and supplier leverage | Active catalogue coverage, supplier completeness |
| Quotation upload | Removes manual retyping | Faster price capture, fewer missed quotes | Upload-to-review time, extraction success rate |
| Quotation review | Human validates AI output | Bad data does not become bad purchasing | Correction rate, unresolved low-confidence count |
| Matching | Links supplier wording to products | Like-for-like comparison becomes possible | Auto-match precision, queue resolution time |
| Normalisation and landed cost | Converts packs, VAT, fees, discounts | Stops false cheap prices and margin leakage | Replayable landed-cost calculations |
| Smart Compare | Shows best offer with evidence | Lower purchasing cost and better negotiation | Accepted recommendations, cost avoided |
| Basket split | Allocates basket across suppliers | Reduces total landed cost across orders | Solver saving vs single-supplier baseline |
| Alerts | Surfaces expiring or changing conditions | Avoids price shocks and emergency buying | Alert action rate, prevented expiries |
| Savings ledger | Records actual outcome | Turns savings from claims into audit proof | Verified savings per month |
| Requests and approvals | Controls demand and spend | Prevents unauthorized or over-budget purchasing | Approval cycle time, budget exception rate |

---

## 1. Catalogue and Supplier Master Data

### User Pain Solved

Small businesses usually describe the same item many ways: supplier wording, internal nicknames, branch shorthand, pack labels, and invoice names. That makes it hard for a buyer to know whether two prices refer to the same thing.

### Journey Impact

The catalogue gives the buyer a stable product identity and base unit. Supplier profiles add payment terms, lead time, delivery fees, minimum order value, and status. This means later screens can compare the real commercial offer, not just a copied line from a supplier file.

### Business and Revenue Impact

- Reduces duplicate products and fragmented spend.
- Enables supplier negotiation because volume is grouped correctly.
- Makes branch-level and supplier-level reporting credible.
- Prevents "cheap" offers from winning when the pack, delivery fee, or terms make them more expensive.

### KPIs

- Catalogue coverage of recurring spend.
- Percentage of products with GTIN, base unit, and pack definition.
- Supplier records with payment terms, lead time, and fees completed.
- Duplicate or ambiguous product rate.

---

## 2. Quotation Upload

### User Pain Solved

Buyers receive quotes in PDFs, images, spreadsheets, emails, and supplier-specific formats. Manually entering these quotes is slow, inconsistent, and easy to postpone until the information is already stale.

### Journey Impact

Upload turns supplier documents into structured quotation records. The buyer can capture prices as they arrive instead of waiting for a spreadsheet-cleanup task.

### Business and Revenue Impact

- Shortens the time from receiving a quote to using it in a decision.
- Increases the number of supplier offers considered.
- Reduces missed discounts or expiring prices.
- Creates a source document trail for later audit and supplier challenge.

### KPIs

- Upload-to-extraction completion time.
- Number of supplier quotes captured per cycle.
- Percentage of uploaded documents reaching review.
- Manual data-entry hours avoided.

---

## 3. Quotation Review

### User Pain Solved

AI extraction is useful only if users can see where it might be wrong. Buyers need a fast way to inspect low-confidence fields, arithmetic mismatches, and source evidence without leaving the workflow.

### Journey Impact

The review screen turns AI output into trusted commercial data. The reviewer checks source evidence, corrects extracted values, confirms suppliers, resolves low-confidence flags, and authorizes the quotation before it can influence matching and comparisons.

### Business and Revenue Impact

- Prevents incorrect totals, dates, suppliers, or prices from driving purchase decisions.
- Protects trust in the recommendation engine.
- Reduces disputes because every correction is tied to the source document and reviewer.
- Creates training data that improves future extraction and matching quality.

### KPIs

- Review queue age and throughput.
- Low-confidence fields resolved per quotation.
- Arithmetic mismatch rate.
- Correction rate by field and supplier.
- Percentage of quotations authorized without rework.

---

## 4. Matching

### User Pain Solved

Supplier wording rarely matches the internal catalogue exactly. Without matching, a buyer cannot know whether "A4 Copy Paper 80gsm", "copy paper ream", and "office paper 5 pack" are equivalent.

### Journey Impact

Matching routes uncertain lines to a human only when needed. The reviewer can choose the same product, a different pack size, a variant, a compatible alternative, or create a new product. Confirmed decisions teach aliases so repeated supplier wording becomes automatic next time.

### Business and Revenue Impact

- Unlocks like-for-like comparison across suppliers.
- Reduces repeated manual mapping work.
- Prevents fake savings caused by comparing different products.
- Builds a tenant-specific purchasing knowledge base over time.

### KPIs

- Auto-match precision at threshold.
- Percentage of lines auto-accepted.
- Match queue volume and age.
- Repeat supplier wording resolved automatically.
- New product creation rate from matching.

---

## 5. Normalisation and Landed Cost

### User Pain Solved

Unit prices are misleading when suppliers quote different pack sizes, VAT treatments, delivery fees, discounts, and minimum order quantities. The buyer needs the true cost of buying the required quantity.

### Journey Impact

Normalisation converts each offer to a shared base unit and landed-cost calculation. The result is replayable and evidence-backed, so the same inputs produce the same answer later.

### Business and Revenue Impact

- Reveals the true cheapest supplier, not the visually cheapest unit price.
- Protects gross margin by including fees, tax, discounts, and pack rules.
- Supports supplier negotiation with defensible calculations.
- Makes savings credible because the baseline and actual cost use the same rule set.

### KPIs

- Landed-cost calculation coverage.
- Difference between raw unit-price winner and landed-cost winner.
- Replayed calculation match rate.
- Margin leakage detected through fees, VAT, or pack-size differences.

---

## 6. Smart Compare

### User Pain Solved

Buyers often compare offers manually in spreadsheets and still miss expiry dates, supplier risks, or hidden costs. They need a ranked recommendation with the reasons visible.

### Journey Impact

Smart Compare lets the buyer select a product and quantity, then see comparable supplier offers, total landed cost, validity, risk, and recommendation evidence. The next step is built in: record the purchase outcome.

### Business and Revenue Impact

- Lowers recurring purchasing cost.
- Speeds up buying decisions without removing human authority.
- Improves negotiation because alternatives and historical context are visible.
- Reduces over-reliance on familiar suppliers.

### KPIs

- Recommendation acceptance rate.
- Average savings or cost avoidance per comparison.
- Time from compare screen open to decision.
- Share of purchases using evidence-backed comparison.

---

## 7. Product Price Intelligence

### User Pain Solved

Buyers often do not know whether today's offer is high, low, or normal because purchase memory lives in emails, invoices, and staff memory.

### Journey Impact

Product Price Intelligence shows historical landed-cost context for a selected product, supplier, and time window. It helps the user understand price drift before making or challenging a buying decision.

### Business and Revenue Impact

- Makes supplier price increases visible.
- Gives buyers stronger evidence in negotiation.
- Helps owners spot inflation, supplier drift, or branch-level leakage.
- Supports timing decisions when prices are volatile.

### KPIs

- Products with usable price history.
- Detected price swing events.
- Negotiated reductions after historical evidence is shown.
- Supplier price drift by category.

---

## 8. Basket Split

### User Pain Solved

The cheapest supplier for one product may not be the cheapest supplier for a whole basket after delivery fees, minimum order values, and discounts. Manual optimisation is slow and error-prone.

### Journey Impact

Basket Split lets the user choose two suppliers and a basket, then calculates an allocation that minimizes total landed cost within the current constraints.

### Business and Revenue Impact

- Reduces total order cost when no single supplier is best for all items.
- Helps buyers exploit supplier strengths without manual spreadsheet modelling.
- Makes delivery-fee and minimum-order tradeoffs explicit.
- Prevents small line-item wins from hiding basket-level losses.

### KPIs

- Basket saving versus best single-supplier baseline.
- Number of baskets with feasible split savings.
- Solver result acceptance rate.
- Average delivery-fee leakage avoided.

---

## 9. Alerts

### User Pain Solved

Commercial conditions change quietly: prices expire, suppliers stop quoting, and costs swing. Users need a focused inbox for actions, not another dashboard to watch.

### Journey Impact

Alerts direct the user to the next action: compare again, review a supplier, inspect product intelligence, renew a quotation, or investigate a price change.

### Business and Revenue Impact

- Avoids expired-price surprises.
- Reduces emergency purchasing.
- Detects supplier dependency and missing offers.
- Helps buyers act before price changes become realized cost.

### KPIs

- Alert action rate.
- Expired offers prevented.
- Price swings reviewed before purchase.
- Emergency purchases reduced.

---

## 10. Savings Ledger and Outcome Capture

### User Pain Solved

Savings are often claimed in spreadsheets but hard to defend. Owners need proof that a recommendation actually changed a purchase outcome.

### Journey Impact

Outcome Capture records what was ordered, delivered, and paid. The Savings Ledger compares that outcome to a historical baseline and keeps the evidence chain from quotation to match to offer to purchase to saving.

### Business and Revenue Impact

- Converts procurement improvement into auditable financial proof.
- Supports management reporting, investor/customer success stories, and supplier negotiations.
- Prevents inflated savings claims by requiring evidence and verification.
- Creates the north-star metric: verified savings and cost avoidance per active business per month.

### KPIs

- Verified savings per month.
- Pending vs verified savings count.
- Savings by supplier, branch, category, and buyer.
- Evidence completeness rate.
- Exported reports generated.

---

## 11. Requests and Approvals

### User Pain Solved

When purchasing starts in informal messages, managers lose control over who requested what, which branch needs it, whether budget exists, and whether the purchase was approved.

### Journey Impact

Purchase Requests capture demand before ordering. Approvals route spend to the right decision maker, with branch, cost centre, estimated value, budget status, and eventual delivery outcome connected to the same record.

### Business and Revenue Impact

- Controls spend before money leaves the business.
- Reduces unauthorized purchases and duplicate buying.
- Speeds approval decisions with context in one place.
- Creates a clean bridge from demand to order to delivery to verified saving.

### KPIs

- Request-to-approval cycle time.
- Percentage of spend originating from approved requests.
- Budget warning and exception rate.
- Withdrawn/rejected/request-change rate.
- Delivery confirmation completion rate.

---

## 12. Team, Roles, Settings, and Tenant Isolation

### User Pain Solved

Owners need confidence that each person sees and changes only what they should, and that one business's supplier prices never leak into another business.

### Journey Impact

Team Management controls who belongs to the workspace and what role they have. Settings define branches, cost centres, and budgets. Tenant isolation keeps each workspace's commercial data separate by construction.

### Business and Revenue Impact

- Makes the product safe for real supplier pricing and purchase history.
- Supports delegation without losing control.
- Enables branch and cost-centre accountability.
- Reduces adoption friction because owners can invite staff into clear roles.

### KPIs

- Active users by role.
- Invitation acceptance rate.
- Requests and savings grouped by branch/cost centre.
- Zero cross-tenant isolation failures.
- Audit events for role and membership changes.

---

## How to Use This Document

- Product and strategy: use it to explain why each function exists.
- Sales and onboarding: use it to connect screens to business outcomes.
- UX: use it to ensure every page explains or implies its value.
- Engineering: use it to preserve the value chain when prioritising fixes.
- Customer success: use it to map adoption metrics to realized business benefit.
