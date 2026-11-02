# Workflow A: product onboarding

**Lead:** `product-discovery` · **Upstream skills:** `product-marketing`, `customer-research`, `competitor-profiling`, `marketing-psychology` (for objections) · **Gates:** G-positioning, G-claims

| # | Step | Output |
|---|---|---|
| 1 | Add the product's repo to `config/sources.yaml` and run `npm run sources:sync`. Create the knowledge folder: `npm run new:product -- <id> <FolderName>`; set `onboarding_status: discovery-in-progress` in `config/marketing-config.yaml` and `knowledge/products/README.md` | `<Product>/knowledge/` |
| 2 | Inspect company and product materials: repo docs and code, live app and landing page, website copy, existing assets in `marketing/`. Log every source | `research/source-log.md` |
| 3 | Review brand identity and approved communication (company and product sub-brand) | notes in `product-profile.md` |
| 4 | Decide which upstream skills help, and say why | Discovery Report, Method section |
| 5 | Research audience, use cases and alternatives (web research with dates; no guessing) | `target-audience.md`, `research/competitor-analysis/<id>/` |
| 6 | Document verified capabilities with evidence (screen, doc, code path) | `product-profile.md`, `proof-points.md` (status `proposed`) |
| 7 | Draft positioning and messaging **hypotheses** | `product-positioning.md`, `messaging-matrix.md` (status `draft`) |
| 8 | Record unknowns, discrepancies and questions for the owner | `product-profile.md` section 9, `research/discrepancies.md` |
| 9 | Write the Product Discovery Report from `templates/product-discovery-template.md` | `<Product>/knowledge/discovery-report.md` |
| 10 | Request review. Nothing is final until G-positioning and G-claims are recorded | status `discovery-report-ready` |

Done when every capability is labelled V / I / H / ?, every V has a source, and the report lists the decisions the
owner needs to make.
