# Workflow E: website and SEO

**Lead:** `marketing-orchestrator` · **Upstream skills:** `seo-audit`, `ai-seo`, `site-architecture`, `schema`, `copywriting`, `cro`, `competitors` (comparison pages), `link-building` · **Gate:** G-live-change

The website is `<workspace>/Website/iron-system-next` (Next.js static export; copy in `lib/i18n/en.ts` and `ar.ts`;
products in `lib/products/registry.ts`, guide `docs/PRODUCTS.md`). **Read it; don't edit it from here.**
Pushing to its `master` branch deploys to production.

1. Inspect the relevant pages and code (metadata in `app/[[...lang]]/layout.tsx`, `public/robots.txt`), and the live site if browsing is available.
2. Use the SEO, copy and CRO skills that fit the question.
3. Identify technical SEO, content, messaging and conversion opportunities. Known starting point: D-10 in `research/discrepancies.md`.
4. Prioritise by impact × confidence ÷ effort, and state the evidence for each item.
5. Prepare proposed copy (EN + AR) and an implementation brief naming the files and copy keys in the website repo.
6. Hand the brief to a separate website task. It ships through the website repo's own process after explicit approval (G-live-change).
7. Measure outcomes only with real analytics or Search Console data; until then, write "not measured".
