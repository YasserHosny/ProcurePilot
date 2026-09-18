# Implementation Plan: Accounting Integration & Reconciliation Foundation

**Branch**: `014-accounting-integration` | **Date**: 2026-09-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-accounting-integration/spec.md`

## Summary

R3.1: connect one QuickBooks Online account per workspace (owner-only, OAuth 2.0), sync its
supplier bills and vendor list daily (plus on-demand), automatically match bills to existing
`purchase_record` rows by supplier + amount (±$0.01) + a 14-day date window, and surface a
reconciliation discrepancy list (amount mismatches, unmatched bills, and purchase records with no
bill after 30 days) for an owner/buyer to review and resolve. Strictly read-only against
QuickBooks — nothing is ever written back. Follows this codebase's established "provider mode"
pattern (`EXTRACTION_PROVIDER_MODE`, `INGESTION_EMAIL_PROVIDER`) for the connector itself, so the
sync/matching/discrepancy logic can be built and tested against a stub client before real
QuickBooks sandbox credentials are wired in.

## Technical Context

**Language/Version**: Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) —
unchanged from every prior chunk.
**Primary Dependencies**: FastAPI (existing), `httpx` (existing, already used for outbound HTTP —
sufficient for QuickBooks's plain REST + OAuth2 token endpoints without a new SDK dependency, see
research.md R1), RQ/Redis (existing, same queue infrastructure as `extraction-worker`/
`export-worker` for the daily sync job).
**Storage**: Supabase Postgres 17 (unchanged). New tables: `accounting_connection`,
`synced_bill`, `synced_vendor`, `purchase_bill_match`, `reconciliation_discrepancy`.
**Testing**: pytest + pytest-asyncio (backend), Karma/Jasmine (frontend unit), Playwright (E2E) —
unchanged. The QuickBooks connector itself is tested against a stub client (same convention as
`extraction_provider_mode=stub`); no live sandbox account is required for the test suite.
**Target Platform**: Linux server (Docker), unchanged modular-monolith deployment.
**Project Type**: Web application (existing `apps/api` + `apps/web`, no new deployable — see
Constitution Principle VI).
**Performance Goals**: No new throughput target beyond the spec's own UX-level criteria (SC-001
connect in <2 min, SC-003 resolve a discrepancy in <60s) — this is a low-QPS, daily-batch feature,
not a request-path-latency-sensitive one.
**Constraints**: Read-only against QuickBooks (FR-013, no create/update/delete calls of any kind
against the provider — enforced by the connector client never exposing a write method, not just
by convention); OAuth tokens encrypted at rest (`SecretStr`-equivalent column-level handling,
matching `smtp_password`/`mailgun_signing_key`'s existing pattern); one active connection per
workspace (FR's own "Accounting Connection" entity definition).
**Scale/Scope**: One provider (QuickBooks Online) for this release; a second provider is R3.3.
90-day initial historical sync window (FR-015); daily recurring sync (FR-008).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Evidence Over Assertion** — N/A for provenance-of-savings specifically (this feature adds
  no AI extraction/matching confidence score), but the spirit applies to reconciliation itself:
  every `Purchase-Bill Match` MUST record whether it was produced automatically or confirmed
  manually (FR's own Key Entities section), so a reconciled figure is traceable to how it was
  decided. **Pass**, carried into data-model.md.
- **II. Deterministic, Replayable Normalisation** — Not applicable to landed-cost specifically;
  the closest analog is that a `Synced Bill`'s history should not be destructively overwritten on
  each sync (an amount correction at the provider should be visible as a change, not silently
  erase what was previously known). Addressed in data-model.md via `updated_at` + retaining the
  provider's own record reference rather than upserting blind. **Pass**.
- **III. Human Authority Over Automation (NON-NEGOTIABLE)** — Directly on-point: FR-013 forbids
  any write-back to QuickBooks (no autonomous action against a customer's live financial system,
  ever), and FR-011 requires an explicit human resolution step for every discrepancy rather than
  auto-resolving. Automatic matching (FR-007) only *links* records for review, it does not itself
  authorize or record a payment/purchase decision. **Pass**.
- **IV. Every Insight Ends in an Action** — The discrepancy list (User Story 3) is the executable
  next step for every insight this feature surfaces; there is no read-only "here are your bills"
  view without a resolution action attached to what needs one. **Pass**.
- **V. Tenant Isolation by Construction (NON-NEGOTIABLE)** — All five new tables are tenant-scoped,
  `ENABLE + FORCE` RLS required (FR-014), proven by extending the existing canonical
  `test_tenant_isolation.py` file (same convention T034 established for 013-automated-ingestion),
  not a new isolation test file. **Pass**, must be verified in data-model.md + implementation.
- **VI. Modular Monolith Until Scale Demands Otherwise** — New `modules/accounting/` inside the
  existing `apps/api` monolith; the daily sync runs as a new worker type on the existing RQ/Redis
  infrastructure (same pattern as `extraction_worker`/`export_worker`/`digest_worker`), not a new
  service. No ADR needed. **Pass**.
- **VII. Money, Tax, and Language Correct from the Schema Up** — Every monetary field
  (`synced_bill.amount`, `purchase_bill_match` comparison, `reconciliation_discrepancy`'s
  side-by-side figures) carries an explicit currency column, never a bare number (spec's own
  edge case on unsupported currencies makes this explicit). All new UI strings go through
  `packages/i18n` (en + ar), RTL-compatible layout, matching every prior feature. **Pass**.

No violations requiring Complexity Tracking.

**Post-design re-check** (after Phase 1 data-model.md/contracts): confirmed, not just assumed —
all five new tables carry `ENABLE + FORCE` RLS with tenant-pinned policies (Principle V); every
cross-module FK pins to a `(tenant_id, id)` composite key, including a companion migration to add
that key to the one pre-existing table (`purchase_record`) that lacked it (Principle V, and
closes a standing memory-noted gap rather than reproducing it in new code); every monetary column
carries an explicit currency (Principle VII); `purchase_bill_match` has no `UPDATE`/`DELETE` grant
(supersede-by-insert instead), matching Principle I's provenance spirit; the OAuth
connector/client design in research.md never exposes a write method against QuickBooks at all
(Principle III). No new violations introduced by the detailed design.

## Project Structure

### Documentation (this feature)

```text
specs/014-accounting-integration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── accounting-integration.openapi.yaml
└── tasks.md              # Phase 2 output (/speckit.tasks — not created here)
```

### Source Code (repository root)

```text
apps/api/src/procurepilot_api/
├── modules/
│   └── accounting/                    # new
│       ├── __init__.py
│       ├── router.py                  # connection + sync-trigger + bills/discrepancies endpoints
│       ├── schemas.py                 # Pydantic request/response models
│       ├── service.py                 # ConnectionService: connect/disconnect/status
│       ├── quickbooks_client.py       # OAuth2 dance + read-only REST calls against QuickBooks
│       ├── connector.py               # AccountingConnector protocol + StubConnector + QuickBooksConnector
│       ├── sync_service.py            # SyncService: fetch bills/vendors, upsert, mark connection health
│       ├── matching_service.py        # MatchingService: bill <-> purchase_record matching (FR-007)
│       └── reconciliation_service.py  # ReconciliationService: discrepancy derivation + resolution
├── workers/
│   └── accounting_sync_worker.py      # new — FOR UPDATE SKIP LOCKED daily sync claim loop
└── tests/
    ├── unit/
    │   ├── test_quickbooks_client.py
    │   └── test_matching_service.py
    └── integration/
        ├── test_accounting_connection.py
        ├── test_accounting_sync.py
        ├── test_accounting_matching.py
        ├── test_reconciliation_discrepancies.py
        └── test_accounting_sync_worker.py

apps/web/src/app/features/accounting/    # new
├── connection-settings/                 # connect/disconnect, connection health
├── bills/                                # synced bills + matched/unmatched view
├── discrepancies/                        # discrepancy list + resolve action
└── accounting-api.ts                     # typed API client, same shape as ingestion-api.ts

supabase/migrations/
└── 202609XXXXXXXX_accounting_*.sql       # accounting_connection, synced_bill, synced_vendor,
                                            purchase_bill_match, reconciliation_discrepancy
```

**Structure Decision**: Mirrors `013-automated-ingestion`'s own structure exactly — one new
backend module (`modules/accounting/`) inside the existing monolith, one new worker on the
existing RQ/Redis infrastructure, one new frontend feature directory with its own typed API
client. No new deployable, no new service, consistent with Principle VI and this codebase's own
established pattern for every prior integration-shaped feature.

## Complexity Tracking

*No Constitution Check violations — this section is intentionally empty.*
