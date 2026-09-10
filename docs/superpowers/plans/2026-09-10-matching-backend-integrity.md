# Matching Backend Integrity Plan

## Goal

Make match resolution safer under retries and more trustworthy as evidence:

- The live pipeline must use deterministic supplier-code aliases instead of leaving that path dead.
- Human match resolution must honor `Idempotency-Key` so client retries do not create confusing conflicts after a successful first attempt.
- Match/cost history append-only guarantees must be covered by authenticated database regression tests.
- Audit and landed-cost side effects must be reviewed for failure windows and improved where the current API stack can do so without introducing Phase 2+ workflows.

## Constraints

- Tenant context comes only from the verified member/JWT flow.
- `match_candidate`, `match_decision`, and `landed_cost` remain append-only.
- No autonomous purchasing or request/approval implementation.
- Keep changes scoped to matching backend, tests, contracts, and quality docs.

## Implementation Steps

1. Add a failing supplier-code integration test.
   - Seed a `product_alias` whose `alias_text` is a supplier product code for a reviewed quotation supplier.
   - Store that code as line-level extracted metadata or the closest currently supported field path.
   - Prove `MatchingService.quotation_matches()` creates an automatic decision with `supplier_code_match = true`.

2. Implement live supplier-code alias loading.
   - Add `_supplier_code_aliases_for_line(...)` in `matching/service.py`.
   - Scope aliases by quotation supplier when present.
   - Pass those aliases into `find_deterministic_candidate(...)`.

3. Add match-resolution idempotency tests.
   - Verify the router passes `Idempotency-Key` into `MatchResolutionService.resolve(...)`.
   - Verify a repeated successful key for the same line returns the original decision instead of `line_already_matched`.
   - Verify reusing the same key for a different line or different payload fails with a conflict.

4. Implement idempotency persistence.
   - Add an append-only, tenant-scoped table for match resolution idempotency mappings.
   - Store tenant, idempotency key, line id, request fingerprint, decision id, and created timestamp.
   - Enable and force RLS with select/insert policies.
   - Update the matching OpenAPI contract to make retry semantics explicit.

5. Add append-only regression tests.
   - Under authenticated tenant context, prove update/delete on `match_candidate`, `match_decision`, and `landed_cost` are denied.
   - Keep `match_task` mutable for its queue status transition.

6. Review audit/landed-cost side effects.
   - If a narrow code fix is possible in this stack, make it.
   - Otherwise document the remaining transaction/outbox gap as a quality conclusion rather than pretending application sequencing is atomic.

## Verification

- `TEST_DATABASE_URL=... pnpm test:api -- apps/api/tests/integration/test_match_alias_learning.py apps/api/tests/integration/test_matching_routing.py`
- `TEST_DATABASE_URL=... pnpm test:api -- apps/api/tests/integration/test_tenant_isolation.py`
- `pnpm test:api -- apps/api/tests/unit/test_matching_audit.py apps/api/tests/unit/test_matching_queue.py`
- `pnpm lint:api apps/api/src/procurepilot_api/modules/matching apps/api/tests/integration/test_match_alias_learning.py apps/api/tests/integration/test_matching_routing.py`
- `git diff --check`
