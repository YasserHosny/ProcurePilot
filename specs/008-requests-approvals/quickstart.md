# Quickstart: Requests + Approvals

This walkthrough assumes an existing workspace with R2.0's organisation model already in place:
at least one branch, a member holding the `approver` role scoped to that branch (or the owner
acting as the only approver), and — for the budget-check steps — a budget defined for the branch.

Base URL: `/api/v1`
Auth: `Authorization: Bearer <supabase_jwt>`

## 1. Define a Threshold Rule (as owner)

```bash
curl -sS -X POST "$API_URL/api/v1/approvals/threshold-rules" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"branch_id": "'"$BRANCH_A_ID"'", "min_amount": "0.0000", "max_amount": "500.0000", "currency": "GBP", "approver_membership_id": "'"$BRANCH_A_APPROVER_ID"'"}'

curl -sS -X POST "$API_URL/api/v1/approvals/threshold-rules" \
  -H "Authorization: Bearer $OWNER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"min_amount": "500.0000", "currency": "GBP", "approver_membership_id": "'"$OWNER_MEMBERSHIP_ID"'"}'
```

The second rule omits `branch_id` (tenant-wide) and `max_amount` (uncapped top tier): anything
£500 and above, for any branch without its own more specific rule, routes to the owner.

## 2. Buyer Creates and Submits a Purchase Request

```bash
curl -sS -X POST "$API_URL/api/v1/requests" \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
        "branch_id": "'"$BRANCH_A_ID"'",
        "cost_centre_id": "'"$COST_CENTRE_ID"'",
        "required_by_date": "2026-10-01",
        "lines": [{"workspace_product_id": "'"$PRODUCT_ID"'", "quantity": "10.000000"}]
      }'
# note the returned id as $REQUEST_ID; status=draft, lines[0].estimated_unit_price reflects the
# product's last known price if any quotation has ever priced it (research.md R2)

curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/submit" \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Idempotency-Key: $(uuidgen)"
# expect: status=submitted, approval_step present with source (threshold_match/owner_fallback),
# estimated_total now frozen — will not change even if price history changes afterward
```

## 3. Approver Sees It in Their Queue and Decides

```bash
curl -sS "$API_URL/api/v1/approvals/pending" \
  -H "Authorization: Bearer $BRANCH_A_APPROVER_TOKEN"
# expect: the request appears with requester, branch, cost centre, lines, required_by_date,
# and budget_status all embedded (FR-005) — no further navigation needed

curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/approve" \
  -H "Authorization: Bearer $BRANCH_A_APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Approved per budget"}'
# expect: status=approved; the request no longer appears in GET /approvals/pending for this approver
```

## 4. Confirm a Different Member Cannot Decide On It

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$OTHER_REQUEST_ID/approve" \
  -H "Authorization: Bearer $UNRELATED_APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
# expect: 403 forbidden (FR-007) — not the resolved approver, not the owner
```

## 5. Delegate Cover While an Approver Is Away

```bash
curl -sS -X POST "$API_URL/api/v1/approvals/delegations" \
  -H "Authorization: Bearer $BRANCH_A_APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"delegate_membership_id": "'"$COLLEAGUE_MEMBERSHIP_ID"'", "starts_on": "2026-09-01", "ends_on": "2026-09-07"}'

# A request submitted for Branch A during that window routes to $COLLEAGUE_MEMBERSHIP_ID instead:
curl -sS "$API_URL/api/v1/approvals/pending" \
  -H "Authorization: Bearer $COLLEAGUE_TOKEN"
# expect: the newly submitted request appears here, not in $BRANCH_A_APPROVER_TOKEN's queue
```

## 6. Confirm a Budget-Exceeding Request Still Submits, With a Warning

Assumes a branch budget with less remaining headroom than the next request's estimated value.

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$LARGE_REQUEST_ID/submit" \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Idempotency-Key: $(uuidgen)"

curl -sS "$API_URL/api/v1/requests/$LARGE_REQUEST_ID" \
  -H "Authorization: Bearer $BUYER_TOKEN"
# expect: budget_status.exceeds = true, remaining_amount shown, status still submitted
# (FR-011 — informational, never a block) and the same warning appears in the approver's
# GET /approvals/pending item for this request
```

## 7. Confirm No Approver Resolves to the Owner (No Threshold Rule, No Approver Assigned)

```bash
curl -sS -X POST "$API_URL/api/v1/requests" \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"branch_id": "'"$BRANCH_WITH_NO_APPROVER_ID"'", "required_by_date": "2026-10-01", "lines": [{"workspace_product_id": "'"$PRODUCT_ID"'", "quantity": "1.000000"}]}'

curl -sS -X POST "$API_URL/api/v1/requests/$UNROUTED_REQUEST_ID/submit" \
  -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Idempotency-Key: $(uuidgen)"
# expect: approval_step.source = "owner_fallback", assigned to the tenant owner (FR-009);
# audit_event gains a requests.approval_step_escalated row for this request
```
