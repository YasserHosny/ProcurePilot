# ProcurePilot - Wave 14 Execution Plan (R2.4 start)

**Written**: 2026-09-13, by Codex orchestrator, after Wave 13 and preserved docs/web work were
merged to `main` at `308454d`.

**Target feature**: `011-optimisation-supplier-iq`

**Release**: R2.4 - Optimisation + Supplier IQ

## 0. Starting point

The project already has the R1.4/R2.4 foundations delivered in
`005-smart-compare-intelligence`:

- Compare/recommendation endpoint and UI
- Price-history intelligence
- Two-supplier basket split with `basket_split_job`
- Alerts inbox with live recomputation and dismissal-only storage
- Existing `services/optimiser` worker

Wave 14 must extend those surfaces. It must not rebuild them or introduce a second optimiser,
offer, landed-cost, matching, or alert source of truth.

## 1. Scope for Wave 14

Wave 14 is the kickoff wave for `011-optimisation-supplier-iq`. It creates the schema and
foundation needed for later implementation waves:

1. `supplier_commercial_term` table, RLS, and tests.
2. `supplier_scorecard_snapshot` table, RLS, and tests.
3. API schema/contract baseline for supplier terms, Supplier IQ, advanced basket results, and
   anomaly alert kinds.
4. Initial optimiser-worker model/test baseline for advanced constraints.
5. Initial frontend route/i18n/test baseline for advanced basket and supplier scorecard surfaces.

## 2. Task split

### Orchestrator lane (not delegated)

- T001 `supabase/migrations/20260914000001_supplier_commercial_term.sql`
- T002 `supabase/migrations/20260914000002_supplier_scorecard_snapshot.sql`
- T003 `supabase/migrations/20260914000003_supplier_iq_rls.sql`
- T008 `apps/api/tests/integration/test_tenant_isolation.py`
- T009 `apps/api/tests/integration/test_supplier_iq_rbac.py`
- T010 `apps/api/tests/integration/test_supplier_iq_audit.py`

Reason: this lane touches tenant isolation, audit, and migration ordering.

### Backend/API delegate lane

- T006 `apps/api/src/procurepilot_api/modules/offers/schemas.py`
- T007 `apps/api/tests/contract/test_optimisation_supplier_iq_contract.py`
- T013 `apps/api/src/procurepilot_api/modules/offers/supplier_terms.py`
- T014 `apps/api/src/procurepilot_api/modules/offers/router.py`

Reason: bounded API contract and supplier-term service work.

### Optimiser delegate lane

- T011 `services/optimiser/tests/test_advanced_solver.py`
- T016 `services/optimiser/src/procurepilot_optimiser_worker/models.py`

Reason: pure worker model/test setup with no API or web conflicts.

### Frontend delegate lane (Agy)

- T004 `packages/i18n/en.json`, `packages/i18n/ar.json`
- T005 `apps/web/src/app/app.routes.ts`
- T020 `apps/web/src/app/features/offers/basket-split/basket-split.component.spec.ts`

Reason: user preference is to use Agy especially for frontend. This lane starts with i18n/routes
and tests only; UI implementation waits for stable API/result models.

Dispatch note: if Agy headless runs are blocked by permission prompts, include
`agy --dangerously-skip-permissions` in the delegate command only after explicit user approval.
This flag auto-approves Agy tool permission requests and must be treated as full-access execution:
do not combine it with read-only mode, keep the file scope tight in the brief, and review the diff
plus gates before landing any Agy-authored change.

## 3. Branches

- Planning branch: `011-optimisation-supplier-iq`
- Wave 14 implementation branches:
  - `codex/wave14-r2-4-foundation`
  - `codex/wave14-r2-4-backend-api`
  - `codex/wave14-r2-4-optimiser`
  - `codex/wave14-r2-4-frontend-agy`

## 4. Gate commands

Run the smallest relevant gate per branch, then full gates before merging:

```bash
pnpm test:api -- apps/api/tests/contract/test_optimisation_supplier_iq_contract.py
pnpm test:api -- apps/api/tests/integration/test_tenant_isolation.py apps/api/tests/integration/test_supplier_iq_rbac.py apps/api/tests/integration/test_supplier_iq_audit.py
cd services/optimiser && uv run pytest tests/test_advanced_solver.py
pnpm test:web -- --include apps/web/src/app/features/offers/basket-split/basket-split.component.spec.ts
pnpm lint
```

If integration database variables are not configured, record the skip honestly and do not claim DB
coverage passed.

## 5. Cautions

- Keep tenant scope from JWT only.
- Use database RLS for new tables.
- Do not update or delete audit events.
- Do not create an order, approval, payment, or supplier message from optimiser output.
- Do not add hardcoded UI strings.
- Do not introduce FX conversion.
- Do not persist live anomaly alert rows; persist dismissals only.
- Do not use Agy write mode with permission bypass unless the user explicitly approves it. Once
  approved for a blocked Agy lane, document `agy --dangerously-skip-permissions` in the dispatch
  brief and treat the run as full-access.
