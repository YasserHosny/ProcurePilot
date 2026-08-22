# Quickstart: Organisation Model

This walkthrough assumes an existing signed-up workspace (chunk 4.1) with an owner and at least
one other member already invited (chunk 4.1's team management).

Base URL: `/api/v1`
Auth: `Authorization: Bearer <supabase_jwt>`

## 1. Create Two Branches (as owner)

```bash
curl -sS -X POST "$API_URL/api/v1/organisation/branches" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"name": "Downtown Store", "address": "12 Market St", "region": "GB"}'

curl -sS -X POST "$API_URL/api/v1/organisation/branches" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"name": "Warehouse", "address": "4 Industrial Way", "region": "GB"}'
```

Note both returned `id`s as `$BRANCH_A_ID` and `$BRANCH_B_ID`.

## 2. Create a Branch-Linked and an Organisation-Wide Cost Centre

```bash
curl -sS -X POST "$API_URL/api/v1/organisation/cost-centres" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"name": "Kitchen", "code": "KTC-01", "branch_id": "'"$BRANCH_A_ID"'"}'

curl -sS -X POST "$API_URL/api/v1/organisation/cost-centres" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"name": "Marketing", "code": "MKT-01"}'
```

The second omits `branch_id` — organisation-wide, visible to every branch-scoped member too.

## 3. Define a Budget at Each Scope

```bash
curl -sS -X POST "$API_URL/api/v1/organisation/budgets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"amount": "50000.0000", "currency": "GBP", "period": "annual", "period_start": "2026-01-01", "scope": "organisation"}'

curl -sS -X POST "$API_URL/api/v1/organisation/budgets" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"amount": "5000.0000", "currency": "GBP", "period": "monthly", "period_start": "2026-08-01", "scope": "branch", "branch_id": "'"$BRANCH_A_ID"'"}'
```

## 4. Scope an Existing Branch Manager to Branch A Only

Assumes `$MEMBER_ID` already holds the `branch_manager` role (chunk 4.1's team management,
unchanged) before this step.

```bash
curl -sS -X POST "$API_URL/api/v1/organisation/branch-role-assignments" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"membership_id": "'"$MEMBER_ID"'", "branch_id": "'"$BRANCH_A_ID"'"}'
```

## 5. Confirm Branch-Scoped Visibility

Sign in as the branch-scoped member and list branches — only Branch A should appear, never
Branch B:

```bash
curl -sS "$API_URL/api/v1/organisation/branches" \
  -H "Authorization: Bearer $BRANCH_MANAGER_TOKEN"
# expect: items contains Branch A only

curl -sS "$API_URL/api/v1/organisation/branches/$BRANCH_B_ID" \
  -H "Authorization: Bearer $BRANCH_MANAGER_TOKEN"
# expect: 404 not_found, never 403 — Branch B's existence is not disclosed (FR-008)
```

Then confirm the owner still sees everything:

```bash
curl -sS "$API_URL/api/v1/organisation/branches" \
  -H "Authorization: Bearer $OWNER_TOKEN"
# expect: items contains both Branch A and Branch B
```

## 6. Deactivate a Branch With a Dependent Cost Centre

```bash
curl -sS -X PATCH "$API_URL/api/v1/organisation/branches/$BRANCH_A_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
# expect: 200, but response/details names the Kitchen cost centre and the branch role
# assignment as dependents, per FR-009's "explicit confirmation" requirement — retry with
# confirm_dependents: true to proceed knowingly.

curl -sS "$API_URL/api/v1/organisation/cost-centres/$KITCHEN_COST_CENTRE_ID" \
  -H "Authorization: Bearer $OWNER_TOKEN"
# expect: is_orphaned: true, since its linked branch is now inactive (FR-010)
```
