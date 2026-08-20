# Phase 1 Data Model: Catalogue and Suppliers

**Feature**: 002-catalogue-suppliers | **Date**: 2026-08-20

Field names follow `docs/architecture/data-dictionary.md`. Where this chunk adds fields the
dictionary lacks, they are marked **[new]** and must be folded back when the feature lands — the
same discipline applied in chunk 4.1.

---

## Reference data

### `supported_base_unit`

| Field | Type | Notes |
|---|---|---|
| `code` | text PK | `litre`, `millilitre`, `kilogram`, `gram`, `each` |
| `label_en` / `label_ar` | text | Display names |
| `dimension` | text | `volume`, `mass`, `count` — only same-dimension units are comparable |
| `is_enabled` | boolean | Widen the set by flipping a flag, not by migrating |

Global, not tenant-scoped: readable by any authenticated user, writable by service role only.
A fixed set rather than free text, because normalising arbitrary unit names is not decidable and
every comparison downstream rests on this being right (research R3 of this chunk's spec assumptions).

---

## Shared spine

### `canonical_product` — **the one table with no `tenant_id`**

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `brand` | text | nullable |
| `name` | text | not null |
| `variant` | text | nullable |
| `gtin` | text | nullable, unique where present, shape-validated |
| `base_unit` | text | not null, FK → `supported_base_unit.code` |
| `created_at` | timestamptz | not null |

Deliberately shared, so the cross-tenant benchmarking asset the roadmap names in §10.1 remains
reachable without a later migration over every customer's catalogue. It holds **nothing that
identifies a workspace** — no naming preferences, no suppliers, no substitutes. Readable by any
authenticated user; not writable directly by them.

**This is the table to check first** if workspace data ever appears where it should not. See
research R5 and the plan's Complexity Tracking.

---

## Workspace-scoped tables

### `workspace_product`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK → `tenant.id` — RLS key |
| `canonical_product_id` | uuid | not null, FK → `canonical_product.id` |
| `tenant_name` **[new]** | text | not null — the name this workspace uses |
| `preferred_supplier_id` | uuid | nullable, FK → `supplier.id` |
| `status` **[new]** | enum | `active` \| `archived`, default `active` |
| `created_at` | timestamptz | not null |

- **unique** `(tenant_id, canonical_product_id)` — one workspace view per canonical product.
- Duplicate `tenant_name` within a workspace is **permitted with a warning**, not refused:
  businesses legitimately buy "gloves" in several specifications.

### `pack_definition`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null — RLS key, denormalised so the policy needs no join |
| `workspace_product_id` | uuid | not null, FK → `workspace_product.id` |
| `pack_count` | integer | not null, **check > 0** |
| `unit_size` | numeric(18,6) | not null, **check > 0** |
| `base_quantity` | numeric(18,6) | **GENERATED ALWAYS AS (pack_count * unit_size) STORED** |
| `created_at` | timestamptz | not null |

`base_quantity` is generated, not written. Nothing can set it independently, so it cannot drift from
its inputs, and recomputation is not a second code path that might one day disagree — which is what
Principle II asks for and SC-007 tests. `numeric`, never floating point: `3 × 0.33` must equal
`0.99` exactly, because every landed-cost comparison in chunk 4.4 is downstream of this number.

### `product_substitute`

| Field | Type | Constraints |
|---|---|---|
| `tenant_id` | uuid | not null — RLS key |
| `workspace_product_id` | uuid | not null, FK |
| `substitute_product_id` | uuid | not null, FK |

- PK `(tenant_id, workspace_product_id, substitute_product_id)`.
- **check** `workspace_product_id <> substitute_product_id` — a product is not its own substitute.
- Stored as a table rather than the dictionary's `uuid[]`, so the foreign keys are real and a
  referenced product cannot silently vanish from an array.

### `supplier`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null — RLS key |
| `name` | text | not null |
| `payment_terms` | text | nullable, e.g. `Net 30` |
| `lead_time_days` | integer | nullable, check >= 0 |
| `minimum_order_value_amount` **[new]** | numeric(18,4) | nullable |
| `minimum_order_value_currency` **[new]** | text | nullable, FK → `supported_currency.code` |
| `delivery_fee_amount` **[new]** | numeric(18,4) | nullable |
| `delivery_fee_currency` **[new]** | text | nullable, FK → `supported_currency.code` |
| `reliability_score` | numeric(4,3) | nullable, 0–1, computed in a later chunk |
| `status` | enum | `active` \| `preferred` \| `blocked` \| `archived` |
| `created_at` | timestamptz | not null |

**Two check constraints carry Principle VII**, one per monetary pair:

```sql
check ((minimum_order_value_amount is null) = (minimum_order_value_currency is null))
check ((delivery_fee_amount is null) = (delivery_fee_currency is null))
```

An amount without a currency is refused outright. Without this, the column eventually holds nulls
and something downstream infers a default — which is how a £500 minimum becomes a plausible, wrong
﷼500. No conversion is performed anywhere.

### `product_alias`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null — RLS key |
| `workspace_product_id` | uuid | not null, FK |
| `supplier_id` | uuid | nullable, FK — the supplier whose wording this is |
| `alias_text` | text | not null |
| `created_by` | uuid | FK → `membership.id` — a human confirmed this |
| `created_at` | timestamptz | not null |

- **unique** `(tenant_id, lower(alias_text))` — one meaning per wording per workspace.
- Private to the workspace that recorded it (FR-027). One business's vocabulary is not another's.

### `import_job`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null — RLS key |
| `kind` | enum | `products` \| `suppliers` |
| `filename` | text | not null |
| `status` | enum | `validating` \| `previewed` \| `committed` \| `refused` |
| `row_count` | integer | rows read |
| `error_report` | jsonb | `[{line, column, reason}]` — line numbers as they appear in the file |
| `created_by` | uuid | FK → `membership.id` |
| `created_at` | timestamptz | not null |

Retained after the fact so an import can be explained — which rows were refused and why. Principle I
applied to bulk data: a catalogue that changed for reasons nobody can reconstruct is not trustworthy.

---

## Row-level security

Every table above **except `canonical_product` and `supported_base_unit`** gets:

```sql
alter table <t> enable row level security;
alter table <t> force  row level security;
create policy tenant_isolation on <t>
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());
```

`USING` and `WITH CHECK` both, always — `USING` alone lets a member write a row carrying another
workspace's `tenant_id` which they then cannot see, a silent corruption path. `FORCE` because the
migration role owns these tables and would otherwise bypass every policy.

`canonical_product` and `supported_base_unit`: RLS enabled with a read policy for `authenticated`,
no write policy. Writes go through the application's insert path, which runs inside the same
transaction as the `workspace_product` it supports.

**Role gate (FR-032)**: RLS scopes *whose* data; the role gate decides *who may write*. Owner and
buyer may mutate; branch manager, approver and viewer read. Enforced by the existing
`require_role` dependency, exactly as research R9 of chunk 4.1 established — roles govern actions,
RLS governs tenancy, and keeping them separate means a role bug cannot become a tenancy bug.

---

## Validation rules traced to requirements

| Rule | Source |
|---|---|
| `pack_count > 0` and `unit_size > 0` | FR-003 |
| `base_quantity` generated, full precision retained | FR-002, FR-004, SC-007 |
| GTIN shape-validated when present | FR-008 |
| Archive rather than delete; referenced supplier cannot be deleted | FR-006, FR-014, R7 |
| Every monetary amount has a currency | FR-011, SC-006 |
| No currency conversion anywhere | FR-012 |
| Aliases unique per workspace, private to it | FR-026, FR-027 |
| Import is all-or-nothing | FR-017, SC-004 |
| Errors report file line numbers | FR-018, SC-003 |
| Every mutation writes an audit event | FR-030 |

---

## Notes for later chunks

- No prices here. Offers and per-supplier pricing arrive in chunk 4.4 and will reference
  `workspace_product` and `supplier`.
- `reliability_score` stays null until outcomes are recorded in chunk 4.6.
- `product_alias` is the seed of the matching engine in chunk 4.4; it starts hand-fed and becomes
  machine-fed once extraction exists.
- `pgvector` and `pg_trgm` are already enabled (migration 0001) and remain unused until 4.4.
