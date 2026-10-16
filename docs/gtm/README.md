# Go-to-market — first customer

Everything for landing ProcurePilot's first pilot customer (Egypt, multi-branch F&B/retail).
Start with [`gtm-execution-plan.md`](gtm-execution-plan.md): current state, task list with
Jira keys, and the handoff log.

## In this folder

| File | What it is |
|---|---|
| [`first-customer-gtm-plan.md`](first-customer-gtm-plan.md) | The plan: ICP, fit and currency gaps (C1–C5, G1–G5), demo walkthrough, pilot prerequisites, sales-pipeline stages |
| [`gtm-execution-plan.md`](gtm-execution-plan.md) | Execution tracker and cold-start handoff for any model: Jira setup, tasks, dependencies, handoff log |
| [`one-pager/ProcurePilot-one-pager.pdf`](one-pager/ProcurePilot-one-pager.pdf) | Approved one-pager, 2 × A4 (Arabic, English) — PP-8 |
| [`demo-tenant/`](demo-tenant/) | Demo tenants plan (PP-5 / G-1): one clean hosted tenant per vertical, restaurant dataset (Sanad Kitchens: branches, suppliers, ~30-item EGP catalogue), recording scenario — **draft** |
| [`video/`](video/) | Demo video spec and decisions (PP-6): style, storyboard with music map, beat-locked logo sting, end card, audio sources and licences, beat data, render scripts |
| [`test-fixtures/egypt-quotes/`](test-fixtures/egypt-quotes/) | 5 synthetic Egyptian supplier quotes + `expected.json` for extraction testing (spec 022 US2, PP-3). Fictional suppliers, each marked TEST FIXTURE |

## Live documents (source of truth — edit there, not here)

| Document | Link | Jira |
|---|---|---|
| Pilot agreement (EN + AR, Annex A baseline) | <https://claude.ai/code/artifact/7f1d9481-a2a7-43a7-a0e4-b397c64e042b> | PP-10 |
| Outreach DM script (approved) | <https://claude.ai/code/artifact/30523eee-168f-4a1c-b7ac-dcb50cd9ded8> | PP-9 |
| One-pager design canvas | <https://claude.ai/artifact/6FPMTMHy37esXbEAZgQmmF> | PP-8 |
| Logo + video animation canvas (logo exploration, sting, end cards) | <https://claude.ai/artifact/CYVrF8484uFkpiJTqcGPdS> | PP-6 |
| Jira: ProcurePilot (non-code tasks) | <https://yasser-hosny.atlassian.net/jira/core/projects/PP/board> | — |
| Jira: Sales Pipeline | <https://yasser-hosny.atlassian.net/jira/core/projects/SP/board> | — |

When the one-pager canvas changes, re-export the PDF into `one-pager/`.

## Convention

New GTM / sales / pilot documents go in this folder. Product code specs stay in `specs/`.
