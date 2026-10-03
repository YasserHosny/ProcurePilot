# Tasks: R4.1 Supplier IQ v2 and Negotiation Briefs

**Input**: Design documents from `/specs/019-supplier-risk-negotiation/`
**Prerequisites**: plan.md, spec.md

> **Retroactive task list, written 2026-10-03.** Every task below was already implemented and
> merged to `main` in September 2026 (primary commit `def1c35` "feat: R4.1 Supplier IQ v2 and
> negotiation briefs (Tasks 1-11)", plus the granular commits it bundles/follows:
> `2c91482`, `07b3437`, `879771f`, `dd09f90`, `6631328`, `45fe957`, `eb046c1`, `189b7d7`,
> `af3cfbf`, `d602010`, `ca3c986`, `f221df8`, `5c42257`, `19803d6`, `e336874`, `bdffa28`) — none of
> it is proposed future work. Each `[x]` task below was independently re-verified against the real
> file/migration/test on 2026-10-03, exactly as `specs/004-matching-normalisation/tasks.md` and
> `specs/008-requests-approvals/tasks.md` do for their own post-hoc verification passes. The one
> task that could **not** be verified as built is left `[ ]` with an honest note — it is not
> checked off to make the list look complete.

**Organization**: grouped by the four user stories in `spec.md` (US1–US4), with a shared
foundational phase first, matching this repo's established tasks.md convention.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1–US4 from spec.md; setup/foundational tasks carry no story label
- Every task names its exact file path and, since this is a retroactive list, the exact evidence
  that proves it was actually built

---

## Phase 1: Setup

**Purpose**: Confirm this chunk extends the existing Supplier IQ domain rather than forking a
second one (FR-001).

- [x] T001 Confirm no new backend module or frontend domain root was created for supplier risk —
      **verified 2026-10-03**: all v2 code lives inside the pre-existing
      `apps/api/src/procurepilot_api/modules/offers/` package (`supplier_iq_v2.py`,
      `supplier_iq_repository.py`, `negotiation_briefs.py` sit alongside the unchanged
      `supplier_iq.py`, `router.py`, `schemas.py`), and the only new frontend root is the
      feature-scoped `apps/web/src/app/features/supplier-risk/` directory, not a second "risk"
      backend module

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, forced RLS, and the pure deterministic calculator every user story depends
on.

- [x] T002 Create the six new tables (`supplier_scorecard_metric`, `supplier_scorecard_evidence`,
      `negotiation_brief`, `negotiation_brief_item`, `negotiation_brief_item_evidence`,
      `negotiation_brief_action`) plus the `supplier_scorecard_snapshot` v2 columns
      (`state`/`confidence`/`release_posture`/`valid_from`/`valid_until`/`source_fingerprint`/
      `observed_history_days`) and the `synced_bill` payment columns
      (`due_date`/`remaining_balance_amount`/`remaining_balance_currency`) — **verified
      2026-10-03**: `supabase/migrations/20260920000009_supplier_iq_v2.sql` (read in full), with
      the paired-nullability check on `remaining_balance_amount`/`remaining_balance_currency` and
      the `num_nonnulls(...) = 1` exactly-one-typed-source check on
      `supplier_scorecard_evidence`; follow-up idempotency fix in
      `supabase/migrations/20260921000001_supplier_iq_recompute_idempotency.sql`
- [x] T003 Enable and force RLS on all six new tables with tenant-scoped `select` policies and
      owner/buyer-only `insert` policies, and revoke `update`/`delete`/`truncate` from
      `authenticated` and `service_role` on all six — **verified 2026-10-03**: the `do $$ ...
      foreach table_name ...$$` block at the end of `20260920000009_supplier_iq_v2.sql`; proven
      live by `apps/api/tests/integration/test_supplier_iq_v2_isolation.py::
      test_r4_supplier_tables_have_forced_rls_and_policies` and
      `::test_r4_supplier_tables_do_not_grant_mutation_privileges`
- [x] T004 Prove cross-tenant isolation (no read, no insert, no enumeration) across every new
      table, plus a deferred-trigger proof that a brief item cannot commit without an evidence
      link — **verified 2026-10-03**:
      `test_supplier_iq_v2_isolation.py::test_r4_tenant_visibility_and_cross_tenant_insert_are_blocked`,
      `::test_r4_tables_reject_authenticated_update_delete_and_truncate`,
      `::test_brief_item_without_evidence_cannot_commit`,
      `::test_r4_owner_can_insert_every_new_table`,
      `::test_v2_snapshot_fingerprint_preserves_recomputation_history` (8 test functions total in
      this file)
- [x] T005 [P] Implement the pure v2 risk calculator — concentration (currency-bucketed share),
      price drift (median-based, zero-baseline excluded), reliability (cumulative partial
      receipts, expected-date period assignment, decay), single-source exposure (compatible active
      alternative lookup), exactly-three-of-four renormalization, `insufficient_data`/
      `provisional`/`ready` states, and the `0.35`/`0.65` risk-level boundaries, all under
      `Decimal` with a canonical-JSON `source_fingerprint` — **verified 2026-10-03**: read
      `apps/api/src/procurepilot_api/modules/offers/supplier_iq_v2.py` in full (563 lines);
      covered by `apps/api/tests/unit/test_supplier_iq_v2.py` (32 test functions)
- [x] T006 [P] Extend the accounting provider boundary to persist `due_date` and
      `remaining_balance` without ever inferring a payment date from `updated_at` —
      **verified 2026-10-03**: the paired check constraint in T002's migration plus
      `_brief_bills()` in `negotiation_briefs.py` reading `due_date`,
      `remaining_balance_amount`, `remaining_balance_currency` directly off `synced_bill`
      (commit `07b3437` "feat: retain supplier bill due evidence")
- [x] T007 Load tenant-visible evidence and persist a v2 snapshot (header + normalized metric rows
      + typed evidence links) in one authenticated transaction, with `source_fingerprint`-based
      replay and zero partial rows on failure — **verified 2026-10-03**:
      `apps/api/src/procurepilot_api/modules/offers/supplier_iq_repository.py`'s
      `load_risk_input`/`persist_snapshot`/`list_latest` (the last using
      `row_number() over (partition by supplier_id ...) where row_number = 1` for "latest snapshot
      per supplier" dedup — FR-021); proven atomic by
      `apps/api/tests/integration/test_supplier_iq_v2.py::test_recompute_persists_four_metrics_and_replays_by_fingerprint`,
      `::test_recompute_rolls_back_header_and_children_on_child_failure`,
      `::test_recompute_and_evidence_are_tenant_scoped`

**Checkpoint**: Schema, RLS, and the deterministic calculator are proven before any route or UI
exists.

---

## Phase 3: User Story 1 - Review tenant-wide supplier risk (P1)

**Goal**: A buyer scans active suppliers by risk level, confidence, evidence sufficiency,
validity, and top driver.

- [x] T008 [US1] Implement `GET /api/v1/supplier-iq/risks` with cursor pagination (limit 1–100,
      default 50) returning only the latest snapshot per supplier — **verified 2026-10-03**:
      `list_supplier_risks` in `apps/api/src/procurepilot_api/modules/offers/router.py` (line 229);
      contract-proven by
      `apps/api/tests/contract/test_supplier_iq_v2_contract.py::test_supplier_iq_v2_exposes_the_approved_paths_and_methods`
      and `::test_supplier_risk_queue_contract_includes_scan_fields`
- [x] T009 [US1] Implement `POST /api/v1/supplier-iq/recompute` restricted to owner/buyer with a
      required `Idempotency-Key` — **verified 2026-10-03**: `recompute_supplier_risk` in
      `router.py` (line 206) using `require_role(*WRITE_ROLES)` and the `Idempotency-Key` header
      dependency; proven by
      `test_supplier_iq_v2_contract.py::test_supplier_iq_v2_mutations_require_idempotency_keys`
- [x] T010 [US1] Build the Supplier Risk queue page — all members read, only owner/buyer
      recompute, low/medium/high/insufficient risk levels, confidence, stale/G3 posture shown —
      **verified 2026-10-03**:
      `apps/web/src/app/features/supplier-risk/risk-queue/risk-queue.component.ts` +
      `.component.html` exist and are real; `risk-queue.component.spec.ts` passes as part of the
      31/31 focused Angular test count recorded in `docs/quality/r4.1-release-evidence.md`
- [x] T011 [US1] Keep concentration in separate per-currency buckets with no converted or summed
      total displayed — **verified 2026-10-03**: `RiskCurrencyBucket` in `_concentration()`
      (`supplier_iq_v2.py`) never sums across `currency` keys; the share is computed
      currency-by-currency and the overall risk takes `max(bucket.share)`, never a cross-currency
      aggregate

**Checkpoint**: Risk queue is independently testable — scan, read, recompute, currency-bucketed
display — without touching scorecard detail or briefs.

---

## Phase 4: User Story 2 - Inspect risk evidence and trends (P1)

**Goal**: A buyer opens a scorecard and sees every metric's calculation inputs, confidence,
window, and source links before acting.

- [x] T012 [US2] Extend `GET /api/v1/suppliers/{supplier_id}/scorecard` to stay v1-compatible
      while attaching the latest persisted v2 detail (components, currency buckets, exclusions,
      validity, evidence references, risk level, `g3_unmet` posture) — **verified 2026-10-03**:
      `get_supplier_scorecard` in `router.py` (line 191) calling into the extended
      `SupplierIqService`; proven by
      `test_supplier_iq_v2_contract.py::test_supplier_scorecard_contract_preserves_v1_and_adds_v2_detail`
- [x] T013 [US2] Return the standard not-found envelope for a cross-tenant supplier/snapshot ID,
      revealing no existence information — **verified 2026-10-03**: covered by the same
      tenant-scoped RLS proven in T004 plus the service-layer `NotFoundError` raised in
      `negotiation_briefs.py` (`_brief_response`, `_latest_snapshot`) and `supplier_iq.py`'s
      scorecard lookup — a nonexistent and a cross-tenant ID are structurally indistinguishable
      because RLS `select` filters the row out before the application ever decides
- [x] T014 [US2] Build the scorecard v2 evidence panel — metric table with calculation inputs,
      sample count, evidence window, confidence, validity, and source links; `provisional` state
      shown for <180 days observed history with ≥3 calculable components —
      **verified 2026-10-03**: `apps/web/src/app/features/supplier-risk/scorecard-v2-panel/
      scorecard-v2-panel.component.ts` + `.html` exist; embedded in the existing
      `apps/web/src/app/features/catalogue/supplier-scorecard/supplier-scorecard.component.ts`
      (per the file map in `docs/superpowers/plans/2026-09-20-r4-1-supplier-risk-negotiation.md`
      Task 9, directly confirmed by reading `scorecard-v2-panel.component.ts`); the
      `provisional`/`insufficient_data` state logic matches `_calculate_supplier_risk`'s own
      `state` derivation verified in T005

**Checkpoint**: Scorecard detail is independently testable against real evidence, confidence, and
cross-tenant-404 behavior.

---

## Phase 5: User Story 3 - Prepare an evidence-backed negotiation brief (P1)

**Goal**: An owner or buyer prepares a brief from a valid snapshot with ranked, source-linked
talking points; insufficient/expired snapshots are rejected; replays are idempotent.

- [x] T015 [US3] Implement `build_negotiation_brief()` producing at most one item per category
      (price trajectory, alternatives, service performance, concentration/volume, payment context,
      purchase pattern), sorted by descending risk then fixed category order, with purchase
      frequency requiring ≥4 order dates — **verified 2026-10-03**: read
      `apps/api/src/procurepilot_api/modules/offers/negotiation_briefs.py` in full (817 lines);
      `_ORDER` tuple + the `available.sort(...)` key in `build_negotiation_brief` implement FR-011B
      exactly; covered by
      `apps/api/tests/unit/test_negotiation_briefs.py::test_prepare_builds_ranked_source_linked_categories`
- [x] T016 [US3] Implement `POST /api/v1/suppliers/{supplier_id}/negotiation-briefs`, rejecting
      insufficient or expired snapshots with the standard 422 envelope and creating no partial
      rows, and making replay with the same idempotency key return the original brief with no
      duplicate rows — **verified 2026-10-03**: `prepare_for_supplier()`'s `UnprocessableEntityError`
      on `snapshot_expired` and `build_negotiation_brief`'s `ValueError` on
      `snapshot.state == "insufficient_data"`; the `on conflict (tenant_id, supplier_id,
      snapshot_id, brief_version) do nothing` + fallback select in `_insert_brief` makes
      preparation idempotent by construction; proven end-to-end by
      `apps/api/tests/integration/test_negotiation_briefs.py::test_prepare_is_idempotent_and_actions_are_append_only`
      against a real RLS-enforced Postgres, and independently re-confirmed live against hosted
      `procurepilot.iron-sys.com` on 2026-09-23 (`docs/quality/r4.1-release-evidence.md`'s
      "Live Walkthrough Supplier" section)
- [x] T017 [US3] Implement `GET /api/v1/negotiation-briefs` and
      `GET /api/v1/negotiation-briefs/{brief_id}` with every talking point showing evidence,
      confidence, risk, validity, and a localized question key — **verified 2026-10-03**:
      `list_negotiation_briefs`/`get_negotiation_brief` in `router.py` (lines 265–286);
      `_brief_response()` in `negotiation_briefs.py` joins `negotiation_brief_item_evidence` →
      `supplier_scorecard_evidence` and resolves each row's one typed source kind via
      `_brief_evidence_refs()`
- [x] T018 [US3] Build the brief detail screen rendering typed i18n templates, calculations,
      money, confidence, risk, validity, and source links with prepare-button eligibility gated on
      snapshot sufficiency — **verified 2026-10-03**:
      `apps/web/src/app/features/supplier-risk/brief-detail/brief-detail.component.ts` + `.html`
      exist; route `/negotiation-briefs/:id` confirmed ahead of generic routes per the Task 9 file
      map
- [ ] T019 [US3] FR-011A: compute the `service_performance` item's risk as
      `max(reliability_risk, non_matched_qualifying_three_way_rate, quality_incidents_per_qualifying_completed_order)`
      — **left unchecked, 2026-10-03**: this was *not* found built. The shipped
      `_risk_component_item(snapshot, "reliability", "service_performance", ...)` in
      `negotiation_briefs.py` forwards only the `reliability` component's risk value; no query
      against `three_way_match` or `delivery_quality_issue` exists anywhere in
      `negotiation_briefs.py`, and no test in `test_negotiation_briefs.py` (unit or integration)
      asserts a three-way maximum. `supplier_iq.py` (the *v1* module) does compute a
      quality-issue rate for its own, separate v1 reliability metric, but that value is never
      read by the v2 brief path. The internal implementation plan
      (`docs/superpowers/plans/2026-09-20-r4-1-supplier-risk-negotiation.md`, Task 5, "FR-011A:
      Task 5 enforces category uniqueness and service/payment risk formulas") intended this and
      claims it, but the merged code only delivers the category-uniqueness half, not the
      three-signal risk formula. This is a real gap against spec.md, not a documentation
      oversight — closing it would mean wiring `three_way_match`/`delivery_quality_issue` data
      into `BriefContext` and replacing `_risk_component_item`'s reliability-only call for the
      `service_performance` category.

**Checkpoint**: Brief preparation, listing, and detail view are independently testable. One
sub-requirement (FR-011A's three-signal formula) is honestly incomplete.

---

## Phase 6: User Story 4 - Record a human brief decision (P2)

**Goal**: An owner or buyer acknowledges or dismisses a brief with an append-only action history;
an ordinary requester can read but not mutate.

- [x] T020 [US4] Implement `POST /api/v1/negotiation-briefs/{brief_id}/acknowledge` and
      `.../dismiss`, both owner/buyer-only, both requiring `Idempotency-Key`, dismiss requiring a
      non-empty reason, both appending an immutable `negotiation_brief_action` row (never
      updating the brief) with status derived from the latest action —
      **verified 2026-10-03**: `NegotiationBriefService._act()` in `negotiation_briefs.py`
      (idempotency-key reuse returns the original result or raises `ConflictError` on a
      genuine mismatch; `dismiss_reason_required` 422 on an empty reason); table-level enforcement
      via `negotiation_brief_action`'s `check (action <> 'dismissed' or ...)` constraint and
      `unique (tenant_id, idempotency_key)` in `20260920000009_supplier_iq_v2.sql`; end-to-end
      proof in `test_negotiation_briefs.py::test_prepare_is_idempotent_and_actions_are_append_only`
      and the live hosted acknowledge/dismiss sequence recorded in
      `docs/quality/r4.1-release-evidence.md`
- [x] T021 [US4] Prove an ordinary (non-owner/buyer) member gets `403` on
      acknowledge/dismiss/recompute/prepare while reads remain available —
      **verified 2026-10-03**: `require_role(*WRITE_ROLES)` on all four mutation routes in
      `router.py`; RBAC proven by `apps/api/tests/integration/test_supplier_iq_rbac.py` (extended
      for R4.1 per the Task 6 file map) and the tenant-wide `_tenant_select` RLS policy from T003
      that grants every authenticated tenant member read access regardless of role

**Checkpoint**: The full human decision loop (prepare → read → acknowledge/dismiss) is proven,
including the negative RBAC case.

---

## Phase 7: Polish & Cross-Cutting

**Purpose**: i18n/RTL/accessibility, end-to-end coverage, and the release evidence record.

- [x] T022 [P] Add exact English/Arabic key parity for every `supplierRisk.*` and
      `negotiationBrief.*` string — **verified 2026-10-03** (re-counted directly, not just taken
      from the release note): 143 keys on each side of `packages/i18n/en.json` and
      `packages/i18n/ar.json`, zero keys missing on either side
- [x] T023 [P] Write the end-to-end Supplier Risk user journey (queue → scorecard → brief →
      acknowledge/dismiss, Arabic RTL, keyboard navigation, zero axe violations) —
      **verified 2026-10-03**: `apps/web/tests/e2e/supplier-risk.spec.ts` exists (261 lines per
      commit `f221df8`'s diffstat, "test: cover supplier risk user journey"); recorded as 3/3
      passing and the full accessibility gate as 114/114 passing in
      `docs/quality/r4.1-release-evidence.md`
- [x] T024 Record the delivered contract, data model, and G3-unmet posture, including a live
      hosted walkthrough — **verified 2026-10-03** by reading the document directly:
      `docs/quality/r4.1-release-evidence.md` records the full hosted prepare/list/get/
      acknowledge/dismiss flow against `procurepilot.iron-sys.com` on 2026-09-23 (a second,
      synthetic "Live Walkthrough Supplier" was created because the tenant's original supplier
      never cleared the evidentiary gate), 99/99 tenant isolation, 1576/1584 API tests passing
      (8 pre-existing unrelated `azure`-SDK failures), 573/573 Angular unit tests, and a passing
      production build
- [x] T025 Confirm `release_posture = "g3_unmet"` is present on every v2 response and stored
      header without altering the G3 measurements recorded for R3.4 — **verified 2026-10-03**:
      the `check (release_posture is null or release_posture = 'g3_unmet')` constraint on
      `supplier_scorecard_snapshot` and the `not null default 'g3_unmet' check (release_posture =
      'g3_unmet')` constraint on `negotiation_brief` in `20260920000009_supplier_iq_v2.sql` make
      any other value structurally impossible, not merely conventional

---

## Summary

26 tasks (T001–T025, with T019 unchecked). Everything in Phases 1–2 and 4–7, and all of Phase 3
and Phase 6, was independently re-verified on 2026-10-03 against the real migration, the real
source files, and the real test files named above — not re-derived from the commit messages or
the release-evidence document alone, though both corroborate the same facts. Phase 5's T019
(FR-011A's three-signal service-risk formula) is the one requirement from `spec.md` that the
merged code does not deliver; it is left `[ ]` deliberately rather than checked off on the
strength of the internal plan document's claim that it was done.
