# Phase 1 Data Model: Matching and Normalisation

**Feature**: 004-matching-normalisation | **Date**: 2026-08-21

This chunk reuses chunk 4.2's `workspace_product`, `product_alias` and `pack_definition`, and chunk
4.3's `quotation`, `quotation_line` and `field_extraction`. It does not redefine them. In
particular, `pack_definition.base_quantity` remains a generated column, `quotation_line` has
`vat_rate` rather than `vat_amount`, and there is no `other_charges` field on quotation lines.

Where this chunk adds fields the dictionary lacks, they are marked **[new]** and should be folded
back when the feature lands.

---

## Entities

### `match_candidate`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_line_id` | uuid | not null, FK -> `quotation_line.id` |
| `candidate_workspace_product_id` | uuid | not null, FK -> `workspace_product.id` |
| `confidence` **[new]** | numeric(5,4) | not null, check 0 <= confidence <= 1 |
| `reasons` **[new]** | jsonb | not null; structured per-signal reason breakdown |
| `rank` **[new]** | integer | not null, check > 0 |
| `scoring_version` **[new]** | text | not null, e.g. `matching-score-v1` |
| `embedding_model` **[new]** | text | nullable; e.g. `stub-hash-v1` or real provider model |
| `created_at` | timestamptz | not null |

`reasons` is structured, not free prose. It must support at least:

```json
{
  "alias_hit": false,
  "gtin_match": false,
  "supplier_code_match": false,
  "lexical_similarity": "0.8123",
  "semantic_similarity": "0.7012",
  "feature_score": {
    "brand_match": "1.0000",
    "variant_match": "0.5000",
    "pack_unit_match": "1.0000",
    "pack_size_plausibility": "0.7500",
    "price_plausibility": "0.5000"
  }
}
```

Constraints:
- **unique** `(tenant_id, quotation_line_id, candidate_workspace_product_id, scoring_version)` -
  one candidate per product per scoring run.
- **unique** `(tenant_id, quotation_line_id, scoring_version, rank)` - ranks are stable within a
  line and scoring version.
- Writes must validate in the same transaction that the quotation line and candidate product belong
  to the same tenant.

### `match_task`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_line_id` | uuid | not null, FK -> `quotation_line.id` |
| `status` **[new]** | enum | `open` \| `in_progress` \| `resolved` |
| `priority` **[new]** | enum | `low` \| `normal` \| `high` |
| `reason` **[new]** | enum | `low_confidence` \| `close_candidates` \| `no_candidate` \| `alias_conflict` |
| `created_at` | timestamptz | not null |
| `resolved_at` | timestamptz | nullable |

`match_task` is the standalone queue resource required by FR-011 and Constitution Principle III. It
is not a view over candidates. The task gives the queue its own state, while candidate rows carry
evidence and decision rows carry immutable outcomes.

Constraints:
- **unique partial** `(tenant_id, quotation_line_id) where status in ('open', 'in_progress')` - one
  outstanding task per line.
- `resolved_at` is present only when `status = 'resolved'`.

### `match_decision`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_line_id` | uuid | not null, FK -> `quotation_line.id` |
| `matched_workspace_product_id` | uuid | not null, FK -> `workspace_product.id` |
| `selected_match_candidate_id` **[new]** | uuid | nullable, FK -> `match_candidate.id` |
| `outcome` **[new]** | enum | `same_product` \| `different_pack` \| `different_variant` \| `compatible_alternative` \| `no_match_new_product` |
| `is_automatic` **[new]** | boolean | not null |
| `decided_by` **[new]** | uuid | nullable, FK -> `membership.id` |
| `decided_at` **[new]** | timestamptz | not null |
| `confidence` **[new]** | numeric(5,4) | not null, check 0 <= confidence <= 1 |
| `alias_id` **[new]** | uuid | nullable, FK -> `product_alias.id` |
| `created_at` | timestamptz | not null |

One decision resolves one quotation line. `matched_workspace_product_id` is not nullable because
FR-009's no-match path creates a product inline before the decision is saved. `outcome =
no_match_new_product` therefore means "no existing product fit; this newly created product is the
match," not "the line remains unmatched."

Constraints:
- **unique** `(tenant_id, quotation_line_id)` - one final decision per line in this chunk.
- `decided_by` is null only for automatic decisions. Human decisions require it.
- `selected_match_candidate_id` is required for `same_product`, `different_pack`,
  `different_variant` and `compatible_alternative` when the reviewer selected an existing
  candidate; it is null for `no_match_new_product`.
- Writes must validate that the quotation line, candidate, product, alias and decider membership
  all belong to the same tenant.

**Append-only note**: decisions are outcome history. This chunk does not update or delete an
existing `match_decision`. Correcting a previously confirmed match is outside this chunk and will
need its own supersession model later.

### `landed_cost`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_line_id` | uuid | not null, FK -> `quotation_line.id` |
| `match_decision_id` | uuid | not null, FK -> `match_decision.id` |
| `quantity` **[new]** | numeric(18,6) | not null, check > 0 |
| `normalised_base_quantity` **[new]** | numeric(18,6) | not null, check > 0 |
| `base_unit` **[new]** | text | not null, FK -> `supported_base_unit.code` |
| `unit_price_amount` | numeric(18,4) | not null |
| `unit_price_currency` | text | not null, FK -> `supported_currency.code` |
| `vat_amount` **[new]** | numeric(18,4) | not null |
| `vat_currency` **[new]** | text | not null, FK -> `supported_currency.code` |
| `delivery_fee_amount` | numeric(18,4) | not null |
| `delivery_fee_currency` | text | not null, FK -> `supported_currency.code` |
| `discount_amount` | numeric(18,4) | not null |
| `discount_currency` | text | not null, FK -> `supported_currency.code` |
| `other_charges_amount` **[new]** | numeric(18,4) | not null, default 0 |
| `other_charges_currency` **[new]** | text | not null, FK -> `supported_currency.code` |
| `total_amount` **[new]** | numeric(18,4) | not null |
| `total_currency` **[new]** | text | not null, FK -> `supported_currency.code` |
| `raw_inputs` **[new]** | jsonb | not null; complete replay input snapshot |
| `rule_version` **[new]** | text | not null, e.g. `landed-cost-v1` |
| `valid_from` | timestamptz | not null |
| `valid_to` | timestamptz | nullable |
| `recorded_at` | timestamptz | not null |
| `created_at` | timestamptz | not null |

Money follows chunks 4.2 and 4.3 exactly: amount columns are `numeric(18,4)` and every amount has a
paired currency column. The API exposes these as `Money { amount, currency }` with decimal strings.

Constraints:
- **unique** `(tenant_id, match_decision_id, rule_version)` - one stored computation for the
  decision and rule version in this chunk.
- **check** all monetary currency columns equal `total_currency`; this chunk performs no currency
  conversion.
- **check** `valid_to is null or valid_to >= valid_from`.
- `recorded_at` is required and distinct from `valid_from`; this is the bitemporal record-time.

`raw_inputs` stores the values used by the rule, for example:

```json
{
  "quantity": "10.000000",
  "normalised_base_quantity": "60.000000",
  "base_unit": "each",
  "unit_price": {"amount": "12.5000", "currency": "GBP"},
  "vat_rate": "0.2000",
  "vat_amount": {"amount": "25.0000", "currency": "GBP"},
  "delivery_fee": {"amount": "5.0000", "currency": "GBP"},
  "discount": {"amount": "10.0000", "currency": "GBP"},
  "other_charges": {"amount": "0.0000", "currency": "GBP"}
}
```

`vat_amount` is derived from `quotation_line.vat_rate` as
`unit_price_amount * quantity * vat_rate`. Missing `vat_rate` is treated as zero. `other_charges` is
stored as zero because it is not modelled in chunk 4.3's `quotation_line` and is explicitly outside
this chunk's assumptions.

---

## Existing tables reused

### `product_alias`

This chunk becomes a new writer of chunk 4.2's existing `product_alias` table. It does not change
the table shape:

- alias uniqueness remains `(tenant_id, lower(alias_text))`
- `workspace_product_id` points to `workspace_product.id`
- `supplier_id` is nullable
- `created_by` points to the human `membership.id`

On a human decision, matching inserts the exact `quotation_line.original_text` as `alias_text`. If
the lowercased wording already exists for the same product, the alias is reused. If it exists for a
different product, matching refuses the alias write with a conflict; correcting or retiring the old
alias is out of scope.

### `workspace_product` and `pack_definition`

`match_candidate` and `match_decision` reference `workspace_product.id`, not the stale planned
`tenant_product_id` name in `docs/architecture/data-dictionary.md`'s `SupplierOffer` placeholder.
Pack normalisation reads the existing `pack_definition` row and its generated `base_quantity`; this
chunk never writes `base_quantity` directly.

This chunk extends `workspace_product` with tenant-scoped semantic search fields:

| Field | Type | Constraints |
|---|---|---|
| `tenant_name_embedding` **[new]** | vector(256) | nullable until computed; built only from `workspace_product.tenant_name` |
| `tenant_name_embedding_model` **[new]** | text | nullable until computed; e.g. `stub-hash-v1` |

`tenant_name_embedding` is tenant-scoped because `tenant_name` is workspace-specific vocabulary. It
must not be stored on `canonical_product`.

### `canonical_product`

This chunk extends the shared canonical spine with a boundary-safe semantic search field:

| Field | Type | Constraints |
|---|---|---|
| `canonical_embedding` **[new]** | vector(256) | nullable until computed; built only from `brand`, `name` and `variant` |
| `canonical_embedding_model` **[new]** | text | nullable until computed; e.g. `stub-hash-v1` |

`canonical_product` remains shared and still carries no `tenant_id`. The embedding is safe to share
only because it is derived exclusively from fields already present on `canonical_product`; it must
not include `workspace_product.tenant_name`, supplier wording, aliases, preferences or any other
workspace-specific text.

### Matching search indexes

The lexical search string is not stored as a mixed canonical/workspace column. It is made indexable
with expression trigram indexes:

- `canonical_product`: GIN trigram index over
  `lower(concat_ws(' ', brand, name, variant))`.
- `workspace_product`: GIN trigram index over `lower(tenant_name)`.

Semantic search uses the explicit vector columns above. Candidate scoring combines
`canonical_embedding` similarity and `tenant_name_embedding` similarity at query time, preserving
the shared-table boundary.

### `quotation_line`

Matching consumes only lines whose parent `quotation.status = 'reviewed'`. It does not add
`workspace_product_id` to `quotation_line`; the relationship is recorded by `match_decision`.

---

## Relationships

```text
tenant             1--* match_candidate
tenant             1--* match_task
tenant             1--* match_decision
tenant             1--* landed_cost
quotation          1--* quotation_line
quotation_line     1--* match_candidate
quotation_line     0..1 -- 1 match_task       (only when human resolution is needed)
quotation_line     0..1 -- 1 match_decision   (once resolved)
workspace_product  1--* match_candidate
workspace_product  1--* match_decision
match_decision     1--1 landed_cost
match_candidate    0..1 -- 1 match_decision   (selected existing candidate)
product_alias      0..1 -- 1 match_decision   (learned or reused alias)
membership         1--* match_decision        (human decisions)
```

---

## Row-level security

Every table in this chunk carries `tenant_id` and gets the same pattern:

```sql
alter table <t> enable row level security;
alter table <t> force  row level security;
create policy tenant_isolation on <t>
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());
```

This applies to `match_candidate`, `match_task`, `match_decision` and `landed_cost`. `USING` and
`WITH CHECK` are both required; `FORCE` is required because table owners otherwise bypass RLS.

**Role gate**: owner and buyer may resolve matches and create products from no-match decisions.
Branch manager, approver and viewer may read match state and landed costs but may not mutate them.
Cross-tenant reads return 404-style not found, never forbidden.

---

## Migration sketch

Latest existing migration is `supabase/migrations/20260819000021_quotation_rls.sql`; this chunk
continues sequentially. These files are sketches only; implementation creates the SQL later.

| File | Contents |
|---|---|
| `20260819000022_matching_reference.sql` | enums for match task status/priority/reason and match decision outcome; no tenant data |
| `20260819000023_match_candidates_tasks.sql` | `match_candidate`, `match_task`; FKs to `quotation_line`, `workspace_product`; candidate rank and confidence constraints |
| `20260819000024_match_decisions.sql` | `match_decision`; FK to selected candidate, workspace product, membership and product alias; one decision per line |
| `20260819000025_landed_cost.sql` | `landed_cost`; money pairs, raw input snapshot, rule version, valid-time and record-time constraints |
| `20260819000026_matching_indexes.sql` | adds `canonical_product.canonical_embedding vector(256)`, `canonical_product.canonical_embedding_model`, `workspace_product.tenant_name_embedding vector(256)`, `workspace_product.tenant_name_embedding_model`; expression GIN trigram indexes over canonical brand/name/variant text and workspace `tenant_name`; vector cosine indexes for both embedding columns when implementation volume warrants HNSW |
| `20260819000027_matching_rls.sql` | `ENABLE` + `FORCE` RLS and tenant-isolation policies for all chunk 4.4 tenant tables in one file |

The RLS migration is last, matching chunks 4.2 and 4.3: tables and constraints first, then all
tenant policies together for review.

---

## Validation rules traced to requirements

| Rule | Source |
|---|---|
| Matching consumes only parent quotations in `reviewed` status | FR-001 |
| Deterministic candidate reasons include GTIN, supplier code and alias hit | FR-002, FR-005 |
| Similarity candidate reasons include lexical, semantic and feature scores | FR-003, FR-004, FR-005 |
| Auto-accepted decisions record confidence and automatic/human origin | FR-006 |
| Low confidence, close candidates and no-candidate lines create `match_task` | FR-007, FR-011 |
| Decision outcomes cover same product, pack, variant, alternative and no-match-new-product | FR-008, FR-009 |
| Human decisions create or reuse `product_alias` from exact line wording | FR-010 |
| Owner/buyer role gate on match resolution and inline product creation | FR-019 |
| Cross-tenant match/cost records return not found | FR-020 |
| Landed cost stores amount+currency pairs, never bare money | FR-013 |
| Raw inputs and rule version stored with every cost | FR-014, FR-015 |
| Valid-time and record-time are both required | FR-016 |
| Match decisions and landed costs are append-only outcome records | FR-017 |
| Normalised quantity uses catalogue base-unit convention | FR-018 |

---

## Notes for later chunks

- The stale planned `SupplierOffer` placeholder in `docs/architecture/data-dictionary.md` is not
  used here. This chunk stores per-line `landed_cost` tied to `match_decision` and
  `workspace_product.id`; broader supplier-offer aggregation, offer comparison and price history
  belong to later chunks.
- No savings ledger entries are created here.
- No currency conversion is performed here.
- Alias correction/retirement and match supersession are out of scope.
