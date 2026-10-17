# ProcurePilot Documentation Index

> Navigation for the product, technical, and operational docs.

---

## Product

- [`product/prd.md`](product/prd.md) — Product Requirements Document (Phase 1–2): goals, personas, functional requirements, NFRs, constraints, open questions.
- [`product/function-business-value.md`](product/function-business-value.md) — Function-by-function business/revenue value, user journey impact, and proof metrics.
- [`product/user-stories.md`](product/user-stories.md) — Persona-driven user stories and end-to-end use cases.
- [`product/ui-mockup-prompts.md`](product/ui-mockup-prompts.md) — Google Stitch text prompts for web and mobile screen mockups.
- [`product/r2.2-mobile-mvp-DESIGN.md`](product/r2.2-mobile-mvp-DESIGN.md) — Mobile MVP design system and screen design (R2.2), with [mockup prompts](product/r2.2-mobile-mvp-ui-mockup-prompts.md) and [mockups](product/r2.2-mobile-mvp-mockups/).
- [`software-product-documentation-roadmap.md`](software-product-documentation-roadmap.md) — Standard checklist of documents from idea to release.

## Orchestration

- [`speckit-plan.md`](speckit-plan.md) — Step-by-step entry point for Speckit: constitution, plan, and Phase 1 specify chunks.

## Technical

- [`architecture/tech-stack-blueprint.md`](architecture/tech-stack-blueprint.md) — Reusable blueprint for the Angular + FastAPI + Supabase + Bunny stack.
- [`architecture/adrs.md`](architecture/adrs.md) — Architecture Decision Records (Angular, Flutter, Supabase, Bedrock/Azure DI, Bunny, Nginx, migrations, monorepo, AI eval, workers app, responsive design, remote DB, extraction fallback, structured logging).
- [`architecture/engineering-spec.md`](architecture/engineering-spec.md) — Low-Level Design: service boundaries, API patterns, data layer, algorithms, state management, security model.
- [`architecture/api-specification.md`](architecture/api-specification.md) — OpenAPI-style contract for Phase 1–2 endpoints.
- [`architecture/data-dictionary.md`](architecture/data-dictionary.md) — Field-level definitions for core entities.
- [`roadmap/procurepilot_roadmap.md`](roadmap/procurepilot_roadmap.md) — Master roadmap: vision, phases, scope, architecture summary.
- [`roadmap/procurepilot_roadmap_visual.html`](roadmap/procurepilot_roadmap_visual.html) — Interactive dashboard visualisation of the roadmap.
- [`product/procurepilot_ai_context.md`](product/procurepilot_ai_context.md) — AI/product context package.

## Quality & Operations

- [`quality/test-strategy.md`](quality/test-strategy.md) — Test pyramid, AI eval plan, E2E scenarios, performance targets.
- [`quality/quotation-upload-review-findings.md`](quality/quotation-upload-review-findings.md) — Manual QA walkthrough of the quotation upload + review flow (staging, 2026-09-04): bugs, missing functions, UX improvements, suggested additions.
- [`operations/release-plan.md`](operations/release-plan.md) — CI/CD, environments, Bunny Magic Containers (production + workers apps), rollback, secrets, IaC.
- [`operations/runbook.md`](operations/runbook.md) — Operations manual, production topology, extraction provider operations, logging & diagnostics, incident response, scaling, backup/restore.
- [`operations/ci-pipeline.md`](operations/ci-pipeline.md) — CI jobs, docs-only skip, sharded end-to-end tests.
- [`operations/local-dev.md`](operations/local-dev.md) — Running the stack locally.
- [`operations/self-hosted-deployment-plan.md`](operations/self-hosted-deployment-plan.md) — Draft plan for running on a local workstation instead of hosted services.
- [`operations/pentest-scope.md`](operations/pentest-scope.md) — Scope for third-party penetration testing.
- [`operations/dependency-audit-allowlist.txt`](operations/dependency-audit-allowlist.txt) — Advisories the dependency audit ignores, with reasons.
- [`operations/mobile-build-release-gate.md`](operations/mobile-build-release-gate.md) — App-size and cold-start checklist to run before any mobile store submission.

## Quality records

- Stage gate: [`quality/g2-stage-gate-evaluation.md`](quality/g2-stage-gate-evaluation.md).
- Release evidence: [022 + Oct 2026 demo fixes](quality/022-and-demo-fix-wave-release-evidence.md) · [R3.4](quality/r3.4-release-evidence.md) · [R4.1](quality/r4.1-release-evidence.md) · [R4.2](quality/r4.2-release-evidence.md) · [R4.3](quality/r4.3-release-evidence.md) (G3 status is recorded in these).
- Security reviews: [R2.5](quality/r2.5-security-review-record.md) · [R3.0](quality/r3.0-security-review-record.md) · [R3.1 accounting](quality/r3.1-accounting-security-review-record.md); critique: [R2.5 hardening](quality/r2.5-security-hardening-critique.md).
- R2.5 baselines and audits: [performance and accessibility](quality/r2.5-performance-accessibility-baseline.md) · [docs gap audit](quality/r2.5-docs-gap-audit.md) · [reporting product critique](quality/r2.5-reporting-hardening-product-critique-agy.md).
- Matching reviews: [functionality critique](quality/matching-functionality-critique.md) · [normalisation audit](quality/matching-normalisation-audit.md) · [resolution-queue critique](quality/match-resolution-queue-critique.md).

## Go-to-market and brand

- [`gtm/README.md`](gtm/README.md) — First-customer plan, execution tracker, demo tenant, demo video, one-pager, company formation research.
- [`brand/README.md`](brand/README.md) — Logo, lockups and brand assets.

## Historical working notes

- [`superpowers/`](superpowers/) — Design notes and implementation plans written while building R1.3, R3.3, R3.4, R4.0 and R4.1. Kept for history; the specs under `specs/` and the code are the current source of truth.
- `operations/parallel-execution-plan-*.md` — Per-wave delegation plans from the build. Historical.

## User-facing

- [`user/user-documentation.md`](user/user-documentation.md) — Help center guides for upload, compare, request, approve, and delivery confirmation (web app).
- [`user/feature-map.html`](user/feature-map.html) — Hierarchical, filterable map of every web-app page and its key features, grouped by module (open in a browser).
- [`user/user-flows.md`](user/user-flows.md) — Route-by-route navigation paths and journey diagrams for the web app.
- [`user/mobile-app-user-documentation.md`](user/mobile-app-user-documentation.md) — Screen-by-screen guide to the mobile app (sign-in, biometric unlock, purchase requests, approvals, delivery confirmation, quality-issue reporting).

---

## Still visual / post-release

- Wireframes / high-fidelity UI — managed in Figma; not in this repo.
- Release notes / changelog — produced per release in the repo's GitHub Releases.
