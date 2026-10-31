# ProcurePilot — Architecture Decision Records (ADRs)

> Key technical decisions and their rationale. Companion to the [Master Roadmap](../roadmap/procurepilot_roadmap.md) and [Tech Stack Blueprint](./tech-stack-blueprint.md).

---

## ADR-001 — Web Frontend Framework: Angular 19

- **Status:** Accepted
- **Context:** Need a stable, enterprise-friendly SPA with strong TypeScript support, a mature component library, and a single language across web and mobile-generated types.
- **Options considered:** Next.js (App Router), React + Vite, Angular.
- **Decision:** Angular 19 (latest stable) with Angular Material, Angular CDK, SCSS, RxJS, and Angular Reactive Forms.
- **Consequences:**
  - Strong out-of-the-box tooling, routing, forms, and i18n path.
  - NgModule-based structure aligns with the blueprint.
  - Nginx serves the built SPA with SPA fallback.
- **Amended 2026-10-24 (PP-29):** upgraded to Angular 22 + Angular Material 22 (TypeScript 6.0,
  Node 24 to build). Reason: the new design system's Material theme uses the M3 API, including the
  tonal button that first shipped in Material 20, so building it once on the current major is
  cheaper than building it on 19 and porting it. Builders moved from `@angular-devkit/build-angular`
  (deprecated) to `@angular/build`; Karma stays. Every component with state carries
  `ChangeDetectionStrategy.Eager`, which keeps pre-22 behaviour under Angular 22's OnPush default.

## ADR-002 — Mobile Framework: Flutter

- **Status:** Accepted
- **Context:** Single codebase for iOS and Android; native UI performance; store distribution.
- **Options considered:** React Native via Expo, native iOS + Android, Flutter.
- **Decision:** Flutter (Dart) with OpenAPI-generated Dart types.
- **Consequences:**
  - One mobile engineering hire instead of two native teams.
  - Mobile container in CI is build-only; the runtime artifact is an App Store / Play Store binary.
  - Shared domain contracts generated from the same OpenAPI spec as web.

## ADR-003 — Database & Auth Platform: Supabase

- **Status:** Accepted
- **Context:** Need managed Postgres, Auth, Storage, and Realtime with minimal initial infrastructure work.
- **Options considered:** Self-managed PostgreSQL + custom Auth, Managed provider, Supabase.
- **Decision:** Supabase Postgres 17 with Auth, Storage, Realtime, and Row-Level Security.
- **Consequences:**
  - No hand-rolled auth in Phase 1.
  - Future path to self-managed Postgres remains available.
  - Python backend uses `supabase-py` 2.11.0; frontend uses `@supabase/supabase-js` ^2.105.

## ADR-004 — Document Intelligence: AWS Bedrock + Azure Document Intelligence

- **Status:** Accepted
- **Context:** Need template-free extraction from PDFs/images with a cost-controlled fallback.
- **Options considered:** Frontier VLM only, PaddleOCR/Tesseract, AWS Bedrock (Claude 3 Haiku) + Azure DI fallback.
- **Decision:** Primary extraction via AWS Bedrock (Claude 3 Haiku); fallback to Azure Document Intelligence for cost control and layout heuristics.
- **Consequences:**
  - Strict JSON schema with field-level confidence.
  - Structured inputs (Excel/CSV) bypass LLM calls.
  - Cost per document tracked; caching by document hash.

## ADR-005 — Container Hosting: bunny.net Magic Containers

- **Status:** Accepted
- **Context:** Need managed containers with minimal ops headcount pre-scale.
- **Options considered:** Vercel, Fly.io, AWS ECS, bunny.net Magic Containers.
- **Decision:** bunny.net Magic Containers for Web FE (Nginx, port 80) and Backend (Uvicorn, port 8000); mobile CI produces store binaries.
- **Consequences:**
  - Containers share a network namespace; frontend uses `BACKEND_HOST=localhost`.
  - CI deploys via `BunnyWay/actions/container-update-image` with GHCR images.
  - Three path-filtered workflows: backend, frontend, mobile build.

## ADR-006 — Reverse Proxy: Nginx

- **Status:** Accepted
- **Context:** Angular SPA needs `/api/` proxy to backend, SPA fallback, and security headers.
- **Options considered:** Traefik, Caddy, Nginx.
- **Decision:** Nginx Alpine in the frontend container; config template injects `BACKEND_HOST` at runtime.
- **Consequences:**
  - SPA fallback with `try_files`.
  - Security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options).
  - Gzip and cache control for CSS/index.html.

## ADR-007 — Schema Migrations: Versioned SQL + Supabase CLI

- **Status:** Accepted
- **Context:** Need auditable, reproducible schema evolution against Supabase Postgres.
- **Options considered:** SQLAlchemy + Alembic, versioned SQL files, Supabase CLI migrations.
- **Decision:** Application-managed versioned SQL files in `<project>-backend/migrations/`; Supabase CLI migrations for local dev.
- **Consequences:**
  - Explicit, reviewable migrations.
  - No runtime ORM dependency; backend uses `supabase-py` and Pydantic schemas.

## ADR-008 — Monorepo Layout: Apps + Packages + Services

- **Status:** Accepted
- **Context:** Web, mobile, backend, shared types, and AI workers in one repo.
- **Options considered:** Separate repos per service, blueprint `formcraft-backend`/`formcraft-frontend` root directories.
- **Decision:** `apps/` (web, mobile, api), `packages/` (domain-types, ui, validation, i18n), `services/` (extraction, matching, optimiser), plus `ml/`, `infra/`, `.github/workflows/`.
- **Consequences:**
  - Shared types and validation generated from OpenAPI.
  - Turborepo + pnpm for JS; uv for Python.
  - CI path-filtered workflows keep builds fast.

## ADR-009 — AI Evaluation Harness in CI

- **Status:** Accepted
- **Context:** Prevent silent regression on extraction and matching accuracy.
- **Options considered:** Manual QA only, periodic offline evals, CI gate on every model/prompt change.
- **Decision:** Versioned benchmark datasets; any model, prompt, or threshold change runs the eval suite; precision regression blocks merge.
- **Consequences:**
  - Quality of AI outputs is measurable and enforced.
  - Dataset grows continuously from review-queue corrections.

## ADR-010 — Recorded exception: proceeding to Phase 2 without a passed G1 gate

- **Status:** Accepted (exception, not a principle amendment)
- **Context:** The constitution's Development Workflow and Phase Discipline section states stage
  gates are binding — "Phase N+1 code MUST NOT be written until gate G(N-1) is passed and
  recorded" — and non-compliance blocks merge "unless an explicit, recorded exception is granted
  by the project owner." Phase 1 (chunks 4.1–4.6 / R1.0–R1.5) merged to `main` on 2026-08-22 (PR
  #2), completing Phase 1's engineering scope. The roadmap's G1 → Phase 2 exit criteria (§2.3) —
  matching precision and extraction accuracy targets met against the Phase 0 benchmark datasets,
  ≥10 verified savings, ≥8 paying customers on the self-serve product — are business/usage
  milestones that have not been independently evidenced anywhere in this repo.
- **Decision:** The project owner explicitly chose to proceed into Phase 2 build work on
  2026-08-22 without that evidence, overriding the gate rather than waiting for it. This is
  recorded here per the constitution's own exception-granting mechanism, not treated as the gate
  having been passed.
- **Consequences:**
  - `CLAUDE.md`'s Current phase section reflects this exception and Phase 2 as active.
  - The G1 exit criteria remain unmet; if usage data later contradicts the product assumptions
    Phase 2 is being built on (accuracy, retention, willingness to pay), that risk was knowingly
    accepted at this decision point, not discovered late.
  - Future phase transitions (G2 → Phase 3, G3 → Phase 4) still default to requiring their gates
    unless a similar explicit, recorded exception is granted.

## ADR-011 — Separate bunny.net App for Background Workers

- **Status:** Accepted
- **Context:** The extraction worker and Redis need to run alongside the API but should not
  share compute resources or restart cycles with the production app.
- **Options considered:** (a) Add worker + Redis containers to the production app — simplest
  but couples deployments and shares CPU/RAM. (b) Separate bunny.net app — independent scaling,
  isolated restarts, but requires cross-app networking. (c) External VPS — full control but
  more ops overhead.
- **Decision:** Separate bunny.net app (`procurepilot-workers`) with the extraction worker and
  Redis in a shared network namespace. The production app's backend connects to Redis via the
  workers app's Anycast IP.
- **Consequences:**
  - Worker deployments do not restart the API or frontend.
  - Cross-app communication uses bunny.net Anycast IPs, not DNS names.
  - A fourth GitHub secret (`BUNNY_WORKERS_APP_ID`) is required.
  - The `REDIS_URL` on the backend container differs from the worker's `REDIS_URL`
    (`<anycast-ip>:6379` vs `localhost:6379`).

## ADR-012 — Responsive-First Web Design with Shared Breakpoints

- **Status:** Accepted
- **Context:** The web SPA must be usable on mobile, tablet, and desktop viewports. Many
  procurement users access the system from phones or tablets on the shop floor.
- **Decision:** A shared SCSS breakpoints mixin (`apps/web/src/styles/_breakpoints.scss`)
  defines three tiers: mobile (≤ 599px), tablet (600–959px), desktop (≥ 960px). CSS logical
  properties are mandatory for RTL support.
- **Consequences:**
  - Every component includes responsive adjustments via `@include bp.mobile { ... }`.
  - Layouts collapse gracefully: side-by-side → single column, reduced padding, condensed
    fonts.
  - No horizontal overflow on any viewport width.
  - RTL (Arabic) layout is a first-class citizen, not an afterthought.

## ADR-013 — Remote-Only Database (No Local DB Build)

- **Status:** Accepted
- **Context:** Supabase provides Postgres, Auth, Storage, and Realtime as a hosted service.
  Building and maintaining a local Postgres instance duplicates infrastructure that Supabase
  already manages.
- **Decision:** The application uses hosted Supabase exclusively. Local development uses the
  Supabase CLI (`supabase start`) for a local stack, or connects directly to the hosted
  project. Docker Compose does not include a Postgres service.
- **Consequences:**
  - Developers run `supabase start` instead of `docker compose up` for database services.
  - Migrations are the single source of truth for schema.
  - No database container to build, version, or maintain in Docker Compose.
  - Development requires internet access (for hosted project) or the Supabase CLI (for local).

## ADR-014 — Extraction Provider Fallback Chain

- **Status:** Accepted
- **Context:** The extraction worker supports multiple AI providers. Bedrock (Claude 3 Haiku)
  is the primary provider; Azure Document Intelligence is the fallback. Provider failures
  should not block extraction entirely.
- **Decision:** When `EXTRACTION_PROVIDER_MODE=bedrock`, the worker tries Bedrock first. If
  Bedrock throws any exception, it silently falls back to Azure DI. The provenance metadata
  records which provider actually performed the extraction.
- **Consequences:**
  - Extraction continues even when Bedrock credentials are misconfigured or the service is
    unavailable.
  - The fallback is silent — operators must check provenance metadata to know which provider
    ran. Monitoring should alert when `method != bedrock` despite the mode being `bedrock`.
  - The stub provider (`FakeExtractionProvider`) misleadingly sets `method: "bedrock"` in
    provenance — always verify `model_version` is not `stub-provider-v1`.

## ADR-015 — Structured JSON Logging with Trace IDs and Secret Redaction

- **Status:** Accepted
- **Context:** Container-based deployments write to stdout; structured logs are essential for
  filtering, correlation, and aggregation. Sensitive data (tokens, API keys) must never appear
  in log output.
- **Options considered:** (a) Plain text logging with grep. (b) Structured JSON with manual
  field construction. (c) Structured JSON via a custom `logging.Formatter` with middleware-
  injected trace IDs and automatic secret redaction.
- **Decision:** Option (c). A `JsonFormatter` in `shared/logging.py` emits one JSON object
  per log record to stdout. `TraceIdMiddleware` propagates or generates a UUID4 trace ID per
  request via `ContextVar`, included in every log record and every error response. A `redact()`
  function scrubs sensitive dict keys and string patterns before output.
- **Consequences:**
  - Every API log record is machine-parseable and carries a trace ID for request correlation.
  - Secrets are scrubbed automatically — no per-call redaction needed by module code.
  - Both the API and the extraction worker share the `procurepilot-logging` package,
    ensuring identical log format across all services.
  - Log level is configurable at deploy time via `API_LOG_LEVEL` without code changes.

## ADR-016 — G2 Stage Gate Evaluation & Transition to Phase 3

- **Status:** Accepted (recorded transition and evaluation)
- **Context:** Phase 2 ("Workflow Expansion", releases R2.0–R2.5) engineering scope completed with
  the close-out of Wave 18 (`012-reporting-hardening`). All technical gates passed in CI run
  `35146371910` with 1000 backend tests, 343 web unit tests, Playwright E2E suites, axe-core WCAG
  2.1 AA a11y across English and Arabic, and RLS tenant isolation all verified green. The roadmap's
  G2 exit criteria (§2.3) require ≥70% workflow-origination, mobile adoption target met, and ≥90%
  retention — business adoption metrics that depend on live multi-month pilot cohort usage.
- **Decision:** Formally record software completion of Phase 2 in `docs/quality/g2-stage-gate-evaluation.md`
  and authorize the engineering transition into Phase 3 ("Connected Procurement", starting with R3.0
  Automated Ingestion: email forwarding + WhatsApp capture), mirroring the precedent established by
  ADR-010 for Phase 1→Phase 2.
- **Consequences:**
  - `AGENTS.md` and `CLAUDE.md` updated to reflect Phase 2 complete and Phase 3 initiation.
  - Development may proceed into Phase 3 specification, architecture, and implementation.
  - Third-party penetration testing is scoped in `docs/operations/pentest-scope.md` and ready for
    external engagement prior to general commercial availability.

## ADR-017 — Grounded Procurement Analyst Retrieval Architecture

- **Status:** Accepted
- **Context:** R4.2 introduces the Grounded Procurement Analyst feature. To comply with Constitution Principle I (Evidence Over Assertion) and ensure deterministic, auditable answers, the system must separate question understanding (intent classification) from answer generation (factual content, numbers, and citations).
- **Decision:** Question understanding for R4.2 reuses the existing Bedrock/Claude provider pattern from ADR-004 (initial provider choice) and ADR-014 (fallback chain) — no new LLM provider was introduced. The language model in `intent.py`'s `BedrockIntentProvider` ONLY classifies the question into a category + entities (FR-005) — it never generates the answer's factual content, numbers, or citations; those come exclusively from `retrieval.py`'s deterministic pure functions.
- **Consequences:**
  - The feature provides retrieval-augmented question routing, not free generation.
  - The `IntentResult` Pydantic model enforces this at the boundary, ensuring no free text leaks through from the LLM.
  - Calculation and formatting logic inside `retrieval.py` guarantees replay-determinism (Constitution Principle II) and relies on explicit typed input objects passed by the caller.

## ADR-018 — Reuse Mailgun for Outbound RFQ Dispatch

- **Status:** Accepted
- **Context:** R4.3 introduces outbound RFQ email dispatch. The inbound side of email ingestion already runs on Mailgun (via webhook security configured with `MAILGUN_SIGNING_KEY`). We need an email provider to dispatch these outbound RFQs. Introducing a second transactional email vendor just for outbound would duplicate domain verification and configuration complexity.
- **Decision:** Outbound RFQ dispatch reuses the Mailgun vendor relationship already established for inbound ingestion, rather than introducing a second transactional-email vendor. A thin outbound wrapper (`MailgunMailer`) will interact with the Mailgun Messages API using `MAILGUN_API_KEY` and `MAILGUN_SENDING_DOMAIN`. Note that `ingestion_email_provider` currently defaults to `"stub"` in this deployment; Mailgun is the chosen vendor via real webhook-verification code, but not yet a fully live-in-production inbound integration.
- **Consequences:**
  - One email vendor for both inbound and outbound routing.
  - Reduced DNS and credentials management overhead.
  - Mailgun send failures must leave the RFQ recipient in a `draft` status, never silently marking it as `sent`.

## ADR-019 — Evaluate RFQ Auto-Preparation Guardrails at Match-Decision Time

- **Status:** Accepted
- **Context:** R4.3 evaluated auto-preparation guardrails inline in `process_inbound_email()`,
  immediately after a supplier's reply was captured. At that point the reply has no extracted
  lines and no product matches: extraction is asynchronous (the extraction worker), and matching
  only runs once a human has confirmed the quotation in Quotation Review (`status='reviewed'`).
  Every candidate therefore failed `all_lines_matched`, and guardrail-triggered auto-preparation
  could never fire on a real captured response. The R4.3 end-to-end test hid this by
  monkeypatching a pre-matched line into the capture call. Found during the T047 live hosted
  walkthrough.
- **Decision:**
  - Guardrails are evaluated when a `match_decision` is created — the only point at which a
    response's eligibility can actually change. Both decision paths (automatic acceptance and
    human resolution in Match Resolution) enqueue a `guardrail_eval` job on `ingestion_jobs` for
    quotations linked to an RFQ response; the standing email-ingestion worker evaluates it. The
    capture-time evaluation is removed.
  - Evaluation runs through the queue, not inline in the match-resolution request: the
    auto-preparation keeps acting as the guardrail's creator rather than the person resolving the
    match, a guardrail failure cannot break or slow match resolution, and failed evaluations retry.
  - **Settled response set:** a guardrail only fires once every captured response for the RFQ is
    settled — either terminal (refused/deleted) or reviewed with every line matched. Otherwise the
    first response a human happened to review could auto-prepare ahead of a cheaper response still
    in review, breaking FR-012's "single lowest-priced qualifying response".
  - **FR-014, conservative reading:** a guardrail only applies to responses captured after the
    guardrail was created.
  - **Human data review stays in the loop:** auto-preparation still requires a human-confirmed
    quotation. The guardrail saves the buyer the compare-and-prepare step, not the review step.
  - Pending responses block firing indefinitely in v1 (no response-window cutoff).
  - The RFQ row is locked for the duration of an evaluation, the prepare-request idempotency key
    stays deterministic per (tenant, RFQ, guardrail), and the price-history baseline excludes the
    candidate responses' own landed costs (which now exist by the time evaluation runs).
- **Consequences:**
  - Guardrail auto-preparation can fire on real captured responses; draft purchase requests still
    enter the unmodified human approval workflow (Constitution Principle III unchanged).
  - A response stuck in review delays auto-preparation for its whole RFQ. Revisit with real usage;
    a response-window cutoff (e.g. the RFQ's needed-by date) is the likely follow-on.
  - Fuller autonomy — auto-matching quotations whose extraction was fully high-confidence and
    reconciled, without human review — remains a separate, explicit product decision.

## ADR-020 — Quantities and Estimates Are in the Purchasing Unit (Pack), Not the Base Unit

- **Status:** Accepted (2026-10-17)
- **Context:** A demo walkthrough on the hosted tenant showed a 56,425 EGP request re-estimated to
  6,135.58 at submit. Request quantities are in packs (10 tins of 18 L), but the submit-time
  estimate came from `landed_cost.total_amount / normalised_base_quantity`, a price per litre or kg.
  Pack quantity × per-base price understated the total ~9×, so approval thresholds and budget
  checks saw the wrong amount. The estimate also ignored the RFQ response the request was prepared
  from and used another supplier's latest landed cost.
- **Decision:**
  - Quantities on requests, RFQs and purchase orders are in the product's **purchasing unit** (a
    pack: tin, sack, carton, or one kg for loose goods). Prices on those documents are **per pack**.
  - Base-unit conversion (`pack_count × unit_size`) is used only to normalise across suppliers
    (Smart Compare, Basket Split, price history). Those screens take quantity in packs and show the
    base-unit equivalent ("10 × 18 litre = 180 litre") before calling the base-unit APIs.
  - A request's line estimates are the per-pack prices of its source RFQ response
    (`purchase_request.source_rfq_response_id`) when it has one, else the latest landed cost per
    pack (`landed_cost.total_amount / landed_cost.quantity`). Submit and draft edits use the same
    rule, so submit never swaps the estimate the user saw for another supplier's.
  - Purchase-order prefill from a request carries the pack label and the per-pack estimate.
- **Consequences:** `estimated_unit_price` on request lines now means "per pack". Existing draft
  requests prepared before this change should be withdrawn and re-prepared. Pre-filling the PO
  supplier from the source response is not done yet (the request API does not expose it).

## ADR-021 — VAT-Inclusive Quotes Keep Their Printed Prices; Orders and Savings Are Net + Tax

- **Status:** Accepted (2026-10-30, owner; PPS-122, PPS-128)
- **Context:** Saudi suppliers print prices that already include 15% VAT («الأسعار شاملة ضريبة
  القيمة المضافة 15%»). Extraction left line `vat_rate` empty, so the review screen showed no VAT,
  purchase orders carried tax 0, and Record outcome saved VAT-inclusive amounts as «Total paid excl.
  tax» (flow review R9, R17). The obvious fix, extracting `vat_rate = 0.15`, is wrong: landed-cost
  rule v1 adds VAT on top (`total = price × qty × (1 + r)`), so SAR 4,830 would become 5,554.50.
  The empty rate was the only thing keeping Saudi comparisons right.
- **Options considered:**
  1. Convert printed prices to net at extraction. Rejected: the stored quote would no longer match
     the document the reviewer sees, and every reviewer correction would need converting back.
  2. Store the rate and keep v1. Rejected: double-counts VAT.
  3. Keep printed prices, record the basis on the quote, and make the rule aware of it. Chosen.
- **Decision:**
  - `quotation.prices_include_vat` records the document's basis. Extraction sets it from an
    explicit statement («الأسعار شاملة ضريبة القيمة المضافة N%», «prices include VAT», «incl. VAT
    N%»). A total-row label alone counts only when the lines sum to the stated total. Lines take
    the document rate unless they print their own. The reviewer confirms or changes both: they are
    shown as flagged fields.
  - **Landed-cost rule v2** (`landed-cost-v2`): on a VAT-inclusive quote,
    `vat = gross × qty × r / (1 + r)` and `total = gross × qty + delivery − discount`. On an
    exclusive quote v2 equals v1. Rows already priced under v1 stay v1 (append-only, FR-016/017).
    Both versions put the landed total on the same basis (including VAT, delivery and discount).
    For that reason the latest offer per supplier is chosen across rule versions: the readers'
    `row_number()` window no longer partitions by `rule_version`, so a version bump never splits a
    supplier into two offers. A decision's cost is its latest landed_cost row: readers that list
    offers, price history or alert rows read the `current_landed_cost` view, so a decision with a
    v1 and a v2 row is counted once. The earlier row stays as evidence.
  - **Purchase orders are net + tax.** An order line priced from a VAT-inclusive quote gets
    net unit price = `gross / (1 + r)` rounded to 4 dp, and line tax = gross line total − net line
    total. The order total therefore equals the printed total exactly, with no cent drift.
  - **Savings compare net to net.** Record outcome pre-fills the order's net line totals. Quoted
    baselines use the landed total minus its VAT. The last-PO-price baseline uses the PO's net unit
    price (`saving-baseline-v4`).
- **Consequences:** Offers, Smart Compare and price history stay VAT-inclusive (landed cost);
  orders and savings are net. Existing VAT-inclusive data recorded before this decision (the
  «مطاعم رواق» demo quotes and PO-000001…PO-000009) needs a one-off correction, run with the
  owner's approval. The saving ledger rows already recorded are left as they are. A quote whose
  lines mix inclusive and exclusive prices is not modelled: the flag is per document.

## ADR-022 — Match Decisions Are Corrected by Supersession, Never Updated

- **Status:** Accepted (2026-10-29, spec 023 research R5; PPS-95)
- **Context:** `match_decision` is append-only and held one row per quotation line, with correction
  left to "a supersession model later". Spec 023 accepts an unambiguous RFQ fit automatically (owner
  decision Q1, 2026-10-28), so a wrong automatic match must be correctable. About 19 modules read
  decisions (offers, landed cost, savings, supplier IQ, alerts, analyst, request valuation, RFQ
  responses, the guardrail, the optimiser worker).
- **Options considered:**
  1. `superseded_at` on the old row. Rejected: it updates an outcome record (Constitution II).
  2. Delete and reinsert into a history table. Rejected: it destroys history and breaks the
     `landed_cost` cascade.
  3. A separate supersession table. Rejected: the database cannot enforce one current decision per
     line across two tables without triggers on both.
  4. An insert-only chain on `match_decision`. Chosen.
- **Decision:**
  - `match_decision.supersedes_decision_id` names the decision a correction replaces;
    `learned_from_decision_id` names the decision that taught the wording (the alias sweep).
  - The database enforces one chain per line with one head: unique nulls not distinct
    `(tenant_id, quotation_line_id, supersedes_decision_id)` and unique `(supersedes_decision_id)`,
    plus a trigger that requires the same line. Two concurrent corrections of one head are
    stopped by the unique index (`23505`).
  - The view `current_match_decision` (`security_invoker`) serves the heads. Readers that mean "the
    line's match" read the view; lookups by decision id and history read the table.
  - A correction inserts a new human decision, computes its landed cost (old rows stay as
    evidence), enqueues guardrail evaluation (ADR-019) and audits `matching.decision_corrected`.
  - A correction is refused (`409 line_on_purchase_request`) while a live purchase request is priced
    from the decision. `match_decision_live_request()` answers that for the caller's tenant whatever
    branch the caller can see.
- **Consequences:** Every new reader must choose the view or the table on purpose. A superseded
  decision's product attribution stops counting toward offers, supplier IQ and alerts. Corrections
  are blocked, not cascaded, once a request is priced from the decision: the buyer must withdraw it first.

## ADR-023 — An RFQ Split Is One Request Group with One Preparation Lock

- **Status:** Accepted (2026-10-28, spec 024 research R4, R5; PPS-96)
- **Context:** A basket split divides one RFQ between the suppliers who replied. Approval, budgets,
  purchase orders, notifications and the phone all hang off a per-request `approval_step`. An RFQ may
  be converted to requests once; the guardrail (ADR-019) prepares through the same path.
- **Options considered:**
  1. One `approval_step` on the group. Rejected: every consumer of a request's step (PO validation,
     budgets, mobile) would need a second path.
  2. Independent requests with no group. Rejected: nothing stops splitting an order below an approval
     threshold, and the buyer could approve half.
  3. A group of requests, each keeping its own step, decided together. Chosen.
- **Decision:**
  - `purchase_request_group` (one per RFQ, `unique (tenant_id, rfq_id)` as the database backstop)
    records the split's totals and saving as computed at preparation. Its state is the state of its
    requests. Each request names its group in `request_group_id`.
  - Preparation takes the same transaction advisory lock as single-request preparation
    (`rfq-prepare:{tenant}:{rfq}`) and the same status check, creates the group and its requests in
    one transaction, and calls `mark_rfq_converted` once. The guardrail goes through that lock too,
    so it cannot race a split.
  - Submit resolves one approver from the group's combined total and branch (the anti-splitting
    control) and creates one step per request, all with source `group_threshold_match` or
    `owner_fallback`. Approve, reject and withdraw run the existing per-request decision SQL for every
    request in one transaction, with one notification.
  - The single-request endpoints answer `409 part_of_split` for a request in a group.
  - A split result is compared with the quotations it was priced from; a stale one is refused.
- **Consequences:** An enabled guardrail prepares a single request as soon as every reply is matched
  and converts the RFQ, so the split cannot be prepared on that RFQ. That is by design in 024's edge
  cases and is tracked as a product decision (W2, PPS-148).
