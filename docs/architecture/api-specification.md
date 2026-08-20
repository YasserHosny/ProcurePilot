# ProcurePilot — API Specification

> OpenAPI 3.1-style contract for the Phase 1–2 API surface.

---

## Conventions

- Base path: `/api/v1`
- Auth: `Authorization: Bearer <supabase_jwt>`
- Tenant scoping from token; no `tenant_id` in path or query.
- Pagination: `?cursor=<cursor>&limit=<int>`; max limit 100.
- Idempotency: `Idempotency-Key: <uuid>` on mutating endpoints.
- Async ops return a `Job` resource.
- Error envelope: `{ "code", "message", "details", "trace_id" }`.

---

## Delivered Platform Foundation API

The following endpoints are delivered for chunk 4.1 and mirror
`specs/001-platform-foundation/contracts/auth-tenant.openapi.yaml`.

### `POST /auth/signup`

- Public.
- Accepts `Idempotency-Key`.
- Creates a workspace and first owner from a valid platform invitation token.
- Request fields: `invitation_token`, `email`, `password`, `business_name`, `region`,
  `currency`, `tax_model`, optional `default_locale`.
- Returns `201` with a `Session`.
- Returns `403` when the platform invitation is missing, expired, spent, or revoked.

### `POST /auth/login`

- Public.
- Request fields: `email`, `password`.
- Returns `200` with a `Session`.
- Invalid credentials return `401` without distinguishing an unknown account from a wrong
  password.
- Rate limited.

### `POST /auth/logout`

- Requires bearer auth.
- Optional request field: `refresh_token`.
- Returns `204`.
- If a client holds a refresh token it should send it, because Supabase can only revoke a refresh
  token it receives.

### `POST /auth/password-reset`

- Public.
- Request field: `email`.
- Always returns `202` to avoid account enumeration.
- Rate limited.

### `GET /me`

- Requires bearer auth.
- Returns the caller's id, email, role, MFA status, preferred locale, and active `Tenant`.

### `PATCH /me`

- Requires bearer auth.
- Updates caller profile preferences.
- Request field: optional `preferred_locale` (`en` or `ar`).
- Returns the updated `Me` resource.

### `GET /me/workspaces`

- Requires bearer auth.
- Returns every active workspace membership for the caller as `WorkspaceSummary` items.

### `PUT /me/active-workspace`

- Requires bearer auth.
- Request fields: `tenant_id`, `refresh_token`.
- Sets the caller's active membership and returns a re-issued `Session`.
- `refresh_token` is required because the tenant claim is injected when an access token is issued;
  switching workspace must mint a new access token carrying the new `tenant_id`.
- Returns `404` when the caller has no active membership in the requested workspace.

### `GET /tenant`

- Requires bearer auth.
- Returns the active workspace.

### `PATCH /tenant`

- Requires bearer auth and owner role.
- Updates workspace settings.
- Request fields: optional `name`, optional `default_locale`.
- `region`, `currency`, and `tax_model` are immutable after creation.

### `GET /members`

- Requires bearer auth.
- Lists members of the active workspace.
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50.

### `PATCH /members/{member_id}`

- Requires bearer auth and owner role.
- Request field: `role`.
- Changes a member's role.
- Returns `409` when the change would leave the workspace without an active owner.

### `DELETE /members/{member_id}`

- Requires bearer auth and owner role.
- Removes a member by setting their status to `removed`; the membership row is retained.
- Returns `409` when removal would leave the workspace without an active owner.

### `GET /invitations`

- Requires bearer auth.
- Lists pending member invitations for the active workspace.

### `POST /invitations`

- Requires bearer auth and owner role; accepts `Idempotency-Key`.
- Request fields: `email`, `role`.
- Creates a member invitation that expires after 7 days.
- Returns `201` with the invitation and the plaintext invitation token.
- The plaintext token is returned once because this chunk has no email delivery; after creation it
  is stored only as a hash and is not retrievable from listings.
- Returns `409` when an invitation is already pending for that address.

### `DELETE /invitations/{invitation_id}`

- Requires bearer auth.
- Revokes a pending invitation.

### `POST /invitations/accept`

- Public.
- Request field: `token`; `password` is required only when the invitee has no account yet.
- Idempotent: accepting the same invitation again returns the existing membership rather than
  creating a duplicate.
- Returns `200` with a `Session`.

### `GET /reference/config-options`

- Public.
- Returns enabled regions, currencies, and tax models for sign-up.

---

## Catalogue

### `GET /products`

Query: `?cursor=&limit=&search=&supplier_id=`

Response:
```json
{
  "data": [
    {
      "id": "uuid",
      "name": "...",
      "brand": "...",
      "base_unit": "litre",
      "pack_count": 6,
      "unit_size": 5.0,
      "preferred_supplier_id": "uuid",
      "updated_at": "..."
    }
  ],
  "next_cursor": "..."
}
```

### `POST /products`

Request:
```json
{
  "canonical_product_id": "uuid?",
  "name": "...",
  "brand": "...",
  "base_unit": "litre",
  "pack_count": 6,
  "unit_size": 5.0,
  "preferred_supplier_id": "uuid?"
}
```

### `POST /products/import`

Async CSV import. Request: multipart/form-data with `file`.
Response: `Job` resource.

---

## Documents

### `POST /documents/presign`

Request:
```json
{
  "filename": "quote.pdf",
  "mime_type": "application/pdf",
  "size": 123456
}
```

Response:
```json
{
  "document_id": "uuid",
  "upload_url": "https://...",
  "path": "tenants/<id>/documents/..."
}
```

### `GET /documents/{id}`

Response:
```json
{
  "id": "uuid",
  "storage_uri": "...",
  "mime_type": "...",
  "hash": "...",
  "source_channel": "upload",
  "created_at": "..."
}
```

---

## Quotations

### `POST /quotations`

Request:
```json
{
  "document_id": "uuid",
  "supplier_id": "uuid?"
}
```

Response:
```json
{
  "id": "uuid",
  "document_id": "uuid",
  "status": "pending",
  "job_id": "uuid"
}
```

### `POST /quotations/{id}/extract`

Triggers or re-runs extraction. Response: `Job`.

### `GET /quotations/{id}`

Response includes header, lines, extraction confidence, review status.

```json
{
  "id": "uuid",
  "supplier_id": "uuid",
  "currency": "GBP",
  "lines": [
    {
      "id": "uuid",
      "original_text": "6 x 5L ...",
      "quantity": 6,
      "unit_price": 12.50,
      "vat_rate": 0.20,
      "confidence": 0.94
    }
  ]
}
```

---

## Review Queue

### `GET /review-tasks`

Query: `?type=extraction|matching&status=open&priority=high&cursor=&limit=`

Response:
```json
{
  "data": [
    {
      "id": "uuid",
      "type": "extraction",
      "quotation_id": "uuid",
      "line_id": "uuid?",
      "priority_score": 0.95,
      "created_at": "..."
    }
  ],
  "next_cursor": "..."
}
```

### `POST /review-tasks/{id}/resolve`

Request:
```json
{
  "field_corrections": {
    "line_id": { "unit_price": 13.00, "quantity": 6 }
  },
  "match_decision": {
    "tenant_product_id": "uuid",
    "outcome": "same_product"
  }
}
```

Response: updated `Quotation` or `QuotationLine`.

---

## Offers & Compare

### `GET /offers`

Query: `?product_id=uuid&quantity=10&include_expired=false`

Response:
```json
{
  "data": [
    {
      "id": "uuid",
      "supplier_id": "uuid",
      "landed_cost": 145.00,
      "unit_price_normalised": 2.42,
      "lead_time_days": 3,
      "valid_to": "...",
      "confidence": 0.96
    }
  ]
}
```

### `GET /offers/compare`

Query: `?product_id=uuid&quantity=10`

Response:
```json
{
  "product": { "id": "uuid", "name": "..." },
  "offers": [...],
  "recommendation": {
    "recommended_offer_id": "uuid",
    "expected_saving": 12.50,
    "confidence": 0.91,
    "risk": "price_valid_until_tomorrow",
    "valid_until": "..."
  }
}
```

---

## Baskets

### `POST /baskets/optimise`

Request:
```json
{
  "items": [
    { "tenant_product_id": "uuid", "quantity": 10 }
  ],
  "constraints": {
    "urgency": "standard",
    "preferred_supplier_ids": ["uuid"],
    "risk_tolerance": "low"
  }
}
```

Response: `Job` resource.

### `GET /baskets/{id}`

Response:
```json
{
  "id": "uuid",
  "status": "completed",
  "allocation": [
    { "supplier_id": "uuid", "lines": [...], "total_landed_cost": 245.00 }
  ],
  "policy_exceptions": [...]
}
```

---

## Savings

### `GET /savings`

Query: `?period=&branch_id=&supplier_id=&cursor=&limit=`

### `GET /savings/{id}/evidence`

Response:
```json
{
  "saving_record": { ... },
  "quotation": { ... },
  "competing_offers": [...],
  "purchase_record": { ... },
  "calculation": { "baseline_value": 100.00, "actual_value": 88.00, "delta": 12.00 }
}
```

---

## Requests & Approvals (Phase 2)

### `POST /requests`

Request:
```json
{
  "branch_id": "uuid",
  "cost_centre_id": "uuid",
  "required_by_date": "2026-10-01",
  "lines": [
    { "tenant_product_id": "uuid", "quantity": 10, "note": "..." }
  ]
}
```

### `POST /requests/{id}/approve`

Request:
```json
{ "comment": "Approved per budget" }
```

### `POST /requests/{id}/reject`

Request:
```json
{ "comment": "Need alternative supplier" }
```

### `GET /approvals/pending`

List pending approvals for the current approver.

---

## Reports

### `POST /reports/export`

Request:
```json
{
  "type": "savings_ledger",
  "format": "xlsx",
  "filters": { "period": "2026-09" }
}
```

Response: `Job` resource; result URL returned on completion.

---

## Jobs

### `GET /jobs/{id}`

Response:
```json
{
  "id": "uuid",
  "status": "pending|running|completed|failed",
  "progress": 0.75,
  "result_url": "...",
  "error": { "code": "", "message": "" }
}
```

---

## Health

### `GET /health`

Response:
```json
{ "status": "ok" }
```
