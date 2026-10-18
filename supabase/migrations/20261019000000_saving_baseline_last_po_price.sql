-- 20261019000000_saving_baseline_last_po_price.sql
--
-- Demo-tenant findings 22 and 23 (docs/gtm/demo-tenant/README.md). Owner decision 2026-10-18:
-- the savings baseline is the LAST PO PRICE for the product. The quoted landed cost
-- (`last_paid`) and the 6-month rolling average stay as fallbacks for tenants without
-- purchase orders.
--
--   1. baseline_policy gains 'last_po_price'. The value is not used anywhere in this file:
--      ALTER TYPE ... ADD VALUE may run inside a transaction only if the new value is not used
--      before commit.
--   2. saving_record.baseline_source_po_line_ids — the purchase_order_line rows the baseline was
--      taken from (null for the quote-based policies). Existing table: its RLS policies
--      (20260927000000_saving_record_rls_hardening.sql) and table grants are unchanged and cover
--      the new column.
--   3. purchase_record.purchase_order_line_id — the PO line an outcome was recorded from, so the
--      baseline can exclude the PO being recorded. The composite foreign key pins the line to the
--      same tenant (RLS WITH CHECK pins purchase_record.tenant_id to the caller's tenant), and a
--      partial unique index stops one PO line being recorded as two outcomes.
--   4. The pending -> verified metadata-only trigger also freezes the new saving_record column.

alter type baseline_policy add value if not exists 'last_po_price' after 'last_paid';

alter table saving_record
  add column if not exists baseline_source_po_line_ids uuid[];

comment on column saving_record.baseline_source_po_line_ids is
  'purchase_order_line ids the last_po_price baseline was taken from; null for quote-based
   policies. Captured at record time, never recomputed.';

alter table purchase_record
  add column if not exists purchase_order_line_id uuid;

alter table purchase_record
  drop constraint if exists purchase_record_purchase_order_line_fkey;
alter table purchase_record
  add constraint purchase_record_purchase_order_line_fkey
  foreign key (tenant_id, purchase_order_line_id)
  references purchase_order_line (tenant_id, id);

create unique index if not exists purchase_record_purchase_order_line_key
  on purchase_record (tenant_id, purchase_order_line_id)
  where purchase_order_line_id is not null;

comment on column purchase_record.purchase_order_line_id is
  'The purchase_order_line this outcome was recorded from (finding 22), or null for a manual
   outcome. At most one outcome per PO line.';

create or replace function enforce_saving_record_verification_is_metadata_only()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.status = 'pending' and new.status = 'verified' then
    if old.tenant_id is distinct from new.tenant_id
      or old.purchase_record_id is distinct from new.purchase_record_id
      or old.workspace_product_id is distinct from new.workspace_product_id
      or old.supplier_id is distinct from new.supplier_id
      or old.baseline_policy is distinct from new.baseline_policy
      or old.baseline_source_landed_cost_ids is distinct from new.baseline_source_landed_cost_ids
      or old.baseline_source_po_line_ids is distinct from new.baseline_source_po_line_ids
      or old.baseline_unit_price_amount is distinct from new.baseline_unit_price_amount
      or old.baseline_unit_price_currency is distinct from new.baseline_unit_price_currency
      or old.baseline_value_amount is distinct from new.baseline_value_amount
      or old.baseline_value_currency is distinct from new.baseline_value_currency
      or old.actual_value_amount is distinct from new.actual_value_amount
      or old.actual_value_currency is distinct from new.actual_value_currency
      or old.delta_amount is distinct from new.delta_amount
      or old.delta_currency is distinct from new.delta_currency
      or old.calculation_version is distinct from new.calculation_version
      or old.calculation_inputs is distinct from new.calculation_inputs
      or old.recorded_by is distinct from new.recorded_by
      or old.recorded_at is distinct from new.recorded_at
      or old.created_at is distinct from new.created_at
    then
      raise exception 'verification may only change status, verified_at, and verified_by'
        using errcode = 'restrict_violation',
              hint = 'Every other saving_record field is fixed at record time (research.md R1).';
    end if;
  end if;
  return new;
end;
$$;
