# ProcurePilot — Test Strategy & Test Plan

> How ProcurePilot will be tested across the pyramid, with special attention to AI accuracy and financial correctness.

---

## 1. Strategy

| Layer | Tool | Responsibility | When |
|---|---|---|---|
| Unit | pytest (backend), Karma/Jasmine (frontend) | Functions, services, components, validators | Every PR |
| Integration | pytest + httpx TestClient | API endpoints, DB queries, auth middleware | Every PR |
| E2E | Playwright | Critical user journeys on web | Nightly + before release |
| Mobile E2E | Flutter integration tests | Request, approval, delivery flows | Before store release |
| AI eval | Custom harness + benchmark datasets | Extraction and matching accuracy | Every model/prompt change |
| Performance | Locust / k6 | Latency, throughput, concurrent extraction | Before G1 and G2 |
| Security | OWASP ZAP + penetration test | OWASP Top 10, auth, RLS | P1 ongoing + third-party at end P2 |
| Accessibility | axe-core / Lighthouse | WCAG 2.1 AA | Every release |

## 2. Test Environments

- **Local:** `docker compose up` with seeded demo tenant.
- **CI:** ephemeral containers spun up by GitHub Actions.
- **Staging:** Bunny Magic Containers, seeded dataset, shared with design partners.
- **Production:** live; feature flags protect new capabilities.

## 3. Unit / Integration Test Targets

### Backend
- Pydantic schema validation for every request/response model.
- Tenant isolation: queries fail without `tenant_id` and pass with RLS.
- Auth middleware rejects expired/revoked tokens.
- Landed-cost engine: deterministic outputs per rule version.
- Matching pipeline: alias hits, GTIN hits, lexical/semantic candidates, confidence thresholds.

### Frontend
- Form validation with Zod schemas.
- Component rendering for review queue, compare grid, savings ledger.
- HTTP services retry and error handling.

### Mobile
- Offline draft persistence and sync.
- Barcode scan to product lookup.
- Approval action with idempotency.

## 4. AI Evaluation Plan

### Extraction
- **Dataset:** 300+ labelled quotation line items, versioned per release.
- **Metrics:** field-level accuracy, document-level exact match, arithmetic-validation pass rate, cost per document.
- **Gate:** ≥ 90% field-level accuracy on priority fields; no regression versus previous baseline.

### Matching
- **Dataset:** 500+ labelled product-match pairs, including hard negatives.
- **Metrics:** precision at auto-accept, recall, review-band size, alias hit rate.
- **Gate:** ≥ 92% precision at auto-accept; review-band ≤ 8%.

### Calibration
- Expected calibration error (ECE) on confidence scores.
- Confidence must match observed accuracy within 5% per bucket.

## 5. E2E Scenarios

### Web
1. Self-onboard → upload quotation → review extraction → confirm matches → see Smart Compare → record purchase → verify saving in ledger.
2. CSV import catalogue → upload quotation → extraction uses catalogue aliases.
3. Invite team member → assign role → verify RBAC limits.

### Mobile
1. Branch manager creates request → approver receives push → approves → buyer records order → branch confirms delivery.
2. Offline draft → sync on reconnect → no duplicate request.

## 6. Performance Targets

- Dashboard FCP < 1.5 s.
- Compare grid recalculation < 150 ms.
- Extraction p95 < 45 s per document.
- 99th percentile API latency < 500 ms for read endpoints.

## 7. Responsibilities

- **Engineering lead:** unit/integration/E2E infrastructure.
- **AI lead:** eval datasets, harness, and gates.
- **Product designer:** accessibility and UX acceptance.
- **Founder:** prioritises E2E scenarios based on pilot feedback.

## 8. Responsive & RTL Testing

All UI changes must be verified at three viewport widths:

| Tier | Width | Key checks |
|---|---|---|
| Mobile | < 600px | Single-column layout, no horizontal scrollbar, reduced padding |
| Tablet | 600–959px | Intermediate layouts, flex-wrap correct |
| Desktop | ≥ 960px | Multi-column grids, side-by-side panels |

RTL verification: switch locale to Arabic and confirm:
- Logical properties flip correctly (margins, paddings).
- Text alignment reverses.
- Navigation and action buttons reorder.
- No text clipping or overflow.

## 9. Production Smoke Testing

After every deployment, run the end-to-end flow on the live production URL:

1. Sign in or sign up.
2. Upload a real document (not stub mode) → verify extraction provenance shows the expected
   AI provider (not `stub-provider-v1`).
3. Review and confirm the quotation.
4. Verify the review queue, Smart Compare, and savings flows.
5. Resize the browser to mobile width and verify responsive layout.

This catches issues that local tests cannot: misconfigured container env vars (e.g.
`EXTRACTION_PROVIDER_MODE` still set to `stub`), cross-app Redis connectivity failures,
and GHCR image pull issues.

## 10. R2.5 Hardening & Release Gates

Release R2.5 (`012-reporting-hardening`) introduces formal performance, accessibility, security, and tenant-isolation gates before the G2 stage gate:

### 10.1 Compare-Grid Timing Regression & CI-Noise Strategy
- **Gate:** Compare-grid recalculation under 150 ms (constitution Principle V, FR-025, SC-006).
- **CI-Noise Mitigation:** To eliminate false positives from runner load spikes, Playwright test `compare-grid-performance.spec.ts` computes the median of 7 consecutive quantity recalculation samples rendered entirely inside the browser DOM via `performance.now()`.
- **Target:** Median recalculation time < 150 ms for a 25-offer comparison grid.

### 10.2 Initial Bundle & Component Style Budgets
- **Initial Bundle Budget:** Raw initial bundle must remain ≤ 500 kB (Wave 15 baseline was 588 kB; lazy routes + lazy Sentry SDK achieved 457.79 kB).
- **Component Style Budget:** Strict ≤ 4 kB SCSS limit per component stylesheet (`styleUrl` single, no evasion via `styleUrls` array). Monitored via Angular CLI build budgets in `angular.json`.

### 10.3 Accessibility (axe-core) Mandatory Surfaces
- **Automated Gate (`pnpm test:a11y`):** Zero WCAG 2.1 AA violations across both English (LTR) and Arabic (RTL) for all primary user journeys:
  - Sign-in / Sign-up
  - Dashboard & Home
  - Product Catalogue & Supplier management
  - Quotation Upload & Review
  - Smart Compare & Basket Split
  - Alerts Inbox & Savings Ledger
  - Reports Center (`/reports`) & Digest Settings (`/reports/digest-settings`)
- **Keyboard Navigation:** Full bidirectional Tab/Shift+Tab navigation traversable through all interactive elements on data tables, banner toolbars, and forms.
- **Print Coverage:** Reports Center includes `@media print` coverage ensuring artifact tables print without UI chrome.

### 10.4 Dependency Audit CI Gate
- **Automated Check:** `.github/workflows/ci.yml` runs `pip-audit` across all Python environments (`apps/api`, worker services) and `pnpm audit --prod` across web workspaces.
- **Enforcement:** Blocks CI on any unallowlisted High or Critical vulnerability.
- **Allowlist (`docs/operations/dependency-audit-allowlist.txt`):** Every accepted finding must carry an assigned owner and explicit rationale (e.g. upstream framework constraint, non-exploitable transitive dependency).

### 10.5 Rate Limiting & Resource Caps
- **Endpoint Limits:** Export creation, report schedule mutations, and digest subscription mutations enforce tenant+membership claim rate limits with client IP fallbacks (FR-020).
- **Standing Caps:** Active schedules and digest subscriptions enforce strict per-member cardinality limits (422 structured error) preventing unbounded daemon job accumulation.

### 10.6 Security Review & Penetration Test Readiness
- **Internal Security Review (`docs/quality/r2.5-security-review-record.md`):** Evidence-based verification covering RLS policy shapes (`ENABLE` + `FORCE`), worker tenant re-derivation from DB state, reader-function authorization pins, storage bucket policies (`exports`), signed-URL max TTLs, and append-only audit enforcement.
- **Third-Party Penetration Test Scope (`docs/operations/pentest-scope.md`):** Formal procurement-ready scope document establishing in-scope boundaries, data classification, and test environments for third-party adversarial testing at the G2 gate.

### 10.7 Tenancy & Isolation Extension
- **Automated Isolation Tests (`pnpm test:isolation`):** Verified RLS policies across `report_schedule`, `digest_subscription`, `export_job`, and Supabase Storage `exports` bucket.
- **Cross-Tenant Guarantees:** Any cross-tenant or unauthorized-branch access resolves to HTTP 404 (Not Found), never HTTP 403 (Forbidden), avoiding existence leakage.

## 11. Open Decisions

1. Which Flutter testing framework (integration tests vs. Maestro).
2. Whether to add synthetic data generation for performance testing.
