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
- Deterministic matching checks exact GTIN, supplier product code, and learned supplier wording
  before similarity search. Supplier-code matching uses line-level extracted fields and
  tenant/supplier-scoped aliases.
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
- When `Idempotency-Key` is supplied, retrying the same line and request body returns the original
  decision. Reusing that key for another line or request body returns `409`.
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
- `quantity` is expressed in the product's normalised base unit (the same unit returned as
  `base_unit` on every offer) — e.g. kilograms for a product whose catalogue pack is defined in
  kg — never a count of the supplier's original pack/case. A quantity of `10` for a product packed
  6×5L means "10 litres", not "10 cases". This was previously ambiguous and silently misread as a
  pack count, corrupting landed cost and downstream purchase/saving totals by the pack-size
  factor; the API and every client must treat `quantity` as base-unit-denominated.
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
- Query parameters: required `product_id`, required decimal-string `quantity`, denominated in the
  product's normalised base unit — see the equivalent note on `GET /offers` above.
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
- Each item has `workspace_product_id` and decimal-string `quantity`, denominated in the product's
  normalised base unit — same convention as `quantity` on `GET /offers` and `GET /offers/compare`,
  never a count of the supplier's original pack/case.
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
- `branch_id` is accepted for future-compatible filtering. `Branch` now exists as a real entity
  (chunk R2.0, `007-organisation-model`), but `SavingRecord` itself carries no `branch_id` column
  yet — wiring savings to branch scoping is separate, later work, not delivered by this chunk; the
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

- Requires bearer auth and owner or buyer role; accepts `Idempotency-Key`; rate-limited (429,
  `rate_limit.exceeded`, keyed by tenant + membership — chunk R2.5, FR-020).
- Requests an asynchronous export. Extended for R2.5 (FR-002, FR-012, FR-013, FR-029): `kind` is
  `savings_ledger`, `spend_by_supplier`, or `alerts_summary`; `format` is `csv`, `xlsx`, or `pdf`
  (PDF is not offered for `spend_by_supplier` — its value is the currency-grouped table, not a
  printable layout — refused `422`).
- `filters` fields: required `period_start`, optional `period_end` (defaults to today in the
  workspace reporting timezone), optional `supplier_id`, optional `branch_id`. Branch filtering
  is now fully supported with branch-visibility validation — the R1/R2.4-era restriction
  (`unsupported_in_phase_1`, refusing any non-null `branch_id`) is gone as of R2.5.
- Row counts are capped (`EXPORT_ROW_CAP`, default 10,000). An over-cap request is refused with
  `422`, `code: export_row_cap_exceeded`, `details: {cap, actual}` — evaluated before the job row
  is created, so nothing is ever queued for a refused request (SC-004).
- Only verified rows are included for `savings_ledger`. `alerts_summary` reflects live alert
  conditions at generation time, not the requested period (consistent with R2.4's dismissal-only
  alert model — the period/branch filters are accepted but do not narrow this one kind; see
  `docs/quality/r2.5-security-review-record.md` §3).
- Returns `202` with an `ExportJob`.
- Returns `403` when the caller's role may not request exports.
- Returns `422` when validation fails, including an unknown kind/format combination, a branch or
  supplier the caller cannot see, an invalid period, or the row cap exceeded.
- Concurrent equivalent on-demand requests are not de-duplicated; each returns its own job
  (scheduled runs ARE de-duplicated per period — see `POST /reports/schedules` below).

Request:

```json
{
  "kind": "spend_by_supplier",
  "format": "csv",
  "filters": {
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "branch_id": "00000000-0000-4000-8000-000000000030"
  },
  "locale": "en"
}
```

### `GET /exports/{id}`

- Requires bearer auth.
- Polls export job status and result in the active workspace.
- Returns `200` with `ExportJob`.
- Job statuses are `queued`, `running`, `completed`, `failed`, and `expired` (chunk R2.5 —
  retention-purged artifacts).
- `row_count`, `download_url`, and storage-backed result metadata are null until completion, and
  are nulled again once the artifact expires and is purged. A completed empty export has
  `row_count = 0`.
- Failed jobs carry structured `error`.
- Returns `404` when the export job is not in the caller's workspace.

Response:

```json
{
  "id": "00000000-0000-4000-8000-000000000100",
  "kind": "spend_by_supplier",
  "format": "csv",
  "filters": {
    "period_start": "2026-08-01",
    "period_end": "2026-08-31",
    "supplier_id": "00000000-0000-4000-8000-000000000020",
    "branch_id": "00000000-0000-4000-8000-000000000030"
  },
  "status": "completed",
  "row_count": 1,
  "schedule_id": null,
  "locale": "en",
  "download_url": "/api/v1/exports/00000000-0000-4000-8000-000000000100/download",
  "expires_at": "2026-11-21T09:01:00Z",
  "error": null,
  "created_at": "2026-08-21T09:00:00Z",
  "started_at": "2026-08-21T09:00:05Z",
  "completed_at": "2026-08-21T09:01:00Z"
}
```

`schedule_id` is present (non-null) for artifacts generated by a scheduled run — see
`POST /reports/schedules` below — and null for on-demand exports created directly through this
endpoint.

### `GET /exports/{id}/download`

- Requires bearer auth.
- Mints a short-lived signed Supabase Storage URL for a completed export artifact in the active
  workspace, from the private `exports` Storage bucket (chunk R2.5:
  `docs/quality/r2.5-security-review-record.md` §4). The URL lifetime is bounded by
  `EXPORT_DOWNLOAD_URL_TTL_SECONDS` (default 300 seconds, clamped to 60–3600).
- Appends a `reports.artifact_downloaded` audit event with the job id, kind, format, and row
  count.
- Returns `200` with `{ "download_url": "<signed storage url>" }`.
- Returns `404` when the export job does not exist, is not in the caller's workspace, has no
  completed artifact yet (`queued`, `running`, or `failed` jobs), or has been retention-purged
  (`expired`) — a link issued before purge stops resolving once the underlying storage object is
  deleted and the row's storage metadata is nulled.
- The `download_url` field on an `ExportJob` names this endpoint; it is not itself a storage URL.

Response:

```json
{
  "download_url": "https://<project>.supabase.co/storage/v1/object/sign/exports/<tenant>/<path>?token=..."
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

## Delivered Organisation Model API (chunk R2.0, `007-organisation-model`)

Branches, cost centres, and budgets are the organisational structure later Phase 2 releases
(purchase requests and approval routing, R2.1) assign against. A member holding a branch-scoped
role (`branch_manager`, `approver`) sees only their own assigned branch(es) and organisation-wide
entities; an owner sees everything; a same-tenant, different-branch reference resolves as
`not_found`, never forbidden, extending the existing cross-tenant convention to this new axis
(FR-008). Full contract: `specs/007-organisation-model/contracts/organisation.openapi.yaml`.

### `GET /organisation/branches`

- Requires bearer auth. Owner sees every branch in the tenant; a branch-scoped member sees only
  their assigned branch(es); a member holding an unscoped role (or a branch-scoped role with no
  assignment yet) sees every branch, same as owner (research.md R1).
- Query parameters: optional `is_active`, optional `cursor`, optional `limit` capped at 100 and
  defaulting to 50.
- Returns `200` with `items` containing `Branch` resources and nullable `next_cursor`.

### `POST /organisation/branches`

- Requires bearer auth and owner role; accepts `Idempotency-Key`.
- Request fields: required `name`, optional `address`, optional `region`.
- Returns `201` with the created `Branch`.
- Returns `403` when the caller's role is not owner.
- Returns `422` when validation fails.

### `PATCH /organisation/branches/{branch_id}`

- Requires bearer auth and owner role.
- Request fields: all optional — `name`, `address`, `region`, `is_active`, and
  `confirm_dependents` (boolean).
- Deactivating (`is_active: false`) a branch that still has dependents (linked cost centres or
  branch role assignments) requires `confirm_dependents: true`; without it, returns `422` with
  `details.reason = "dependents_confirmation_required"` and `cost_centre_count`/
  `branch_role_assignment_count` naming what is still attached (FR-009 — deactivation is always
  permitted, this is a confirmation step, never a hard block). No hard-delete route exists.
- Returns `200` with the updated `Branch`.
- Returns `403` when the caller's role is not owner.
- Returns `404` when the branch is not in the caller's workspace or branch-scoped visibility.
- Returns `422` on the dependents-confirmation case above or other validation failures.

Request (deactivating with dependents already confirmed):

```json
{ "is_active": false, "confirm_dependents": true }
```

### `GET /organisation/cost-centres`

- Requires bearer auth. Same branch-scoped visibility as branches, evaluated against the cost
  centre's own `branch_id` (a `null` branch_id — organisation-wide — is always visible).
- Query parameters: optional `branch_id`, optional `is_archived`, optional `cursor`, optional
  `limit` capped at 100 and defaulting to 50.
- Returns `200` with `items` containing `CostCentre` resources and nullable `next_cursor`.

### `POST /organisation/cost-centres`

- Requires bearer auth and owner role; accepts `Idempotency-Key`.
- Request fields: required `name`, required `code`, optional `budget_owner_membership_id`,
  optional `branch_id` (omit for an organisation-wide cost centre).
- Returns `201` with the created `CostCentre`.
- Returns `403` when the caller's role is not owner.
- Returns `409` when `code` is already in use elsewhere in the tenant (FR-003).
- Returns `422` when validation fails.

### `PATCH /organisation/cost-centres/{cost_centre_id}`

- Requires bearer auth and owner role.
- Request fields: all optional — `name`, `code`, `budget_owner_membership_id`, `branch_id`,
  `is_archived`.
- Returns `200` with the updated `CostCentre`, including a computed `orphan_reason`
  (`branch_deactivated` | `owner_removed` | `null`) alongside the stored `is_orphaned` flag —
  derived live from the linked branch's `is_active` / the budget owner's membership status, never
  stored itself.
- Returns `403` when the caller's role is not owner.
- Returns `404` when the cost centre is not in the caller's workspace or branch-scoped visibility.
- Returns `409` when `code` collides with another cost centre in the tenant.
- Returns `422` when validation fails.

### `GET /organisation/budgets`

- Requires bearer auth. Same branch-scoped visibility, evaluated against `scope`/`branch_id`/
  `cost_centre_id`; `organisation`-scoped budgets are always visible once tenant matches.
- Query parameters: optional `scope`, optional `branch_id`, optional `cost_centre_id`, optional
  `cursor`, optional `limit` capped at 100 and defaulting to 50.
- Returns `200` with `items` containing `Budget` resources (`amount` as nested `Money`) and
  nullable `next_cursor`.

### `POST /organisation/budgets`

- Requires bearer auth and owner role; accepts `Idempotency-Key`.
- Request fields: required decimal-string `amount` (non-negative only, unlike `Money`'s own
  pattern), required `currency`, required `period` (`monthly` | `quarterly` | `annual`), required
  `period_start`, required `scope` (`organisation` | `branch` | `cost_centre`), and `branch_id`/
  `cost_centre_id` required if and only if the matching scope is chosen.
- `currency` is never inferred from `tenant.currency` (research.md R3) — always explicit.
- Multiple budgets may coexist for the same scope with overlapping periods (spec.md User Story 3,
  Acceptance Scenario 3); an overlap with any existing budget for the same scope/target is
  reported via `overlap_warning`, never rejected.
- Returns `201` with the created `Budget` plus `overlap_warning: boolean`.
- Returns `403` when the caller's role is not owner.
- Returns `404` when the referenced branch or cost centre is not in the caller's workspace.
- Returns `422` when validation fails (including the `budget_scope_target` database constraint on
  a mismatched scope/reference pairing).

Request:

```json
{
  "amount": "5000.0000",
  "currency": "GBP",
  "period": "annual",
  "period_start": "2026-01-01",
  "scope": "organisation"
}
```

Response:

```json
{
  "id": "00000000-0000-4000-8000-000000000100",
  "amount": { "amount": "5000.0000", "currency": "GBP" },
  "period": "annual",
  "period_start": "2026-01-01",
  "scope": "organisation",
  "branch_id": null,
  "cost_centre_id": null,
  "created_by": "00000000-0000-4000-8000-000000000070",
  "created_at": "2026-08-22T09:05:00Z",
  "overlap_warning": false
}
```

No `PATCH`/`DELETE` route exists for budgets in this chunk — list and create only.

### `POST /organisation/branch-role-assignments`

- Requires bearer auth and owner role; accepts `Idempotency-Key`.
- Assigns a member's branch-scoped role (`branch_manager` or `approver`) to a specific branch —
  this endpoint adds branch scope on top of an existing role, it does not itself change what role
  the member holds.
- Request fields: required `membership_id`, required `branch_id`.
- Returns `201` with the created `BranchRoleAssignment`.
- Returns `403` when the caller's role is not owner.
- Returns `404` when the referenced membership or branch is not in the caller's workspace.
- Returns `409` when this member is already assigned to this branch.
- Returns `422` with `details.reason = "branch_scopable_role_required"` when `membership_id` does
  not currently hold `branch_manager` or `approver` — the caller must change the member's role
  first; the two are always two separate, sequential API calls (a role change must succeed before
  an assignment referencing that role can be created), never a single combined operation.

### `DELETE /organisation/branch-role-assignments/{assignment_id}`

- Requires bearer auth and owner role.
- Removing the last assignment for a member returns them to unscoped (tenant-wide) visibility,
  per research.md R1 — there is no separate "unassign" state, only the presence or absence of
  assignment rows.
- Returns `204` on success.
- Returns `403` when the caller's role is not owner.
- Returns `404` when the assignment is not in the caller's workspace.

---

## Delivered Requests and Approvals API (chunk R2.1, `008-requests-approvals`)

Purchase request creation, threshold-based approval routing with delegation and owner fallback,
an informational budget check, an approval queue, and a full audit-log entry on every request
lifecycle event. Requests carry R2.0's branch-scoped visibility: an owner sees every request; a
branch-scoped member sees only their assigned branch(es); the requester always sees their own
request; a same-tenant, different-branch reference resolves `404`, never `403`. A request's
estimated value is the sum of its lines' unit estimates, each drawn from the product's own price
history — recomputed live while `draft`, frozen on submit; a line whose product has no known
price contributes zero and sets `has_incomplete_estimate`. All money is `{amount, currency}`
with decimal-string amounts; every threshold rule and budget carries an explicit currency and is
compared only against a same-currency request total. Full contract:
`specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml`.

### `POST /requests`

- Requires bearer auth; accepts `Idempotency-Key`. Creates the request in `draft`.
- Request fields: required `branch_id`, optional `cost_centre_id`, required `required_by_date`,
  required `lines` (at least one; each `workspace_product_id`, `quantity` decimal string,
  optional `note`).
- Returns `201` with the `PurchaseRequest` — `lines[]` with a live `estimated_unit_price`
  (nullable `Money`) each, `estimated_total` (nullable `Money`, null when lines span more than
  one currency), `has_incomplete_estimate`, `status: "draft"`.
- Returns `422` when `lines` is empty or a field fails validation.

Request:
```json
{
  "branch_id": "00000000-0000-4000-8000-000000000010",
  "cost_centre_id": "00000000-0000-4000-8000-000000000020",
  "required_by_date": "2026-10-01",
  "lines": [
    { "workspace_product_id": "00000000-0000-4000-8000-000000000030", "quantity": "10.000000", "note": "Q4 restock" }
  ]
}
```

### `GET /requests`

- Requires bearer auth. Branch-scoped visibility as above.
- Query parameters: optional `status`, optional `branch_id`, optional `cursor`, optional `limit`
  capped at 100 and defaulting to 50.
- Returns `200` with `items` of `PurchaseRequest` and nullable `next_cursor`.

### `GET /requests/{request_id}`

- Requires bearer auth. Returns `200` with the `PurchaseRequest`, including `approval_step`
  (once submitted) and `budget_status` (when an applicable budget exists — see below).
- Returns `404` when the request is outside the caller's workspace or branch-scoped visibility.

### `PATCH /requests/{request_id}`

- Requires bearer auth; the caller must be the requester.
- Request fields: all optional — `branch_id`, `cost_centre_id`, `required_by_date`, `lines`
  (if given, at least one). Replacing `lines` re-runs live estimation.
- Returns `200` with the updated `PurchaseRequest`.
- Returns `403` (`not_requester`) when the caller did not create the request.
- Returns `409` (`not_draft`) once the request has left `draft` — no edits after submission
  (FR-004).

### `POST /requests/{request_id}/submit`

- Requires bearer auth (the requester); accepts `Idempotency-Key`.
- Freezes every line estimate (`estimated_at` stamped, never updated again), moves the request
  `draft -> submitted`, and creates the single `approval_step` via `resolve_approver()`:
  most-specific threshold rule wins (branch-scoped beats tenant-wide, then narrowest range),
  an active delegation over the resolved approver redirects to the delegate, and the owner is
  the fallback when nothing resolves. `requests.approval_step_escalated` is audited when the
  source is `owner_fallback`.
- Returns `200` with the `PurchaseRequest` (`status: "submitted"`, `approval_step` populated).
- Returns `409` (`not_draft`) if the request is not in `draft`.
- Returns `422` (`no_lines`) if the request has no lines (FR-003).

### `POST /requests/{request_id}/withdraw`

- Requires bearer auth (the requester).
- Moves `submitted -> withdrawn` and stamps `withdrawn_at`.
- Returns `200` with the `PurchaseRequest`.
- Returns `409` (`already_decided_or_withdrawn`) if the request is not `submitted`.

### `GET /approvals/pending`

- Requires bearer auth. Lists requests awaiting the caller's decision — the assigned approver
  sees their own pending steps; an owner sees every pending step (FR-007 standing override).
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50.
- Returns `200` with `items` of `PurchaseRequest`, each embedding the full decision context
  (requester, branch, cost centre, lines, required-by date, `approval_step`, and `budget_status`
  when applicable) so the approver never has to navigate elsewhere (FR-005). A decided request
  no longer appears here.

### `POST /requests/{request_id}/approve` · `POST /requests/{request_id}/reject`

- Requires bearer auth. The caller must be the step's `assigned_membership_id` or an owner
  (FR-007).
- Request fields: optional `comment`.
- Records a human decision — sets `status`, `decided_by_membership_id`, and `decided_at`
  together on the step (FR-006, enforced by the `approval_step` check constraint), and audits
  `requests.approval_step_approved` / `requests.approval_step_rejected` recording that human
  decision unchanged. The request row itself moves to **`ordered`** on approval (not `approved` —
  as of chunk R2.3, `010-mobile-approvals-receipt`, there is no separate "place the order" human
  action this release, so the same decision that approves a request is also what marks it
  ordered) or to `rejected` on rejection. The request row is updated before the step so a
  concurrent withdrawal cannot strand a decided step on a non-submitted request.
- Returns `200` with the `PurchaseRequest`.
- Returns `403` (`not_assigned_approver`) when the caller is neither the assignee nor an owner.
- Returns `409` (`not_submitted` or `no_pending_approval`) when the request has already left
  `submitted` or the step is no longer pending.

Request:
```json
{ "comment": "Approved — within the branch quarterly budget" }
```

### `GET /approvals/threshold-rules`

- Requires bearer auth; readable by any member (routing configuration is not a per-branch
  secret, research.md R1).
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50.
- Returns `200` with `items` of `ThresholdRule` and nullable `next_cursor`.

### `POST /approvals/threshold-rules`

- Requires bearer auth and owner role; accepts `Idempotency-Key`.
- Request fields: optional `branch_id` (null = tenant-wide default), required decimal-string
  `min_amount`, optional decimal-string `max_amount` (null = top tier), required `currency`,
  required `approver_membership_id`.
- Returns `201` with the created `ThresholdRule`.
- Returns `403` when the caller is not an owner.
- Returns `422` when validation fails (including the `max_amount > min_amount` constraint).

### `PATCH /approvals/threshold-rules/{rule_id}` · `DELETE /approvals/threshold-rules/{rule_id}`

- Requires bearer auth and owner role.
- `PATCH` fields: all optional — `branch_id`, `min_amount`, `max_amount`, `currency`,
  `approver_membership_id`. Returns `200` with the updated `ThresholdRule`.
- `DELETE` returns `204`.
- Both return `403` when the caller is not an owner and `404` when the rule is not in the
  caller's tenant.

### `GET /approvals/delegations`

- Requires bearer auth.
- Query parameter: optional `membership_id` to filter to one delegator.
- Returns `200` with `items` of `ApprovalDelegation`.

### `POST /approvals/delegations`

- Requires bearer auth; accepts `Idempotency-Key`. The caller may create a delegation for
  themselves; an owner may create one for anyone.
- Request fields: optional `delegator_membership_id` (defaults to the caller), required
  `delegate_membership_id`, required `starts_on`, required `ends_on`.
- Returns `201` with the created `ApprovalDelegation`.
- Returns `403` (`not_delegator_or_owner`) when a non-owner names someone else as delegator.
- Returns `422` when `delegator == delegate` or `ends_on < starts_on`.

### `DELETE /approvals/delegations/{delegation_id}`

- Requires bearer auth; the delegator or an owner.
- Returns `204` on success, `403` (`not_delegator_or_owner`) otherwise, `404` when the
  delegation is not in the caller's tenant.

### Budget status (`budget_status` on `PurchaseRequest`)

- Computed, not stored: `compute_budget_status()` resolves the single most applicable R2.0
  budget for the request's scope — cost centre beats branch beats organisation, and within a
  tier the tightest period wins (shortest period, then latest start) — then compares the
  request's estimated total against that budget's remaining amount for its own period window.
- Present only when an applicable same-currency budget exists (FR-012); otherwise the field is
  omitted entirely rather than shown as a misleading zero.
- Shape: `{ "remaining_amount": { "amount": "...", "currency": "..." }, "exceeds": true }`. It
  is informational only — an `exceeds: true` request still submits and can still be approved
  (FR-011); nothing about the budget blocks a decision.

---

## Delivered Mobile MVP API (chunk R2.2, `009-mobile-app-mvp`)

Device push-token registration and a fast, unlinked low-stock signal, both consumed by the
Flutter mobile app. `low_stock_report` reuses `purchase_request`'s own branch-scoped visibility
shape (see the R2.1 section above): an owner sees everything; a member always sees a report they
raised themselves regardless of branch scope; a branch-scoped member sees only their own
branch's reports; a same-tenant, different-branch reference resolves `404`, never `403`. Full
contract: `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`.

### `POST /devices`

- Requires bearer auth; accepts (but does not need) `Idempotency-Key` — the operation is already
  a plain upsert on `(tenant_id, member_id, push_token)`, so a replayed registration is naturally
  idempotent regardless of the header.
- Request fields: required `platform` (`ios` \| `android`), required `push_token`.
- Returns `200` with the `DeviceRegistration` (`id`, `member_id`, `platform`, `push_token`,
  `last_seen_at`).

Request:
```json
{ "platform": "android", "push_token": "fcm-token-abc123" }
```

### `DELETE /devices/{device_id}`

- Requires bearer auth; a member may only delete their own device registration
  (`device_registration_own_rows_only` is RESTRICTIVE for every operation, not just `SELECT` —
  there is no owner-delete-any-member's-device path).
- Called on sign-out, not on a passive timer — this is what makes sign-out stop push delivery to
  that device immediately rather than waiting on `last_seen_at` staleness.
- Returns `204` on success.

### `POST /low-stock-reports`

- Requires bearer auth; accepts and **enforces** `Idempotency-Key` — a real, database-level
  guarantee (`insert ... on conflict (tenant_id, idempotency_key) do nothing returning *`,
  falling back to a plain read on a zero-row insert), not merely an accepted-but-ignored header.
  A client retry after a dropped response returns the original report, `200` instead of `201`,
  and creates no second row.
- Request fields: required `branch_id`, required `workspace_product_id`, optional
  `count_remaining` (unsigned decimal string).
- Returns `201` (or `200` on an idempotent replay) with the `LowStockReport`.
- Insert-only (FR-006) — there is no `PATCH`/`DELETE` surface for a low-stock report this
  release.

Request:
```json
{
  "branch_id": "00000000-0000-4000-8000-000000000010",
  "workspace_product_id": "00000000-0000-4000-8000-000000000030",
  "count_remaining": "2.000000"
}
```

### `GET /low-stock-reports`

- Requires bearer auth. Branch-scoped visibility as above.
- Query parameters: optional `branch_id`, optional `workspace_product_id`, optional `cursor`,
  optional `limit` capped at 100 and defaulting to 50.
- Returns `200` with `items` of `LowStockReport` and nullable `next_cursor`.

### Durable push notifications on decision (no dedicated endpoint)

- Not a client-facing surface — `push_notification` has no `authenticated` grant at all and no
  router of its own. Documented here because it is the direct behavioural consequence of
  `POST /requests/{request_id}/approve` and `POST /requests/{request_id}/reject` (R2.1 section
  above): each decision writes a `push_notification` row **in the same transaction** as the
  decision itself, then enqueues a send job. A decision's own HTTP response is unaffected by
  whether that job ever actually sends — there is no real FCM/APNs provider configured in this
  codebase, so a real device registration's send attempt is an honest, deliberate stub that
  currently always reports failure rather than a fabricated success (FR-008 is still satisfied:
  zero registrations correctly reports `sent`, since there was nothing to attempt).

**Note on `Idempotency-Key` enforcement across this API**: as of this chunk, real
database-level enforcement exists for `POST /requests`; `POST /requests/{request_id}/submit`
is documented above as accepting the header but does not yet enforce it server-side (a client
retrying a submit whose response was lost gets `409 not_draft`, not the original success — the
mobile offline-queue client handles this narrow case itself by treating that specific conflict as
success once the request has actually moved past `draft`, rather than looping forever); and
`POST /low-stock-reports` enforces it per the endpoint above. Do not assume every endpoint that
accepts the header actually enforces it — check the specific endpoint's own section.

---

## Delivered Mobile Approvals and Delivery Receipt API (chunk R2.3, `010-mobile-approvals-receipt`)

Delivery confirmation and delivery-quality reporting, extending `PurchaseRequest`'s own lifecycle
rather than the pre-existing, unrelated `PurchaseRecord` entity (research.md R1). The approval
decision endpoints themselves (`POST /requests/{request_id}/approve` · `/reject`, R2.1 section
above) are reused completely unchanged by the mobile client — this chunk adds no new decision
surface, only what happens after a decision (research.md R2). Full contract:
`specs/010-mobile-approvals-receipt/contracts/mobile-approvals-receipt.openapi.yaml`.

### `POST /requests/{request_id}/confirm-delivery`

- Requires bearer auth. The caller must be the request's own requester or hold branch-scoped
  write access for the request's branch (the same authorization shape `low_stock_report` already
  uses for its own requester-initiated action) — an owner or an unscoped member always qualifies.
- Requires the request's `status` to be `ordered`.
- Request fields: required `lines`, an array of `{purchase_request_line_id, quantity_received}`
  (decimal string, `>= 0`) — at least one line required.
- Records each line's `quantity_received`, derives `has_delivery_discrepancy` (`true` if any
  line's received quantity was short of ordered — over-delivery is not a discrepancy this
  release), stamps `delivered_at`/`delivery_confirmed_by_membership_id`, moves the request to
  `delivered`, and audits `requests.delivery_confirmed`.
- Returns `200` with the `PurchaseRequest` (now including `delivered_at`,
  `delivery_confirmed_by_membership_id`, `has_delivery_discrepancy`, and each line's
  `quantity_received`).
- Returns `403` when the caller is neither the requester nor authorized for the branch.
- Returns `409` (`not_ordered`) when the request is not currently `ordered`.

Request:
```json
{
  "lines": [
    { "purchase_request_line_id": "00000000-0000-4000-8000-000000000040", "quantity_received": "3.000000" }
  ]
}
```

### `POST /requests/{request_id}/quality-issues` · `GET /requests/{request_id}/quality-issues`

- Requires bearer auth. Visibility/write access follows the parent request's own scoped-
  visibility policy — no separate branch-authorization check on top of it (unlike
  `confirm-delivery` above), since reporting a quality issue does not mutate the request itself.
- `POST` requires the request's `status` to be `delivered`. Request fields: required
  non-empty `description`. Photos are attached afterward via the endpoint below, not in this call
  — FR-007 requires a report with zero photos to succeed.
- `POST` returns `201` with the created `QualityIssue` (`photos: []`); audits
  `requests.quality_issue_reported`.
- `POST` returns `409` (`not_delivered`) when the request is not currently `delivered`.
- `GET` returns `200` with `items` of `QualityIssue`, each embedding its own `photos` (each with a
  freshly-generated signed `url`, never a raw storage path).

Request:
```json
{ "description": "Outer carton crushed, two bottles broken on arrival" }
```

### `POST /quality-issues/{issue_id}/photos`

- Requires bearer auth. `multipart/form-data` with a single `file` field — the server receives
  the bytes directly (a simpler, single-request shape than `POST /documents/presign`'s two-step
  presigned-upload dance elsewhere in this API, appropriate for a small single photo capped at
  10MB by the `quality-issue-photos` bucket's own `file_size_limit`).
- Allocates the Storage path server-side under
  `tenants/{tenant_id}/quality-issues/{issue_id}/{filename}` (the client never supplies a path;
  the filename itself is sanitized against path traversal) and uploads via the tenant-scoped
  client — `quality-issue-photos`' own RLS already permits this, no service-role bypass needed.
  Multiple calls attach multiple photos (`delivery_quality_issue_photo` is a one-to-many child,
  not a single column).
- Returns `201` with the `QualityIssuePhoto` (`id`, `delivery_quality_issue_id`, a signed
  time-limited `url`, `created_at`) — audits `requests.quality_issue_photo_attached`.
- Returns `404` when the referenced quality issue is not in the caller's tenant.

---

## Delivered Optimisation and Supplier IQ API (chunk R2.4, `011-optimisation-supplier-iq`)

The following endpoints deliver advanced multi-supplier basket optimisation with hard commercial
constraints, deterministic supplier risk scorecards, and live anomaly alert detection.
Contract: `specs/011-optimisation-supplier-iq/contracts/optimisation-supplier-iq.openapi.yaml`.

### `POST /baskets/optimise`

- Requires bearer auth (owner or buyer role; viewer/branch_manager return `403`).
- Accepts `Idempotency-Key`.
- Submits an advisory multi-supplier basket optimisation job across 2 to 10 suppliers.
- Request fields:
  - `supplier_ids`: array of 2 to 10 supplier UUIDs.
  - `items`: array of 1 to 50 basket items (`{workspace_product_id, quantity}`).
  - `hard_constraints`: optional `{supplier_minimum_order_values, supplier_free_delivery_thresholds, supplier_delivery_fees, quantity_tiers, supplier_exclusions, urgency}`.
  - `soft_weights`: optional `{price, preferred_supplier, risk, lead_time, quality}`.
- Returns `202` with a `BasketSplitJob` resource (`queued` status).
- Returns `422` when fewer than 2 or more than 10 suppliers are provided, items exceed 50, or mixed currencies cannot be reconciled.
- Advisory only: strictly creates no purchase orders, payments, or supplier communications.

### `GET /baskets/{id}`

- Requires bearer auth.
- Polls the status and result of a basket optimisation job.
- Returns `200` with `BasketSplitJob`. When `completed`, includes `result`:
  - `allocation`: product lines mapped to assigned supplier.
  - `total_landed_cost`: minimum landed cost total amount and currency.
  - `single_supplier_baselines`: cost comparisons versus allocating entirely to one supplier.
  - `applied_constraints` and `violated_constraints`: evaluation of hard commercial rules.
  - `confidence`: calibrated solver confidence (`high`, `medium`, `low`).
  - `risk_notes`: advisory risk notices.
- Returns `404` when the job does not exist in the caller's tenant.

### `GET /suppliers/{supplier_id}/commercial-terms`

- Requires bearer auth (all active tenant members).
- Returns `200` with `items` of `SupplierCommercialTerm` ordered by `effective_from desc`.
- Returns `404` if the supplier does not exist in the caller's tenant.

### `POST /suppliers/{supplier_id}/commercial-terms`

- Requires bearer auth (owner or buyer role; other roles return `403`).
- Accepts `Idempotency-Key`.
- Creates a new versioned commercial term for a supplier.
- Request fields:
  - `effective_from`: RFC 3339 timestamp.
  - `effective_to`: optional RFC 3339 timestamp.
  - `minimum_order_value`: optional `{amount, currency}`.
  - `delivery_fee`: optional `{amount, currency}`.
  - `free_delivery_threshold`: optional `{amount, currency}`.
  - `quantity_tiers`: optional array of `{workspace_product_id, min_quantity, unit_price: {amount, currency}}`.
- Returns `201` with created `SupplierCommercialTerm`.
- Returns `422` on invalid money pairings or invalid date bounds.

### `GET /suppliers/{supplier_id}/scorecard`

- Requires bearer auth (all active tenant members).
- Query parameter: optional `window_months` (integer, 1-24, default 6).
- Returns `200` with `SupplierScorecard`:
  - `supplier`: supplier summary.
  - `window_start` & `window_end`: date range evaluated.
  - `metrics`: performance metrics (`fulfilment_rate`, `on_time_delivery`, `quality_score`, `price_competitiveness`, `spend_exposure`, `dispute_rate`).
  - `risk_score`: deterministic risk evaluation (`total`, `rule_version`, sub-score breakdown).
  - `source_counts`: counts of quotations, deliveries, and quality issues analysed.
  - `confidence`: confidence rating (`high`, `medium`, `low`).
  - `insufficient_evidence`: boolean flag indicating whether transaction history was sparse.
- Audits `supplier_iq.scorecard.viewed`.
- Returns `404` if supplier is not found in caller's tenant.

### `GET /alerts` (Extended with Anomaly v1)

- Requires bearer auth.
- Query parameter: optional `kind` filter.
- Returns `200` with live-computed commercial signals and anomalies:
  - Extended anomaly kinds: `price_spike`, `likely_duplicate_quotation_line`, `decimal_or_quantity_anomaly`, `delivery_cost_anomaly`, and `supplier_quality_trend_change`.
  - Additional fields: `confidence` (`high`, `medium`, `low`), `valid_until`, `evidence`, and action routing (`inspect_scorecard`, `review_quotation`, `view_delivery_issues`).
- Dismissal persists via deterministic fingerprints without storing ephemeral alert condition rows.

---

## Delivered Reporting and Hardening API (chunk R2.5, `012-reporting-hardening`)

Contract: `specs/012-reporting-hardening/contracts/reporting-hardening.openapi.yaml`. Adds
scheduled reports, the Reports center artifact list, per-member weekly digest subscriptions, and
extends `POST /exports`/`GET /exports/{id}`/`GET /exports/{id}/download` (documented above) and
`PATCH /tenant` (reporting timezone). Every mutation endpoint in this section is rate-limited
(429, `rate_limit.exceeded`, keyed by tenant + membership claims — FR-020); schedule and digest
mutation endpoints additionally enforce an independent per-member cap on *active* rows
(422, `report_schedule_cap_exceeded` / `digest_subscription_cap_exceeded`, `details: {cap,
actual}`) so the count of standing recurring jobs cannot grow unbounded regardless of creation
rate. Cross-tenant and unauthorised-branch references resolve `404`, never `403` (FR-019).

### `GET /reports/schedules` · `POST /reports/schedules`

- Requires bearer auth. List: any tenant member (team visibility by design — see
  `docs/quality/r2.5-security-review-record.md` §1); cursor-paginated, newest first.
- Create: owner or buyer role; accepts `Idempotency-Key`. One schedule per member per
  kind/format/filters combination — a duplicate create is refused `409` with the filters digest
  named in the response, not silently accepted as a second schedule. A named `branch_id` the
  caller cannot see resolves `404`.
- Request fields: `kind`, `format`, `filters` (`{supplier_id?, branch_id?}` — the period is
  **not** stored; scheduled windows derive at run time from `weekday` and the workspace's
  `reporting_timezone`), `weekday` (0 = Monday), optional `locale` (defaults to the requester's
  preferred locale, then the workspace default).
- Returns `201` with a `ReportSchedule`; `next_run_at` is derivable immediately from `weekday`.

Request:

```json
{
  "kind": "savings_ledger",
  "format": "xlsx",
  "filters": { "branch_id": null, "supplier_id": null },
  "weekday": 0,
  "locale": "en"
}
```

Response (`ReportSchedule`):

```json
{
  "id": "00000000-0000-4000-8000-000000000200",
  "kind": "savings_ledger",
  "format": "xlsx",
  "filters": { "supplier_id": null, "branch_id": null },
  "weekday": 0,
  "status": "active",
  "next_run_at": "2026-08-24T00:00:00Z",
  "last_run_at": null,
  "rule_version": "",
  "locale": "en",
  "created_at": "2026-08-21T09:00:00Z",
  "updated_at": "2026-08-21T09:00:00Z"
}
```

### `PATCH /reports/schedules/{schedule_id}` · `DELETE /reports/schedules/{schedule_id}`

- Owner or buyer role — any owner/buyer in the tenant, not only the schedule's own creator (team
  visibility/control by design). Accepts `Idempotency-Key`.
- `PATCH`: `format`, `filters`, `weekday`, `locale`, and `status` (`active`/`paused`) are
  editable. Pausing keeps the schedule's position but the scheduler skips it; resuming
  recomputes `next_run_at` from `weekday`. The schedule survives its creator's own deactivation —
  deactivating a member never deletes or pauses their schedules.
- `DELETE`: hard delete of the configuration only. Generated artifacts survive via their
  immutable `schedule_snapshot` on `export_job` — deleting a schedule never deletes its history.
- Returns `200` (`PATCH`, `ReportSchedule`) or `204` (`DELETE`); `404` for a cross-tenant or
  nonexistent id.

### `GET /reports/artifacts`

- Requires bearer auth. Cursor list over `export_job` rows for the workspace, newest first —
  this is the Reports center's single "Artifacts" surface, covering both on-demand exports and
  scheduled runs in one feed. Optional `kind` and `status` (`queued`/`running`/`completed`/
  `failed`/`expired`) query filters narrow the list.
- Each item carries the immutable filters snapshot, period, locale, status, row count, rule
  version, source `schedule_id` where applicable, timestamps, `expires_at`, and `download_url`
  while the artifact is still downloadable (null once purged).
- Branch-scoped roles see only artifacts whose branch filter includes a branch they can see;
  artifacts with no branch filter are visible to every member.

### `GET /digests/subscriptions` · `POST /digests/subscriptions`

- Requires bearer auth. List: per-member — a non-owner sees only their own subscriptions; owners
  additionally see every subscription in the tenant for visibility only, never to modify them
  (matches the RLS shape in `docs/quality/r2.5-security-review-record.md` §1).
- Create: the caller always subscribes themselves — there is no "create on behalf of another
  member" path. One active weekly digest per filters combination (duplicate create refused
  `409`). New memberships are auto-provisioned with one active in-app subscription
  (`digests.subscription_provisioned`) on accept; this endpoint exists for re-subscribing after
  deletion or for an additional branch-filtered subscription.
- Request fields: `filters` (`{branch_id?}`), `locale`, `channel` (`in_app` or `email`).
- Returns `201` with a `DigestSubscription`.

Response (`DigestSubscription`):

```json
{
  "id": "00000000-0000-4000-8000-000000000300",
  "kind": "weekly_digest",
  "filters": { "branch_id": null },
  "channel": "in_app",
  "status": "active",
  "locale": "en",
  "next_run_at": "2026-08-24T00:00:00Z",
  "last_delivery_at": null,
  "last_delivery_status": null,
  "email_configured": false,
  "created_at": "2026-08-21T09:00:00Z",
  "updated_at": "2026-08-21T09:00:00Z"
}
```

`email_configured` is workspace-level (from `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` settings),
not per-subscription — it explains why a `channel: email` subscription's delivery status may read
`email_unconfigured` rather than `succeeded`/`failed`.

### `PATCH /digests/subscriptions/{subscription_id}` · `DELETE /digests/subscriptions/{subscription_id}`

- The owning member only — unlike schedules, an owner cannot modify another member's digest
  subscription (visibility is shared; control is not). `403` for any other member, including
  owners, attempting to mutate someone else's subscription.
- `PATCH` fields: `filters`, `locale`, `channel`, `status`. Returns `200` with the updated
  `DigestSubscription`.
- `DELETE` returns `204`.

### `GET /digests/latest`

- Requires bearer auth. The caller's latest in-app weekly digest, rendered from their active
  subscription (or the workspace default when none exists) for the last complete week in the
  workspace's reporting timezone.
- Sections are in a fixed order (FR-009) with verified savings first (hero position):
  `verified_savings`, `pending_verifications`, `pending_approvals`, `anomalies`,
  `expiring_validity`. Every item carries a `deep_link` into the acting surface, and a `money`
  object (amount + explicit currency, never a bare number) where a monetary value applies.
- Advisory only (FR-017) — nothing returned here can act on a purchase, approval, order, payment,
  or supplier message; every action still requires the human to follow the deep link and act
  through the real surface.

### `PATCH /tenant` — `reporting_timezone` extension

- Owner only (existing `PATCH /tenant` surface from the foundation contract; region, currency,
  and tax model remain immutable). New field: `reporting_timezone`, an IANA timezone name
  (default `UTC`) — every scheduled-report window, digest window, and next-run computation for
  the workspace derives from it. The change takes effect for future scheduled runs; windows
  already derived are not recomputed retroactively.

---

## Delivered Automated Ingestion API (chunk R3.0, `013-automated-ingestion`)

Contract: `specs/013-automated-ingestion/contracts/automated-ingestion.openapi.yaml`. Delivers automated
quotation ingestion via inbound email forwarding, external mail delivery webhook, mobile and desktop
document capture, and supplier catalogue spreadsheet imports. Mutation endpoints enforce dedicated
rate limits (`rate_limit_ingestion_config_mutation`, `rate_limit_capture_upload`,
`rate_limit_catalogue_import`, and `rate_limit_inbound_email_webhook`).

Role-based access control is evaluated individually per endpoint:
- Tenant email configuration mutations (`PUT /tenants/email-config`, `POST /tenants/email-config/enable`,
  `POST /tenants/email-config/disable`): strictly **owner-only** (`require_role(owner)`).
- Document capture (`POST /capture`) and catalogue import (`POST /suppliers/{supplier_id}/catalogue-import`):
  **owner or buyer** (`require_role(owner, buyer)`).
- Email log inspection (`GET /ingestion/emails`), catalogue import history (`GET /suppliers/{supplier_id}/catalogue-imports`),
  tenant email configuration retrieval (`GET /tenants/email-config`), and dashboard statistics
  (`GET /ingestion/stats`): accessible to **any authenticated tenant member**.
- Inbound email webhook (`POST /webhooks/inbound-email`): public, **no Bearer auth**; authenticated
  exclusively via cryptographic provider signature verification.

### `GET /tenants/email-config` · `PUT /tenants/email-config`

- `GET`: requires bearer auth; accessible to any authenticated member in the tenant. Returns the
  workspace's inbound email forwarding configuration. The configuration is upserted on first write;
  before any write occurs, `GET` returns `404` (`{"resource": "tenant_email_config"}`).
- `PUT`: owner only (`403` for non-owners); rate limited (`rate_limit_ingestion_config_mutation`,
  default 30/minute). Upserts the tenant configuration on first call or updates existing settings.
- Request fields (`TenantEmailConfigUpdate`):
  - `enabled` (optional boolean): toggles inbound email ingestion for the workspace.
  - `domain_allowlist` (optional list of string domain names, e.g. `["supplier.com"]`): restrict
    inbound email processing to messages originating from explicitly approved sender domains.
    Inbound messages from unlisted domains are accepted at the webhook and discarded without queuing
    an ingestion job.
  - `daily_limit` (optional integer between 1 and 10,000, default 100): maximum count of inbound
    emails processed per calendar day to protect against runaway volume or abuse.
  - `spf_dkim_required` (optional boolean, default false): enforce SPF/DKIM verification checks.
- Server-derived forwarding address: `forwarding_address` is **never client-supplied**; it is
  deterministically derived server-side from `{tenant.slug}@{INGESTION_EMAIL_DOMAIN}` (e.g.
  `acme-catering@ingest.procurepilot.local`) and is immutable.
- `PUT` records an audit event (`ingestion.email_config_updated`).
- Returns `200` with `TenantEmailConfig`:

```json
{
  "id": "00000000-0000-4000-8000-000000000101",
  "forwarding_address": "acme-catering@ingest.procurepilot.local",
  "enabled": true,
  "domain_allowlist": ["acmefood.com", "beverageco.net"],
  "daily_limit": 100,
  "daily_count": 12,
  "daily_count_date": "2026-09-17",
  "spf_dkim_required": false,
  "created_at": "2026-09-17T08:00:00Z",
  "updated_at": "2026-09-17T09:30:00Z"
}
```

### `POST /tenants/email-config/enable` · `POST /tenants/email-config/disable`

- Owner only (`403` for non-owners); rate limited (`rate_limit_ingestion_config_mutation`, default 30/minute).
- Quick state mutation endpoints that toggle the `enabled` boolean flag without supplying a full body payload.
  If no configuration row exists yet, one is created with default settings.
- Auditing: records `ingestion.email_config_enabled` or `ingestion.email_config_disabled`.
- Returns `200` with the updated `TenantEmailConfig`.

### `POST /webhooks/inbound-email`

- Public endpoint called by external email delivery services (Mailgun, SES, or local stub); **no Bearer auth**.
- Rate limited via provider limiter (`rate_limit_inbound_email_webhook`, default 60/minute).
- Authentication via cryptographic signature verification:
  - Mailgun mode (`INGESTION_EMAIL_PROVIDER="mailgun"`): multipart form submission containing `timestamp`,
    `token`, and `signature` verified using HMAC-SHA256 against `MAILGUN_SIGNING_KEY`. Raw email bytes are
    read from `body-mime`, recipient address from `recipient`.
  - Stub and SES modes (`INGESTION_EMAIL_PROVIDER="stub"` or `"ses"`): constant-time verification of the
    `X-Ingestion-Webhook-Secret` request header against `INGESTION_WEBHOOK_SHARED_SECRET`. Expects a JSON
    payload containing `recipient` and `raw_email_base64`. (Note: SES mode uses interim shared-secret
    verification pending a dedicated AWS SNS certificate-chain validation spike).
  - Unauthenticated requests (invalid or missing signature/secret) return `401` (`AuthenticationError`).
  - Malformed payloads (missing recipient/body or invalid base64 encoding) return `422` (`UnprocessableEntityError`).
- Always returns `202 Accepted` for processed deliveries (R10 anti-enumeration guarantee):
  - In accordance with requirement R10, the webhook always returns `202` for **every** delivery outcome once
    signature verification passes, specifically including:
    - Unknown forwarding address (recipient address does not match any tenant).
    - Disabled tenant ingestion (`enabled: false`).
    - Sender domain not present in the tenant's `domain_allowlist`.
    - Tenant daily ingestion quota exceeded (`daily_count >= daily_limit`).
    - Raw email size exceeds maximum allowable payload (`INGESTION_MAX_EMAIL_BYTES`, default 50 MB).
    - Success (valid email accepted, raw email uploaded to Supabase `ingestion-raw` bucket, and pending
      `ingestion_jobs` row inserted with `job_type='email_ingest'`).
  - Rationale: External HTTP response codes must never leak whether a recipient email address exists on
    ProcurePilot or whether a tenant's email ingestion is currently enabled or disabled. Returning `404`,
    `403`, or `429` would allow external attackers to probe and enumerate valid workspace addresses. Furthermore,
    returning a 4xx error to an external mail provider would trigger repeated delivery retries for permanently
    refused messages; returning `202` acknowledges delivery termination from the provider's perspective while
    the system handles rejection internally.

### `POST /capture`

- Owner or buyer role (`require_role(owner, buyer)`). Rate limited (`rate_limit_capture_upload`, default 30/minute).
- Accepts `multipart/form-data`:
  - `file`: binary file (required, non-empty).
  - `supplier_id`: optional UUID string attributing the quotation to a known supplier.
  - `notes`: optional free-text string (e.g. buyer context or mobile photo notes).
- Server-side MIME type sniffing via `python-magic`: The server inspects file magic bytes directly rather than
  trusting the client's declared `Content-Type` header. Permitted MIME types are `application/pdf`,
  `image/jpeg`, `image/png`, and `image/heic`. Unsupported media types return `415` (`UnsupportedMediaTypeError`,
  `details: {detected_mime}`).
- Size limit: Maximum 10 MB (`CAPTURE_MAX_BYTES`, 10,485,760 bytes). Payloads exceeding this limit return `422`
  (`UnprocessableEntityError`, `reason: file_too_large`).
- Supplier validation: If `supplier_id` is supplied, validates that the supplier exists within the caller's tenant;
  returns `404` (`NotFoundError`) if nonexistent or cross-tenant.
- Synchronous upload pipeline: Unlike inbound email, capture uploads have file bytes immediately available. The
  service uploads the document to Supabase storage (`quotation-documents` bucket), creates a `document`
  (`source_channel: 'capture'`, `status: 'uploaded'`), creates a `quotation` (`source: 'capture'`, `status: 'pending'`),
  creates an `extraction_job` (`status: 'queued'`), and dispatches extraction synchronously within the request.
  Notes are recorded on the `capture_uploaded` audit event (since `quotation` has no dedicated free-text notes column).
- Returns `202 Accepted` (`status.HTTP_202_ACCEPTED`):

```json
{
  "quotation_id": "00000000-0000-4000-8000-000000000200",
  "status": "pending"
}
```

### `POST /suppliers/{supplier_id}/catalogue-import`

- Owner or buyer role (`require_role(owner, buyer)`), matching the `catalogue_imports_owner_buyer_insert` RLS policy.
- Path parameter: `supplier_id` (UUID). Validates supplier existence within caller's tenant; returns `404` (`NotFoundError`)
  for unknown or cross-tenant supplier IDs.
- Accepts `multipart/form-data`:
  - `file`: binary spreadsheet file (required). Only `.csv` and `.xlsx` file extensions are supported.
- Rate limited via mutation limiter (`rate_limit_catalogue_import`, default 10/minute).
- Validation and limits:
  - File size capped at 25 MB (`CATALOGUE_IMPORT_MAX_BYTES`, 26,214,400 bytes). Larger files return `422`
    (`UnprocessableEntityError`, `reason: file_too_large`).
  - Unsupported file extensions return `422` (`unsupported_file_format`).
  - Structural errors (unparseable file, missing required columns such as `product_name` or `unit_price_amount`)
    raise `422` (`UnprocessableEntityError`) and record a failed `catalogue_imports` entry.
- Synchronous execution (no async polling):
  - Catalogue import runs completely synchronously within the HTTP request. There is no async job ID to poll;
    the response body IS the completed import summary.
  - The service stores the spreadsheet in `quotation-documents` storage, synthesizes one `quotation` record with
    `status: 'reviewed'` and `source: 'catalogue_import'` (the importing buyer or owner acts as the human reviewer
    vouching for the bulk price list), inserts a `quotation_line` for every valid row, and immediately invokes the
    matching pipeline (`MatchingService.quotation_matches()`) using the caller's bearer credentials.
  - Persists an audit record to `catalogue_imports` with status `completed` (or `failed` if zero rows could be imported).
- Returns `201 Created` (`status.HTTP_201_CREATED`):

```json
{
  "id": "00000000-0000-4000-8000-000000000300",
  "supplier_id": "00000000-0000-4000-8000-000000000050",
  "status": "completed",
  "total_rows": 120,
  "imported_rows": 118,
  "skipped_rows": 0,
  "error_rows": 2,
  "error_details": [
    { "row": 42, "column": "currency", "error": "unsupported_currency" }
  ]
}
```

### `GET /ingestion/emails`

- Requires bearer auth. Accessible to any authenticated member of the tenant.
- Lists inbound email processing logs for the workspace, ordered newest first (`order by received_at desc, id desc`).
- Query parameters:
  - `cursor`: optional base64-encoded integer offset string.
  - `limit`: optional integer, capped at 100 and defaulting to 50.
  - `status`: optional filter by `IngestionEmailStatus` (`received`, `processing`, `completed`, `failed`, `duplicate`, `rejected`).
  - `from_domain`: optional string for exact matching against sender domain.
  - `date_from`: optional ISO 8601 datetime or `YYYY-MM-DD` date string (bare dates widened to `00:00:00` UTC).
  - `date_to`: optional ISO 8601 datetime or `YYYY-MM-DD` date string (bare dates widened to `23:59:59` UTC).
- Pagination: Follows the workspace cursor-pagination convention (`_encode_cursor`/`_decode_cursor` pattern,
  matching `digests` and `reports/schedules`).
- Returns `200` with `items` containing `IngestionEmailLog` resources and nullable `next_cursor`:

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000401",
      "message_id": "<202609170830.abc123@supplier.com>",
      "from_address": "orders@supplier.com",
      "from_domain": "supplier.com",
      "subject": "Quote #9872 - Fresh Produce",
      "received_at": "2026-09-17T08:30:00Z",
      "processed_at": "2026-09-17T08:30:05Z",
      "status": "completed",
      "error_message": null,
      "attachment_count": 1,
      "quotation_id": "00000000-0000-4000-8000-000000000201",
      "supplier_id": "00000000-0000-4000-8000-000000000050",
      "match_method": "domain",
      "created_at": "2026-09-17T08:30:00Z"
    }
  ],
  "next_cursor": null
}
```

### `GET /suppliers/{supplier_id}/catalogue-imports`

- Requires bearer auth. Accessible to any authenticated member of the tenant.
- Path parameter: `supplier_id` (UUID). Validates supplier existence within caller's tenant; returns `404`
  (`NotFoundError`) if supplier does not belong to the caller's tenant.
- Query parameters: optional `cursor`, optional `limit` capped at 100 and defaulting to 50.
- Ordering: Newest first (`order by created_at desc, id desc`).
- Pagination: Cursor-paginated; returns `200` with `items` containing `CatalogueImportSummary` resources and
  nullable `next_cursor`:

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000300",
      "supplier_id": "00000000-0000-4000-8000-000000000050",
      "file_name": "q3_price_list.xlsx",
      "file_path": "tenants/00000000-0000-4000-8000-000000000001/quotations/00000000-0000-4000-8000-000000000202/q3_price_list.xlsx",
      "file_size_bytes": 1048576,
      "file_format": "xlsx",
      "status": "completed",
      "total_rows": 120,
      "imported_rows": 118,
      "skipped_rows": 0,
      "error_rows": 2,
      "error_details": [
        { "row": 42, "column": "currency", "error": "unsupported_currency" }
      ],
      "column_mapping": {
        "product_name": "Item Description",
        "unit_price_amount": "Price",
        "unit_price_currency": "Curr"
      },
      "created_at": "2026-09-17T09:00:00Z",
      "completed_at": "2026-09-17T09:00:04Z",
      "created_by": "00000000-0000-4000-8000-000000000010"
    }
  ],
  "next_cursor": null
}
```

### `GET /ingestion/stats`

- Requires bearer auth. Accessible to any authenticated member of the tenant.
- Single aggregate metrics object; no pagination.
- Timezone semantics: Calendar windows for `emails_received_today`, `emails_received_week`, and `emails_received_month`
  are derived dynamically in the workspace's configured `reporting_timezone` (from `tenant.reporting_timezone`,
  defaulting to `UTC`; week window begins Monday 00:00).
- Calculated metrics:
  - `emails_received_today`: count of inbound email log rows received since local midnight today.
  - `emails_received_week`: count of inbound email log rows received since Monday 00:00 of the current week.
  - `emails_received_month`: count of inbound email log rows received since the 1st of the current month.
  - `capture_uploads_total`: all-time count of quotations created via mobile/desktop capture (`source = 'capture'`).
  - `catalogue_imports_total`: all-time count of catalogue imports recorded for the tenant.
  - `supplier_match_rate`: float ratio (0.0 to 1.0) of completed email logs with an attributed supplier (`supplier_id is not null`)
    over all completed email logs (`status = 'completed'`). Unprocessed, failed, or rejected emails are excluded from
    the denominator; returns 0.0 when no completed emails exist.
  - `extraction_success_rate`: float ratio (0.0 to 1.0) of succeeded extraction jobs (`status = 'succeeded'`) over all
    terminal extraction jobs (`status not in ('queued', 'running')`) strictly for automated-ingestion quotations
    (`source in ('email', 'capture')`). Excludes non-ingestion manual uploads and in-flight jobs; returns 0.0 when no
    terminal ingestion extraction jobs exist.
- Returns `200` with `IngestionStats`:

```json
{
  "emails_received_today": 12,
  "emails_received_week": 45,
  "emails_received_month": 180,
  "capture_uploads_total": 34,
  "catalogue_imports_total": 8,
  "supplier_match_rate": 0.88,
  "extraction_success_rate": 0.95
}
```

---

## Health

### `GET /health`

Response:
```json
{ "status": "ok" }
```
