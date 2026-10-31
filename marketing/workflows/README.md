# Workflows

Reusable procedures. `config/workflow-rules.yaml` is the machine-readable version (inputs, outputs, gates);
`marketing-orchestrator` picks the workflow and scales it to the task.

| id | Workflow | Lead skill | Gates |
|---|---|---|---|
| A | [Product onboarding](A-product-onboarding.md) | product-discovery | G-positioning, G-claims |
| B | [Market and competitor research](B-market-and-competitor-research.md) | marketing-orchestrator | none |
| C | [Campaign strategy](C-campaign-strategy.md) | marketing-orchestrator | G-campaign-strategy |
| D | [Content production](D-content-production.md) | campaign-operations | G-asset, G-claims |
| E | [Website and SEO](E-website-and-seo.md) | marketing-orchestrator | G-live-change |
| F | [Review and optimisation](F-review-and-optimization.md) | campaign-review | none |
| P | [Publishing](publishing.md) | campaign-operations | G-publish |

Small tasks (one post, one edit, one question) skip the full workflow: read the relevant knowledge, use the
fitting skill, run the review checklist, and record approval needs.
