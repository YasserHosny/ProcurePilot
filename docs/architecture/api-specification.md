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

## Delivered Matching and Normalisation API

The following endpoints are delivered for chunk 4.4 and mirror
`specs/004-matching-normalisation/contracts/matching.openapi.yaml`. All routes require bearer
auth. Tenant scope is resolved from the token. Owner and buyer may resolve matches and create
products from a no-match decision; branch manager, approver, and viewer are read-only.
Cross-tenant records return `404`, deliberately indistinguishable from records that do not exist.

Every monetary value is a `Money` object with `amount` as a decimal string and explicit
`currency`; the API has no bare money numbers.

### `GET /quotations/{quotation_id}/matches`

- Requires bearer auth.
- Reads match state for every line of a reviewed quotation.
- Returns `200` with `QuotationMatches`: `quotation_id` and `lines`.
- Each line state includes `line`, ranked `candidates`, optional open or resolved `task`,
  optional final `decision`, and optional `landed_cost` once computed.
- Line summaries include `id`, `line_number`, `original_text`, optional decimal-string
  `quantity`, optional `pack`, optional `unit_price`, optional decimal-string `vat_rate`,
  optional `delivery_fee`, and optional `discount`.
- Candidate fields include `id`, `quotation_line_id`, `candidate_product`, decimal-string
  `confidence`, structured `reasons`, `rank`, `scoring_version`, optional `embedding_model`, and
  `created_at`.
- `reasons` includes `alias_hit`, `gtin_match`, `supplier_code_match`, decimal-string
  `lexical_similarity`, decimal-string `semantic_similarity`, and `feature_score` components for
  brand, variant, pack unit, pack size, and price plausibility.
- Returns `404` when the quotation is not in the caller's workspace; this is deliberately
  indistinguishable from a quotation that exists in another workspace.
- Returns `409` when the quotation is not in the reviewed state yet.

### `GET /match-tasks`

- Requires bearer auth.
- Lists outstanding match-resolution work in the active workspace.
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50,
  optional `status` (`open`, `in_progress`, `resolved`, or `all`) defaulting to `open`, optional
  `priority` (`low`, `normal`, or `high`), optional `reason` (`low_confidence`,
  `close_candidates`, `no_candidate`, or `alias_conflict`), and optional `quotation_id`.
- Returns `200` with `items` containing `MatchTask` resources and nullable `next_cursor`.
- Match task fields include `id`, optional `quotation_id`, `quotation_line`, `status`, `priority`,
  `reason`, ranked `candidates`, optional `decision`, `created_at`, and optional `resolved_at`.
- `MatchTask.quotation_line` uses the same `QuotationLineSummary` shape returned by quotation match
  state.

### `POST /quotation-lines/{line_id}/match`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Resolves one quotation line's match.
- Request fields: `outcome`, optional `selected_match_candidate_id`, optional `create_product`.
- `outcome` is one of `same_product`, `different_pack`, `different_variant`,
  `compatible_alternative`, or `no_match_new_product`.
- `selected_match_candidate_id` is required unless `outcome` is `no_match_new_product`.
- `create_product` is required when `outcome` is `no_match_new_product` and uses the same shape as
  chunk 4.2 product creation: `tenant_name`, `base_unit`, `pack`; optional `brand`,
  `canonical_name`, `variant`, `gtin`, and `preferred_supplier_id`.
- `pack` fields are `pack_count` and decimal-string `unit_size`; `base_quantity` is returned
  read-only and supplying it is an error.
- The exact quotation line wording is inserted or reused as a `ProductAlias`. If that lowercased
  wording already belongs to the same product, the alias is reused. If it belongs to a different
  product, the request returns `409` and the existing alias is not overwritten.
- Returns `200` with a `MatchDecision`.
- Match decision fields include `id`, `quotation_line_id`, `matched_product`,
  optional `selected_match_candidate_id`, `outcome`, `is_automatic`, optional `decided_by`,
  `decided_at`, decimal-string `confidence`, and optional `alias_id`.
- Returns `403` when the caller's role may not resolve matches.
- Returns `404` when the line is not in the caller's workspace; this is deliberately
  indistinguishable from a line that exists in another workspace.
- Returns `409` when the line is not matchable, already has a decision, the selected candidate is
  not valid for the line, or the exact alias wording already belongs to another product.
- Returns `422` when validation fails.

### `GET /quotation-lines/{line_id}/landed-cost`

- Requires bearer auth.
- Reads landed cost, rule version, and replay inputs for one matched quotation line.
- Returns `200` with `LandedCost`.
- Landed cost fields include `id`, `quotation_line_id`, `match_decision_id`, decimal-string
  `quantity`, decimal-string `normalised_base_quantity`, `base_unit`, `unit_price`, `vat_amount`,
  `delivery_fee`, `discount`, `other_charges`, `total`, `raw_inputs`, `rule_version`,
  `valid_from`, optional `valid_to`, `recorded_at`, and `created_at`.
- `unit_price`, `vat_amount`, `delivery_fee`, `discount`, `other_charges`, and `total` are all
  `Money { amount, currency }`; `amount` is a decimal string.
- `vat_amount` is derived from `unit_price_amount * quantity * vat_rate`. `other_charges` is
  always zero in chunk 4.4 because quotation lines do not model other charges yet.
- `raw_inputs` is the complete replay snapshot used by the pinned `rule_version`; recomputation
  uses these stored inputs rather than live quotation, supplier, or catalogue state.
- Returns `404` when the line is not in the caller's workspace; this is deliberately
  indistinguishable from a line that exists in another workspace.
- Returns `409` when the line has not been matched yet, so landed cost is not available.

---

## Delivered Smart Compare and Intelligence API

The following endpoints are delivered for chunk 4.5 and mirror
`specs/005-smart-compare-intelligence/contracts/offers-and-baskets.openapi.yaml`. All routes
require bearer auth. Tenant scope is resolved from the token. Owner and buyer may submit basket
splits and dismiss alerts; branch manager, approver, and viewer are read-only. Cross-tenant
records return `404`, deliberately indistinguishable from records that do not exist.

Every monetary value is a `Money` object with `amount` as a decimal string and explicit
`currency`; the API has no bare money numbers. Offers, recommendations, price history, and alert
conditions are computed at request time from existing catalogue, supplier, match, and landed-cost
data. They are not new persisted sources of price or match truth.

### `GET /offers`

- Requires bearer auth.
- Lists current supplier offers for one workspace product and requested quantity.
- Query parameters: required `product_id`, required decimal-string `quantity`, optional
  `include_expired` defaulting to `false`, optional `cursor`, optional `limit` capped at 100 and
  defaulting to 50.
- Returns `200` with `items` containing `Offer` resources and nullable `next_cursor`.
- Offer fields include `id`, `workspace_product_id`, `supplier_id`, `supplier_name`,
  `quotation_line_id`, `match_decision_id`, `landed_cost`, `normalised_unit_price`,
  decimal-string `requested_quantity`, `base_unit`, optional `lead_time_days`, optional
  decimal-string `reliability_score`, nullable `stock_signal`, decimal-string
  `match_confidence`, `valid_from`, optional `valid_to`, `is_expired`, `rule_version`, and
  `recorded_at`.
- `landed_cost` and `normalised_unit_price` are `Money { amount, currency }`; `amount` is a
  decimal string.
- `stock_signal` is nullable and always null in chunk 4.5 because no stock, availability, or
  inventory source field exists yet.
- Returns `404` when the product is not in the caller's workspace.
- Returns `422` when validation fails.

Example:

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000001",
      "workspace_product_id": "00000000-0000-4000-8000-000000000010",
      "supplier_id": "00000000-0000-4000-8000-000000000020",
      "supplier_name": "Acme Supplies",
      "quotation_line_id": "00000000-0000-4000-8000-000000000030",
      "match_decision_id": "00000000-0000-4000-8000-000000000040",
      "landed_cost": { "amount": "145.0000", "currency": "GBP" },
      "normalised_unit_price": { "amount": "2.4167", "currency": "GBP" },
      "requested_quantity": "10.000000",
      "base_unit": "each",
      "lead_time_days": 3,
      "reliability_score": "0.920",
      "stock_signal": null,
      "match_confidence": "0.9600",
      "valid_from": "2026-08-21T00:00:00Z",
      "valid_to": "2026-08-28T00:00:00Z",
      "is_expired": false,
      "rule_version": "landed-cost-v1",
      "recorded_at": "2026-08-21T09:00:00Z"
    }
  ],
  "next_cursor": null
}
```

### `GET /offers/compare`

- Requires bearer auth.
- Compares offers for one workspace product and requested quantity, then returns one current
  recommendation when at least one eligible non-expired offer exists.
- Query parameters: required `product_id`, required decimal-string `quantity`.
- Returns `200` with `product`, decimal-string `requested_quantity`, `offers`, and nullable
  `recommendation`.
- `product` includes `id` and `tenant_name`.
- `recommendation` fields include `recommended_offer_id`, decimal-string `score`, `confidence`
  (`high`, `medium`, or `low`), `valid_from`, optional `valid_to`, `risk_notes`, and structured
  `evidence`.
- Recommendation evidence includes score weights, score components, winning margin, and tie-break
  evidence. The deterministic tie-break is disclosed when applied.
- Returns `404` when the product is not in the caller's workspace.
- Returns `422` when validation fails.

### `GET /products/{product_id}/price-history`

- Requires bearer auth.
- Reads product price-history intelligence derived from historical landed-cost rows.
- Path parameter: `product_id`.
- Query parameters: optional `supplier_id`, optional `window_months` from 1 to 24 defaulting to 6,
  optional `cursor`, optional `limit` capped at 100 and defaulting to 100.
- Returns `200` with `product`, `window_months`, `points`, `summary`, and nullable `next_cursor`.
- Each `PriceHistoryPoint` includes `landed_cost_id`, `workspace_product_id`, `supplier_id`,
  `supplier_name`, `recorded_at`, `valid_from`, optional `valid_to`, `normalised_unit_price`,
  `landed_cost_total`, decimal-string `quantity`, and `base_unit`.
- `summary` includes nullable `last_paid`, `average_paid_rolling_window`, and `best_price`
  metrics. Each metric has `value: Money` and `source_landed_cost_ids`.
- Returns `404` when the product is not in the caller's workspace.
- Returns `422` when validation fails.

### `POST /baskets/optimise`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Submits an asynchronous two-supplier basket split. This chunk accepts exactly two named
  suppliers and optimises only for minimum total landed cost.
- The request does not accept MOV, delivery-tier, branch, budget, urgency, preference-weight, or
  risk-tolerance constraints in chunk 4.5.
- Request fields: `supplier_ids` with exactly two unique supplier ids, and `items`.
- Each item has `workspace_product_id` and decimal-string `quantity`.
- Returns `202` with a `BasketSplitJob` resource.
- Returns `403` when the caller's role may not submit basket splits.
- Returns `404` when a product, supplier, or job reference is not in the caller's workspace.
- Returns `409` when an equivalent basket split is already queued or running.
- Returns `422` when validation fails.

Request:

```json
{
  "supplier_ids": [
    "00000000-0000-4000-8000-000000000020",
    "00000000-0000-4000-8000-000000000021"
  ],
  "items": [
    {
      "workspace_product_id": "00000000-0000-4000-8000-000000000010",
      "quantity": "10.000000"
    }
  ]
}
```

Response:

```json
{
  "id": "00000000-0000-4000-8000-000000000100",
  "supplier_ids": [
    "00000000-0000-4000-8000-000000000020",
    "00000000-0000-4000-8000-000000000021"
  ],
  "items": [
    {
      "workspace_product_id": "00000000-0000-4000-8000-000000000010",
      "quantity": "10.000000"
    }
  ],
  "status": "queued",
  "result": null,
  "error": null,
  "result_url": "/api/v1/baskets/00000000-0000-4000-8000-000000000100",
  "created_at": "2026-08-21T09:00:00Z",
  "started_at": null,
  "completed_at": null
}
```

### `GET /baskets/{id}`

- Requires bearer auth.
- Polls basket split job status and result in the active workspace.
- Returns `200` with `BasketSplitJob`.
- Job statuses are `queued`, `running`, `completed`, and `failed`.
- `result` is null until a solve completes. Completed result fields include `feasible`,
  `allocation`, nullable `total_landed_cost`, optional `single_supplier_baselines`,
  `infeasible_items`, optional `solver_version`, and `computed_at`.
- Allocation lines include `workspace_product_id`, decimal-string `quantity`, `offer_id`, and
  `landed_cost: Money`.
- An infeasible solve is still `status = "completed"` with `result.feasible = false` and
  structured `infeasible_items`; `status = "failed"` is reserved for worker, database, queue, or
  unexpected solver failures and carries `error`.
- Returns `404` when the job is not in the caller's workspace.

Completed feasible result:

```json
{
  "id": "00000000-0000-4000-8000-000000000100",
  "supplier_ids": [
    "00000000-0000-4000-8000-000000000020",
    "00000000-0000-4000-8000-000000000021"
  ],
  "items": [
    {
      "workspace_product_id": "00000000-0000-4000-8000-000000000010",
      "quantity": "10.000000"
    }
  ],
  "status": "completed",
  "result": {
    "feasible": true,
    "allocation": [
      {
        "supplier_id": "00000000-0000-4000-8000-000000000020",
        "lines": [
          {
            "workspace_product_id": "00000000-0000-4000-8000-000000000010",
            "quantity": "10.000000",
            "offer_id": "00000000-0000-4000-8000-000000000001",
            "landed_cost": { "amount": "145.0000", "currency": "GBP" }
          }
        ],
        "total_landed_cost": { "amount": "145.0000", "currency": "GBP" }
      }
    ],
    "total_landed_cost": { "amount": "145.0000", "currency": "GBP" },
    "single_supplier_baselines": [
      {
        "supplier_id": "00000000-0000-4000-8000-000000000020",
        "feasible": true,
        "total_landed_cost": { "amount": "145.0000", "currency": "GBP" }
      }
    ],
    "infeasible_items": [],
    "solver_version": "basket-split-v1",
    "computed_at": "2026-08-21T09:01:00Z"
  },
  "error": null,
  "result_url": "/api/v1/baskets/00000000-0000-4000-8000-000000000100",
  "created_at": "2026-08-21T09:00:00Z",
  "started_at": "2026-08-21T09:00:05Z",
  "completed_at": "2026-08-21T09:01:00Z"
}
```

### `GET /alerts`

- Requires bearer auth.
- Lists currently true actionable alerts in the active workspace, excluding dismissed
  fingerprints.
- Query parameters: optional `kind` (`recommended_price_expiring`,
  `preferred_supplier_offer_disappeared`, or `price_swing`), optional `cursor`, optional `limit`
  capped at 100 and defaulting to 50.
- Returns `200` with `items` containing `Alert` resources and nullable `next_cursor`.
- Alert fields include deterministic fingerprint `id`, `kind`, `workspace_product_id`, optional
  `supplier_id`, `severity`, structured `evidence`, `action`, `created_from_current_data_at`, and
  `dismissed`.
- Alert conditions are recomputed from current data on every request; only dismissals are stored.

### `POST /alerts/{id}/dismiss`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Dismisses one currently true alert fingerprint.
- Stores the fingerprint in `alert_dismissal`, not the alert condition itself.
- Returns `200` with `AlertDismissal` fields `alert_id` and `dismissed_at`.
- Returns `403` when the caller's role may not dismiss alerts.
- Returns `404` when the alert fingerprint is not currently visible in the caller's workspace.

---

## Delivered Value Proof and Launch Readiness API

The following endpoints are delivered for chunk 4.6 and mirror
`specs/006-value-proof-launch/contracts/savings-and-billing.openapi.yaml`. All routes require
bearer auth. Tenant scope is resolved from the token. Owner and buyer may record purchase outcomes,
verify savings, and request exports; branch manager, approver, and viewer are read-only.
Cross-tenant records return `404`, deliberately indistinguishable from records that do not exist.

Every monetary value is a `Money` object with `amount` as a decimal string and explicit
`currency`; the API has no bare money numbers. Purchase outcome capture creates one
`PurchaseRecord` and one paired pending `SavingRecord` in a single transaction. Baseline, actual,
delta, and calculation inputs are captured at record time from chunk 4.5 price history; verification
later changes only `status`, `verified_at`, and `verified_by`.

### `POST /purchases`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Records an actual purchase outcome and creates its paired pending saving record.
- Request fields: `workspace_product_id`, decimal-string `quantity`, `base_unit`, `unit_price`,
  `total_paid`, and `delivery_result`; optional `supplier_id`, `quotation_line_id`,
  `match_decision_id`, `landed_cost_id`, `ordered_at`, `delivered_at`, and `notes`.
- `unit_price` and `total_paid` are `Money { amount, currency }`; both currencies must match.
- `delivery_result` is `ordered`, `partially_delivered`, `delivered`, `cancelled`, or `disputed`.
- Returns `201` with `purchase_record` and `saving_record`.
- Returns `403` when the caller's role may not record outcomes.
- Returns `404` when any referenced product, supplier, quotation line, match decision, or landed
  cost is not in the caller's workspace.
- Returns `409` for idempotency or state conflicts.
- Returns `422` when validation fails.

Request:

```json
{
  "workspace_product_id": "00000000-0000-4000-8000-000000000010",
  "supplier_id": "00000000-0000-4000-8000-000000000020",
  "quotation_line_id": "00000000-0000-4000-8000-000000000030",
  "match_decision_id": "00000000-0000-4000-8000-000000000040",
  "landed_cost_id": "00000000-0000-4000-8000-000000000050",
  "quantity": "10.000000",
  "base_unit": "each",
  "unit_price": { "amount": "8.8000", "currency": "GBP" },
  "total_paid": { "amount": "88.0000", "currency": "GBP" },
  "delivery_result": "delivered",
  "ordered_at": "2026-08-21T09:00:00Z",
  "delivered_at": "2026-08-22T09:00:00Z",
  "notes": "Delivered in full."
}
```

Response:

```json
{
  "purchase_record": {
    "id": "00000000-0000-4000-8000-000000000060",
    "workspace_product_id": "00000000-0000-4000-8000-000000000010",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "quotation_line_id": "00000000-0000-4000-8000-000000000030",
    "match_decision_id": "00000000-0000-4000-8000-000000000040",
    "landed_cost_id": "00000000-0000-4000-8000-000000000050",
    "quantity": "10.000000",
    "base_unit": "each",
    "unit_price": { "amount": "8.8000", "currency": "GBP" },
    "total_paid": { "amount": "88.0000", "currency": "GBP" },
    "delivery_result": "delivered",
    "ordered_at": "2026-08-21T09:00:00Z",
    "delivered_at": "2026-08-22T09:00:00Z",
    "recorded_by": "00000000-0000-4000-8000-000000000070",
    "recorded_at": "2026-08-21T09:05:00Z",
    "notes": "Delivered in full."
  },
  "saving_record": {
    "id": "00000000-0000-4000-8000-000000000080",
    "purchase_record_id": "00000000-0000-4000-8000-000000000060",
    "workspace_product_id": "00000000-0000-4000-8000-000000000010",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "status": "pending",
    "baseline_policy": "last_paid",
    "baseline_source_landed_cost_ids": ["00000000-0000-4000-8000-000000000090"],
    "baseline_unit_price": { "amount": "10.0000", "currency": "GBP" },
    "baseline_value": { "amount": "100.0000", "currency": "GBP" },
    "actual_value": { "amount": "88.0000", "currency": "GBP" },
    "delta": { "amount": "12.0000", "currency": "GBP" },
    "calculation_version": "saving-baseline-v1",
    "calculation_inputs": {
      "quantity": "10.000000",
      "selected_policy": "last_paid",
      "window_months": 6
    },
    "recorded_by": "00000000-0000-4000-8000-000000000070",
    "recorded_at": "2026-08-21T09:05:00Z",
    "verified_by": null,
    "verified_at": null
  }
}
```

### `GET /savings`

- Requires bearer auth.
- Lists pending and verified savings for the active workspace.
- Query parameters: optional `status` (`pending` or `verified`), optional `period_start`, optional
  `period_end`, optional `supplier_id`, optional `branch_id`, optional `cursor`, optional `limit`
  capped at 100 and defaulting to 50.
- `branch_id` is accepted for future-compatible filtering, but Phase 1 has no Branch entity; the
  only meaningful current value is null or omitted.
- Returns `200` with `items` containing `SavingRecord` resources and nullable `next_cursor`.
- Returns `422` when validation fails.

### `GET /savings/{id}`

- Requires bearer auth.
- Returns one saving record in the active workspace.
- `SavingRecord` fields include `id`, `purchase_record_id`, `workspace_product_id`, optional
  `supplier_id`, `status`, `baseline_policy`, `baseline_source_landed_cost_ids`, nullable
  `baseline_unit_price`, nullable `baseline_value`, `actual_value`, nullable `delta`,
  `calculation_version`, `calculation_inputs`, `recorded_by`, `recorded_at`, nullable
  `verified_by`, and nullable `verified_at`.
- `baseline_policy` is `last_paid`, `rolling_average_6m`, or `none_available`. When no baseline
  exists, `baseline_unit_price`, `baseline_value`, and `delta` are null.
- Returns `404` when the saving record is not in the caller's workspace.

### `GET /savings/{id}/evidence`

- Requires bearer auth.
- Returns the evidence view for one saving record in the active workspace.
- Response fields: `saving_record`, `purchase_record`, nullable `quotation`, nullable
  `match_decision`, `competing_offers`, and `calculation`.
- `calculation` includes `baseline_policy`, nullable `baseline_value`, `actual_value`, nullable
  `delta`, `source_landed_cost_ids`, and `calculation_inputs`.
- Returns `404` when the saving record is not in the caller's workspace.

Response:

```json
{
  "saving_record": {
    "id": "00000000-0000-4000-8000-000000000080",
    "purchase_record_id": "00000000-0000-4000-8000-000000000060",
    "workspace_product_id": "00000000-0000-4000-8000-000000000010",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "status": "verified",
    "baseline_policy": "last_paid",
    "baseline_source_landed_cost_ids": ["00000000-0000-4000-8000-000000000090"],
    "baseline_unit_price": { "amount": "10.0000", "currency": "GBP" },
    "baseline_value": { "amount": "100.0000", "currency": "GBP" },
    "actual_value": { "amount": "88.0000", "currency": "GBP" },
    "delta": { "amount": "12.0000", "currency": "GBP" },
    "calculation_version": "saving-baseline-v1",
    "calculation_inputs": { "selected_policy": "last_paid" },
    "recorded_by": "00000000-0000-4000-8000-000000000070",
    "recorded_at": "2026-08-21T09:05:00Z",
    "verified_by": "00000000-0000-4000-8000-000000000070",
    "verified_at": "2026-08-21T09:10:00Z"
  },
  "purchase_record": {
    "id": "00000000-0000-4000-8000-000000000060",
    "workspace_product_id": "00000000-0000-4000-8000-000000000010",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "quotation_line_id": "00000000-0000-4000-8000-000000000030",
    "match_decision_id": "00000000-0000-4000-8000-000000000040",
    "landed_cost_id": "00000000-0000-4000-8000-000000000050",
    "quantity": "10.000000",
    "base_unit": "each",
    "unit_price": { "amount": "8.8000", "currency": "GBP" },
    "total_paid": { "amount": "88.0000", "currency": "GBP" },
    "delivery_result": "delivered",
    "ordered_at": "2026-08-21T09:00:00Z",
    "delivered_at": "2026-08-22T09:00:00Z",
    "recorded_by": "00000000-0000-4000-8000-000000000070",
    "recorded_at": "2026-08-21T09:05:00Z",
    "notes": "Delivered in full."
  },
  "quotation": {
    "id": "00000000-0000-4000-8000-000000000031",
    "quotation_line_id": "00000000-0000-4000-8000-000000000030"
  },
  "match_decision": {
    "id": "00000000-0000-4000-8000-000000000040",
    "status": "accepted"
  },
  "competing_offers": [],
  "calculation": {
    "baseline_policy": "last_paid",
    "baseline_value": { "amount": "100.0000", "currency": "GBP" },
    "actual_value": { "amount": "88.0000", "currency": "GBP" },
    "delta": { "amount": "12.0000", "currency": "GBP" },
    "source_landed_cost_ids": ["00000000-0000-4000-8000-000000000090"],
    "calculation_inputs": { "selected_policy": "last_paid" }
  }
}
```

### `POST /savings/{id}/verify`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Explicitly verifies a pending saving. The recording buyer may self-verify.
- Verification changes only `status`, `verified_at`, and `verified_by`; it never recomputes
  baseline, actual, delta, or evidence.
- Returns `200` with the verified `SavingRecord`.
- Returns `403` when the caller's role may not verify savings.
- Returns `404` when the saving record is not in the caller's workspace.
- Returns `409` when the saving is already verified or cannot be verified in its current state.

### `POST /exports`

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`.
- Requests an asynchronous savings-ledger export.
- Request fields: `kind` fixed to `savings_ledger`, `format` (`xlsx` or `pdf`), and `filters`.
- `filters` fields: required `period_start`, required `period_end`, optional `supplier_id`, and
  optional `branch_id`. Phase 1 has no Branch entity; non-null `branch_id` is future-compatible
  input only.
- Only verified savings are included in savings-ledger exports.
- Returns `202` with an `ExportJob`.
- Returns `403` when the caller's role may not request exports.
- Returns `404` when a filter reference is not in the caller's workspace.
- Returns `409` when an equivalent export is already queued or running.
- Returns `422` when validation fails.

Request:

```json
{
  "kind": "savings_ledger",
  "format": "xlsx",
  "filters": {
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "branch_id": null
  }
}
```

### `GET /exports/{id}`

- Requires bearer auth.
- Polls export job status and result in the active workspace.
- Returns `200` with `ExportJob`.
- Job statuses are `queued`, `running`, `completed`, and `failed`.
- `row_count`, `download_url`, and storage-backed result metadata are null until completion. A
  completed empty export has `row_count = 0`.
- Failed jobs carry structured `error`.
- Returns `404` when the export job is not in the caller's workspace.

Response:

```json
{
  "id": "00000000-0000-4000-8000-000000000100",
  "kind": "savings_ledger",
  "format": "xlsx",
  "filters": {
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "branch_id": null
  },
  "status": "completed",
  "row_count": 1,
  "download_url": "/api/v1/exports/00000000-0000-4000-8000-000000000100/download",
  "error": null,
  "created_at": "2026-08-21T09:00:00Z",
  "started_at": "2026-08-21T09:00:05Z",
  "completed_at": "2026-08-21T09:01:00Z"
}
```

### `GET /billing/account`

- Requires bearer auth.
- Returns the active workspace's billing account and assigned plan.
- Billing uses the stub provider in chunk 4.6. No real payment provider credentials, Stripe SDK, or
  financial transaction exists.
- `BillingAccount` fields include `id`, `plan`, `provider`, `provider_customer_id`, nullable
  `provider_subscription_id`, `status`, nullable `current_period_start`, nullable
  `current_period_end`, and `assigned_at`.
- `plan` fields include `code`, `name`, `status`, `monthly_price`, `limits`, and `features`.
- Returns `404` when no billing account is configured for the workspace.

Response:

```json
{
  "id": "00000000-0000-4000-8000-000000000110",
  "plan": {
    "code": "starter",
    "name": "Starter",
    "status": "active",
    "monthly_price": { "amount": "0.0000", "currency": "GBP" },
    "limits": { "active_catalogue_products": 100 },
    "features": {}
  },
  "provider": "stub",
  "provider_customer_id": "stub_customer:00000000-0000-4000-8000-000000000001",
  "provider_subscription_id": "stub_subscription:00000000-0000-4000-8000-000000000001:starter",
  "status": "active",
  "current_period_start": null,
  "current_period_end": null,
  "assigned_at": "2026-08-21T09:00:00Z"
}
```

### `GET /billing/limits/active-catalogue-products`

- Requires bearer auth.
- Checks the active catalogue product limit for the current plan.
- The check reads the caller's tenant-scoped active `workspace_product` count and the assigned
  plan. The seeded `starter` plan allows 100 active catalogue products; `growth` allows 1000.
- Returns `200` with `resource`, `plan_code`, nullable `limit`, `used`, `allowed`, and nullable
  `remaining`.
- Returns `404` when no billing account is configured for the workspace.

Response:

```json
{
  "resource": "active_catalogue_products",
  "plan_code": "starter",
  "limit": 100,
  "used": 42,
  "allowed": true,
  "remaining": 58
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
    { "workspace_product_id": "uuid", "quantity": "10.000000", "note": "..." }
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

## Health

### `GET /health`

Response:
```json
{ "status": "ok" }
```
