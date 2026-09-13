# ProcurePilot — Wave 11 Execution Plan (dynamic pool)

**Written**: 2026-09-13, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave10.md` ("Wave 10"), now landed (`main` @ `5b1f69d`,
T009-T016 complete: mobile can approve/reject from the queue built in Wave 10).

**Orchestration model** (unchanged from Waves 6-10): neither the orchestrator role nor an
implementer assignment is fixed to one model. Pool: **Claude (in-house), Codex, Agy** (OpenCode
available per the standing memory). If a dispatched model hits a limit or fails mid-task,
re-dispatch immediately to another pool member; do not schedule a wait for a specific reset time.

---

## 0. Repo state right now

- `main` @ `5b1f69d`. Phases 1-3 of `specs/010-mobile-approvals-receipt/tasks.md` are complete:
  schema/RLS (T001-T005), the `approved -> ordered` transition (T006), mobile scaffolding
  (T007-T008), and mobile approve/reject (T009-T016).
- **This wave covers Phase 4 (User Story 2, T017-T023)** — confirming delivery of an `ordered`
  request, transitioning it to `delivered` with per-line received quantities and a derived
  `has_delivery_discrepancy` flag.
- **Unlike Wave 10, this phase has a real backend component** (T017-T020: contract test,
  integration test, service method, route+schemas) in addition to mobile (T021-T023). Per
  tasks.md's own Delegation Lanes note, T019-T020 suit the `backend` lane and T021-T023 the
  `mobile` lane — with the explicit caveat there that tenancy/RLS work is a candidate for in-house
  handling, "not fixed" until whichever wave plan dispatches this decides.
- **Orchestrator's call for this wave**: delegate both tracks. The schema/RLS work this endpoint
  reads and writes against was already built and independently reviewed in Wave 9
  (`has_delivery_discrepancy`, `quantity_received`, the `ordered`/`delivered` enum values, all
  already exist with RLS in place) — T019/T020 add a new service method and route on top of an
  already-correct foundation, not a new tenancy surface. This is comparable in risk to other
  backend feature work already delegated earlier in this project's history (008's own approval
  endpoints), not to Wave 9's T006 (which modified the single most constitutionally-sensitive
  existing code path). The orchestrator still independently re-verifies against real disposable
  Postgres before merging, per this project's standing "trust but verify" practice — delegation
  does not relax that.
- **Dispatch backend and mobile sequentially, not in parallel** — a standing lesson from earlier
  in this session (parallel Codex+Agy dispatches were both killed by an external SIGTERM twice in
  a row; running one track at a time fixed it immediately). Mobile's T021 also has a real
  dependency on backend's final response shape (T020's schema additions), so sequencing is
  correct here regardless of that lesson.

### Groundwork findings from this plan's own investigation (so the implementer doesn't rediscover them)

1. **The response schema does not yet expose the new delivery fields at all.** `schemas.py`'s
   `PurchaseRequest` has no `delivered_at`/`delivery_confirmed_by_membership_id`/
   `has_delivery_discrepancy`, and `PurchaseRequestLine` has no `quantity_received` — even though
   the DB columns exist (Wave 9). The row-mapper functions `_purchase_request`/
   `_purchase_request_line` in `service.py` don't read them either. T020's "response schemas" task
   must add all four fields to the Pydantic models AND extend both row mappers to populate them —
   this is implied by T019/T020's descriptions, not a separate task, so don't miss it.
2. **The authorization shape is a genuine OR, not a single existing helper.** `_require_requester`
   (raises unless the caller is the request's own requester) and `_authorize_branch_for_write`
   (raises unless the caller is the owner, an unscoped member, or has a `branch_role_assignment`
   for this specific branch — used today by `create_low_stock_report`) each exist independently in
   `service.py`, but nothing today combines them with OR semantics. `confirm_delivery` needs:
   permit if either check would pass; only raise `PermissionDeniedError` if BOTH would fail.
3. **`withdraw_request`** (`service.py` ~line 679) is the closest existing analogue for the overall
   shape of a requester-initiated status-transition method — fetch, check current status raises
   `ConflictError` with a `reason` detail if wrong, authorize, update, record audit, refetch lines,
   return via `_purchase_request_with_budget_status`. `confirm_delivery` should follow the same
   skeleton, checking `status == 'ordered'` (else `ConflictError(details={"reason": "not_ordered"})`
   per the contract) instead of `draft`/`submitted`.
4. **The discrepancy rule is under-delivery only**, per data-model.md: `has_delivery_discrepancy`
   is `true` when ANY line's `quantity_received < quantity` (the ordered quantity). Over-delivery
   is not a discrepancy in this spec — do not add handling for it.
5. **`Idempotency-Key` is accepted but not enforced anywhere in this codebase today** (a standing,
   already-documented caveat from Wave 7, not something this wave fixes). `confirm-delivery` should
   accept the header the same way every other mutating endpoint does — do not add enforcement here
   that doesn't exist elsewhere; that would be inconsistent, not an improvement.

---

## 1. Non-negotiables (unchanged from Wave 1-10)

1. **Tenant isolation is enforced in the database.** Already true for every table this wave
   touches (Wave 9). This wave adds no new table and no new RLS policy.
2. **Tenancy comes from the verified JWT claim.** `confirm_delivery` must use
   `authenticated_client(self._settings, bearer_token)` like every other service method — never a
   path/query tenant parameter.
3. **A cross-tenant read returns "not found," never "forbidden."** A same-tenant-but-different-
   branch request that the caller has no write access to is a `PermissionDeniedError` (403) per
   finding #2 above — that's a real difference in kind, not a violation: the row IS visible to the
   caller (same tenant, RLS lets them read it), the caller is simply not authorized to act on it.
   A genuinely different-tenant request must still 404 via RLS's own SELECT policy, unchanged.
4. **No secrets in the repo.**
5. **Every user-facing string comes from `packages/i18n`** (en + ar). T023 adds `delivery.*` keys
   — check first whether anything reusable already exists (there is no web delivery-confirmation
   screen this reuses from, unlike Wave 10's approvals.* reuse, so a fuller new key set is expected
   here, not a one-key addition).
6. **Every monetary value carries an explicit currency.** Not touched by this wave — quantities,
   not money, are what's being recorded.
7. **`audit_event` is append-only.** `confirm_delivery` must call `self._record(...)` exactly like
   every other mutating method in this file, with a new action string
   (e.g. `requests.delivery_confirmed`) — never skip the audit call.
8. **No autonomous purchasing.** Not directly implicated (this is post-purchase receipt recording,
   not a purchasing decision) but the same discipline applies to WHO may record it: only a human
   request participant (requester or branch-scoped write access), never an automatic transition.
9. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**

---

## 2. Wave 11 scope

### Track A: backend (Codex) — T017-T020

**File scope**: `apps/api/tests/contract/test_confirm_delivery_contract.py` (new),
`apps/api/tests/integration/test_confirm_delivery.py` (new),
`apps/api/src/procurepilot_api/modules/requests/service.py` (new `confirm_delivery` method + row
mapper extensions, per finding #1),
`apps/api/src/procurepilot_api/modules/requests/schemas.py` (new fields + `DeliveryConfirmation*`
input schema),
`apps/api/src/procurepilot_api/modules/requests/router.py` (new route). No migration file should
be needed — the schema this wave reads/writes already exists from Wave 9. If the implementer finds
a migration is actually needed, stop and flag it rather than writing one; that would mean Wave 9's
schema was incomplete, worth surfacing rather than quietly patching.

1. **(T019)** `RequestsService.confirm_delivery()`: fetch the request, require `status == 'ordered'`
   (else `ConflictError(details={"reason": "not_ordered"})`), authorize per finding #2, validate
   each `purchase_request_line_id` in the payload belongs to this request (reject/ignore any that
   don't — decide and document which), write `quantity_received` per line, derive
   `has_delivery_discrepancy` per finding #4, stamp `delivered_at`/
   `delivery_confirmed_by_membership_id`, set `status = 'delivered'`, call `self._record(...)` with
   a new audit action, return the updated `PurchaseRequest` (extend the row mappers per finding
   #1).
2. **(T020)** `POST /requests/{request_id}/confirm-delivery` route + `DeliveryConfirmationCreate`/
   `DeliveryConfirmationLineInput` schemas (mirroring `contracts/mobile-approvals-receipt.openapi.yaml`'s
   `DeliveryConfirmationCreate` shape exactly: `lines: [{purchase_request_line_id, quantity_received}]`),
   plus the four new response fields on `PurchaseRequest`/`PurchaseRequestLine` per finding #1.
3. **(T017)** Contract test: request/response shape matches the OpenAPI contract; `409
   not_ordered` for a request not in `ordered` status.
4. **(T018)** Integration test against real disposable Postgres: full-quantity delivery leaves
   `has_delivery_discrepancy = false`; a short quantity on one line leaves it `true` with the exact
   `quantity_received` recorded on that line only; a request not yet `ordered` refuses with `409
   not_ordered`; a same-tenant different-branch request the caller has no write access to resolves
   with the correct status per finding #2/non-negotiable #3 (403, since it's visible-but-
   unauthorized, not invisible) — confirm this exact distinction is tested, not assumed.

**Land as**: `backend/010-confirm-delivery`.

### Track B: mobile (Codex) — T021-T023, dispatched only after Track A is merged to `main`

**File scope**: `apps/mobile/lib/core/api/requests_api_client.dart` (new method),
`apps/mobile/lib/features/delivery/delivery_confirmation_screen.dart` (new),
`apps/mobile/test/features/delivery/**` (new), `packages/i18n/en.json`/`ar.json` (new `delivery.*`
keys). Written against Track A's actual merged contract, not the OpenAPI doc alone, in case
implementation details differ from the spec in a way that matters to the client.

1. **(T021)** `confirmDelivery(requestId, lines)` on `RequestsApiClient`, calling Track A's new
   endpoint.
2. **(T022)** Delivery confirmation screen: one quantity-received field per line, pre-filled with
   the ordered quantity (`request.lines[i].quantity`), submitting via T021. Reachable from wherever
   an `ordered` request is shown (check `RequestDetailScreen`/the request list for the natural
   entry point — an `ordered`-status request should offer a way into this screen, the same way an
   approver's pending request offers a way into Wave 10's decision screen).
3. **(T023)** `delivery.*` i18n keys (en + ar, exact parity) for the new screen.

**Land as**: `mobile/010-confirm-delivery`.

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T017-T020 (backend) | Codex | orchestrator, against real disposable Postgres |
| T021-T023 (mobile) | Codex | orchestrator, `flutter analyze` + full mobile suite |

Track A gets the fuller scrutiny of the two: re-run the new contract+integration tests plus the
full backend suite against real Postgres (the established disposable-Postgres recipe), read the
authorization-check diff line by line against finding #2, and confirm the 403-not-404 distinction
in non-negotiable #3 is actually exercised by a test, not just asserted in this plan. Track B gets
Wave 10's lighter mobile-only review (analyze + full suite + diff-vs-brief scope check).

---

## 4. What comes after

Once T017-T023 land, Wave 12 covers Phase 5 (User Story 3, quality issue + photo evidence,
T024-T032) — the last user-story phase, and the one that finally exercises the camera-capture
abstraction built in Wave 9 (T008) and the offline-queue pattern for delivery/quality actions
(unlike decisions, which spec.md deliberately requires live connectivity for). Wave 13 (Phase 6,
Cross-cutting, T033-T037) closes out the feature, mirroring 009-mobile-app-mvp's own final phase.

---

## 5. Cautions

- **Don't let the OR-authorization check collapse into an AND by accident** — a request's own
  requester who happens to have no branch assignment must still be able to confirm delivery of
  their own order; test that path explicitly, not just the branch-write-access path.
- **Don't add Idempotency-Key enforcement** that doesn't exist elsewhere in this codebase (finding
  #5) — accept and ignore it, matching every other mutating endpoint.
- **Don't invent a migration** if the schema already supports everything this wave needs (it
  should, per Wave 9) — if one seems necessary, stop and flag it first.
- Constitution non-negotiables (§1): unchanged, still apply to every task.
