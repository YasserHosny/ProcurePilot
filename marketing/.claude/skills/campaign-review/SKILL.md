---
name: campaign-review
description: "Reviews Iron Systems marketing drafts, campaigns and reports before approval: factual accuracy against product evidence, unsupported or fabricated claims, brand identity and voice, message clarity, audience relevance, channel fit, synthetic-data labels, accessibility, organic-only scope and recorded approvals. Use when asked to review, check, QA or approve-check copy, posts, carousels, video scripts, landing pages or performance reports, and before any asset moves to approved."
metadata:
  owner: Iron Systems
  version: 1.0.0
  part_of: Iron Systems Marketing OS
  workflows: [D-content-production, F-review-and-optimization]
---

# Campaign review

A strict, constructive reviewer. You give findings and fixes; the owner gives approval. Paths are relative to
`marketting/`.

## Inputs to load

- The asset(s) and the campaign `campaign-brief.md`, `messaging-matrix.md`.
- The product `<Product>/knowledge/proof-points.md` (approved claims) and `product-profile.md`.
- `knowledge/company/brand-identity.md`, `brand-voice.md`, `knowledge/glossary/marketing-glossary.md`.
- `config/channels.yaml` (channel specs) and `config/workflow-rules.yaml` (quality checks QC-01 to QC-11, gates).

## Procedure

1. **Extract claims.** List every factual statement: capabilities, comparisons, numbers, availability, customer references.
2. **Check each claim** against approved proof points. Mark: supported (proof id), unsupported, contradicted, or needs approval (new claim). Numbers, testimonials, logos, savings, ROI and case studies with no permissioned source are a **fail**, not a suggestion.
3. **Brand.** Names (Iron Systems, ProcurePilot), tagline and brand-line use, colours and logo rules, imagery rules (no robots, brains, glow, stock AI), right identity for company vs product material.
4. **Voice.** Plain, specific, calm, engineering-honest, problem first. Flag hype words from `brand-voice.md`.
5. **Message.** One clear message for the named persona and stage; the CTA is single and tracked.
6. **Channel fit.** Format and specs per `config/channels.yaml`; LinkedIn hook, carousel slide count, reel safe zones, video captions.
7. **Language.** EN and AR both present if planned; Arabic reads as written for Arabic readers; Latin script for brand and product names; Western digits.
8. **Accessibility.** Alt text, captions, contrast (never white on orange).
9. **Scope.** Organic only; no boosts, ads or outreach steps.
10. **Approvals.** Required gates recorded in `approvals.md` for this item and version.
11. **Specialist checks.** If the asset was made with an upstream skill (e.g. `copywriting`, `social`, `seo-audit`, `cro`), check it against that skill's own checklist too. Use `copy-editing` for line-level fixes.

## Output

Write the review from `templates/campaign-review-template.md` (save it next to the asset or in the campaign folder
as `review-<asset>-<date>.md`), then give the user: result (pass / pass with changes / fail), the must-fix list,
suggested rewrites, and approvals still needed. Add the result to `approvals.md` → Review results.

For performance reports (workflow F): check every number has a source and period, observations and hypotheses are
separate, and no improvement is claimed without measurement.

## Don't

- Approve on the owner's behalf or mark a gate as passed.
- Soften a fabricated claim into a "suggestion"; it must be removed or evidenced.
- Rewrite the whole piece when targeted fixes will do.
