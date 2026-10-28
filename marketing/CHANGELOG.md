# Changelog

## 2.0.0 · 2026-10-29

- Upstream skills are installed without their `evals/` test folders (`scripts/sync-upstream-skills.mjs`): a sample prompt there carries a fake key that the repo's secret scan (gitleaks) flags.
- **Moved into the ProcurePilot repo** as `marketing/` (owner request; G-14, PPS-111; branch `docs/marketing-os`). Product docs are linked from the repo (`../docs/gtm`, `../docs/brand`, `../packages/i18n`) instead of mirrored; `config/sources.yaml` reads this repo (warns when behind origin) and treats the website and brand folders as optional workspace sources. Brand files needed for production copied to `brand/iron-systems/`. Demo video v2.2 (pre-limiter mix) not copied: the repo holds the corrected cut.
- LinkedIn About updated on the live page (EN; AR added as a page language), 2026-10-29.
- LinkedIn images v2 (`scripts/render-linkedin-v2.cjs`): editorial, real material only (v2.5 frames, round-6 WhatsApp quote photo), following `docs/gtm/video/motion-style.md`; A-05 and A-06 now made from real Egypt frames. Text pass removed AI-sounding lines (A-02, CP-01).

## 1.3.0 · 2026-10-29

- Senior review of the 10 LinkedIn posts (pass with changes; text fixes applied) and visual plans per campaign.
- LinkedIn language rule MD-13: one bilingual post per idea, Arabic first; bilingual blocks added to every post.
- Image production: `scripts/render-linkedin-launch.cjs` (Playwright, dev dependency) renders CP-01 to CP-04 and A-01 (carousel PNG + PDF), A-02, A-03, A-04 thumbnail in each identity. A-05 and A-06 wait for Egypt screens.
- LinkedIn launch order in `strategy/company-marketing-plan.md`.

## 1.2.0 · 2026-10-28

- **Company marketing started:** `strategy/company-marketing-plan.md` (decisions CD-01 to CD-04: both goals with ProcurePilot as proof, AI solutions first, Egypt + Saudi, LinkedIn page + X + Facebook + Instagram); company claims register `knowledge/company/proof-points.md` (CO-01 to CO-10, proposed); profile kit for the new accounts `Social/profiles/v1.0_2026-10-28/`; first company campaign `campaigns/2026-11-company-ai-in-production/` (four ideas, EN + MSA Arabic). X (Twitter) added as an organic channel.
- C-16 and C-17 approved (MD-12).

- **Owner decisions** MD-01 to MD-11 (`ProcurePilot/planning/decisions.md`): positioning approved (Arabic-first +
  verified savings), claims C-01 to C-12, C-14, C-15 approved, Egypt + Saudi, founder voice, pricing private.
- **Research (Workflow B):** competitor files for ProcurePilot (Supy, Foodics, OneOrder, Precoro/Odoo) and a
  summary in `research/market-research/`; D-13 ("English-only competitors" does not hold).
- **Campaign** `ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/`: six LinkedIn posts (EN, Egyptian and
  Gulf Arabic), in review. LinkedIn About v1.4 (product paragraph removed), ready to paste.
- **Latest product data:** mirror extended to the demo round records and 80 real screens (Saudi ar/en, Rawaq English,
  Liffey) and the Egypt rounds; product profile section 11 (demo workspaces and assets); Q-07 and Q-08 answered
  from the live privacy policy and the approved v2.5 cuts; proposed claims C-16 (one RFQ to every supplier) and C-17
  (no AI training on customer data). Sources SRC-022 to SRC-033.

## 1.1.0 · 2026-10-27

ProcurePilot discovery (Workflow A) and a way to stay current with the product and the company.

- **One folder per product.** `ProcurePilot/` now holds everything for the product: `knowledge/` (moved from
  its first location under `knowledge/products/`), `planning/`, `campaigns/`, the existing `demo-video/` and `design-system/`
  (unchanged except a pointer note in `VERSIONS.md`), and `product-repo/`, a generated read-only mirror.
  `new:product` takes a folder name; `new:campaign` puts product campaigns in the product folder. CLAUDE.md rule 10.
- **Source sync.** `config/sources.yaml` and `npm run sources:sync`: pulls the product repo clone (fast-forward only,
  never pushes), mirrors its GTM, brand, product, user docs and landing copy into `../`
  (`--with-video` adds the latest demo cuts), reads the website repo's HEAD and hashes the brand folder, and reports
  changes since the last review in `research/source-updates/latest.md`. `--mark-reviewed` moves the baseline.
  CLAUDE.md "Before any marketing work" step 0.
- **ProcurePilot knowledge:** product profile, target audience, 14 proposed claims, three positioning hypotheses
  (draft), messaging matrix (draft, from live landing copy), discovery report. Status `discovery-report-ready`.
- **Research:** sources SRC-011 to SRC-021; D-05 to D-08 updated (D-05 and D-08 resolved for knowledge, D-06 and
  D-07 need the owner); new D-11 (landing says Egypt, hero shows SAR) and D-12 (hosted app runs on staging).
- **Validator:** requires `config/sources.yaml` and the sync script; checks that products' sources exist and that
  `knowledge_dir` sits in the product folder; generated mirrors are not link-checked (still secret-scanned).

## 1.0.0 · 2026-10-27

Marketing OS built inside the existing `marketting/` folder. Existing `LinkedIn/` and `ProcurePilot/` assets left
unchanged; `README.md` extended (its original lines kept).

- **Knowledge:** company profile, brand identity summary and brand voice from Branding/Identity-v3 v3.3, the website
  copy (git a1904c7) and the LinkedIn page v1.2/v1.3. Audience files hold hypotheses only (no customer evidence in
  the workspace). Product registry and reusable `product-template/`.
- **Research:** source log (SRC-001 to SRC-010) and discrepancy log (D-01 to D-10).
- **Strategy:** principles, positioning framework, draft content and channel strategy.
- **Config:** marketing-config, channels (all organic), workflow-rules (7 gates, 11 quality checks, 7 workflows), upstream-skills.
- **Workflows:** A to F and publishing.
- **Campaigns:** `campaign-template/` (13 files, asset states drafts / in-review / approved).
- **Templates, analytics, integrations:** 7 templates; metrics, measurement and reporting; integration registry.
- **Skills:** 4 custom skills; 24 upstream skills from coreyhaines31/marketingskills at commit
  `17772c7a80b7b8c7a47af30f648374cd8bd8adc5` (v2.13.5), installed by `scripts/sync-upstream-skills.mjs` with a hash lock.
- **Shared context:** `.agents/product-marketing.md` v1.0 (company level; ProcurePilot pending discovery).
- **Checks:** `scripts/validate.mjs` and `tests/`.
