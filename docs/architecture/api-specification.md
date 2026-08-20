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

## Delivered Catalogue and Suppliers API

The following endpoints are delivered for chunk 4.2 and mirror
`specs/002-catalogue-suppliers/contracts/catalogue.openapi.yaml`. All routes require bearer auth.
Tenant scope is resolved from the token. Owner and buyer may mutate; branch manager, approver, and
viewer are read-only.

### `GET /products`

- Requires bearer auth.
- Lists products in the active workspace.
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50,
  optional `status` (`active`, `archived`, or `all`) defaulting to `active`, optional `q`
  free-text filter on the workspace's own product name.
- Returns `200` with `items` containing `Product` resources and nullable `next_cursor`.

### `POST /products`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Creates a product in the active workspace.
- Request fields: `tenant_name`, `base_unit`, `pack`; optional `brand`, `canonical_name`,
  `variant`, `gtin`, `preferred_supplier_id`.
- `pack` fields: `pack_count`, `unit_size`; `base_quantity` is database-derived and returned
  read-only.
- Returns `201` with a `Product`.
- Returns `403` when the caller's role may not create products.
- Returns `422` when validation fails.

### `GET /products/{product_id}`

- Requires bearer auth.
- Returns a product in the active workspace.
- Returns `200` with a `Product`.
- Returns `404` when the product is not in the caller's workspace; this is deliberately
  indistinguishable from a product that exists in another workspace.

### `PATCH /products/{product_id}`

- Requires bearer auth and owner or buyer role.
- Updates a product in the active workspace.
- Request fields: optional `tenant_name`, optional `gtin`, optional `pack`, optional
  `preferred_supplier_id`.
- Pack changes recompute the normalised quantity.
- Returns `200` with the updated `Product`.
- Returns `403` when the caller's role may not update products.

### `DELETE /products/{product_id}`

- Requires bearer auth and owner or buyer role.
- Archives a product; it never deletes the row.
- Returns `204`.
- Returns `403` when the caller's role may not archive products.

### `POST /products/{product_id}/substitutes`

- Requires bearer auth and owner or buyer role.
- Approves another workspace product as a substitute.
- Request field: `substitute_product_id`.
- Returns `201` when the substitute is recorded.
- Returns `403` when the caller's role may not record substitutes.
- Returns `422` when a product is submitted as its own substitute.

### `GET /suppliers`

- Requires bearer auth.
- Lists suppliers in the active workspace.
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50,
  optional `status` (`active`, `preferred`, `blocked`, `archived`, or `all`) defaulting to
  `active`.
- Returns `200` with `items` containing `Supplier` resources and nullable `next_cursor`.

### `POST /suppliers`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Creates a supplier in the active workspace.
- Request fields: `name`; optional `payment_terms`, `lead_time_days`, `minimum_order_value`,
  `delivery_fee`.
- Monetary fields are objects with `amount` as a decimal string and explicit `currency`; the API
  has no bare money numbers.
- Returns `201` with a `Supplier`.
- Returns `403` when the caller's role may not create suppliers.
- Returns `422` when validation fails.

### `GET /suppliers/{supplier_id}`

- Requires bearer auth.
- Returns a supplier in the active workspace.
- Returns `200` with a `Supplier`.
- Returns `404` when the supplier is not in the caller's workspace; this is deliberately
  indistinguishable from a supplier that exists in another workspace.

### `PATCH /suppliers/{supplier_id}`

- Requires bearer auth and owner or buyer role.
- Updates a supplier, including its status.
- Request fields: optional `name`, optional `payment_terms`, optional `lead_time_days`, optional
  `minimum_order_value`, optional `delivery_fee`, optional `status` (`active`, `preferred`,
  `blocked`, or `archived`).
- Returns `200` with the updated `Supplier`.
- Returns `403` when the caller's role may not update suppliers.

### `DELETE /suppliers/{supplier_id}`

- Requires bearer auth and owner or buyer role.
- Archives a supplier.
- Returns `204` when archived.
- Returns `409` when the supplier is referenced by other records and cannot be deleted; archiving
  is offered instead.

### `GET /aliases`

- Requires bearer auth.
- Lists the active workspace's supplier-wording aliases.
- Returns `200` with `items` containing `Alias` resources.

### `POST /aliases`

- Requires bearer auth and owner or buyer role.
- Records that supplier wording refers to a workspace product.
- Request fields: `workspace_product_id`, `alias_text`, optional `supplier_id`.
- Returns `201` with an `Alias`.
- Returns `409` when the wording already resolves to a product in this workspace.

### `DELETE /aliases/{alias_id}`

- Requires bearer auth and owner or buyer role.
- Removes an alias from the active workspace.
- Returns `204`.

### `POST /imports`

- Requires bearer auth and owner or buyer role.
- Uploads a file and validates it without saving catalogue or supplier rows.
- Request: `multipart/form-data` with `kind` (`products` or `suppliers`) and `file`.
- Returns `200` with `ImportPreview`. A `200` means the file was read, not that the file was valid.
- `ImportPreview` includes `import_id`, `kind`, `row_count`, `valid`, `missing_columns`,
  `unrecognised_columns`, `duplicates`, `errors`, and `preview`.
- Import errors include the source file `line`, optional `column`, and `reason`.
- Returns `403` when the caller's role may not import.
- Returns `415` when the file type is refused before parsing.

### `POST /imports/{import_id}/commit`

- Requires bearer auth and owner or buyer role.
- Commits a previously validated import all-or-nothing.
- Request field: optional `on_duplicate` (`skip` or `update`), default `skip`.
- Returns `200` with `ImportResult` fields `import_id`, `created`, `skipped`, and `updated`.
- Returns `409` when the import had errors or was already committed.

### `GET /reference/base-units`

- Requires bearer auth.
- Returns enabled base units a product may be measured in.
- Returns `200` with `items` containing `BaseUnit` resources.

---

## Delivered Quotation Inbox and Extraction API

The following endpoints are delivered for chunk 4.3 and mirror
`specs/003-quotation-inbox-extraction/contracts/quotation-inbox.openapi.yaml`. All routes require
bearer auth. Tenant scope is resolved from the token. Owner and buyer may upload, extract, correct,
and confirm; branch manager, approver, and viewer are read-only. Cross-tenant records return `404`,
deliberately indistinguishable from records that do not exist.

Every monetary value is a `Money` object with `amount` as a decimal string and explicit
`currency`; the API has no bare money numbers.

### `POST /documents/presign`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Creates a tenant-scoped document row and returns a short-lived Supabase Storage upload target.
- File bytes go directly from the client to Storage.
- Request fields: `filename`, `mime_type`, `size_bytes`, optional `content_hash`.
- Accepted MIME types: `application/pdf`, `image/png`, `image/jpeg`, `image/tiff`, `text/csv`,
  `application/vnd.ms-excel`, and
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- Returns `201` with `document_id`, `storage_bucket`, `storage_path`, `upload_url`, optional
  `upload_fields`, and `expires_at`.
- Returns `403` when the caller's role may not request an upload target.
- Returns `415` when the file type is refused before extraction.
- Returns `422` when validation fails.

### `GET /documents/{document_id}`

- Requires bearer auth.
- Reads document metadata and processing status in the active workspace.
- Returns `200` with `id`, `storage_bucket`, `storage_path`, `mime_type`, optional
  `content_hash`, `source_channel`, `status`, `created_at`, and `created_by`.
- `source_channel` is `upload`; `status` is `uploaded` or `failed_to_read`.
- Returns `404` when the document is not in the caller's workspace; this is deliberately
  indistinguishable from a document that exists in another workspace.

### `POST /quotations`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Creates a quotation lifecycle record for an uploaded document after direct upload completes.
- Request fields: `document_id`, optional `supplier_id`.
- `supplier_id` is optional because the reviewer may confirm it later.
- Returns `201` with a `Quotation`.
- Returns `403` when the caller's role may not create quotations.
- Returns `404` when the document is not in the caller's workspace.
- Returns `409` when the document already has an active quotation or cannot be used.
- Returns `422` when validation fails.

### `GET /quotations/{quotation_id}`

- Requires bearer auth.
- Reads a quotation in the active workspace.
- Returns `200` with `QuotationDetail`: quotation header, `document`, `lines`,
  `field_extractions`, and optional `review_task`.
- Header fields include `id`, `document_id`, optional `supplier_id`, optional `currency`,
  optional `issue_date`, optional `expiry_date`, `status`, optional `previous_quotation_id`,
  optional `stated_total`, optional `arithmetic_status`, `created_at`, optional `reviewed_by`, and
  optional `reviewed_at`.
- Line fields include `id`, `line_number`, `original_text`, optional decimal-string `quantity`,
  optional `pack`, optional `unit_price`, optional decimal-string `vat_rate`, optional
  `delivery_fee`, and optional `discount`.
- Field extraction records include the per-field `extracted_value`, decimal-string `confidence`,
  optional `source_page`, optional `source_region`, `extraction_method`, `model_version`, and
  optional correction metadata.
- Returns `404` when the quotation is not in the caller's workspace; this is deliberately
  indistinguishable from a quotation that exists in another workspace.

### `PATCH /quotations/{quotation_id}`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Corrects extracted fields and confirms supplier.
- Request fields: optional `supplier_id`, optional `corrections`.
- Each correction has `field_extraction_id` and `corrected_value`.
- Corrections are recorded as human decisions on field provenance records; original extracted
  values are retained.
- Returns `200` with the updated `QuotationDetail`.
- Returns `403` when the caller's role may not correct quotations.
- Returns `404` when the quotation is not in the caller's workspace.
- Returns `409` when the quotation is not editable in its current state.
- Returns `422` when validation fails.

### `POST /quotations/{quotation_id}/extract`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Enqueues asynchronous extraction for a quotation.
- Returns `202` with the pollable `Job` resource.
- `Job` fields include `id`, `quotation_id`, `status`, optional `attempted_provider`, optional
  `error`, optional `result_url`, `created_at`, optional `started_at`, and optional
  `completed_at`.
- Returns `403` when the caller's role may not extract quotations.
- Returns `404` when the quotation is not in the caller's workspace.
- Returns `409` when extraction is already running or the quotation cannot be extracted.

### `POST /quotations/{quotation_id}/confirm`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Confirms a reviewed quotation as the human authorization step.
- Optional request field: `previous_quotation_id` to link this quotation to an earlier supplier
  re-quote.
- Returns `200` with a `Quotation`.
- A quotation is not trusted commercial data until this endpoint succeeds.
- Returns `403` when the caller's role may not confirm quotations.
- Returns `404` when the quotation is not in the caller's workspace.
- Returns `409` when supplier confirmation, required corrections, or arithmetic mismatch remain
  unresolved.

### `GET /review-tasks`

- Requires bearer auth.
- Lists outstanding quotation review work in the active workspace.
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50,
  optional `status` (`open`, `in_progress`, `resolved`, or `all`) defaulting to `open`, optional
  `priority` (`low`, `normal`, or `high`).
- Returns `200` with `items` containing `ReviewTask` resources and nullable `next_cursor`.
- Review task fields include `id`, `quotation_id`, `status`, `priority`, `reason`, `created_at`,
  and optional `resolved_at`.

### `GET /jobs/{job_id}`

- Requires bearer auth.
- Polls asynchronous extraction job status in the active workspace.
- Returns `200` with a `Job`.
- Job statuses are `queued`, `running`, `succeeded`, and `failed`.
- `attempted_provider` is optional and may be `structured_parse`, `bedrock`, or `azure_di`.
- `result_url` is present on success and usually points to `/api/v1/quotations/{quotation_id}`.
- Returns `404` when the job is not in the caller's workspace; this is deliberately
  indistinguishable from a job that exists in another workspace.

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

## Health

### `GET /health`

Response:
```json
{ "status": "ok" }
```
