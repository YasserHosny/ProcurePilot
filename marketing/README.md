# Marketing

Home for all Iron Systems marketing work, and the **Iron Systems Marketing OS**: company and product knowledge,
workflows, templates, Claude Code skills and checks for organic B2B marketing (website, SEO, LinkedIn, Facebook,
Instagram, video). Paid media is out of scope.

The Iron Systems brand source of truth is `<workspace>\Branding\Identity-v3`. The live website is `<workspace>\Website\iron-system-next`.

## Existing asset library (kept as it was)

- `ProcurePilot\demo-video` — versioned demo videos, see `VERSIONS.md`.
- `ProcurePilot\design-system` — ProcurePilot brand reference page, logos, app stills.
- `LinkedIn\company-page` — Iron Systems LinkedIn company page kit (copy EN/AR, logo, cover, setup steps), one folder per version.

`Social\profiles\` holds the profile kits (names, bios, images) for the Iron Systems X, Facebook and Instagram
accounts, one folder per version, like `LinkedIn\`. Company marketing: `strategy/company-marketing-plan.md` and
`campaigns/`.

`ProcurePilot/` is the single home for everything marketing holds about ProcurePilot: `knowledge/`, `planning/`,
`campaigns/` and the asset folders. The product's own docs are next door in this repo (`../docs/`). See
`ProcurePilot/README.md`.

## Marketing OS

| Folder | What's in it |
|---|---|
| `CLAUDE.md` | Operating rules for Claude Code (read first) |
| `config/` | `marketing-config.yaml` (company, products, channels, languages, evidence, approvals), `channels.yaml`, `workflow-rules.yaml` (gates, checks, workflows), `upstream-skills.yaml` |
| `knowledge/company/` | Company profile, brand identity summary, brand voice (from workspace sources) |
| `knowledge/products/` | Product registry; `product-template/` for onboarding a product (each product's knowledge lives in its own folder, e.g. `ProcurePilot/knowledge/`) |
| `config/sources.yaml`, `research/source-updates/` | Product and company sources the OS keeps up with, and the latest change report |
| `knowledge/audience/`, `knowledge/glossary/` | Audience hypotheses and evidence log; approved names and terms |
| `research/` | Source log, discrepancy log, market / competitor / customer research |
| `strategy/` | Principles, positioning framework, content and channel strategy (drafts marked) |
| `workflows/` | A product onboarding · B research · C campaign strategy · D content production · E website and SEO · F review and optimisation · publishing |
| `campaigns/` | One folder per campaign, from `campaign-template/` |
| `templates/` | Discovery report, competitor analysis, content brief, social post, video brief, landing page, review |
| `analytics/` | Metrics dictionary, measurement framework, reporting template |
| `integrations/` | Integration registry, setup guides, upstream skill provenance |
| `.claude/skills/` | 4 custom skills + 24 upstream skills |
| `.agents/product-marketing.md` | Shared context file the upstream skills read first (summary of `knowledge/`) |
| `scripts/`, `tests/` | Skill sync, scaffolding, validator and its tests |

## Getting started

Start Claude Code **in this folder** so every skill loads at startup:

```bash
cd marketing
claude
```

Started at the repo root instead, the skills here load the first time Claude reads a file in `marketing/`
(for example this README or `CLAUDE.md`).

One-time setup for the scripts (Node 20+):

```bash
npm install
npm test
```

| Command | Does |
|---|---|
| `npm test` | Unit tests for the validator, then the full validation |
| `npm run validate` | Validation only |
| `npm run sources:sync` | Report product (this repo), website and brand changes since the last review; warns if the checkout is behind origin (`-- --mark-reviewed`) |
| `npm run new:product -- <id> <FolderName>` | New product knowledge folder from the template (`<FolderName>/knowledge/`) |
| `npm run new:campaign -- <YYYY-MM-product-slug>` | New campaign folder from the template (product campaigns go in the product folder) |
| `npm run skills:sync` | Reinstall the pinned upstream skills (see `integrations/setup-guides/marketingskills.md`) |

## Skills

Custom (Iron Systems): `marketing-orchestrator` (coordinates multi-step work), `product-discovery` (evidence-based
product onboarding), `campaign-operations` (structure, status, publish-ready packages), `campaign-review` (claims,
brand, channel and approval checks).

Upstream (`coreyhaines31/marketingskills` v2.13.5, commit `17772c7`, MIT): product-marketing, customer-research,
competitor-profiling, competitors, marketing-plan, marketing-ideas, marketing-psychology, content-strategy,
copywriting, copy-editing, social, video, image, seo-audit, ai-seo, site-architecture, schema, link-building, cro,
analytics, ab-testing, launch, sales-enablement, lead-magnets.

## Status

ProcurePilot discovery is done and waiting for the owner's review (`ProcurePilot/knowledge/discovery-report.md`). No
product positioning or claim is approved yet.
See `CHANGELOG.md`.
