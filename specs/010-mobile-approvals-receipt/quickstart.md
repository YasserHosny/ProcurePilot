# Quickstart: Mobile Approvals and Delivery Receipt

This walkthrough assumes an approved request already exists (008-requests-approvals' own
approve/reject endpoints, unchanged — see that spec's quickstart for how to reach `approved` in
the first place). It exercises the two new endpoints this chunk adds.

Base URL: `/api/v1`
Auth: `Authorization: Bearer <supabase_jwt>`

## 1. Decide on a Pending Request (unchanged from 008 — mobile calls the same endpoint)

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/approve" \
  -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"comment": "Looks good"}'
# expect: 200, status "approved" -- research.md R2: no new endpoint for this
```

## 2. Confirm Delivery

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/confirm-delivery" \
  -H "Authorization: Bearer $REQUESTER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"lines": [{"purchase_request_line_id": "'"$LINE_ID"'", "quantity_received": "10.000000"}]}'
# expect: 200, status "delivered", has_delivery_discrepancy false if quantity_received == ordered
```

## 3. Confirm Delivery with a Shortage

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$SHORT_REQUEST_ID/confirm-delivery" \
  -H "Authorization: Bearer $REQUESTER_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"lines": [{"purchase_request_line_id": "'"$LINE_ID"'", "quantity_received": "7.000000"}]}'
# expect: 200, status "delivered", has_delivery_discrepancy true (ordered 10, received 7)
```

## 4. Report a Quality Issue

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$REQUEST_ID/quality-issues" \
  -H "Authorization: Bearer $REQUESTER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "Two boxes arrived crushed"}'
# expect: 201, issue id returned
```

## 5. Attach a Photo to That Issue

```bash
curl -sS -X POST "$API_URL/api/v1/quality-issues/$ISSUE_ID/photos" \
  -H "Authorization: Bearer $REQUESTER_TOKEN" \
  -F "file=@damage.jpg"
# expect: 201, a signed URL back -- storage path is server-allocated (research.md R3), never
# supplied by the client
```

## 6. Confirm a Request Not Yet Ordered Cannot Be Delivery-Confirmed

```bash
curl -sS -X POST "$API_URL/api/v1/requests/$DRAFT_REQUEST_ID/confirm-delivery" \
  -H "Authorization: Bearer $REQUESTER_TOKEN" -H "Content-Type: application/json" -d '{"lines": []}'
# expect: 409, reason "not_ordered"
```

## 7. Confirm Cross-Branch Visibility Still Resolves Not-Found

```bash
curl -sS "$API_URL/api/v1/requests/$OTHER_BRANCH_REQUEST_ID" \
  -H "Authorization: Bearer $SCOPED_MEMBER_TOKEN"
# expect: 404 -- same convention every prior chunk uses (constitution Principle III)
```
