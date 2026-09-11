# Quickstart: Mobile MVP

This walkthrough assumes an existing workspace with R2.0's organisation model and R2.1's
requests/approvals already in place: at least one branch, a signed-in member scoped to it, and an
approver reachable by routing. It exercises the two new endpoints this chunk adds; the request
submission and status-visibility steps call the exact same `/requests` and `/approvals/*` endpoints
008's quickstart already walks through, unchanged.

Base URL: `/api/v1`
Auth: `Authorization: Bearer <supabase_jwt>`

## 1. Sign In and Register the Device (mobile app, first launch)

```bash
# Same Supabase Auth sign-in web already uses — no new backend surface (research.md R3)
curl -sS -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_ANON_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "'"$MEMBER_EMAIL"'", "password": "'"$MEMBER_PASSWORD"'"}'
# note access_token as $MEMBER_TOKEN

curl -sS -X POST "$API_URL/api/v1/devices" \
  -H "Authorization: Bearer $MEMBER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"platform": "ios", "push_token": "'"$DEVICE_PUSH_TOKEN"'"}'
# expect: 200, last_seen_at stamped now
```

## 2. Re-open the App Later — Registration Refreshes in Place

```bash
curl -sS -X POST "$API_URL/api/v1/devices" \
  -H "Authorization: Bearer $MEMBER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"platform": "ios", "push_token": "'"$DEVICE_PUSH_TOKEN"'"}'
# expect: same id as step 1, last_seen_at bumped — no duplicate row (data-model.md unique constraint)
```

## 3. Branch Manager Submits a Request from Mobile (reuses 008 unchanged)

```bash
curl -sS -X POST "$API_URL/api/v1/requests" \
  -H "Authorization: Bearer $MEMBER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
        "branch_id": "'"$BRANCH_ID"'",
        "required_by_date": "2026-10-01",
        "lines": [{"workspace_product_id": "'"$PRODUCT_ID"'", "quantity": "5.000000"}]
      }'
# note the returned id as $REQUEST_ID

curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/submit" \
  -H "Authorization: Bearer $MEMBER_TOKEN" \
  -H "Idempotency-Key: $(uuidgen)"
# expect: status=submitted — identical shape and behaviour to a web submission (FR-003)
```

## 4. Approver Decides — a Push Notification Fires (research.md R1)

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/approve" \
  -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Approved"}'
# expect: status=approved; a push-send job is queued for every current device_registration
# belonging to $MEMBER_TOKEN's member (FR-007) — delivery itself happens off the request/response
# cycle, so this call's latency is unaffected by push-provider availability (research.md R1)
```

## 5. Branch Manager Reports Low Stock (does not touch purchase_request)

```bash
curl -sS -X POST "$API_URL/api/v1/low-stock-reports" \
  -H "Authorization: Bearer $MEMBER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"branch_id": "'"$BRANCH_ID"'", "workspace_product_id": "'"$PRODUCT_ID"'", "count_remaining": "3.000000"}'
# expect: 201, a new low_stock_report row

curl -sS "$API_URL/api/v1/requests/$REQUEST_ID" \
  -H "Authorization: Bearer $MEMBER_TOKEN"
# expect: the request from step 3 is completely unaffected — no line, status, or field changed
# (FR-006 — confirms the low-stock report created nothing on the request side)
```

## 6. Confirm a Different Branch's Manager Cannot See This Report

```bash
curl -sS "$API_URL/api/v1/low-stock-reports?branch_id=$BRANCH_ID" \
  -H "Authorization: Bearer $OTHER_BRANCH_MANAGER_TOKEN"
# expect: empty items — branch-scoped visibility (data-model.md RLS Summary), same shape as
# purchase_request's own branch scoping
```

## 7. Confirm a Revoked Session Forces Re-Authentication on Mobile

```bash
# (as owner, via web) revoke $MEMBER_TOKEN's session — already possible today, R1

curl -sS "$API_URL/api/v1/requests" \
  -H "Authorization: Bearer $MEMBER_TOKEN"
# expect: 401 — the mobile app must sign in again on next open (FR-014); a successful biometric
# match alone does not bypass this, since biometric unlock only gates use of an already-valid
# refresh token (research.md R3), and a revoked refresh token still fails to refresh
```
