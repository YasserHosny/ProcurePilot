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

## Auth / Tenant

### `POST /auth/login`

Request:
```json
{
  "email": "user@example.com",
  "password": "..."
}
```

Response:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "user": { "id": "uuid", "email": "...", "role": "buyer" }
}
```

### `GET /me`

Response:
```json
{
  "id": "uuid",
  "email": "...",
  "role": "buyer",
  "tenant": { "id": "uuid", "name": "...", "currency": "GBP" }
}
```

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
