# Workflow C: campaign strategy

**Lead:** `marketing-orchestrator` · **Upstream skills:** `content-strategy`, `launch` (announcements), `copywriting` (core message), `analytics` (measurement), `marketing-psychology` · **Gate:** G-campaign-strategy

Precondition: the product's positioning is `approved`. Company-level campaigns use the approved company copy
(`knowledge/company/`).

1. Create the folder: `npm run new:campaign -- <YYYY-MM-product-slug>` (product campaigns land in the product folder, e.g. `ProcurePilot/campaigns/`).
2. **Objective and audience** in `campaign-brief.md`: one primary objective, the persona(s), the problem and the desired outcome.
3. **Core message and proof:** inherit from the product messaging matrix; write the campaign angle in `messaging-matrix.md` with proof ids.
4. **Channels:** choose from `config/channels.yaml` (organic only) and say why each one is in.
5. **Pillars and distribution:** `strategy.md`, `distribution-plan.md` and a first `content-calendar.md`.
6. **Measurement:** objective → metrics → baseline → target in `measurement-plan.md`. Targets are hypotheses until a baseline exists.
7. **Dependencies and approvals:** list them in `approvals.md` and request G-campaign-strategy.
8. Production starts only after the gate is recorded.
