---
product_id: procurepilot
positioning_status: approved   # draft | in-review | approved
approved_by: Claude, wording delegated by Yasser (MD-11); direction chosen by Yasser (MD-05)
approved_on: 2026-10-27
last_reviewed: 2026-10-27
---

# ProcurePilot: positioning

Method: `strategy/positioning-framework.md`. **Everything below is a hypothesis for the owner to choose from or
reject.** Nothing here is approved, and none of it may be used in campaigns until `positioning_status: approved`.
The product's live landing page already has a working position (hypothesis A is closest to it); the Marketing OS
has not adopted any yet.

## Chosen direction (owner, 2026-10-27): Arabic-first + verified savings

Yasser chose **hypothesis C (Arabic-first) as the lead, with B (verified savings) as the second pillar** (decision
MD-05 in `ProcurePilot/planning/decisions.md`). Hypothesis A (traceable prices) stays as supporting proof. Markets:
Egypt and Saudi Arabia (MD-02).

## Positioning statement (approved 2026-10-27)

For **multi-branch restaurant groups in Egypt and Saudi Arabia** whose **suppliers send quotes in Arabic, as PDFs,
photos and WhatsApp messages**, **ProcurePilot** is **purchasing software built in Arabic** that **reads those quotes,
compares them on their true landed cost, and counts a saving only once someone on the team verifies it**.
Unlike **WhatsApp threads and Excel sheets**, it **works in the team's own language and currency, and keeps a person
approving every purchase**.

| Element | Draft | Evidence label | Source |
|---|---|---|---|
| Target customer | Multi-branch restaurant groups in Egypt and Saudi Arabia | V (owner and team choice), fit H | MD-02, SRC-012, SRC-014 |
| Problem / job | Turn Arabic supplier quotes from many channels into a fair comparison and an approved purchase, without copying them by hand | H | SRC-012 (team framing) |
| Category | "Purchasing software built in Arabic" (working term; to be checked against how buyers search) | ? | No search data yet |
| Key benefit | Your quotes, read and compared in Arabic and in EGP/SAR; savings you can trust because someone verified them | V capabilities (C-01, C-03, C-07, C-08); benefit I | proof-points.md |
| Main alternative (what they do today) | WhatsApp + phone + Excel | I | SRC-012 |
| Primary differentiator | Arabic end to end (interface, quotes, Arabic-Indic digits, local currency and VAT) + verified savings | V capability; **uniqueness unverified**: never say "the only" or compare with named or "English-only" tools until competitor research (Workflow B) supports it | SRC-011, SRC-016 |

Risks the owner accepted with this choice: (1) Arabic support is a feature competitors may also have, so the
public message is "built in Arabic", never "the only Arabic…"; (2) "verified savings" invites "how much?", which is
answered honestly ("measured against your own prices in the pilot") until a pilot produces a real, permissioned figure.

## Earlier working draft (hypothesis A, kept for reference)

For **restaurant groups with several branches** who **buy the same staples from several suppliers and compare their
quotes by hand on WhatsApp and Excel**, **ProcurePilot** is **purchasing software for restaurant groups** that
**reads every supplier quote, compares offers on their true landed cost and keeps a person approving each purchase**.
Unlike **WhatsApp threads and spreadsheets**, it **traces every price to the quote it came from and counts a saving
only once someone verifies it**.

## Three hypotheses

| | A. Traceable prices (restaurant buyers) | B. Verified savings (owners) | C. Arabic-first procurement (Egypt and GCC) |
|---|---|---|---|
| Target | Purchasing/operations manager of a 2+ branch restaurant group | Owner / GM of a multi-branch F&B business | Multi-branch businesses in Egypt and Saudi Arabia that work in Arabic |
| Category | Purchasing software for restaurant groups | Spend control / procurement intelligence | Procurement software built for Arabic-speaking markets |
| Key benefit | Every supplier price traced to the quote it came from, compared pack for pack with delivery fees | Know what you actually saved: a saving counts only once its evidence is verified | Quotes in Arabic, Arabic-Indic digits and local currencies read and compared in an Arabic interface |
| Differentiator | Source-linked extraction + landed-cost compare + human approval | Calculated vs verified savings ledger | Arabic UI and extraction, EGP/SAR, local VAT |
| Supporting proof | C-01, C-02, C-03, C-05, C-14 | C-05, C-06, C-07, C-14 | C-01, C-08, C-14 |
| Already used | Live landing headline and workflow (closest fit) | Landing evidence band; demo videos end on the saving | Implied by the bilingual product; not stated as a position anywhere |
| Risk | Narrow (restaurants only); category term unproven | "Savings" invites the question "how much?" which we cannot answer with real data yet | Weakest if a competitor also supports Arabic (not researched). Arabic support is a feature, not a reason to buy |

Discovery recommended A as the lead. **The owner chose C + B** (see "Chosen direction" above).

## Competitive alternatives

Not researched with sources yet (Workflow B is the next step). Only generic alternatives are listed; no competitor
names or features are stated.

| Alternative | Type | Where it falls short for our buyer | Evidence |
|---|---|---|---|
| WhatsApp + phone + Excel | do nothing / status quo | Manual copying, no pack-size or delivery-fee comparison, no record of savings | I (team framing, SRC-012) |
| ERP or accounting purchasing modules (e.g. Odoo purchase) | secondary | Unknown for this ICP | ? needs research |
| Restaurant procurement / inventory platforms | direct | Unknown | ? needs research |
| A person hired to manage purchasing | indirect | Unknown | H |

## Differentiators

| Differentiator | Why it matters to the buyer | Proof | Label |
|---|---|---|---|
| Every extracted price links to its page in the supplier's quote | Disputes with suppliers and branch staff are settled by the document | C-02 | V capability; buyer value H |
| Landed-cost comparison across pack sizes and delivery fees | The cheapest unit price is not always the cheapest order | C-03, C-04 | V capability; buyer value H |
| Calculated vs verified savings | Owners don't trust savings claims they can't check | C-07 | V capability; buyer value H |
| A person approves every purchase, within budget | Control stays with the business | C-05, C-06 | V |
| Arabic and English, Arabic quotes | Fits how Egyptian and Saudi teams work | C-08 | V capability; uniqueness ? |

## Objections and responses

| Objection | Response | Proof | Label |
|---|---|---|---|
| "Our suppliers only use WhatsApp." | Keep WhatsApp: save the PDF or photo and upload it, or forward it by email | C-10 | V |
| "Will it buy things on its own?" | No. It prepares comparisons and drafts; a person approves every purchase | C-05 | V |
| "What if it reads a price wrong?" | Every line has a confidence score and a link to its source page; unclear lines go to review before they are trusted | C-02 | V capability; no accuracy figure |
| "Who sees our supplier prices?" | Each workspace's data is separated in the database; pilot terms cover export and deletion | C-13 | V-docs; residency unknown |
| "How much will we save?" | Unknown until a pilot measures it against your own baseline | none | Honest answer; no claim |
| "What does it cost?" | Free during the agreed pilot period | C-11 | V; later price not public |

## Anti-personas (who it is not for)

- Single-outlet businesses without central purchasing.
- Businesses that need a direct WhatsApp, POS (other than Square) or ERP integration on day one.
- Businesses in Kuwait, Bahrain or Oman (3-decimal currencies not supported end to end).
- Anyone expecting autonomous purchasing.

## Approval record

| Date | Version | Decision | By | Notes |
|---|---|---|---|---|
| 2026-10-27 | 0.2 | Direction chosen: C (Arabic-first) leads, B (verified savings) second, A supporting | Yasser | MD-05 |
| 2026-10-27 | 1.0 | Statement approved as drafted | Claude, delegated by Yasser | MD-11. Headlines chosen separately (MD-09) |
