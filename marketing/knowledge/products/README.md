# Products

Each product has **one folder at the root of the Marketing OS, named as the product writes its name** (e.g.
`ProcurePilot/`). It holds everything marketing makes for that product: `knowledge/` (from `product-template/`),
`planning/`, `campaigns/` and assets. ProcurePilot's own product docs are in this repo, outside `marketing/` (`../docs/`).

```bash
npm run new:product -- <product-id> <FolderName>    # creates <FolderName>/knowledge/
npm run sources:sync                               # keeps product and company sources current (config/sources.yaml)
```

This folder (`knowledge/products/`) keeps only the registry and the template.

Company-level facts stay in `knowledge/company/`. A product folder only holds what is true of that product, so a
new product never inherits another product's claims.

## Registry

Keep this table in step with `products:` in `config/marketing-config.yaml`.

| id | Name | Onboarding status | Positioning status | Folder |
|---|---|---|---|---|
| procurepilot | ProcurePilot | `positioning-approved` (2026-10-27) | approved: Arabic-first + verified savings (MD-05, MD-11) | `ProcurePilot/` (knowledge in `ProcurePilot/knowledge/`) |

Onboarding status values: `not-started` → `discovery-in-progress` → `discovery-report-ready` → `positioning-approved` → `active`.

## ProcurePilot: sources

Analysed in discovery on 2026-10-27: see `ProcurePilot/knowledge/discovery-report.md` and `research/source-log.md`
(SRC-011 to SRC-021). Since 2026-10-29 marketing lives inside the product repo; `config/sources.yaml` reports product changes since the last review.

| Source | Where | Notes |
|---|---|---|
| Live app and public landing page | https://procurepilot.iron-sys.com/ | Website registry status `pilot`; sign-in at `/auth/sign-in` |
| Product repository | GitHub `YasserHosny/ProcurePilot`: this repo (marketing is `marketing/`) | Kept current by `npm run sources:sync`; marketing-relevant docs mirrored to `../` |
| Website product copy | `<workspace>/Website/iron-system-next/lib/i18n/en.ts` → `products.items.procurepilot` (and `ar.ts`) | Capabilities, availability line, screen captions |
| LinkedIn About copy | `LinkedIn/company-page/v1.2-ai-solutions_2026-10-22/LINKEDIN-PAGE.md` | Describes the product differently from the website, see `research/discrepancies.md` D-05 |
| Product brand | `ProcurePilot/design-system/` (2026-10-21) and `../docs/brand/` (current) | The app UI now uses the brand (D-08); the 2026-10-21 app stills are out of date |
| Demo videos | `ProcurePilot/demo-video/` (`VERSIONS.md`); newest cuts v2.5 per market in `../docs/gtm/video/cuts/` | v2.2 approved; v2.3 awaiting review; public use of v2.5 not decided (Q-08) |

## Rules for product knowledge

- Each fact carries an evidence label: `verified` (source cited), `interpretation`, `hypothesis` or `unknown`.
- Only `verified` statements may go into public copy; `claims` in `proof-points.md` must be `approved` too.
- Record `last_reviewed` in every file's front matter and re-review before a campaign.
