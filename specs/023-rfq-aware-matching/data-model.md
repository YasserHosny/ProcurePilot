# Data Model: 023 RFQ-Aware Matching

## Changed: `match_decision` (append-only, now chained)

| Column | Type | Notes |
|---|---|---|
| `supersedes_decision_id` | uuid null | FK `(tenant_id, supersedes_decision_id)` → `match_decision (tenant_id, id)`. Set only on a correction. |
| `learned_from_decision_id` | uuid null | FK as above. Set on decisions made by the alias sweep (FR-011). |

Constraints:

- **Dropped**: `match_decision_one_per_line unique (tenant_id, quotation_line_id)`.
- **Added**:
  - `match_decision_one_root_per_line unique nulls not distinct (tenant_id, quotation_line_id, supersedes_decision_id)`;
  - `match_decision_superseded_once unique (supersedes_decision_id)`;
  - trigger `match_decision_supersession_same_line` (before insert): the superseded row exists in
    the same tenant **and** the same `quotation_line_id`, and is the current head (no successor
    yet). Otherwise it raises `23514`.
- **Unchanged**:
  - no `UPDATE` or `DELETE` grants for client roles;
  - `human_or_automatic`;
  - `candidate_required_unless_new_product`.

A correction is always human: `is_automatic = false` and `decided_by` set.

## New: view `current_match_decision`

```sql
create view current_match_decision with (security_invoker = true) as
select md.* from match_decision md
where not exists (
  select 1 from match_decision s
  where s.tenant_id = md.tenant_id and s.supersedes_decision_id = md.id
);
```

The view gets the same `select` grants as `match_decision`. RLS applies through the base table
because of `security_invoker`.

## Reason payload (stored in `match_candidate.reasons`, immutable)

```json
{
  "rfq": {
    "rule_version": "rfq-fit-v1",
    "rfq_id": "…",
    "rfq_line_id": "…",
    "position": 2,
    "wording_score": "0.6400",
    "pack_check": "equal | conflict | unknown",
    "quoted_pack_base_quantity": "10.000000",
    "rfq_pack_base_quantity": "10.000000",
    "quoted_pack_unit": "kilogram",
    "rfq_pack_unit": "kilogram",
    "fitting_rfq_line_ids": ["…"]
  },
  "measured": {"lexical_similarity": "0.6400", "pack_unit_match": "1.0000"},
  "alias_hit": false,
  "gtin_match": false,
  "supplier_code_match": false
}
```

`quoted_pack_unit` is the unit `quoted_pack_base_quantity` is in: the RFQ line's base unit when the quoted pack
converts to it, the quoted unit when it cannot (a litre pack against a kilogram line is a `conflict` in litres).

The review queue (`GET /match-tasks`) carries `top_candidate.rfq_position`. On an open task, it is the top
candidate's RFQ line position. On a decided row, it is the position only when the decision's own selected candidate
is an RFQ match; a match corrected away from an RFQ line has none.

`measured` lists only signals computed for this line. When it is absent (legacy rows), the web
treats the `feature_score` entries as unmeasured (research R4).

## Audit events (append-only `audit_event`)

| Action | Target |
|---|---|
| `matching.auto_accepted` (existing) | plus `reason: "rfq_fit"`, `rfq_id`, `rfq_line_id`, `rule_version` |
| `matching.decision_corrected` (new) | `quotation_line_id`, `superseded_decision_id`, `decision_id`, `from_product_id`, `to_product_id` |
| `matching.alias_sweep_matched` (new) | `alias_id`, `learned_from_decision_id`, `decision_id`, `quotation_line_id` |

## Read-only inputs

- `rfq_response` → `rfq_recipient` → `rfq_line(workspace_product_id, quantity, position)`.
- `pack_definition.base_quantity` and `workspace_product.base_unit` give the RFQ product's pack in base
  units.
- `quotation_line(pack_count, unit_size, pack_unit, line_number, original_text)`.

## State: match line lifecycle

```text
new line ─RFQ fit (exactly one)──────────────▶ decided (automatic, rfq_fit)
         ─deterministic (gtin/code/alias)─────▶ decided (automatic)
         ─otherwise──▶ task open ─human────────▶ decided (human) ──learns alias──▶ sweep other open lines
                                 ─alias sweep──▶ decided (automatic, learned_from)
decided ─correction (not on a live request)───▶ decided' (human, supersedes previous)
```
