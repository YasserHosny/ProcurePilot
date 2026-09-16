# Implementation Plan: Automated Ingestion

**Feature**: 013-automated-ingestion
**Created**: 2026-09-17
**Status**: Draft

## Overview

R3.0 delivers three ingestion channels — email forwarding, mobile capture, and supplier
catalogue import — feeding into the existing extraction and matching pipelines. The plan
follows the established wave-based execution pattern with orchestrator/delegate lanes.

## Delegation Lanes

| Lane | Owner | Scope |
|---|---|---|
| **Orchestrator** | Antigravity / Claude | Migrations, RLS policies, schemas, isolation tests, security review, documentation |
| **Backend** | Claude / OpenCode | Services, workers, API endpoints, integration tests |
| **Frontend** | Agy | Angular components, i18n, API clients under `apps/web/src/` |

Per AGENTS.md: frontend changes under `apps/web/src/**` dispatched to Agy when practical.

## Wave Plan

### Wave 1 — Foundation (Tasks T001–T007)

**Goal**: All new tables, columns, RLS policies, and storage buckets in place.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T001 | Orchestrator | `ingestion_email_log` table + RLS | — |
| T002 | Orchestrator | `ingestion_jobs` table + RLS | — |
| T003 | Orchestrator | `tenant_email_config` table + RLS | — |
| T004 | Orchestrator | `catalogue_imports` table + RLS | — |
| T005 | Orchestrator | `quotations.source` + `ingestion_email_id` columns | — |
| T006 | Orchestrator | `suppliers.email_domains` column | — |
| T007 | Orchestrator | `ingestion-raw` storage bucket + RLS | — |

**Checkpoint**: All migrations apply cleanly. `pnpm db:migrate` succeeds. Tenant isolation
tests pass for new tables.

### Wave 2 — Email Ingestion Backend (Tasks T008–T014)

**Goal**: Inbound emails are received, parsed, deduplicated, supplier-matched, and quotations
created with attachments stored and extraction queued.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T008 | Backend | Ingestion module skeleton (router, schemas) | T001–T007 |
| T009 | Backend | Supplier domain matcher service | T006, T008 |
| T010 | Backend | Email parser service | T008 |
| T011 | Backend | Email ingestion orchestrator service | T001, T005, T009, T010 |
| T012 | Backend | Email ingestion worker | T002, T011 |
| T013 | Backend | Tenant email config API endpoints | T003, T008 |
| T014 | Backend | SES/Mailgun inbound webhook | T007, T011 |

**Checkpoint**: End-to-end test: send test email → webhook → worker → quotation visible.
Deduplication prevents duplicates. Unmatched suppliers route to review queue.

### Wave 3 — Capture & Catalogue Import Backend (Tasks T015–T018)

**Goal**: Mobile capture and supplier catalogue import endpoints working.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T015 | Backend | Capture endpoint | T005, T008 |
| T016 | Backend | Catalogue file parser | T008 |
| T017 | Backend | Catalogue import orchestrator | T004, T006, T016 |
| T018 | Backend | Catalogue import endpoint | T017 |

**Checkpoint**: Capture upload creates quotation. CSV import creates offers. XLSX import works.
Error rows are reported. Price updates on re-import work.

### Wave 4 — Monitoring & Listing APIs (Tasks T019–T021)

**Goal**: Ingestion activity is visible through API endpoints.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T019 | Backend | Ingestion email log listing endpoint | T001, T008 |
| T020 | Backend | Catalogue import history endpoint | T004, T008 |
| T021 | Backend | Ingestion dashboard stats endpoint | T001, T004, T008 |

**Checkpoint**: All listing endpoints return correct paginated data.

### Wave 5 — Frontend (Tasks T022–T029)

**Goal**: All ingestion features have UI with full i18n.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T028 | Frontend (Agy) | i18n keys (en + ar) | — |
| T029 | Frontend (Agy) | Ingestion API client | Wave 4 |
| T022 | Frontend (Agy) | Email config settings component | T013, T029 |
| T023 | Frontend (Agy) | Email log viewer component | T019, T029 |
| T024 | Frontend (Agy) | Capture upload component | T015, T029 |
| T025 | Frontend (Agy) | Catalogue import component | T018, T029 |
| T026 | Frontend (Agy) | Ingestion dashboard component | T021, T029 |
| T027 | Frontend (Agy) | Ingestion routing + navigation | T022–T026 |

**Checkpoint**: All ingestion screens render, i18n works in en + ar, RTL layout verified.

### Wave 6 — Testing & Quality (Tasks T030–T036)

**Goal**: Full test coverage and quality verification.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T030 | Backend | Unit tests: email parser + supplier matcher | T009, T010 |
| T031 | Backend | Integration tests: email ingestion e2e | T011, T012, T014 |
| T032 | Backend | Integration tests: capture endpoint | T015 |
| T033 | Backend | Integration tests: catalogue import | T017, T018 |
| T034 | Orchestrator | Tenant isolation tests | All new tables |
| T035 | Frontend (Agy) | E2E tests: ingestion flows | Wave 5 |
| T036 | Frontend (Agy) | a11y: ingestion surfaces | Wave 5 |

**Checkpoint**: `pnpm test` passes. `pnpm test:isolation` passes. `pnpm test:a11y` zero
violations on ingestion surfaces. E2E tests pass.

### Wave 7 — Documentation & Close-Out (Tasks T037–T042)

**Goal**: All documentation current. Security review complete.

| Task | Lane | Description | Depends on |
|---|---|---|---|
| T037 | Orchestrator | API specification update | Waves 2–4 |
| T038 | Orchestrator | Data dictionary update | Wave 1 |
| T039 | Orchestrator | User documentation | Waves 2–5 |
| T040 | Orchestrator | Test strategy update | Wave 6 |
| T041 | Orchestrator | OpenAPI contract finalization | Waves 2–4 |
| T042 | Orchestrator | Security review: ingestion surfaces | All |

**Checkpoint**: All documentation current. Security review clean. Ready for merge to `main`.

## Key Risks

| Risk | Mitigation |
|---|---|
| SES Inbound setup complexity | Research R1 evaluates Mailgun as fallback. Start SES; pivot within Wave 2 if blocked. |
| Large email attachments (>10 MB) | Enforce limits at webhook level (T014). Reject before storage. |
| Supplier domain collisions (e.g., `@gmail.com`) | Cascading match (address → domain → thread) degrades to review queue (T009). |
| WhatsApp export format fragility | Deferred to direct API in a later release. Capture endpoint is format-independent (T015). |
| Redis dependency creep | R7 research explicitly defers. Database-backed queue only (T002, T012). |

## Success Criteria

- **SC-001**: Email ingestion latency < 60 seconds from receipt to quotation visible.
- **SC-002**: Capture upload response < 3 seconds on 3G for 5 MB image.
- **SC-003**: Catalogue import of 1,000 rows completes within 30 seconds.
- **SC-004**: Zero cross-tenant data leaks in isolation tests.
- **SC-005**: Supplier auto-match rate ≥ 80% for emails from registered supplier domains.
- **SC-006**: Zero ungrounded writes — every ingested document traces to a raw source.
