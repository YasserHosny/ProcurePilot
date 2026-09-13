# Quickstart: Optimisation and Supplier IQ

This quickstart describes the intended R2.4 validation path once tasks are implemented.

## 1. Apply migrations and seed

```bash
pnpm db:migrate
pnpm db:seed
```

Seed data must include three active/preferred suppliers, current landed costs for at least five
products, supplier commercial terms, delivered purchase requests, quality issues, and anomaly
trigger rows for each anomaly v1 kind.

## 2. Run API checks

```bash
pnpm test:api -- apps/api/tests/contract/test_optimisation_supplier_iq_contract.py
pnpm test:api -- apps/api/tests/integration/test_supplier_iq.py
pnpm test:api -- apps/api/tests/integration/test_advanced_basket_optimisation.py
pnpm test:api -- apps/api/tests/integration/test_anomaly_alerts.py
pnpm test:isolation
```

Expected: contract and integration tests pass; cross-tenant references return not found.

## 3. Run optimiser worker checks

```bash
cd services/optimiser
uv run pytest tests/test_solver.py tests/test_advanced_solver.py tests/test_worker.py
uv run ruff check .
```

Expected: feasible, infeasible, tied, mixed-currency, MOV, delivery-threshold, quantity-tier, and
risk-tolerance cases pass.

## 4. Run web checks

```bash
pnpm test:web
pnpm test:e2e -- apps/web/tests/e2e/optimisation-supplier-iq.spec.ts
pnpm test:a11y
```

Expected: advanced basket constraints, Supplier IQ scorecards, and anomaly actions work in English
and Arabic with zero automated accessibility violations.

## 5. Manual smoke

1. Open Basket Split.
2. Select a basket with at least three suppliers.
3. Set risk tolerance and urgency.
4. Submit optimisation.
5. Confirm the completed result shows allocation, baselines, applied constraints, violated
   constraints if any, confidence, risk notes, and validity.
6. Open a supplier scorecard from the result or alerts.
7. Confirm scorecard evidence and anomaly action links are source-backed.

No step should create a purchase, approval, order, payment, or supplier message.
