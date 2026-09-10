# Matching Resolution Side Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make match-resolution retries repair missing audit, task, landed-cost, and idempotency side effects when the match decision was already inserted.

**Architecture:** Keep the authoritative `match_decision` append-only. If a retry arrives with the same `Idempotency-Key` but the idempotency mapping was not written, compare the existing decision with the submitted payload; when they match, complete the idempotent side effects and return the saved decision. This narrows the current failure window without pretending Supabase REST calls are a true multi-table transaction.

**Tech Stack:** Python 3.12, FastAPI service layer, Supabase/PostgREST client, pytest, ruff.

---

### Task 1: Same-Payload Retry Repair

**Files:**
- Modify: `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`
- Test: `apps/api/tests/unit/test_matching_audit.py`

- [ ] **Step 1: Write the failing test**

Add a test proving that when an idempotency record is absent but a matching decision already exists
for the same line/body, `MatchResolutionService.resolve()` completes side effects and returns the
existing decision.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/unit/test_matching_audit.py -k retry_repairs_missing_side_effects
```

Expected: fail with `ConflictError` reason `line_already_matched`.

- [ ] **Step 3: Write minimal implementation**

Refactor post-decision work into an idempotent helper:

- resolve open task
- record `matching.resolved` only if the decision audit event is not already present
- compute landed cost, relying on landed-cost service replay for existing rows
- write the idempotency mapping after the side effects succeed

- [ ] **Step 4: Run test to verify it passes**

Run the same focused test and then the matching audit unit file.

### Task 2: Different-Payload Guard

**Files:**
- Modify: `apps/api/src/procurepilot_api/modules/matching/resolution_service.py`
- Test: `apps/api/tests/unit/test_matching_audit.py`

- [ ] **Step 1: Write the failing test**

Add a test proving that an idempotent retry repair is refused when the existing decision does not
match the submitted outcome/candidate.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd apps/api
uv run pytest tests/unit/test_matching_audit.py -k retry_rejects_different_payload_after_decision_exists
```

Expected: fail until the decision/payload comparison is implemented.

- [ ] **Step 3: Write minimal implementation**

Add `_decision_matches_payload(...)` for same-product/different-pack/different-variant/compatible-
alternative outcomes by comparing outcome and selected candidate id. Keep `no_match_new_product`
outside retry repair unless a stored idempotency mapping already exists.

- [ ] **Step 4: Run test to verify it passes**

Run the focused test and matching audit unit file.

### Verification

```bash
cd apps/api
uv run ruff check src/procurepilot_api/modules/matching/resolution_service.py tests/unit/test_matching_audit.py
uv run pytest tests/unit/test_matching_audit.py tests/unit/test_matching_queue.py tests/unit/test_matching_deterministic.py tests/contract/test_match_resolution_contract.py
cd ../..
git diff --check
```
