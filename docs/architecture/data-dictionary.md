# ProcurePilot — Data Dictionary

> Field-level definitions for the core domain entities.

---

## `Tenant`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | Business name |
| `slug` | text | Unique subdomain identifier |
| `region` | text | Launch region for data residency |
| `currency` | text | Primary currency code |
| `tax_model` | text | VAT/GST configuration |
| `created_at` | timestamptz | Audit field |

## `User` / `Membership`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `email` | text | Supabase Auth identity |
| `role` | enum | owner, buyer, branch_manager, approver, viewer |
| `mfa_enabled` | boolean | MFA status |
| `created_at` | timestamptz | Audit field |

## `Branch` / `CostCentre`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `name` | text | |
| `code` | text | Short code for requests |
| `parent_id` | uuid | Optional hierarchy |

## `CanonicalProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `brand` | text | Normalised brand name |
| `name` | text | Base product name |
| `variant` | text | Variant (e.g., unscented) |
| `gtin` | text | Global trade item number |
| `base_unit` | text | e.g. litre, kg, each |
| `created_at` | timestamptz | |

## `TenantProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `canonical_product_id` | uuid | FK → CanonicalProduct |
| `tenant_name` | text | Name used inside this tenant |
| `preferred_supplier_id` | uuid | FK → Supplier |
| `substitute_ids` | uuid[] | Approved substitutes |

## `Unit` / `PackDefinition`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_product_id` | uuid | FK |
| `pack_count` | integer | e.g. 6 |
| `unit_size` | decimal | e.g. 5.0 |
| `base_quantity` | decimal | `pack_count × unit_size` |

## `Supplier`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `name` | text | |
| `payment_terms` | text | e.g. Net 30 |
| `lead_time_days` | integer | |
| `minimum_order_value` | money | |
| `delivery_fee` | money | |
| `reliability_score` | decimal | 0–1, computed |
| `status` | enum | active, blocked, preferred |

## `Document`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `storage_uri` | text | Supabase Storage path |
| `mime_type` | text | |
| `hash` | text | SHA-256 for caching |
| `source_channel` | enum | upload, email, api |
| `created_at` | timestamptz | |

## `Quotation`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `document_id` | uuid | FK → Document |
| `supplier_id` | uuid | FK → Supplier |
| `currency` | text | |
| `issue_date` | date | |
| `expiry_date` | date | |
| `status` | enum | pending, extracted, reviewed, accepted |

## `QuotationLine`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `quotation_id` | uuid | FK → Quotation |
| `original_text` | text | Raw extracted description |
| `supplier_sku` | text | |
| `quantity` | decimal | |
| `unit_price` | money | |
| `vat_rate` | decimal | |
| `delivery_fee` | money | |
| `discount` | money | |
| `confidence` | decimal | 0–1 per field aggregate |

## `SupplierOffer`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `tenant_product_id` | uuid | FK → TenantProduct |
| `quotation_line_id` | uuid | FK → QuotationLine |
| `landed_cost` | money | Computed total |
| `valid_from` | timestamptz | |
| `valid_to` | timestamptz | |
| `recorded_at` | timestamptz | Bitemporal record time |

## `SavingRecord`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `tenant_product_id` | uuid | FK |
| `baseline_policy` | text | e.g. last_paid, rolling_avg |
| `baseline_value` | money | |
| `actual_value` | money | |
| `delta` | money | Verified saving |
| `verified_at` | timestamptz | Immutable after verify |

## `PurchaseRequest`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `branch_id` | uuid | FK → Branch |
| `cost_centre_id` | uuid | FK → CostCentre |
| `requested_by` | uuid | FK → User |
| `required_by_date` | date | |
| `status` | enum | draft, submitted, approved, rejected, ordered |

## `ApprovalStep`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `request_id` | uuid | FK → PurchaseRequest |
| `approver_id` | uuid | FK → User |
| `threshold_rule_id` | uuid | FK → PolicyRule |
| `status` | enum | pending, approved, rejected, escalated |
| `comment` | text | |
| `decided_at` | timestamptz | |

## `AuditEvent`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `actor_id` | uuid | FK → User |
| `action` | text | create, update, delete |
| `entity_type` | text | |
| `entity_id` | uuid | |
| `before` | jsonb | |
| `after` | jsonb | |
| `ip_address` | text | |
| `created_at` | timestamptz | |
