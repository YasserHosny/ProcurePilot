# Measurement framework

Upstream skills: `analytics` (tracking plans), `ab-testing` (experiments).

## From objective to metric

| Objective | Leading indicators | Outcome indicators |
|---|---|---|
| Brand awareness | Impressions, reach, follower growth | Branded search (when Search Console exists), direct traffic |
| Product education | Engagement rate, carousel completion, video watch time | Product page visits, product clicks |
| Demand generation | Clicks to website, landing page visits | Inquiries, pilot access requests |
| Thought leadership | Comments, shares, saves | Inbound mentions, inquiries referencing content |
| SEO | Indexed pages, impressions | Organic clicks, inquiries from organic |

Every campaign picks **one** primary objective and **two or three** metrics in its `measurement-plan.md`.

## UTM convention

`utm_source` = linkedin | facebook | instagram | youtube | newsletter | partner
`utm_medium` = organic-social | organic-search | referral | video
`utm_campaign` = campaign id (e.g. `2026-11-procurepilot-pilot-launch`)
`utm_content` = asset id (e.g. `A-03`)

Keep lowercase, hyphens, no spaces. Never put personal data in UTM values.

## Baselines and targets

- First month of any channel = baseline. Targets set before a baseline exists are hypotheses and are labelled so.
- Benchmarks from outside sources need a citation; don't use remembered industry averages.

## Data availability (2026-10-27)

| Source | Available? |
|---|---|
| LinkedIn page analytics | Owner has access in LinkedIn; no export in the workspace |
| Website analytics | None found in the website repo |
| Search Console | Not configured (unknown) |
| Facebook / Instagram insights | Accounts not found |

Workflow F requires real data; until these exist, reports say "not measured".
