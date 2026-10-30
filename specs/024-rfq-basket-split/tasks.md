# Tasks: Split an RFQ Between Suppliers and Turn the Split Into Purchase Requests (024)

**Input**: `specs/024-rfq-basket-split/` — spec.md, plan.md, research.md (R1–R9), data-model.md,
contracts/rfq-split.openapi.yaml, quickstart.md
**Tracking**: Jira PPS-96 (P-66)
**Tests**: included (TDD; each test task goes red before its implementation).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel-safe (different files, no dependency on unfinished tasks)
- **[Story]**: US1–US4 from spec.md
- API paths are under `apps/api/src/procurepilot_api/`.

**Who does what**:

- **In-house (orchestrator)**: the migration, RLS and isolation checks, the conversion lock, and group
  approval routing (T003–T008, T024–T028).
- **Agy**: web.
- **Codex or Agy**: mobile, run in the foreground (memory: background Bash OOM-kills Flutter).
- **Testing unmerged migrations**: on `pp-x-db` (:54399) only.

**Order with 023**: 024 doesn't depend on 023. If 023's `current_match_decision` has merged first,
every new query in this feature joins the view. Otherwise it joins `match_decision`, and 023's T007
moves it.

---

## Phase 1: Setup

- [x] T001 Write a fixture builder `apps/api/tests/integration/fixtures/round1_rfq.py`. It creates, in one tenant:
  - 4 products (rice, flour, oil, sugar) with packs;
  - suppliers الذهبي and الوفرة;
  - an RFQ at the round-1 quantities;
  - two reviewed, fully matched replies at the round-1 prices (الذهبي SAR 4,147, الوفرة SAR 4,137; ideal split SAR 4,063);
  - the landed costs.

  US1–US3 tests reuse it.
- [ ] T002 [P] Add `docs/gtm/demo-tenant/` notes only if the live re-walk later needs a new seed. Otherwise there is nothing to do; record "not needed" in this task when closing it.

---

## Phase 2: Foundational (blocks every story)

- [x] T003 Write a failing migration test in `apps/api/tests/integration/test_request_group_schema.py` (throwaway DB) covering:
  1. insert of a `purchase_request_group` for another tenant's RFQ is refused (RLS WITH CHECK);
  2. a second group for the same RFQ raises a unique violation;
  3. `UPDATE`/`DELETE` on `purchase_request_group` as `authenticated` is denied;
  4. `purchase_request.request_group_id` → a group in another tenant fails the composite FK;
  5. each amount without its currency (or the reverse) fails its check;
  6. `basket_split_job.rfq_id` composite FK.
- [x] T004 Create `supabase/migrations/20261029100000_rfq_split_request_group.sql` per data-model.md:
  - `basket_split_job.rfq_id`;
  - the `purchase_request_group` table: tenant_id, ENABLE + FORCE RLS, select/insert policies with USING and WITH CHECK, no update or delete grants, `unique (tenant_id, rfq_id)`, `unique (tenant_id, idempotency_key)`, composite FKs, money-with-currency checks;
  - `purchase_request.request_group_id` with a composite FK;
  - `approval_step.source` accepts `group_threshold_match` (extend the check or enum, whichever the column uses).

  Shipped in Phase 2 as `20261029080000_rfq_split_request_group.sql`, plus
  `20261029090000_request_group_rls_scope.sql` (the planned filename above differs).
  T003 is green on the throwaway DB (:54398 for this worktree).
- [x] T005 Add group coverage to `apps/api/tests/integration/test_tenant_isolation.py`: a cross-tenant group id is "not found" on read and refused on insert. Run `pnpm test:isolation` on the throwaway DB.
- [x] T006 Add `lock_and_convert(conn, member, rfq_id, purchase_request_id)` to `modules/rfq/service.py`.
  - Shipped in Phase 2 as `lock_rfq_for_preparation` and `mark_converted`.
  - It factors out the `pg_advisory_xact_lock('rfq-prepare:…')`, the `converted` check and the `mark_rfq_converted` call from `prepare_request`.
  - Single-supplier `prepare_request` now uses it, and its existing tests stay green.
  - Add the read of `converted_purchase_request_ids` and `request_group_id` to the RFQ detail (rfq/service.py ~1010) and `modules/rfq/schemas.py`. Single-request RFQs return a one-item list.
- [x] T007 [P] Add `RequestGroupSummary` and `PurchaseRequest.request_group` (nullable, shape in data-model.md) to `modules/requests/schemas.py`. Populate it in one batched query in `_purchase_request_with_budget_status` and the list paths of `modules/requests/service.py`: position by `created_at, id` within the group, plus `sibling_request_ids`.
- [x] T008 [P] Add `BasketSplitJob.rfq_id: UUID | None` in `modules/offers/schemas.py` and read it in `modules/offers/basket_service.py`.

**Checkpoint**: the schema and conversion interface are ready, and the existing RFQ, request and basket
suites are green.

---

## Phase 3: User Story 1 — Split this RFQ from its Responses (P1) 🎯 MVP part 1

**Independent test**: quickstart §2 and §3 step 1. The round-1 split from the RFQ gives SAR 4,063, a
best single total of SAR 4,137 and a saving of SAR 74.

### Tests (red first)

- [x] T009 [P] [US1] Optimiser test in `services/optimiser/tests/test_repository.py`: the same supplier and product have an RFQ-reply quotation and an older, cheaper quotation. A job with `request_snapshot.rfq.price_quotation_ids=[reply]` prices from the reply, and a job without it keeps the latest-price behaviour. Also add a product not quoted by one supplier, which is infeasible for that supplier.
- [x] T010 [P] [US1] Unit tests in `apps/api/tests/unit/test_rfq_split.py`:
  - pack→base conversion: `quantity × pack base_quantity`;
  - eligibility: at least 2 non-refused, reviewed, fully matched replies in one currency;
  - the reasons `not_enough_replies` (with unmatched quotation ids), `mixed_currency` and `rfq_already_converted`.
- [x] T011 [P] [US1] Integration test in `apps/api/tests/integration/test_rfq_split.py`, using T001: `POST /rfq/{id}/split` queues an advanced job with `rfq_id`, base-unit items, the replying suppliers and `price_quotation_ids`. Run the solver in-process, as the existing advanced-basket tests do, and the result total is SAR 4,063 with a saving of 74 against SAR 4,137.

### Implementation

- [x] T012 [US1] Add the `price_quotation_ids` filter to both offer queries in `services/optimiser/src/procurepilot_optimiser_worker/repository.py`, read from `request_snapshot.rfq` (research R2). T009 green.
- [x] T013 [US1] Create `modules/offers/rfq_split.py` with:
  - `build_rfq_split_request(conn, member, rfq_id)`, which handles eligibility (FR-001), builds base-unit items from `rfq_line` × `pack_definition.base_quantity`, takes suppliers and quotation ids from the eligible replies, and builds the snapshot `rfq` block;
  - `start_rfq_split(...)`, which creates the job through `BasketService` and writes the audit `offers.rfq_split_started`.

  T010 green.
- [x] T014 [US1] Add the route `POST /rfq/{rfq_id}/split` (owner/buyer, Idempotency-Key, 202) in `modules/rfq/router.py`, delegating to `offers.rfq_split.start_rfq_split`. T011 green.
- [ ] T015 [P] [US1] Web, delegated to Agy: in `apps/web/src/app/features/rfq/compare/compare.component.{ts,html,scss,spec.ts}` and `rfq-api.ts`, add a "Split between suppliers" button next to Prepare Request.
  - When disabled, it shows the reason: "Needs two matched replies" plus a "Match N lines" link, or "Replies are in different currencies".
  - On click it calls `POST /rfq/{id}/split` and navigates to `/offers/basket-split/{job_id}`.
  - i18n en and ar; Karma red → green.
- [ ] T016 [P] [US1] Web, delegated to Agy: RFQ mode in `apps/web/src/app/features/offers/basket-split/basket-split.component.{ts,html,spec.ts}` and `basket-split-results.component.{ts,html,spec.ts}`.
  - When the job has `rfq_id`, show "From RFQ … (sent Oct 28)" with a link.
  - Items and suppliers are read-only and quantities are shown in packs.
  - The result shows the split total, each single-supplier total and the saving, with money in the shared format.
  - Karma red → green.

---

## Phase 4: User Story 2 — Prepare one request per supplier from the split (P1) 🎯 MVP part 2

**Independent test**: quickstart §3 steps 2–6.

### Tests (red first)

- [ ] T017 [P] [US2] Integration tests in `apps/api/tests/integration/test_rfq_split_prepare.py` (T001 data):
  - prepare creates 2 drafts: الذهبي rice and flour SAR 2,773, الوفرة oil and sugar SAR 1,290;
  - unit prices equal `estimate_from_source_response` for each reply;
  - `source_rfq_response_id` is set, `request_group_id` is set, and the group stores combined 4,063, best single 4,137 and saving 74;
  - the RFQ is `converted` and lists both ids;
  - the same key replays the same body with no new rows;
  - a forced failure on the second insert leaves no group, no requests, and the RFQ `responded`;
  - single `prepare-request` and `prepare-requests` race on two connections: exactly one wins and the other gets 409 `rfq_already_converted`;
  - a new reply or a re-reviewed reply after the split gives 409 `split_stale`;
  - a non-whole pack allocation gives 409 `allocation_not_whole_packs`;
  - an expired reply not confirmed gives 409 `expired_quotation_unconfirmed`.
- [ ] T018 [P] [US2] Unit tests in `apps/api/tests/unit/test_rfq_split.py` for staleness detection (research R6) and base→pack conversion with the 1e-6 whole-pack tolerance.

### Implementation

- [ ] T019 [US2] Add `create_requests_for_group(conn, member, group_row, allocations)` to `modules/requests/service.py`.
  - It inserts one draft `purchase_request` per supplier (branch, required-by, cost centre, `source_rfq_response_id`, `request_group_id`), then its lines with `position` (PPS-99), priced with `requests/valuation.estimate_from_source_response`.
  - Use batched inserts (memory: hosted latency is round trips).
- [ ] T020 [US2] Add `prepare_requests_from_split(member, basket_id, payload, idempotency_key)` to `modules/offers/rfq_split.py`. In one transaction:
  1. return the existing group on an idempotency replay;
  2. `rfq.lock_and_convert` lock and status check;
  3. job completed and `rfq_id` set;
  4. staleness check;
  5. expired-reply confirmation;
  6. base→pack conversion;
  7. insert the group;
  8. `create_requests_for_group`;
  9. `mark_rfq_converted` once;
  10. audit `requests.group_prepared`.

  T017 and T018 green.
- [ ] T021 [US2] Add the route `POST /baskets/{basket_id}/prepare-requests` (owner/buyer, Idempotency-Key; 201, or 200 on replay; 409 reasons per the contract) in `modules/offers/router.py`.
- [ ] T022 [P] [US2] Web, delegated to Agy: "Prepare N requests" on the RFQ-mode result in `apps/web/src/app/features/offers/basket-split/basket-split-results.component.{ts,html,spec.ts}`.
  - A dialog asks for branch (remembered as on RFQ Responses), required-by (defaults to the RFQ's needed-by) and cost centre. It lists expired replies with a confirm checkbox.
  - The `split_stale` reason shows a "Rerun split" action.
  - On success it shows a summary page or panel listing each request with its supplier, total and budget status, with links.
  - Karma red → green.
- [ ] T023 [P] [US2] Web, delegated to Agy: RFQ Details shows "Converted into 2 requests" with links when `converted_purchase_request_ids.length > 1`. This goes in `apps/web/src/app/features/rfq/detail/detail.component.{ts,html,spec.ts}`.

---

## Phase 5: User Story 3 — The split is approved as one (P1)

**Independent test**: quickstart §4.

### Tests (red first)

- [x] T024 [P] [US3] Unit test in `apps/api/tests/unit/test_request_routing.py`: the approver is resolved from the combined total. With thresholds of SAR 2,000 for A and above for B, a group of 2,773 + 1,290 resolves to B, and each request alone would resolve to A for 1,290. The source is `group_threshold_match`, or `owner_fallback` when no rule matches.
- [x] T025 [P] [US3] Integration tests in `apps/api/tests/integration/test_request_group_approval.py`:
  - submit group puts both requests `submitted`, with two steps assigned to B;
  - approve group as B puts both `approved` with the same `decided_at` and comment;
  - one notification is sent to the requester;
  - each request then passes `validate_approved_request_for_order`;
  - reject group with a reason rejects both with that reason;
  - withdraw group withdraws both;
  - approve or reject by A (not assigned, not owner) is refused;
  - single `POST /requests/{id}/submit|withdraw|approve|reject` on a grouped request gives 409 `part_of_split` with `request_group_id`;
  - no group ever ends with mixed statuses.

### Implementation

- [x] T026 [US3] In `modules/requests/service.py` and `modules/requests/routing.py`, add `submit_group`, `approve_group`, `reject_group` and `withdraw_group`.
  - **Submit**: resolve the approver once with `resolve_approver(combined_total, currency, branch_id, …)`, then in one psycopg transaction update the statuses and insert the steps.
  - **Decide**: reuse the SQL of `_decide_and_notify` for every request in one transaction, with one notification outbox row for the group.
  - Audits: `requests.group_submitted`, `requests.group_approved`, `requests.group_rejected` and `requests.group_withdrawn`.
- [x] T027 [US3] Guard `submit_request`, `withdraw_request` and `_decide_request` in `modules/requests/service.py`: a request with `request_group_id` gives `ConflictError(reason="part_of_split", request_group_id=…)`. T025 green.
- [x] T028 [US3] Add the routes `POST /request-groups/{group_id}/submit|approve|reject|withdraw` (Idempotency-Key; roles as the per-request routes) in `modules/requests/router.py`. A cross-tenant id gives 404.
- [ ] T029 [P] [US3] Web, delegated to Agy, in `apps/web/src/app/features/approvals/approval-queue/approval-queue.component.{ts,html,scss,spec.ts}` and `approvals-api.ts`:
  - collapse pending requests by `request_group.id` into one row: "Split from RFQ … · 2 requests · SAR 4,063 · saves SAR 74", with budget status per request, expandable to each request's supplier, lines and total;
  - Approve and Reject on the group call the group endpoints, and the dialog title restates the combined amount and branch.

  Karma red → green.
- [ ] T030 [P] [US3] Web, delegated to Agy: the split context on `apps/web/src/app/features/requests/request-form/request-form.component.{ts,html,spec.ts}` (the request page) and `request-list/request-list.component.{ts,html,spec.ts}`. Show "Part of a split · 1 of 2 · SAR 4,063" with sibling links. Submit and Withdraw on a grouped request call the group endpoints and say so ("Submits both requests of this split").
- [ ] T031 [P] [US3] Mobile, Codex or Agy in the foreground: in `apps/mobile/lib/features/approvals/approval_queue_screen.dart` and `approval_decision_screen.dart`, one card per group, plus a group decision screen calling the group endpoints. Tests in `apps/mobile/test/features/approvals/approval_queue_screen_test.dart` and `approval_decision_screen_test.dart`. Run `flutter test` in the foreground.

---

## Phase 6: User Story 4 — Basket Split used on its own is clearer (P3)

- [ ] T032 [P] [US4] Web, delegated to Agy, in `apps/web/src/app/features/offers/basket-split/basket-split.component.{ts,html,scss,spec.ts}`:
  - the title and subtitle agree with the 2–10 supplier control;
  - `addItem()` adds an empty row (no rice × 10);
  - the pack hint is laid out in flow so it doesn't overlap the next row's label in LTR, RTL, or at ≤ 600 px.

  Karma red → green, with en and ar copy.

---

## Phase 7: Polish & cross-cutting

- [ ] T033 [P] Write an e2e test in `apps/web/tests/e2e/rfq-split-requests.spec.ts`: RFQ Responses → Split → Prepare 2 requests → submit group → approve group, plus an Arabic RTL pass with zero axe violations. Prove it compiles with `npx playwright test --list`; the full run is in CI.
- [ ] T034 [P] Update `docs/architecture/data-dictionary.md` (purchase_request_group, request_group_id, basket_split_job.rfq_id) and `docs/architecture/api-specification.md` (new endpoints, `part_of_split`).
- [ ] T035 Before the PR, run `debate-review --local` and fix the real findings. Write the PR body with `mattpocock-skills:pr`.
- [ ] T036 After merge, run `pnpm db:migrate` on hosted and `pnpm db:check-privileges`, and confirm with `supabase migration list`. Deploy the API and optimiser, and confirm the optimiser image is new.
- [ ] T037 Re-walk round 1 live on «مطاعم رواق»: split (SAR 4,063) → 2 requests → submit → approve as one (web, and mobile if built) → 2 POs, each naming its supplier. Save screenshots to the round-1 flow doc. Update Jira PPS-96 to Done with a Progress comment.

---

## Dependencies

```text
T001 ─▶ T011, T017, T025
T003 ─▶ T004 ─▶ T005, T006, T007, T008
T006 ─▶ T020 ;  T007 ─▶ T029, T030 ;  T008 ─▶ T016
US1 (T009–T016) ─▶ US2 (T017–T023) ─▶ US3 (T024–T031)
US4 (T032) independent
all ─▶ T033–T037
```

- **MVP** = US1 + US2: a split from the RFQ becomes requests. **US3 must ship in the same release**:
  without it, grouped requests could not be submitted (their single-request actions are refused). So
  hold the release or the feature flag until T026–T030 are merged. Mobile (T031) may follow, because
  a 409 on mobile is a safe dead end.

## Parallel examples

- After T004: T006 ‖ T007 ‖ T008.
- US1 tests T009 ‖ T010 ‖ T011, then T012 ‖ T013; web T015 ‖ T016 once the contract is fixed.
- US3: T024 ‖ T025 first; after T028, T029 ‖ T030 ‖ T031.

## Implementation strategy

1. Phase 2 in-house on `pp-x-db`.
2. US1 API + optimiser → US2 API → US3 API, with each test red then green.
3. Web (Agy) for US1–US3 in one or two briefs, after the API contract is fixed; mobile in parallel.
4. Ship US1–US3 together, then US4.
