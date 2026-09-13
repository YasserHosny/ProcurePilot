---
description: "Task list for Optimisation and Supplier IQ implementation"
---

# Tasks: Optimisation and Supplier IQ

**Input**: Design documents from `/specs/011-optimisation-supplier-iq/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/optimisation-supplier-iq.openapi.yaml, quickstart.md

**Tests**: Included. The spec makes advanced basket feasibility, Supplier IQ evidence, anomaly
generation/dismissal, tenant isolation, RBAC, audit, accessibility, and advisory-only behaviour
release conditions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable - different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md
- Every task names exact file paths

## Phase 1: Setup and schema

- [ ] T001 Write `supabase/migrations/20260914000001_supplier_commercial_term.sql` creating `supplier_commercial_term` with money pairing checks, effective-date checks, composite supplier/membership FKs, `ENABLE` and `FORCE` RLS.
- [ ] T002 Write `supabase/migrations/20260914000002_supplier_scorecard_snapshot.sql` creating `supplier_scorecard_snapshot` with unique `(tenant_id,supplier_id,window_start,window_end,rule_version)`, source JSON fields, `ENABLE` and `FORCE` RLS.
- [ ] T003 Write `supabase/migrations/20260914000003_supplier_iq_rls.sql` with `USING` and `WITH CHECK` policies for both new tables, owner/buyer insert permissions, tenant member select permissions, and no update/delete grants.
- [ ] T004 [P] Add R2.4 i18n namespaces to `packages/i18n/en.json` and `packages/i18n/ar.json`: `advancedBasket`, `supplierIq`, `supplierTerms`, and `anomalies`.
- [ ] T005 [P] Extend web routing in `apps/web/src/app/app.routes.ts` for supplier scorecard navigation under suppliers without adding a marketing/dashboard page.
- [ ] T006 [P] Add API schema classes in `apps/api/src/procurepilot_api/modules/offers/schemas.py` for supplier terms, Supplier IQ scorecards, advanced basket request/result fields, and anomaly alert kinds.

## Phase 2: Foundational tests and contracts

- [ ] T007 [P] Write contract tests in `apps/api/tests/contract/test_optimisation_supplier_iq_contract.py` for advanced basket, supplier terms, supplier scorecard, and anomaly alert response shapes.
- [ ] T008 [P] Extend tenant isolation tests in `apps/api/tests/integration/test_tenant_isolation.py` for `supplier_commercial_term` and `supplier_scorecard_snapshot`.
- [ ] T009 [P] Write RBAC tests in `apps/api/tests/integration/test_supplier_iq_rbac.py` proving owner/buyer may mutate terms and submit advanced baskets, while read-only roles can view scorecards/alerts only.
- [ ] T010 [P] Write audit tests in `apps/api/tests/integration/test_supplier_iq_audit.py` for advanced basket submission, scorecard view, and anomaly dismissal audit events.

## Phase 3: User Story 1 - Advanced basket optimisation (P1)

- [ ] T011 [P] Write optimiser solver tests in `services/optimiser/tests/test_advanced_solver.py` for MOV, free-delivery threshold, delivery fee, quantity tiers, risk tolerance, supplier exclusion, infeasible constraints, and deterministic tie-breaks.
- [ ] T012 [P] Write API integration tests in `apps/api/tests/integration/test_advanced_basket_optimisation.py` proving 2-10 suppliers, max 50 lines, mixed-currency refusal, constraint snapshots, idempotency, and advisory-only side effects.
- [ ] T013 Implement supplier term persistence and validation in `apps/api/src/procurepilot_api/modules/offers/supplier_terms.py`.
- [ ] T014 Expose `GET` and `POST /suppliers/{supplier_id}/commercial-terms` in `apps/api/src/procurepilot_api/modules/offers/router.py`.
- [ ] T015 Extend `apps/api/src/procurepilot_api/modules/offers/basket_service.py` to accept advanced constraint snapshots and enqueue the existing optimiser worker payload with `rule_version`.
- [ ] T016 Extend `services/optimiser/src/procurepilot_optimiser_worker/models.py` with advanced request/result, terms, constraints, risk, and confidence models.
- [ ] T017 Extend `services/optimiser/src/procurepilot_optimiser_worker/repository.py` to read supplier terms, scorecard/risk inputs, and current eligible offers without recomputing landed cost.
- [ ] T018 Extend `services/optimiser/src/procurepilot_optimiser_worker/solver.py` with hard constraints, weighted objective, tier prices, baselines, violated constraints, and deterministic tie-breaks.
- [ ] T019 Extend `services/optimiser/src/procurepilot_optimiser_worker/worker.py` to persist R2.4 result payloads and reserve `failed` for infrastructure/unexpected errors.
- [ ] T020 [P] Extend `apps/web/src/app/features/offers/basket-split/basket-split.component.spec.ts` for constraint controls, rerun/poll state, rich results, infeasible constraints, RTL, and keyboard operation.
- [ ] T021 Build advanced basket UI in `apps/web/src/app/features/offers/basket-split/` using i18n strings only and preserving the existing job-polling pattern.

## Phase 4: User Story 2 - Supplier scorecards and risk scoring (P1)

- [ ] T022 [P] Write unit tests in `apps/api/tests/unit/test_supplier_iq_metrics.py` for fulfilment, quality, price competitiveness, spend exposure, freshness, savings contribution, sparse evidence, and rule-versioned risk score.
- [ ] T023 [P] Write integration tests in `apps/api/tests/integration/test_supplier_iq.py` proving scorecard metrics trace to seeded source records and cross-tenant supplier ids return not found.
- [ ] T024 Implement deterministic Supplier IQ calculations in `apps/api/src/procurepilot_api/modules/offers/supplier_iq.py`.
- [ ] T025 Expose `GET /suppliers/{supplier_id}/scorecard` in `apps/api/src/procurepilot_api/modules/offers/router.py`.
- [ ] T026 [P] Add web API client methods/types in `apps/web/src/app/features/catalogue/catalogue-api.ts` or the existing supplier API module.
- [ ] T027 [P] Write supplier scorecard component tests in `apps/web/src/app/features/catalogue/supplier-scorecard/supplier-scorecard.component.spec.ts`.
- [ ] T028 Build `apps/web/src/app/features/catalogue/supplier-scorecard/` component, template, and styles with dense operational layout, source counts, insufficient evidence, and risk breakdown.

## Phase 5: User Story 3 - Anomaly detection v1 (P2)

- [ ] T029 [P] Write anomaly rule tests in `apps/api/tests/unit/test_anomaly_conditions.py` for all five anomaly kinds and severity/confidence rules.
- [ ] T030 [P] Write alert integration tests in `apps/api/tests/integration/test_anomaly_alerts.py` proving live recomputation, deterministic fingerprints, dismissal suppression, and recurrence on changed evidence.
- [ ] T031 Extend `apps/api/src/procurepilot_api/modules/alerts/fingerprints.py` for anomaly recurrence keys.
- [ ] T032 Extend `apps/api/src/procurepilot_api/modules/alerts/conditions.py` with `price_spike`, `likely_duplicate_quotation_line`, `decimal_or_quantity_anomaly`, `delivery_cost_anomaly`, and `supplier_quality_trend_change`.
- [ ] T033 Extend `apps/api/src/procurepilot_api/modules/alerts/schemas.py` and `apps/api/src/procurepilot_api/modules/alerts/router.py` for new kinds, confidence, validity, and supplier-scorecard action links.
- [ ] T034 [P] Extend `apps/web/src/app/features/alerts/alert-actions.ts` and `alerts-inbox` tests for anomaly action routing and recurrence copy.
- [ ] T035 Build anomaly UI states in `apps/web/src/app/features/alerts/alerts-inbox/` with source evidence, confidence, severity, and i18n-only labels.

## Phase 6: User Story 4 - Web integration (P2)

- [ ] T036 [P] Extend Compare UI tests in `apps/web/src/app/features/offers/compare/compare.component.spec.ts` for Supplier IQ risk evidence in recommendation explanations.
- [ ] T037 [P] Extend `apps/web/src/app/features/offers/compare/` to display Supplier IQ/risk evidence when it influenced a recommendation.
- [ ] T038 [P] Add Playwright E2E `apps/web/tests/e2e/optimisation-supplier-iq.spec.ts` covering advanced basket, supplier scorecard, anomaly action links, and advisory-only language.
- [ ] T039 [P] Add Playwright a11y/RTL coverage `apps/web/tests/e2e/optimisation-supplier-iq-a11y.spec.ts`.

## Phase 7: Cross-cutting

- [ ] T040 Update `docs/architecture/data-dictionary.md` with R2.4 tables, JSON snapshots, response entities, RLS, and audit events.
- [ ] T041 Update `docs/architecture/api-specification.md` from `contracts/optimisation-supplier-iq.openapi.yaml`.
- [ ] T042 Update `docs/user/user-documentation.md` and screenshots for advanced basket, Supplier IQ, and anomaly workflows.
- [ ] T043 Run and record release gates: `pnpm test:api`, optimiser pytest, `pnpm test:web`, `pnpm test:e2e`, `pnpm test:a11y`, and `pnpm test:isolation`.

## Delegation lanes

| Lane | Scope | Preferred implementer | Tasks |
|---|---|---|---|
| Orchestrator | migrations, RLS, audit, isolation, final review | Codex in-house | T001-T003, T008-T010, T040-T043 |
| Backend/API | FastAPI schemas/services/routes and API tests | Codex delegate | T006-T007, T012-T015, T022-T025, T029-T033 |
| Optimiser worker | CP-SAT models/repository/solver/worker tests | Codex delegate | T011, T016-T019 |
| Frontend | Angular UI/i18n/E2E/a11y | Agy delegate | T004-T005, T020-T021, T026-T028, T034-T039 |

## Wave 14 recommendation

Start with Phase 1 and Phase 2 plus the first thin slice of US1/US2:

- Orchestrator: T001-T003, T008-T010
- Backend delegate: T006-T007, T013-T014
- Optimiser delegate: T011, T016
- Agy frontend delegate: T004-T005, T020

Do not start US3 anomaly UI until Supplier IQ and advanced basket result shapes are stable.
