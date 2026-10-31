# ProcurePilot campaigns

One folder per ProcurePilot campaign, created from `campaigns/campaign-template/`:

```bash
npm run new:campaign -- 2026-11-procurepilot-<slug>
```

A campaign id whose product part is `procurepilot` is created here; company campaigns stay in `campaigns/`.
Rules, statuses and the approval flow are in `campaigns/README.md`.

| Campaign | Stage | Next gate |
|---|---|---|
| `ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/` | approved 2026-10-29; posting 2026-11-03 to 2026-11-22 (`POSTING.md`) | G-publish per post (Yasser) |
