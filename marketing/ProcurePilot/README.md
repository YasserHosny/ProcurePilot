# ProcurePilot: marketing folder

Everything marketing holds about ProcurePilot, in one place, inside the product repo (`YasserHosny/ProcurePilot`,
folder `marketing/ProcurePilot/`). Product docs outside `marketing/` belong to the product team.

| Folder | What's in it | Who edits it |
|---|---|---|
| `knowledge/` | Product profile, target audience, claims register, positioning and messaging (drafts), discovery report | Marketing OS (`product-discovery`, owner approvals) |
| `planning/` | Marketing plans for ProcurePilot, and the index of the product team's existing GTM work | Marketing OS |
| `campaigns/` | One folder per ProcurePilot campaign (`npm run new:campaign -- YYYY-MM-procurepilot-<slug>`) | Marketing OS (`campaign-operations`) |
| `demo-video/` | Demo video versions kept for marketing (`VERSIONS.md`) | Add versions; never overwrite |
| `design-system/` | Product brand reference compiled 2026-10-21 (logos, palette, app stills) | Keep; see D-08 for what is out of date |

## Status

| Item | State |
|---|---|
| Onboarding | `positioning-approved` (2026-10-27). Discovery: `ProcurePilot/knowledge/discovery-report.md`; decisions: `ProcurePilot/planning/decisions.md` |
| Positioning | Approved: Arabic-first + verified savings, Egypt and Saudi Arabia |
| Claims | 14 approved (C-01 to C-12, C-14, C-15); C-13 held |
| Campaigns | None |

## Staying current

The product changes almost daily. Before any ProcurePilot work, `git pull` the repo, then:

```bash
npm run sources:sync
```

It lists what changed in the product docs and app copy (`../docs/gtm/`, `../docs/brand/`, `../packages/i18n/`), the
Iron Systems website and brand since the last review, in `research/source-updates/latest.md`. Update `knowledge/`
(and retire claims that stopped being true), then:

```bash
npm run sources:sync -- --mark-reviewed
```

Sources and watched paths: `config/sources.yaml`.
