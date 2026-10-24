# Security policy

## Reporting a vulnerability

Email **security@iron-sys.com**. Please do not open a public GitHub issue, pull request or
discussion for a suspected vulnerability. This repository is public.

Include what you can:

- the affected component (API, web app, mobile app, a worker) and URL or file
- steps to reproduce, or a proof of concept
- the impact you expect, for example reading another tenant's data

We aim to acknowledge a report within 2 business days and to agree a fix and disclosure timeline
with you after that. Please give us a reasonable chance to fix the issue before disclosing it.

## Scope

In scope: this repository and the hosted ProcurePilot app at `procurepilot.iron-sys.com`.
Cross-tenant data access is the most serious class of issue for us. Each customer workspace must
only ever see its own data.

Out of scope: denial-of-service and volumetric testing, social engineering, and findings in
third-party services we use (Supabase, Mailgun, bunny.net). Report those to the vendor.

Test only against accounts and workspaces you own, and stop as soon as you reach someone else's data.

## Supported versions

Only the current `main` branch and the hosted deployment built from it receive security fixes.
