# ProcurePilot — AI-Ready Product Context

## 1. Purpose of This Document

This Markdown file is a structured context package for another AI model.

It can be used for:

- Product strategy
- Feature prioritisation
- UX and workflow design
- Software architecture
- AI capability planning
- Market validation
- Go-to-market planning
- Business-model analysis
- Roadmap creation
- Requirements and user-story generation
- Technical feasibility assessment

This document represents the **latest clarified version** of the ProcurePilot concept.

For a function-by-function view of user value, business/revenue impact, and proof metrics, see
[Function Business Value](function-business-value.md).

---

## 2. Product Definition

### Product name

**ProcurePilot**

### Product category

AI-powered B2B procurement intelligence and purchasing operations platform for small businesses.

### Core product statement

> ProcurePilot converts fragmented quotations, supplier prices, invoices, stock signals, and purchasing history into normalised comparisons, recommended orders, approval-ready decisions, and verified savings.

### Core customer promise

> Reduce purchasing cost, avoid stock-outs, and make every supplier decision with evidence.

### What the product is not

ProcurePilot is **not** primarily:

- A consumer shopping application
- A generic price-comparison website
- A coupon or deals application
- A public supplier-review marketplace
- A marketplace seller repricing tool
- A full enterprise Source-to-Pay suite at launch
- A complex ERP replacement

### Main decisions supported

ProcurePilot helps a business decide:

- What should be purchased?
- When should it be purchased?
- From which supplier?
- In what quantity?
- At what total landed cost?
- Under which payment and delivery terms?
- Does the purchase require approval?
- What measurable saving or cost avoidance will result?

---

## 3. Strategic Positioning

### Recommended positioning

> An AI purchasing co-pilot and lightweight procurement operating system for small businesses.

### Main differentiators

1. Product and pack-size normalisation
2. Supplier quotation ingestion
3. Total landed-cost comparison
4. Purchase basket optimisation
5. AI buying recommendations
6. Supplier performance intelligence
7. Demand and reorder forecasting
8. Approval and budget workflows
9. Verified savings measurement
10. Support for fragmented local supplier channels such as PDF, email, Excel, and WhatsApp quotations

### Strategic moat

The long-term product moat is a structured purchasing graph linking:

- Products
- Product variants
- Units and pack sizes
- Suppliers
- Supplier offers
- Quotations
- Prices
- Delivery terms
- Payment terms
- Orders
- Stock signals
- Approval decisions
- Purchase outcomes
- Realised savings

---

## 4. Business Problem

Small businesses purchase repeatedly but often lack procurement systems, supplier analytics, and clean product data.

### 4.1 Fragmented purchasing

Prices and terms exist across:

- Websites
- Supplier catalogues
- Email
- WhatsApp
- PDF quotations
- Excel sheets
- Phone calls
- Paper invoices
- Marketplace pages

### 4.2 Incomparable offers

Supplier offers differ by:

- Pack size
- Product variant
- Quantity
- VAT treatment
- Delivery cost
- Minimum order value
- Quantity discount
- Payment terms
- Lead time
- Stock availability

### 4.3 No purchase memory

Businesses often cannot easily compare:

- Current price
- Last paid price
- Average paid price
- Contract price
- Best historical price
- Alternative supplier price

### 4.4 Weak timing decisions

Businesses may order:

- Too early
- Too late
- Too much
- Too little
- During an unfavourable price period
- Through emergency purchasing

### 4.5 Supplier dependence

Businesses often rely on familiar suppliers without continuously evaluating:

- Market alternatives
- Price drift
- Delivery performance
- Product quality
- Payment flexibility
- Concentration risk

### 4.6 Invisible procurement leakage

Common leakage sources include:

- Weak price comparison
- Emergency orders
- Incorrect quantities
- Missed discounts
- Supplier concentration
- Duplicate spend
- Unapproved purchasing
- Branch-to-branch price variance
- Wrong package selection
- Delivery-fee leakage

---

## 5. Target Customers

### Recommended initial customer segments

1. Cleaning and hygiene buyers
2. Office supply buyers
3. Cafés and restaurants buying packaging and consumables
4. Salons and clinics buying recurring consumables
5. Small retailers replenishing standard inventory
6. Multi-branch small businesses
7. Small online sellers sourcing recurring merchandise

### Recommended initial wedge

**Cleaning, hygiene, office, and café consumables**

Reasons:

- Frequently reordered
- Relatively standardised
- Pack-size normalisation creates visible value
- Available through marketplaces and distributors
- Easier than fashion, fresh food, or industrial spare parts
- Savings can be measured quickly

---

## 6. Primary Personas

### 6.1 Owner or General Manager

Role:

- Economic buyer
- Final approver
- Performance reviewer

Goals:

- Reduce purchasing cost
- Control budgets
- Monitor supplier dependence
- View realised savings
- Identify branch variance
- Approve high-value purchases

### 6.2 Buyer or Operations Officer

Role:

- Daily power user

Goals:

- Collect quotations
- Compare suppliers
- Build baskets
- Create purchase requests
- Track delivery
- Resolve exceptions
- Maintain supplier information

### 6.3 Branch or Store Manager

Role:

- Demand owner

Goals:

- Request products
- Report low stock
- Specify required quantity
- Confirm receipt
- Report quality problems
- Stay within branch budget

---

## 7. Core End-to-End Journey

### Step 1 — Capture the need

The requirement may come from:

- Manual user request
- Low-stock signal
- Recurring schedule
- Forecast
- Branch request
- Historical purchase pattern

### Step 2 — Build the requirement

Required data may include:

- Product
- Product specification
- Quantity
- Required-by date
- Branch
- Department
- Budget
- Preferred supplier
- Approved substitutes

### Step 3 — Collect offers

Offers can come from:

- Supplier quotation
- Supplier catalogue
- Email
- PDF
- Excel
- Marketplace
- Website
- API
- Manual entry

### Step 4 — Normalise the offers

The platform resolves:

- Product identity
- Variant
- Brand
- Pack count
- Unit size
- Total quantity
- VAT
- Delivery cost
- Discounts
- Minimum order value
- Lead time
- Payment terms

### Step 5 — Recommend a purchase

The platform recommends:

- Best supplier
- Best split order
- Best quantity
- Best purchase time
- Best alternative product
- Lowest total landed cost
- Lowest-risk purchase option

### Step 6 — Approve and order

The system supports:

- Policy validation
- Approval routing
- Budget check
- Exception justification
- Purchase request
- Purchase order
- Supplier confirmation
- Audit history

### Step 7 — Measure the result

The platform records:

- Actual purchased quantity
- Actual supplier
- Actual paid cost
- Delivery performance
- Product quality
- Realised saving
- Cost avoidance
- Recommendation accuracy

---

## 8. Core Product Modules

### 8.1 Spend and Savings Dashboard

Functions:

- Monitored spend
- Potential saving
- Realised saving
- Avoided price increase
- Emergency-order count
- Supplier concentration
- Budget variance
- Branch variance
- Actions requiring attention

### 8.2 Business Catalogue

Functions:

- Normalised product master
- Product family
- Product variant
- Brand
- GTIN, EAN, UPC, or SKU
- Unit
- Pack size
- Total normalised quantity
- Preferred brand
- Approved alternative
- Branch usage
- Purchase history

### 8.3 Supplier Hub

Functions:

- Supplier profile
- Contact details
- Price history
- Lead time
- Fulfilment rate
- Payment terms
- Minimum order value
- Delivery fee
- Quality incidents
- Relationship notes
- Risk score
- Approved or blocked status

### 8.4 Quotation Inbox

Functions:

- Upload PDF
- Upload image
- Upload spreadsheet
- Forward email
- Import catalogue
- Extract line items
- Extract expiry date
- Extract VAT
- Extract delivery
- Extract payment terms
- Compare quotation versions

### 8.5 Smart Compare

Comparison criteria:

- Displayed price
- Unit price
- Total landed cost
- VAT
- Delivery
- Lead time
- Payment terms
- Supplier reliability
- Product-match confidence
- Stock availability
- Last paid price
- Historical average

### 8.6 Basket Optimiser

Functions:

- Compare one-supplier order
- Compare split order
- Apply delivery thresholds
- Apply minimum order values
- Apply quantity discounts
- Apply urgency constraints
- Apply supplier preference
- Apply risk tolerance
- Recommend order allocation

### 8.7 Purchase Requests and Approvals

Functions:

- Create request
- Assign branch
- Assign cost centre
- Check budget
- Route approval
- Apply threshold rules
- Record comments
- Record exception reason
- Maintain audit log

### 8.8 Stock and Reorder Signals

Inputs:

- Manual stock
- CSV
- POS
- Inventory system
- ERP
- Purchase history
- Sales history

Outputs:

- Reorder point
- Safety stock
- Suggested order date
- Suggested order quantity
- Stock-out risk
- Overstock risk

### 8.9 Reports and Integrations

Functions:

- Excel export
- PDF export
- Scheduled reports
- Accounting integration
- POS integration
- ERP integration
- Inventory integration
- Supplier API
- Partner API
- Email digest
- WhatsApp digest
- Webhook support

---

## 9. AI Capabilities

AI must be embedded in the data and decision flow rather than added as a decorative chatbot.

### 9.1 Product Matching

Purpose:

Match noisy supplier descriptions to the internal product catalogue.

Outputs:

- Same product
- Different pack size
- Different variant
- Compatible alternative
- Incorrect match
- Match-confidence score
- Human-review request

### 9.2 Document Intelligence

Inputs:

- Quotation PDF
- Invoice
- Receipt
- Product catalogue
- Spreadsheet
- Email
- Image

Extracted fields:

- Supplier
- Product
- SKU
- Quantity
- Unit
- Unit price
- VAT
- Delivery
- Discount
- Expiry date
- Payment terms
- Currency

### 9.3 Unit and Landed-Cost Normalisation

Calculation:

> Item cost + VAT + delivery + payment fees − discounts − cashback

Additional considerations:

- Minimum order
- Quantity tier
- Free-delivery threshold
- Lead time
- Payment terms
- Reliability
- Return policy

### 9.4 Supplier Recommendation

The recommendation balances:

- Cost
- Delivery
- Reliability
- Quality
- Supplier risk
- Payment terms
- Relationship
- Policy
- Budget
- Historical performance

### 9.5 Demand Forecasting

Outputs:

- Expected usage
- Reorder date
- Suggested order quantity
- Safety stock
- Seasonality
- Overstock risk
- Stock-out risk

### 9.6 Anomaly Detection

Detect:

- Price spike
- Duplicate invoice
- Abnormal quantity
- Contract variance
- False discount
- Incorrect currency
- Decimal error
- Delivery-cost anomaly
- Supplier price drift

### 9.7 Alternative Product Discovery

Recommend equivalent products based on:

- Specification
- Size
- Brand tier
- Availability
- Unit cost
- Quality constraint
- Historical usage

### 9.8 Negotiation Assistant

Generate evidence-based supplier negotiation points using:

- Historical price
- Volume
- Alternative suppliers
- Service performance
- Payment behaviour
- Market price
- Purchase frequency

### 9.9 Procurement Analyst

Example questions:

- Which supplier increased prices this month?
- Which products should be purchased this week?
- Where can the business save £2,000 next month?
- Which branch is paying more for the same product?
- Which quotations expire soon?
- Which products are below their six-month average?
- What supplier split produces the lowest total cost?

Requirements:

- Ground every answer in company data
- Link to source records
- Show calculations
- State confidence
- Avoid unsupported recommendations

---

## 10. AI Priority Ranking

Scores are illustrative product-planning assumptions.

| AI capability | Priority score |
|---|---:|
| Product matching | 97/100 |
| Document extraction | 94/100 |
| Landed-cost normalisation | 92/100 |
| Supplier recommendation | 88/100 |
| Anomaly detection | 84/100 |
| Forecasting | 78/100 |
| Negotiation assistant | 73/100 |
| Procurement analyst | 70/100 |

### Interpretation

Build first:

1. Product matching
2. Document extraction
3. Cost normalisation
4. Supplier recommendation

Build after sufficient data:

5. Anomaly detection
6. Forecasting
7. Negotiation assistant
8. Natural-language procurement analyst

---

## 11. Suggested User Experience

### 11.1 Executive Dashboard

Show:

- Potential monthly saving
- Realised saving
- Actions required
- Price increases
- Quotations expiring
- Products below target cost
- Supplier concentration
- Budget status

### 11.2 Quotation Compare

Show:

- Supplier
- Total cost
- Unit cost
- VAT
- Delivery
- Lead time
- Payment terms
- Reliability
- Match confidence
- AI recommendation

### 11.3 Product Intelligence

Show:

- Best landed cost
- Last paid price
- Average paid price
- 30-day change
- Price history
- Preferred supplier
- Reorder date
- Recommended quantity
- Approved alternatives

### 11.4 Approval Queue

Show:

- Request
- Branch
- Amount
- Budget
- Policy exception
- Recommended supplier
- Expected saving
- Required approver
- Approval history

### 11.5 Alerts Inbox

Every alert should include:

- Reason
- Financial impact
- Recommended action
- Validity period
- Confidence
- Risk
- Assign
- Snooze
- Dismiss
- Approve
- Purchase

---

## 12. Data Model

### Product

- Product ID
- Name
- Brand
- Family
- Variant
- Barcode
- Unit
- Pack count
- Unit size
- Normalised quantity
- Preferred status
- Substitute rules

### Supplier

- Supplier ID
- Name
- Contact
- Terms
- Lead time
- Reliability
- Minimum order
- Delivery fee
- Quality score
- Risk score

### Supplier Offer

- Supplier
- Product
- Quantity
- Unit price
- VAT
- Delivery
- Discount
- Currency
- Stock
- Lead time
- Expiry
- Payment terms

### Quotation

- Document ID
- Supplier
- Created date
- Expiry date
- Currency
- Extracted line items
- Extraction confidence
- Review status

### Purchase

- Product
- Supplier
- Quantity
- Paid price
- Branch
- Date
- Buyer
- Approval
- Delivery result
- Quality result

### Stock Signal

- Product
- Branch
- Current stock
- Average usage
- Reorder point
- Forecast
- Urgency

### Approval

- Request
- Approver
- Threshold
- Status
- Comments
- Exception reason
- Timestamp

### Outcome

- Recommendation
- Action taken
- Actual supplier
- Actual quantity
- Actual cost
- Realised saving
- Delivery outcome
- Quality outcome

---

## 13. Suggested System Architecture

### Data Sources

- Supplier quotations
- Invoices
- Receipts
- Marketplace data
- Supplier APIs
- POS
- Inventory systems
- ERP
- Accounting systems
- Email
- WhatsApp-exported files
- CSV and Excel

### Ingestion Layer

- Email forwarding
- File upload
- API connectors
- Crawlers
- Schedulers
- Validation queue
- Data-quality review

### AI and Data Layer

- OCR
- Document parser
- Product entity resolution
- Unit normaliser
- Price-history store
- Supplier graph
- Confidence scoring

### Decision Engine

- Landed-cost engine
- Basket optimiser
- Forecast service
- Policy engine
- Recommendation scorer
- Supplier-risk scorer

### Business Services

- Catalogue service
- Supplier service
- Quotation service
- Purchase-request service
- Approval service
- Order service
- Report service
- Alert service
- Subscription service

### Experience Layer

- Mobile application
- Web console
- Email digests
- WhatsApp digests
- Partner API
- Data-quality administration console

---

## 14. Business Model

### Pricing principle

Pricing should align with:

- Tracked spend
- Product count
- Supplier count
- User count
- Branch count
- Refresh frequency
- Automation level
- AI usage
- Integration depth

### Suggested plans

| Plan | Price | Main scope |
|---|---:|---|
| Free | £0 | 1 user, 20 products, 2 suppliers, manual uploads, monthly report |
| Starter | £39/month | 100 products, 5 suppliers, alerts, basic extraction, savings dashboard |
| Team | £99/month | 500 products, 10 users, approvals, branches, basket optimisation |
| Growth | £249/month | 2,000 products, integrations, advanced AI, API, custom policies |

### Other revenue opportunities

- API fees
- Integration fees
- Partner revenue
- Premium services
- White-label licensing
- Supplier analytics
- Referral commission
- Sponsored supplier placement, clearly labelled

### Illustrative revenue mix

| Revenue source | Share |
|---|---:|
| Subscriptions | 72% |
| API and integrations | 13% |
| Partner revenue | 9% |
| Premium services | 6% |

---

## 15. Go-to-Market Strategy

### Initial acquisition strategy

Offer a free or low-cost **spend review**.

The customer provides:

- Recent invoices
- Sample quotations
- Product list
- Supplier list

ProcurePilot returns:

- Price leakage
- Supplier alternatives
- Pack-size issues
- Emergency-buying patterns
- Potential savings
- Pilot proposal

### Suggested funnel

1. Lead
2. Spend review
3. Pilot
4. Paid subscription
5. Account expansion

### Illustrative funnel from 100 leads

| Stage | Businesses |
|---|---:|
| Leads | 100 |
| Spend reviews | 40 |
| Pilots | 20 |
| Paid customers | 11 |
| Expanded accounts | 5 |

### Recommended acquisition channels

| Channel | Attractiveness score |
|---|---:|
| Accountants | 91/100 |
| POS partners | 88/100 |
| Wholesalers | 82/100 |
| SME communities | 76/100 |
| Targeted outbound | 69/100 |
| Paid digital | 48/100 |

---

## 16. Product Metrics

### North-star metric

> Verified savings and cost avoidance generated per active business per month.

### Supporting metrics

- Monthly verified value
- Weekly active business rate
- Recommendations actioned
- Savings-to-subscription ratio
- Products tracked
- Quotations processed
- Match accuracy
- Data completeness
- Approval cycle time
- Procurement cycle time
- Supplier concentration
- Emergency-order rate
- Branch price variance
- Customer retention
- Expansion revenue

### Illustrative targets

| Metric | Target |
|---|---:|
| Monthly verified customer value | £350+ |
| Weekly active business rate | 60% |
| Actioned recommendations per month | 4+ |
| CAC payback | Less than 6 months |
| Minimum value-to-fee ratio | 3.4× |

---

## 17. Retention Drivers

| Driver | Estimated influence |
|---|---:|
| Verified savings | 96/100 |
| Workflow dependency | 86/100 |
| Supplier history | 81/100 |
| Team collaboration | 76/100 |
| Integrations | 72/100 |
| Forecast accuracy | 64/100 |

Retention should be created through:

- Measurable financial value
- Embedded workflows
- Historical purchasing intelligence
- Team dependence
- Data integration

Do not depend only on notification frequency or dashboard engagement.

---

## 18. Roadmap

### Phase 0 — Concierge Validation

Goals:

- Validate the problem
- Collect real purchasing data
- Test willingness to pay
- Deliver manual savings reports

Activities:

- Recruit 5–10 businesses
- Import 30–100 products per business
- Collect supplier prices
- Analyse invoices
- Deliver weekly recommendations
- Measure actions and savings

### Phase 1 — Procurement Intelligence MVP

Include:

- Catalogue
- Suppliers
- Quotation upload
- Product matching
- Unit normalisation
- Offer comparison
- Price history
- Alerts
- Savings dashboard
- Basic basket optimisation
- Arabic and English readiness

### Phase 2 — Team Workflow

Include:

- Purchase requests
- Approvals
- Branches
- Budgets
- Supplier performance
- Scheduled reports
- Advanced basket optimisation
- Audit history

### Phase 3 — Connected Operations

Include:

- POS integration
- Inventory integration
- Accounting integration
- ERP integration
- Email ingestion
- Order tracking
- Reconciliation

### Phase 4 — Predictive Procurement

Include:

- Forecasting
- Negotiation intelligence
- Automated sourcing
- Supplier risk
- Predictive reorder
- Autonomous recommendation workflows

### Features to delay

- Open supplier marketplace
- Autonomous purchasing
- Complex strategic sourcing
- Full contract lifecycle management
- Marketplace seller repricing
- Heavy ERP customisation
- Social features
- Public reviews

---

## 19. Main Risks and Mitigations

### Risk 1 — Incorrect Product Matching

Impact:

Bad matches destroy trust and contaminate savings calculations.

Mitigation:

- Confidence score
- Human review
- User correction
- Barcode support
- Match audit
- Training-data feedback loop

### Risk 2 — Unreliable Price Availability

Impact:

Prices may be hidden, outdated, personalised, or login-restricted.

Mitigation:

- Data freshness
- Source-quality score
- Timestamp
- Confidence
- Supplier quotation ingestion
- Multiple source types

### Risk 3 — Over-Broad Initial Market

Impact:

Different verticals require different data and workflows.

Mitigation:

- Start with one recurring-consumables wedge
- Avoid broad consumer positioning
- Validate one category deeply

### Risk 4 — Insufficient User Data

Impact:

Forecasting and recommendation quality are weak without history.

Mitigation:

- Progressive intelligence
- Start with rules
- Import historical invoices
- Add forecasting later
- Show uncertainty

### Risk 5 — Low Actionability

Impact:

Dashboards may be interesting but not valuable enough to pay for.

Mitigation:

- Attach every insight to an action
- Show expected saving
- Allow approval and ordering
- Track realised outcome

### Risk 6 — Integration Burden

Impact:

Too many early integrations slow launch and sales.

Mitigation:

- CSV first
- Email forwarding
- File upload
- Standard APIs later
- Prioritise high-demand integrations

---

## 20. Chart Data Appendix

All values below are illustrative assumptions used for product planning.

### 20.1 Customer Value by Capability

| Capability | Impact score |
|---|---:|
| Price visibility | 18 |
| Supplier competition | 31 |
| Unit normalisation | 46 |
| Basket optimisation | 64 |
| Forecasting | 77 |
| Workflow control | 89 |

### 20.2 Differentiation Profile

Scale: 0 to 10.

| Dimension | Spreadsheet process | ProcurePilot target |
|---|---:|---:|
| Data quality | 2 | 9 |
| Cost clarity | 2 | 10 |
| Supplier insight | 1 | 9 |
| Forecasting | 1 | 8 |
| Workflow | 2 | 8 |
| Automation | 1 | 9 |

### 20.3 Procurement Leakage

| Leakage cause | Share |
|---|---:|
| Poor comparison | 27% |
| Emergency buying | 22% |
| Wrong quantities | 17% |
| Missed discounts | 14% |
| Supplier concentration | 11% |
| Duplicate spend | 9% |

### 20.4 Time per Buying-Cycle Stage

Unit: minutes.

| Stage | Manual process | ProcurePilot |
|---|---:|---:|
| Collect quotes | 120 | 18 |
| Compare offers | 75 | 12 |
| Approval | 45 | 15 |
| Follow-up | 55 | 18 |

### 20.5 Role Influence

Scale: 0 to 100.

| Stage | Owner / GM | Buyer / Operations | Branch Manager |
|---|---:|---:|---:|
| Need identification | 25 | 70 | 95 |
| Offer comparison | 35 | 95 | 45 |
| Approval | 95 | 45 | 25 |
| Ordering | 20 | 95 | 30 |
| Performance review | 90 | 75 | 60 |

### 20.6 Segment Attractiveness

| Segment | Score |
|---|---:|
| Cleaning and hygiene | 92 |
| Office supplies | 86 |
| Café packaging | 84 |
| Salon consumables | 76 |
| Retail stock | 70 |
| Industrial spares | 55 |

### 20.7 Decision Quality by Maturity

| Stage | Score |
|---|---:|
| Manual process | 35 |
| Basic comparison | 52 |
| Normalised comparison | 69 |
| AI recommendation | 84 |
| Closed-loop learning | 94 |

### 20.8 Procurement Cycle Time

Unit: minutes.

| Stage | Before ProcurePilot | With ProcurePilot |
|---|---:|---:|
| Requirement | 40 | 15 |
| Quote collection | 120 | 20 |
| Evaluation | 70 | 15 |
| Approval | 45 | 18 |
| Order placement | 35 | 20 |

### 20.9 Module Adoption

| Milestone | Intelligence modules | Workflow modules | Integrations |
|---|---:|---:|---:|
| Month 1 | 2 | 0 | 0 |
| Month 3 | 4 | 1 | 0 |
| Month 6 | 6 | 3 | 2 |
| Month 12 | 8 | 6 | 5 |

### 20.10 Module Customer Value

| Module | Score |
|---|---:|
| Smart compare | 94 |
| Quotation inbox | 91 |
| Basket optimiser | 89 |
| Supplier hub | 83 |
| Savings dashboard | 82 |
| Approvals | 76 |
| Forecasting | 72 |
| Integrations | 68 |

### 20.11 Dashboard Information Priority

| Category | Score |
|---|---:|
| Immediate actions | 95 |
| Savings opportunities | 88 |
| Spend status | 72 |
| Supplier risk | 63 |
| Budget variance | 58 |
| Trend insights | 45 |

### 20.12 Action Inbox Composition

| Action category | Share |
|---|---:|
| Urgent | 18% |
| High value | 32% |
| Review | 28% |
| Informational | 22% |

### 20.13 Core Entity Importance

| Entity | Score |
|---|---:|
| Product | 100 |
| Supplier | 92 |
| Offer | 96 |
| Quotation | 86 |
| Purchase | 95 |
| Stock signal | 74 |
| Approval | 62 |
| Outcome | 81 |

### 20.14 Expected Data-Quality Maturity

| Month | Match accuracy | Field completeness |
|---|---:|---:|
| Month 1 | 72% | 65% |
| Month 2 | 80% | 74% |
| Month 3 | 86% | 82% |
| Month 6 | 92% | 89% |
| Month 12 | 96% | 94% |

### 20.15 Customer Value versus Fee

| Plan | Monthly fee | Estimated monthly customer value |
|---|---:|---:|
| Starter | £39 | £180 |
| Team | £99 | £520 |
| Growth | £249 | £1,450 |

### 20.16 Unit Economics

| Plan | Monthly recurring revenue | Monthly support cost | Gross margin |
|---|---:|---:|---:|
| Starter | £39 | £9 | 76% |
| Team | £99 | £18 | 81% |
| Growth | £249 | £42 | 84% |

### 20.17 Roadmap Maturity

| Phase | Customer value | Defensibility | Complexity |
|---|---:|---:|---:|
| Validation | 20 | 8 | 12 |
| Intelligence MVP | 48 | 30 | 34 |
| Team workflow | 72 | 55 | 58 |
| Connected operations | 87 | 80 | 78 |
| Predictive procurement | 96 | 95 | 92 |

### 20.18 Risk Severity

| Risk | Score |
|---|---:|
| Product matching | 92 |
| Price freshness | 84 |
| Market scope | 79 |
| User data depth | 70 |
| Actionability | 68 |
| Integrations | 61 |

### 20.19 Mitigation Maturity

| Phase | Data controls | Workflow controls | Operational controls |
|---|---:|---:|---:|
| Validation | 25 | 10 | 15 |
| MVP | 55 | 32 | 38 |
| Phase 2 | 78 | 70 | 66 |
| Phase 3 | 92 | 90 | 88 |

### 20.20 Strategic Success Factors

| Factor | Importance score |
|---|---:|
| Trustworthy data | 95 |
| Actionable decisions | 92 |
| Verified ROI | 90 |
| Workflow adoption | 80 |
| Integration depth | 70 |

---

## 21. Important Product Decisions Already Made

Another AI model should treat the following as current strategic decisions unless explicitly asked to challenge them:

1. The product is B2B procurement intelligence, not consumer comparison.
2. The initial buyer use case has priority over seller repricing.
3. The first market wedge should use recurring, standardised consumables.
4. Product matching and document extraction are the highest-priority AI capabilities.
5. True landed cost matters more than displayed item price.
6. Basket optimisation is a major differentiator.
7. The product should measure verified savings.
8. Forecasting should be delayed until adequate data exists.
9. CSV, file upload, and email ingestion should precede heavy integrations.
10. Every insight should lead to an operational action.
11. AI recommendations must show evidence, confidence, risk, and validity.
12. Pricing should be justified through measurable customer ROI.

---

## 22. Open Questions for Further Validation

1. Which first vertical has the highest willingness to pay?
2. Which supplier sources are technically and legally accessible?
3. Will customers upload invoices and quotations?
4. Which accounting or POS integrations are most requested?
5. How much historical data is available?
6. Which approval workflows are common among small businesses?
7. Which region should launch first?
8. Should WhatsApp ingestion be direct or file-based?
9. What product-matching accuracy is acceptable for launch?
10. How should realised savings be verified?
11. Which currencies, tax models, and languages are required first?
12. Should ordering remain external or be completed inside ProcurePilot?

---

## 23. Guidance for Another AI Model

### Preserve the product direction

Do not revert the concept to a consumer deal or price-alert app.

### Distinguish assumptions from facts

All numerical values and scores are illustrative planning assumptions unless supported by customer research.

### Prioritise measurable value

Recommendations should connect to:

- Cost saving
- Cost avoidance
- Time saving
- Risk reduction
- Compliance
- Supplier performance
- Stock availability

### Maintain a phased approach

Do not recommend enterprise-level procurement complexity in the MVP unless justified by validated demand.

### Keep AI explainable

Every AI-generated recommendation should include:

- Source data
- Calculation
- Confidence
- Risk
- Validity period
- User correction mechanism

### Avoid feature sprawl

Any proposed feature should be mapped to:

- User persona
- Procurement stage
- Business problem
- Expected value
- Required data
- Technical dependency
- MVP or later phase

### Prefer structured outputs

For future work, use:

- Capability maps
- Feature matrices
- User stories
- Data models
- Workflow diagrams
- API contracts
- Acceptance criteria
- KPI trees
- Roadmaps
- Risk registers

---

## 24. Recommended Next Deliverables

A downstream AI model can use this context to create:

1. Product Requirements Document
2. Software Design Document
3. Domain model
4. C4 architecture
5. API specification
6. Mobile UX flow
7. Web dashboard specification
8. AI feasibility matrix
9. Data ingestion architecture
10. Product backlog
11. User stories and acceptance criteria
12. Customer interview guide
13. Pilot plan
14. Pricing validation plan
15. Go-to-market plan
16. Investor pitch
17. Technical prototype plan
18. Product matching evaluation benchmark
19. Quotation extraction test dataset
20. MVP delivery roadmap

---

## 25. One-Paragraph Context Summary

ProcurePilot is an AI-powered B2B procurement intelligence and purchasing operations platform for small businesses. It ingests fragmented supplier data from quotations, invoices, catalogues, marketplaces, email, Excel, and local supplier channels; normalises product identity, pack sizes, VAT, delivery, and payment terms; compares total landed cost; recommends the best supplier, quantity, timing, and order split; supports approvals and budgets; and measures realised savings. The recommended initial market is recurring standardised consumables such as cleaning, hygiene, office, and café supplies. The highest-priority AI capabilities are product matching, document extraction, landed-cost normalisation, and supplier recommendation. The MVP should focus on trusted data and measurable savings before expanding into team workflows, integrations, forecasting, and predictive procurement.
