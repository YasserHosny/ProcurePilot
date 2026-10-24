# Saudi demo (G-13, PPS-39) — plan

Status 2026-10-25: product support live on hosted (#266 merged, migration applied, extraction worker deployed); plan approved by the owner 2026-10-25; workspace not created yet (owner step). Owner chose Saudi Arabia as the first GCC market. Built the same way as the Egypt
demo («مطاعم سند», [`../demo-tenant/README.md`](../demo-tenant/README.md)): a separate workspace on hosted, real
runs through the product, a recorded video in Arabic and English. The Egyptian tenant is never touched.

Skills used: `technical-video-script` (script) and `localization-strategy` (what changes for the Saudi market and
what stays). Following the latter, three things are kept apart:

| Layer | Egypt demo | Saudi demo | Work |
|---|---|---|---|
| Language | Arabic, Egyptian colloquial captions | Arabic, Gulf (neutral Saudi) captions | new script copy |
| Locale | EGP, Egypt VAT 14%, DD/MM dates | SAR, Saudi VAT 15%, DD/MM dates | reference data + extraction (product PR) |
| Market | Cairo restaurant group, Egyptian suppliers | Riyadh/Jeddah restaurant group, Saudi suppliers | new tenant data |

## 1. Product changes — done (#266)

- Migration: region `SA`, currency `SAR` (2 decimals), tax model `sa_vat_standard` (Saudi VAT 15%).
- Extraction recognises SAR markers («ر.س», «ريال سعودي», «ريال», SAR, SR) like it does EGP.
- Audit of Egypt-specific assumptions in API, web and mobile.
- Merged as #266 (2026-10-25), migration applied to hosted, privilege check passed, extraction worker deployed. A bare «ريال», Qatari/Omani riyals and QAR still go to review.

Not in scope: Kuwait, Bahrain and Oman (3-decimal currencies are not supported end to end).

## 2. Demo workspace (proposed, all fictional)

| Item | Proposal |
|---|---|
| Workspace | «مطاعم رواق» — region SA, currency SAR, Saudi VAT 15%, language Arabic |
| Accounts | owner `+pp-sa-owner`, buyer `+pp-sa-buyer` (Gmail plus addresses) |
| Branches | فرع العليا (الرياض) · فرع الملقا (الرياض) · فرع التحلية (جدة) |
| Cost centres | المطبخ — العليا · المطبخ — الملقا · المطبخ — جدة |
| Budgets | monthly kitchen budget per branch, in SAR |
| Suppliers (with Gmail send-as aliases) | الذهبي للتموين (`+pp-sa-dhahabi`) · الوفرة للمواد الغذائية (`+pp-sa-wafra`) · خضار القصيم الطازجة (`+pp-sa-qassim`) |
| Products | أرز بسمتي (كيس 10 كجم) · زيت دوار الشمس (تنكة 18 لتر) · دجاج مبرد (كرتون 10 كجم) · طماطم (كرتون 6 كجم) · بصل أحمر (كيس 20 كجم) · … ~20 items |
| Guardrail | up to SAR 10,000, at least 1 reply, ≤ 20% variance, default cost centre «المطبخ — العليا» |
| Quotes | in SAR with «ر.س», prices including 15% VAT stated on the quote, a fictional supplier VAT number, Gregorian DD/MM/YYYY dates; one WhatsApp photo, two PDFs |
| History | a short dry round first, so the recorded round saves against a last PO price |

Indicative prices (to confirm before quotes are made): basmati 10 kg ≈ SAR 85–95, oil 18 L ≈ SAR 140–160, chilled
chicken 10 kg ≈ SAR 150–170.

## 3. Owner steps (Claude never creates accounts or types passwords)

1. After the migration is applied: sign up the new workspace on hosted with SA / SAR / Saudi VAT, and the buyer invite.
2. Add three Gmail "send mail as" aliases for the Saudi suppliers.
3. Sign in to the kiosk Chrome and the phone build with the new owner.
4. OK each batch of supplier emails, as in rounds 4–7.

## 4. Order of work

1. Product PR (above) → merge → migrate hosted → deploy worker.
2. Script (GCC buyer) for owner approval, Arabic Gulf + English.
3. Owner creates the workspace; Claude populates branches, cost centres, budgets, catalogue, suppliers and the guardrail
   through the app.
4. Dry round, then recorded rounds (Arabic UI, English UI).
5. Mask, edit (reuse `source/edit-v2.4`), review, PR.

Script draft: [`script-saudi.md`](script-saudi.md).
