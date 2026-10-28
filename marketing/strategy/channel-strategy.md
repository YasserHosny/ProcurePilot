---
status: draft (roles proposed; channel facts verified)
last_reviewed: 2026-10-27
---

# Channel strategy

Channel definitions, formats and quality rules are in `config/channels.yaml`. This file sets each channel's role.

| Channel | Role | State today (verified) | Primary metrics |
|---|---|---|---|
| Website (www.iron-sys.com) | Home of record: services, products, contact. Where organic traffic and inquiries land | Live, EN + AR, Next.js static site; products section with ProcurePilot | Organic sessions, inquiry submissions, product clicks |
| SEO / organic search | Long-term demand capture for problem and solution searches | No sitemap reference, no `metadataBase` yet (D-10); no Search Console access configured | Impressions, clicks, ranking pages |
| LinkedIn (company page `iron-sys`) | Primary B2B channel: thought leadership, product education, announcements | Live, v1.3 cover, About v1.2 (AI Solutions); suggested first post drafted, not known to be posted | Impressions, engagement rate, follower growth, profile and site clicks |
| Facebook | Secondary: reach for Arabic-speaking business audiences, repurposed content | No page found in the workspace (unknown) | Reach, engagement |
| Instagram | Secondary: visual product education, reels | No account found in the workspace (unknown) | Reach, saves, shares, profile visits |
| Video | Format across channels: product demos, explainers, shorts | ProcurePilot demo v2.2 (approved), v2.3 (awaiting review) | Views, average watch time, completion |

## Rules

- LinkedIn first for B2B; Facebook and Instagram get adapted versions, not copies.
- Every piece points to one destination (usually a website page) with UTM parameters (`analytics/measurement-framework.md`).
- Accounts that don't exist yet (Facebook, Instagram) are created by the owner, not by Claude.
- Paid boosts or ads on any channel are out of scope.
