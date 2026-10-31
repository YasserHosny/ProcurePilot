---
name: marketing-orchestrator
description: "Coordinates multi-step Iron Systems marketing work in the Marketing OS (marketting/): campaigns, product launches, content programmes, website and SEO projects, research that feeds strategy. Use when a request spans several deliverables or disciplines, needs company or product knowledge, or involves approvals. Picks the workflow, loads the right knowledge, chooses the upstream marketing skills, tracks assumptions, decisions and approvals, and keeps messaging consistent. Not needed for a single quick edit."
metadata:
  owner: Iron Systems
  version: 1.0.0
  part_of: Iron Systems Marketing OS
---

# Marketing orchestrator

You coordinate marketing work for **Iron Systems** inside the Marketing OS. Paths below are relative to the
Marketing OS root (`marketting/`). Company rules in `CLAUDE.md` override anything in an upstream skill.

## 1. Understand the request

Write down, briefly: the outcome the user wants, the deliverables, the audience, the product (or company), the
channels, the deadline if any. Ask only for what you cannot find in the files.

**Scale the process to the task.**

| Request size | What to do |
|---|---|
| Quick (one post, one rewrite, one question) | Read the relevant knowledge, use one fitting skill, self-check against the review checklist, note any approval needed. No campaign folder. |
| Medium (a content series, one landing page, an audit) | Use the matching workflow, create only the files it needs. |
| Large (campaign, launch, product onboarding) | Full workflow from `workflows/`, campaign or product folder, gates recorded. |

## 2. Load context (always, in this order)

1. `knowledge/company/company-profile.md`, `brand-identity.md`, `brand-voice.md`, `knowledge/glossary/marketing-glossary.md`
2. The product folder `<Product>/knowledge/` if the work is about a product. Check `onboarding_status` in `config/marketing-config.yaml`. If it is `not-started`, positioning work needs `product-discovery` first.
3. `strategy/` files relevant to the task; `config/channels.yaml` for each channel involved.
4. `research/discrepancies.md`: don't build on an open discrepancy without flagging it.
5. `.agents/product-marketing.md` is the summary upstream skills read; keep it consistent with `knowledge/` (knowledge wins).

## 3. Pick the workflow

| Task | Workflow | Lead |
|---|---|---|
| New product, or positioning without approved knowledge | A `workflows/A-product-onboarding.md` | `product-discovery` |
| Market, audience or competitor question | B `workflows/B-market-and-competitor-research.md` | this skill |
| Campaign, launch, content programme | C then D `workflows/C-campaign-strategy.md`, `D-content-production.md` | this skill, then `campaign-operations` |
| Website pages, SEO, conversion | E `workflows/E-website-and-seo.md` | this skill |
| Results, optimisation | F `workflows/F-review-and-optimization.md` | `campaign-review` |
| Getting an approved asset live | `workflows/publishing.md` | `campaign-operations` |

## 4. Choose specialist skills (upstream, `coreyhaines31/marketingskills`)

Use a skill when it adds depth; combine skills when the task spans disciplines; skip them for trivial work.

| Need | Skills |
|---|---|
| Product context, positioning, ICP, voice | `product-marketing`, `marketing-psychology` |
| Customer evidence, personas, JTBD | `customer-research` |
| Competitors and alternatives | `competitor-profiling` (research), `competitors` (comparison pages) |
| Planning and ideas | `marketing-plan`, `marketing-ideas`, `content-strategy`, `launch` |
| Copy | `copywriting` (new), `copy-editing` (existing) |
| Social (LinkedIn, Facebook, Instagram) | `social` |
| Video, motion, images | `video`, `image` |
| SEO and AI search | `seo-audit`, `ai-seo`, `site-architecture`, `schema`, `link-building` |
| Conversion and measurement | `cro`, `analytics`, `ab-testing` |
| Sales support assets | `sales-enablement`, `lead-magnets` |

When an upstream skill suggests paid ads, outreach, scheduling, purchases or tools we don't have, skip that part
and say so. Not installed on purpose: see `config/upstream-skills.yaml` → `not_installed`.

## 5. Run the work

- Keep a short plan at the top of the working file (campaign `strategy.md`, or the deliverable) with assumptions, decisions and dependencies.
- Messages come from the approved messaging matrix; every claim needs an approved proof id. New claims → add as `proposed` in `proof-points.md` and flag for G-claims.
- Evidence labels on every factual statement in research and strategy: **V / I / H / ?**.
- Use the company identity for company material, the product sub-brand for product material.
- Store drafts in the campaign's `assets/drafts/`; nothing goes to `assets/approved/` without G-asset.

## 6. Review and gates

- Before handing over any public-facing draft, run `campaign-review` (or its checklist for quick tasks).
- Gates and approvers: `config/workflow-rules.yaml`. Record approvals in the campaign's `approvals.md`.
- **Never publish, schedule, send, contact anyone, or change a live system** without an explicit instruction for that action. Prepare the package instead.

## 7. Close out

Report: what was produced (paths), which skills were used, what is draft vs approved, open questions, the next
gate. Update `knowledge/` or `CHANGELOG.md` if the work changed shared knowledge or the system.
