# Campaigns

One folder per campaign, created from `campaign-template/`:

```bash
npm run new:campaign -- 2026-11-procurepilot-<slug>
```

Id format: `YYYY-MM-<product-or-company>-<slug>`. When the product part is a product id from `config/marketing-config.yaml`, the folder is created in that product's folder (e.g. `ProcurePilot/campaigns/`); this folder holds company campaigns. The status board below lists both. The template folder itself is never edited for a real campaign.

## Status board

| Campaign | Product | Objective | Stage | Next gate | Owner |
|---|---|---|---|---|---|
| `ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/` | ProcurePilot | Credibility for founder-led sales: six LinkedIn posts (EN, Egyptian and Gulf Arabic) | review | G-campaign-strategy, G-asset (claims approved) | Yasser |
| `campaigns/2026-11-company-ai-in-production/` | company | Introduce Iron Systems on LinkedIn, X, Facebook, Instagram: four ideas (EN + MSA Arabic) | review | G-campaign-strategy, G-claims (CO-01–CO-10), G-asset | Yasser |

Stages: `brief` → `strategy` → `production` → `review` → `approved` → `published` → `reporting` → `closed`.

## Asset states

`assets/drafts/` (work in progress) → `assets/in-review/` (waiting for `campaign-review` or the owner) →
`assets/approved/` (approved, still **not** published). Publishing is a separate, explicit step (`workflows/publishing.md`).

## Existing channel assets (before the Marketing OS)

Kept in place with their own versioning:
- `LinkedIn/company-page/` (company page kit v1.0 to v1.3; v1.3 cover is live)
- `ProcurePilot/demo-video/` (v2.2 approved, v2.3 awaiting review)
- `ProcurePilot/design-system/` (product brand reference)
