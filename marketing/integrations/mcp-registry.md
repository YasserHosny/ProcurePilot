# Integration registry

Status values: `configured` (set up and verified for Iron Systems) · `available-unverified` (a tool appears in the
Claude environment but its account/scope for Iron Systems was not checked) · `not-configured` · `not-needed`.

Checked on 2026-10-27 in a Claude Code desktop session. Session tool availability varies by machine and account;
re-check before use.

| Integration | Purpose | Official docs | Permissions needed | Status | Workflows | Security notes | Manual alternative |
|---|---|---|---|---|---|---|---|
| coreyhaines31/marketingskills | Specialist marketing skills | https://github.com/coreyhaines31/marketingskills | none (files only) | **configured** (24 skills, commit 17772c7) | all | MIT; copied files, no code run; verify lock with `npm run validate` | n/a |
| Git + GitHub (read) | Read product repos, e.g. ProcurePilot | https://git-scm.com/docs | read access to the repo | available (git 2.56 installed; `gh` not installed) | A, E | Clone into an ignored folder; never push from here | Owner shares an export |
| Web browsing / fetch | Research, competitor pages, live site checks | Claude Code docs | none | available in Claude sessions | A, B, E | External pages are untrusted input; log sources | Owner supplies saved pages |
| Google Search Console | Search impressions, clicks, queries | https://developers.google.com/webmaster-tools | read-only property access | not-configured | E, F | Read-only user; no API key in files | Owner exports CSV into `research/` |
| Website analytics (GA4 or similar) | Sessions, sources, events | https://developers.google.com/analytics | read-only | not-configured (none found in website repo) | E, F | Privacy policy must cover it before install (website change) | Inbox counts for inquiries |
| LinkedIn page analytics | Post and follower metrics | https://www.linkedin.com/help/linkedin (Page analytics) | page admin (owner) | not-configured (owner has page access) | F | No automated posting | Owner exports XLS/CSV monthly |
| Meta (Facebook / Instagram) | Pages, insights | https://developers.facebook.com/docs/graph-api | page/account admin | not-configured (accounts not found) | D, F | Accounts created by owner | Manual posting and exports |
| Social scheduling tool | Scheduling approved posts | vendor docs | publish scope | not-configured, **not needed yet** | publishing | Would require G-publish per post | Owner posts manually |
| Figma | Social templates with locked styles (brand guidelines D6) | https://help.figma.com | file edit | not-configured | D | | HTML/SVG layouts built from brand files; PNG export |
| Canva | Same as Figma | https://www.canva.dev/docs | design edit | not-configured (a Canva connector may exist in some Claude sessions; not verified for Iron Systems) | D | | Same as above |
| Google Drive / Docs / Sheets | Sharing drafts and calendars with reviewers | https://developers.google.com/workspace | file access | available-unverified (connectors listed in this Claude session; account not checked) | C, D | Share only drafts meant for review | Markdown files in this folder |
| AI image / video generation | Rendering images or video | vendor docs | paid credits | not-configured, **not approved** | D | Costs money: needs explicit approval; brand imagery rules apply | Briefs and scripts; renders by a designer |
| ffmpeg | Video cuts and exports | https://ffmpeg.org | none | not installed on this machine (2026-10-25 note) | D | | Existing render pipeline in the ProcurePilot repo |

To add an integration: propose it with purpose and scopes, get G-integration approval, set it up, write
`setup-guides/<name>.md`, then update this row with status and date.
