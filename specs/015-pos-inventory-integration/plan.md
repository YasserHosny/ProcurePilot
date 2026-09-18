# Implementation Plan: POS & Inventory Integration — Usage Signals

**Branch**: `015-pos-inventory-integration` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-pos-inventory-integration/spec.md`

## Summary

R3.2: connect one Square account per workspace (owner-only, OAuth 2.0), sync its sales
transactions and inventory levels on a recurring schedule (plus on-demand), automatically match
Square catalog items to existing `workspace_product` rows by reusing the similarity-search
pipeline quotation-line matching already uses, and surface sales-velocity (30-day trailing
average) and stock-on-hand as read-only context on the screens a buyer already uses to decide how
much to order (Smart Compare, product catalogue) — never as a new standalone dashboard, and never
feeding Smart Compare's own recommendation scoring. Disconnecting, or never connecting, leaves
every purchasing workflow unaffected. Follows the exact connector/sync/worker architecture
established in R3.0 (email ingestion) and R3.1 (accounting integration) rather than inventing a
new integration pattern, per the roadmap's own stated principle.

## Technical Context

**Language/Version**: Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) —
unchanged from every prior chunk.
**Primary Dependencies**: FastAPI (existing), `httpx` (existing — sufficient for Square's plain
REST + OAuth2 endpoints, no new SDK dependency, research.md R1), RQ/Redis (existing, same queue
infrastructure as `accounting_sync_worker`/`email_ingestion_worker` for the recurring sync job).
**Storage**: Supabase Postgres 17 (unchanged). New tables: `pos_connection`,
`synced_product_signal`, `pos_product_match`.
**Testing**: pytest + pytest-asyncio (backend), Karma/Jasmine (frontend unit), Playwright (E2E) —
unchanged. The Square connector itself is tested against a stub client (same convention as
`accounting_provider_mode=stub`); no live sandbox account is required for the test suite.
**Target Platform**: Linux server (Docker), unchanged modular-monolith deployment.
**Project Type**: Web application (existing `apps/api` + `apps/web`, no new deployable — see
Constitution Principle VI).
**Performance Goals**: No new throughput target beyond the spec's own UX-level criteria (SC-001
connect in <2 min) — this is a low-QPS, recurring-batch feature, not a request-path-latency-
sensitive one.
**Constraints**: Read-only against Square (FR-002/FR-004 sync only, enforced by `PosConnector`
never exposing a write method, not just by convention, research.md R2); OAuth tokens encrypted at
rest via an extracted, shared `token_crypto.py` (research.md R3); one active connection per
workspace; sales-velocity figures never alter Smart Compare's recommendation scoring or any other
automated purchasing logic (FR-003, this release's explicit clarification).
**Scale/Scope**: One provider (Square) for this release, matching the user's clarification
answer; a second provider is a future release. 30-day trailing sales-velocity window
(research.md R5); daily recurring sync plus on-demand manual trigger (FR-002).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Evidence Over Assertion** — Every derived figure states its own basis: sales velocity
  carries its window length and last-computed timestamp, stock-on-hand carries its last-synced
  timestamp (FR-004, data-model.md), and an unmatched item is explicitly flagged as such rather
  than silently absent (FR-005/FR-006). A figure computed from less than a full window is marked
  provisional and states how much history it actually reflects (FR-013, `velocity_window_days_
  observed`, added by `/speckit.analyze` after the initial design silently allowed a partial-window
  figure to look identical to a full one — a real instance of exactly what this NON-NEGOTIABLE
  principle forbids). **Pass**.
- **II. Deterministic, Replayable Normalisation** — Velocity is recomputed from stored transaction
  data each sync, not incrementally accumulated, so the same 30 days of input always yields the
  same figure (research.md R5). Product-match confidence scores come from the existing versioned
  scoring pipeline already covered by this principle for quotation matching. `synced_product_
  signal` identity is keyed on the external item alone, not the connection, so a disconnect/
  reconnect cycle re-derives the same row rather than a divergent duplicate (research.md R8, fixes
  an SC-005 violation `/speckit.analyze` found in the initial design). **Pass**.
- **III. Human Authority Over Automation (NON-NEGOTIABLE)** — `PosConnector` exposes no write
  method against Square at all (enforced at the type level, research.md R2) — no autonomous action
  against a customer's live POS system, ever. FR-003 explicitly forbids velocity/stock data from
  automatically changing what Smart Compare recommends; a human buyer reads the signal and decides.
  **Pass**.
- **IV. Every Insight Ends in an Action** — Velocity and stock-on-hand are attached to the existing
  purchasing-decision screens (Smart Compare, product catalogue) a buyer already acts on, not a new
  standalone dashboard (research.md R7 addresses this directly, since it is the least obvious gate
  for a feature whose own FR-003 forbids automation). **Pass**.
- **V. Tenant Isolation by Construction (NON-NEGOTIABLE)** — All three new tables are tenant-scoped,
  `ENABLE + FORCE` RLS required, every cross-module FK pinned to `(tenant_id, id)` from the first
  migration (data-model.md), proven by extending the existing canonical `test_tenant_isolation.py`
  file, not a new isolation test file. **Pass**, must be verified in implementation.
- **VI. Modular Monolith Until Scale Demands Otherwise** — New `modules/pos/` inside the existing
  `apps/api` monolith; the recurring sync runs as a new worker type on the existing RQ/Redis
  infrastructure, not a new service. Token-crypto extraction to `shared/` is a mechanical
  de-duplication, not a new module boundary. No ADR needed. **Pass**.
- **VII. Money, Tax, and Language Correct from the Schema Up** — No new monetary values are
  introduced by this feature (stock-on-hand is a unit count, sales velocity is units/day) — where
  the spec's edge cases discuss currency-adjacent concerns they don't arise here, unlike 014. All
  new UI strings go through `packages/i18n` (en + ar), RTL-compatible layout, matching every prior
  feature. **Pass**.

No violations requiring Complexity Tracking.

**Post-design re-check** (after Phase 1 data-model.md/contracts): confirmed, not just assumed — all
three new tables carry `ENABLE + FORCE` RLS with tenant-pinned policies and composite-key FKs from
the first migration (Principle V, deliberately not reproducing the five-times-fixed bug from
earlier chunks); `pos_product_match` has no `UPDATE` grant (supersede-by-insert, matching
`purchase_bill_match`'s own provenance-preserving shape, Principle I); the connector design in
research.md never exposes a write method against Square at all (Principle III); the token-crypto
extraction touches only `modules/accounting/` and `shared/`, no behavior change to already-shipped
accounting flows (Principle VI, verify via the existing accounting test suite staying green). No
new violations introduced by the detailed design.

## Project Structure

### Documentation (this feature)

```text
specs/015-pos-inventory-integration/
├── plan.md               # This file
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── pos-integration.openapi.yaml
└── tasks.md              # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
apps/api/src/procurepilot_api/
├── shared/
│   └── token_crypto.py                # moved here from modules/accounting/ (research.md R3)
├── modules/
│   ├── accounting/
│   │   └── (service.py, sync_service.py import token_crypto from shared/ instead of locally)
│   └── pos/                           # new
│       ├── __init__.py
│       ├── router.py                  # connection + sync-trigger + signals/match endpoints
│       ├── schemas.py                 # Pydantic request/response models
│       ├── service.py                 # ConnectionService: connect/disconnect/status
│       ├── square_client.py           # OAuth2 dance + read-only REST calls against Square
│       ├── connector.py               # PosConnector protocol + StubConnector + SquareConnector
│       ├── sync_service.py            # SyncService: fetch transactions/inventory, upsert signals
│       └── matching_service.py        # ProductMatchingService: reuses modules/matching/search.py
├── workers/
│   └── pos_sync_worker.py             # new — advisory-lock recurring sync claim loop
└── tests/
    ├── unit/
    │   ├── test_square_client.py
    │   └── test_pos_matching_service.py
    └── integration/
        ├── test_pos_connection.py
        ├── test_pos_sync.py
        ├── test_pos_matching.py
        └── test_pos_sync_worker.py

apps/web/src/app/features/pos/          # new
├── connection-settings/                # connect/disconnect, connection health
├── signals-review/                     # unmatched-signal manual match screen
└── pos-api.ts                          # typed API client, same shape as accounting-api.ts

apps/web/src/app/features/offers/compare/   # existing, gains inline velocity/stock context only
apps/web/src/app/features/catalogue/        # existing, gains inline velocity/stock context only

supabase/migrations/
└── 202609XXXXXXXX_pos_*.sql            # pos_connection, synced_product_signal, pos_product_match
```

**Structure Decision**: Mirrors `014-accounting-integration`'s own structure exactly — one new
backend module (`modules/pos/`) inside the existing monolith, one new worker on the existing
RQ/Redis infrastructure, one new frontend feature directory with its own typed API client, plus
targeted additive changes to two *existing* frontend screens (Smart Compare, catalogue product
view) rather than a new dashboard route — consistent with Constitution Principle IV
(research.md R7). No new deployable, no new service, consistent with Principle VI.

## Complexity Tracking

*No Constitution Check violations — this section is intentionally empty.*
