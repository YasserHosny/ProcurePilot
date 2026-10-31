---
name: campaign-operations
description: "Runs the operational side of an Iron Systems marketing campaign in the Marketing OS: creates campaign folders from the template, tracks deliverables, dependencies, content status, review status and approvals, organises assets from drafts to in-review to approved, and prepares publish-ready packages for organic channels (LinkedIn, Facebook, Instagram, website, video) without publishing them. Use for 'set up a campaign', 'what is the status', 'prepare this for posting', content calendars and distribution plans."
metadata:
  owner: Iron Systems
  version: 1.0.0
  part_of: Iron Systems Marketing OS
  workflows: [D-content-production, publishing]
---

# Campaign operations

Keeps campaigns organised and moving. Paths are relative to `marketting/`.

## Set up

- New campaign: `npm run new:campaign -- <YYYY-MM-product-slug>` (copies `campaigns/campaign-template/`; a product campaign such as `2026-11-procurepilot-…` is created in the product folder, `ProcurePilot/campaigns/`). Fill the front matter in `campaign-brief.md`.
- Add a row to the status board in `campaigns/README.md`.
- Production starts only after G-campaign-strategy is recorded in `approvals.md` (see `workflows/C-campaign-strategy.md`).

## Track

| What | Where | Values |
|---|---|---|
| Deliverables, owners, dates | `content-calendar.md` | status: planned, drafting, in-review, approved, published |
| Review status | `content-calendar.md`, `approvals.md` | not-reviewed, changes-requested, passed |
| Dependencies | `campaign-brief.md` | open, done, blocked |
| Approvals | `approvals.md` | one row per gate, item and version |
| Campaign stage | `campaigns/README.md` | brief, strategy, production, review, approved, published, reporting, closed |

When asked for status, read these files and answer from them; flag anything blocked, overdue, or missing an approval.

## Organise assets

- `assets/drafts/` → `assets/in-review/` (after `campaign-review` is requested) → `assets/approved/` (after G-asset).
- Names: `<channel>-<format>-<slug>-<lang>-v<N>.<ext>`. Never overwrite an approved version.
- Long-lived channel kits keep the existing convention `vMAJOR.MINOR-<name>_<YYYY-MM-DD>/` with a `CHANGES.md` (as in `LinkedIn/company-page/` and `ProcurePilot/demo-video/`).

## Distribution (organic only)

- Plan per channel in `distribution-plan.md`, adapting each asset to the channel's spec in `config/channels.yaml`. Use the upstream `social` skill for platform-native adaptation.
- Every link carries UTM parameters (`analytics/measurement-framework.md`).
- No paid boosts, ads or sponsored placements.

## Publish-ready packages

Follow `workflows/publishing.md`. Prepare: final EN/AR copy, media, alt text, captions, UTM link, hashtags,
proposed date and time, target account. Then **stop and ask** for G-publish for that asset, channel and time.
Publish only on an explicit "yes" for that action and only through a tool that is actually connected; otherwise
hand the package to the owner. Record what was published in the publishing log.

## Don't

- Schedule, post, send or create accounts on your own initiative.
- Move an asset to `approved/` without a recorded approval.
- Mark something reviewed that `campaign-review` hasn't passed.
