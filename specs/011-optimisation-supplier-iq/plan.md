# Implementation Plan: Optimisation and Supplier IQ

**Branch**: `011-optimisation-supplier-iq` | **Date**: 2026-09-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-optimisation-supplier-iq/spec.md`

## Summary

R2.4 upgrades the existing Smart Compare and basket optimisation foundation into richer advisory
decision support: commercial constraints, supplier scorecards, deterministic risk scoring, and
anomaly detection v1. It reuses the current API modules, web feature areas, alerts model, and
`services/optimiser` worker.

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5.6, Angular 19, PostgreSQL 17, Flutter unchanged  
**Primary Dependencies**: FastAPI, Pydantic v2, psycopg, Supabase, Angular Material/CDK, RxJS,
OR-Tools CP-SAT in existing optimiser worker  
**Storage**: Supabase Postgres with RLS; existing Redis/RQ queue for basket jobs  
**Testing**: pytest, Karma/Jasmine, Playwright, optimiser pytest suite, axe-core  
**Target Platform**: ProcurePilot web and API; no new mobile scope in R2.4  
**Project Type**: API + web SPA + existing optimiser worker  
**Performance Goals**: optimisation completes within 30 seconds for 50 lines and 10 suppliers;
web constraint/result interactions remain responsive under 150 ms for local recalculation  
**Constraints**: tenant from JWT only; money pairs always include currency; user-facing strings
from shared i18n; no autonomous purchasing; deterministic replay from rule versions  
**Scale/Scope**: R2.4 advisory workflow for Phase 2 customers, extending existing compare,
basket, supplier, and alerts surfaces

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Principle I: every optimisation, scorecard, risk, and anomaly output includes source ids,
  confidence, validity, and calculation/evidence.
- Principle II: supplier terms, scorecards, and optimiser request/result payloads are versioned and
  replayable.
- Principle III: optimiser remains advisory and cannot create purchases, approvals, orders, or
  payments.
- Principle IV: scorecards and anomaly alerts route to concrete actions.
- Principle V: new tables are tenant-scoped with database RLS and cross-tenant not-found tests.
- Principle VI: existing API modules and existing optimiser worker are extended; no new service.
- Principle VII: money stores explicit currency; UI strings come from `packages/i18n` and support
  RTL.

No constitution violations are planned.

## Project Structure

### Documentation (this feature)

```text
specs/011-optimisation-supplier-iq/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
|-- contracts/
|   `-- optimisation-supplier-iq.openapi.yaml
`-- tasks.md
```

### Source Code (repository root)

```text
apps/api/src/procurepilot_api/modules/offers/
|-- basket_service.py
|-- schemas.py
|-- router.py
|-- supplier_iq.py
`-- supplier_terms.py

apps/api/src/procurepilot_api/modules/alerts/
|-- conditions.py
|-- fingerprints.py
|-- schemas.py
|-- service.py
`-- router.py

services/optimiser/src/procurepilot_optimiser_worker/
|-- models.py
|-- repository.py
|-- solver.py
`-- worker.py

apps/web/src/app/features/offers/
|-- basket-split/
|-- compare/
`-- product-intelligence/

apps/web/src/app/features/catalogue/
|-- supplier-list/
|-- supplier-form/
`-- supplier-scorecard/

apps/web/src/app/features/alerts/
`-- alerts-inbox/

packages/i18n/
|-- en.json
`-- ar.json
```

**Structure Decision**: Extend existing modules. New API calculation helpers live in
`offers/supplier_iq.py` and `offers/supplier_terms.py`; the optimiser worker keeps solver logic
outside FastAPI; the web UI adds Supplier IQ under catalogue suppliers and extends existing offers
and alerts screens.

## Complexity Tracking

No complexity exceptions are planned.
