---
product_id: procurepilot
last_reviewed: 2026-10-27
---

# ProcurePilot: claims and proof points

The register of every statement that may appear in public marketing. `campaign-review` checks drafts against it.

**Rules**
- A claim is usable in public only when `evidence` is filled **and** `status: approved`.
- Never add testimonials, customer logos, ROI figures, savings, time saved or case studies without a real source and written permission (record where the permission is kept).
- Demo or synthetic data must be labelled as such wherever it appears (e.g. "Real screens with synthetic data").
- Third-party statistics need the original source URL and access date; no rounding up, no stripping caveats.

**2026-10-27:** Yasser approved C-01 to C-12 and C-14 for use in posts (decision MD-06); C-13 is held. The limits
and caveats column still applies to every use.

Most wording below is **already live** on the product's landing page or the Iron Systems website, which the
owner approved for those pages. Approval here (G-claims) is still needed before the Marketing OS reuses it in new
channels. Evidence ids: `research/source-log.md`.

## Claims register

| id | Claim (exact wording allowed) | Type | Evidence (path / URL / screen) | Accessed | Status | Approved by / date | Limits and caveats |
|---|---|---|---|---|---|---|---|
| C-01 | ProcurePilot reads the quotations your suppliers send by email or upload. | capability | Landing hero (SRC-017); user docs §8, §28–30 (SRC-019) | 2026-10-27 | approved | Yasser, 2026-10-27 | Not WhatsApp directly: WhatsApp quotes are saved and uploaded or forwarded (C-10) |
| C-02 | Every extracted line keeps a link to its page in the source document, with a confidence score, and is reviewed before it is trusted. | capability | Landing step 1, gallery 01 (SRC-017); website capability (SRC-004) | 2026-10-27 | approved | Yasser, 2026-10-27 | No accuracy figure may be stated: extraction accuracy is unmeasured (roadmap R1.2 "Unvalidated") |
| C-03 | Compares offers pack for pack, with each supplier's delivery fee included, and shows the scoring. | capability | Landing step 2, gallery 02; website "Compares on landed cost" | 2026-10-27 | approved | Yasser, 2026-10-27 | Same currency only (no FX, gap C4) |
| C-04 | Splits one order across suppliers when that lowers the total. | capability | Landing gallery 03; website "Splits the basket"; user docs §13 | 2026-10-27 | approved | Yasser, 2026-10-27 | |
| C-05 | A person on your team approves every purchase. Nothing is ordered before that approval. | capability | Landing step 3, FAQ; repo rule 8 "No autonomous purchasing" (SRC-011) | 2026-10-27 | approved | Yasser, 2026-10-27 | Automation can prepare a draft request when a guardrail is on; never a purchase |
| C-06 | Branch requests reach the approver with the remaining budget shown. | capability | Landing step 3, gallery 04; website "Checked against the cost centre's budget" | 2026-10-27 | approved | Yasser, 2026-10-27 | |
| C-07 | A saving counts only once someone verifies its evidence. | capability | Landing evidence band, gallery 05; website "Verifies savings" | 2026-10-27 | approved | Yasser, 2026-10-27 | Must never be paired with a real savings figure: none exists. All ledger figures shown are demonstration data |
| C-08 | Works in Arabic and English, including Arabic supplier quotes. | capability | i18n en + ar (SRC-016); extraction of Arabic quotes and Arabic-Indic digits (SRC-011) | 2026-10-27 | approved | Yasser, 2026-10-27 | Don't claim accuracy or "native" for every Gulf currency (QAR/KWD/BHD/OMR not supported) |
| C-09 | Approve purchase requests from your phone. | capability | Mobile user docs; demo videos (SRC-015) | 2026-10-27 | approved | Yasser, 2026-10-27 | Requests only, not purchase orders. No push notifications yet. App-store availability unknown |
| C-10 | Suppliers can keep sending quotes on WhatsApp: save the PDF or photo and upload it, or forward it by email. There's no direct WhatsApp connection. | capability | Landing FAQ (SRC-017) | 2026-10-27 | approved | Yasser, 2026-10-27 | Keep the limitation in the same sentence |
| C-11 | Live as an invitation-only pilot, free for the agreed pilot period. | availability | Landing (SRC-017); website registry status `pilot` (SRC-005) | 2026-10-27 | approved | Yasser, 2026-10-27 | Pilot length (14 days) and later price are internal; don't state them without approval |
| C-12 | Built by Iron Systems. | availability | Landing Iron Systems band (SRC-017) | 2026-10-27 | approved | Yasser, 2026-10-27 | Legal entity of ProcurePilot unknown (Q-09) |
| C-13 | Each workspace's data is kept separate, enforced in the database. | capability | Repo rules 1–3, isolation test suite (SRC-011) | 2026-10-27 | proposed (held) | | Internal evidence only; no external audit or certification. Never say "bank-grade", "secure", "certified" |
| C-14 | Real screens with synthetic data. | availability (label) | Landing gallery subtitle; website note | 2026-10-27 | approved | Yasser, 2026-10-27 | Required wherever product screens or demo figures appear |
| C-15 | Works in Egyptian pounds and Saudi riyals, with each country's VAT. | capability | Spec 022 (EGP, VAT 14%), #266 (SAR, VAT 15%) in SRC-011, SRC-014; Saudi demo video (SRC-015) | 2026-10-27 | approved | Yasser, 2026-10-27 | Added for the Arabic-first pillar (MD-05). One currency per comparison (no exchange rates); Egypt pilot compares prices ex-VAT; no KWD/BHD/OMR |
| C-16 | Send one request for quotation to all your suppliers at once; sending is always a person's action. | capability | R4.3 RFQ sourcing shipped (SRC-018); GTM plan demo walkthrough (SRC-012); owner-approved v2.5 video recap "One RFQ to every supplier" (SRC-029) | 2026-10-28 | approved | Yasser, 2026-10-28 | Needed by post A-04. Suppliers reply by email or the buyer uploads their quote; the RFQ email is localised (Arabic/English) |
| C-17 | We don't use your data to train AI models. | capability | Live privacy policy, section "Artificial intelligence" (SRC-032) | 2026-10-28 | approved | Yasser, 2026-10-28 | Quote the policy's wording; don't extend it to other claims (e.g. "secure", "compliant") |

Type: `capability` (the product does X) · `benefit` (X helps you Y) · `comparison` (vs. an alternative) ·
`metric` (a number) · `customer` (testimonial, logo, case) · `availability` (status, pricing, access).

Status: `proposed` → `approved` · `rejected` · `retired` (was true, no longer).

## Claims not available (no evidence; do not use)

| Claim people may want | Why not |
|---|---|
| "Saves X%", "EGP N saved", "cuts quote turnaround from days to hours" | No real customer data. Demo-video and landing figures are synthetic |
| "Trusted by…", customer names or logos, testimonials | No customers recorded in any source |
| "AI extracts with 9x% accuracy" | Not measured (no held-out benchmark) |
| "Integrates with your ERP / Odoo" | Not built. QuickBooks, Xero and Square exist but are not relevant in Egypt and not to be pitched there |
| "Real-time alerts on your phone" | Push notifications are not delivered |
| "Secure", "bank-grade", "compliant" | No external audit or certification |

## Rejected or retired claims (keep the history)

| id | Claim | Reason | Date |
|---|---|---|---|
| — | "Reads requests written in plain language… flags issues before approval" (LinkedIn About, v1.2) | Not proposed: "reads requests written in plain language" has no matching capability in the user docs (the grounded analyst answers questions over data; requests are forms). See D-05 | 2026-10-27 |
