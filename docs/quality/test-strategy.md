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

## 10. Open Decisions

1. Which Flutter testing framework (integration tests vs. Maestro).
2. Whether to add synthetic data generation for performance testing.
