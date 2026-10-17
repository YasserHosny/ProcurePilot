# Tasks: Home Currency Readiness for the Egypt Pilot

**Input**: `specs/022-home-currency-readiness/` (spec, plan, research, data-model, contracts)
**Tracking**: Jira PP-1 (C1) · PP-2 (C3) · PP-3 (C2 fix). **No migration. No RLS change.**
**Format**: `[ID] [P?] [Story] description — path` · `[P]` = parallelisable (different files).
**Rule**: a task is done only when its stated test command was actually run and passed.

## Phase 1: Foundational (blocks US1)

- [x] T001 [US1] Web session helper `homeCurrency()` over `session.tenant()?.currency`, returning `undefined` until loaded, with unit spec — `apps/web/src/app/core/session/`
- [x] T002 [US1] API: restrict `PATCH /tenant` `currency` to `supported_currency` (422 otherwise) + test — `apps/api/src/procurepilot_api/modules/tenants/`
- [x] T003 [US1] API: write an `audit_event` (old → new currency) on `PATCH /tenant` via `record_audit_event`; test shows event row, owner-only (non-owner 403), and that stored documents are untouched — `apps/api/src/procurepilot_api/modules/tenants/` **(in-house: tenant write path)**

## Phase 2: User Story 1 — forms default to home currency (P1)

- [x] T004 [P] [US1] PO create: `'USD'` → `homeCurrency()` (`order-create.component.ts:81`), spec: EGP preselected, USD override saves USD
- [x] T005 [P] [US1] Guardrails settings: `currency` default and reset (`guardrails.component.ts:61,161`) → `homeCurrency()`, spec
- [x] T006 [P] [US1] Quotation review: `|| 'USD'` fallbacks (`quotation-review.component.ts:265,1149`) → quote currency ?? `homeCurrency()`, spec
- [x] T007 [P] [US1] Supplier form: minimum-order and delivery-fee currency default → `homeCurrency()` (`supplier-form.component.ts`), spec
- [x] T008 [US1] Owner-only "Home currency" control in organisation settings (read-only for non-owners), strings in `packages/i18n` en + ar, RTL checked
- [x] T009 [US1] Playwright: tenant EGP → PO create/guardrails/supplier form open EGP; switch one PO to USD stays USD. Run via `pnpm --filter web exec playwright test <spec>` (not `-- <spec>`) — PR #83 merged 2026-10-16, CI End-to-end green; "fails when expected currency is wrong" check not yet done

## Phase 3: User Story 2 — extraction and landed cost (P1)

- [x] T010 [P] [US2] New `currency.py` in extraction-worker: marker detection (`ج.م`, `جنيه`, `جنيه مصري`, `LE`, `L.E.`, `EGP`; adjacent to a number, word-boundary safe; mixed markers → unknown) + Arabic-Indic digit/`٫`/`٬` → exact `Decimal`. **Tests first**, incl. "TABLE"/"Le Pain" negatives and negative amounts
- [x] T011 [US2] Worker: read `tenant.currency` by `tenant_id` on its existing connection; pass as `fallback_currency` into providers/parsers — `worker.py`
- [x] T012 [US2] `structured_parse.py:67` and `azure_di.py:77,153,290-293`: use T010 detection, tenant fallback, remove hard-coded GBP/USD confident values; unresolved currency stores none and routes to review as `currency_unresolved`; tenant currency kept only as `suggested_currency` (amended 2026-10-14)
- [x] T013 [P] [US2] Landed cost: `service.py:89,99,104` GBP → line currency → quote currency → tenant currency → report missing; test all four branches
- [x] T014 [US2] Quotation review UI shows the currency-fallback flag and clears it on confirm/edit (spec, en + ar)
- [ ] T015 [US2] **PP-3 evidence (orchestrator)**: run 5 real/representative Egyptian quotes (incl. Arabic-Indic digits, one unmarked) through extraction; record results on PP-3 and in `specs/022-.../research.md`. SC-002/003

## Phase 4: User Story 3 — mobile money (P2)

- [x] T016 [P] [US3] `intl` available (add to `pubspec.yaml` only if not transitive); `core/format/money_format.dart`: grouping + per-currency minor units (2 default; KWD/BHD/OMR 3; zero-decimal 0), `en`/`ar`, negatives, unknown code → code + 2 decimals, display rounding only. Unit tests incl. 12500 EGP, 12.5 KWD, 1.23456 EGP
- [x] T017 [US3] Use it in `approval_queue_screen.dart:102` and `request_detail_screen.dart:104-148`; widget tests en + ar (RTL). Run `flutter test` in the foreground
- [ ] T018 [US3] Screenshots of both screens (EGP, KWD; en + ar) for SC-004 and the demo video

## Phase 5: Polish

- [x] T019 Docs: user docs (web settings + review flag + mobile), `docs/product/first-customer-gtm-plan.md` C1–C3 marked fixed, CLAUDE.md recent-changes line — PR #81 (verify merged before relying on this)
- [ ] T020 `pnpm lint`, `pnpm test:api`, `pnpm test:web`, worker pytest, `flutter test`, `pnpm test:isolation` all green; run twice consecutively
- [x] T021 Update Jira PP-1/PP-2/PP-3 with PR links (orchestrator, Atlassian connector) — comments on PP-1/2/3 posted 2026-10-15; statuses unchanged

## Dependencies

T001 → T004–T009 · T002/T003 independent · T010 → T011 → T012 → T014/T015 · T013 independent · US3 independent of US1/US2.
**MVP for the demo video**: T001, T004–T007, T016–T018. **Needed before pilot onboarding**: Phase 3.

## Delegation

| Tasks | Lane |
|---|---|
| T002, T003 | In-house (tenant write path) |
| T001, T004–T009, T014 | Codex (web) or agy |
| T010–T013 | Codex (worker/api) |
| T016–T018 | Codex, foreground `flutter test` |
| T015, T019–T021 | Orchestrator |
