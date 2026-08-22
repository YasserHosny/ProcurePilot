-- 20260819000025_landed_cost.sql — task T008
--
-- landed_cost — the first real exercise of Constitution Principle II. A pure, versioned,
-- replayable function's output: raw inputs and rule version are stored alongside the result, so a
-- later rule change never alters this row, and recomputation from the stored inputs at the stored
-- rule version must reproduce it exactly.
--
-- Money follows chunks 4.2/4.3 exactly: numeric(18,4) amount + explicit currency, both or neither
-- never applies here since every amount in this table is required (unlike optional supplier
-- amounts) — a computed cost has no partial state.

create table if not exists landed_cost (
  id                       uuid primary key default gen_random_uuid(),
  tenant_id                uuid not null references tenant(id) on delete cascade,
  quotation_line_id        uuid not null references quotation_line(id) on delete cascade,
  match_decision_id        uuid not null references match_decision(id) on delete cascade,

  quantity                 numeric(18, 6) not null check (quantity > 0),
  normalised_base_quantity numeric(18, 6) not null check (normalised_base_quantity > 0),
  base_unit                text not null references supported_base_unit(code),

  unit_price_amount        numeric(18, 4) not null,
  unit_price_currency      text not null references supported_currency(code),
  vat_amount               numeric(18, 4) not null,
  vat_currency             text not null references supported_currency(code),
  delivery_fee_amount      numeric(18, 4) not null,
  delivery_fee_currency    text not null references supported_currency(code),
  discount_amount          numeric(18, 4) not null,
  discount_currency        text not null references supported_currency(code),
  other_charges_amount     numeric(18, 4) not null default 0,
  other_charges_currency   text not null references supported_currency(code),
  total_amount             numeric(18, 4) not null,
  total_currency           text not null references supported_currency(code),

  -- Complete replay snapshot — see specs/004-matching-normalisation/data-model.md for shape.
  raw_inputs               jsonb not null,
  rule_version             text not null,

  -- Bitemporal: when the price applies (valid-time) vs when the workspace learned it (record-time).
  valid_from               timestamptz not null,
  valid_to                 timestamptz,
  recorded_at              timestamptz not null default now(),

  created_at               timestamptz not null default now(),

  constraint landed_cost_one_per_decision_per_rule
    unique (tenant_id, match_decision_id, rule_version),
  constraint landed_cost_no_currency_conversion
    check (
      unit_price_currency = total_currency
      and vat_currency = total_currency
      and delivery_fee_currency = total_currency
      and discount_currency = total_currency
      and other_charges_currency = total_currency
    ),
  constraint landed_cost_valid_to_after_valid_from
    check (valid_to is null or valid_to >= valid_from)
);

create index if not exists landed_cost_tenant_idx on landed_cost (tenant_id);
create index if not exists landed_cost_decision_idx on landed_cost (match_decision_id);

comment on table landed_cost is
  'Append-only, versioned, replayable (Constitution Principle II). A rule-version change inserts a
   new row when recomputation is requested — it never updates or deletes an earlier one.';
comment on column landed_cost.rule_version is
  'e.g. landed-cost-v1. Pins the pure function used; recomputing from raw_inputs at this version
   must reproduce total_amount exactly.';
